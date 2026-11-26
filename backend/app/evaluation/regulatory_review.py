"""Offline independent-review state machine. Never approves/publishes source documents."""

import hashlib
import json
import statistics
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from app.schemas.assessments import SHA256
from app.schemas.references import Authority, Contract
from app.services.ingestion import digest
from app.services.investigation_provider import strict_json

ROOT = Path(__file__).resolve().parents[3]
INPUTS = (
    "contracts/regulatory_benchmark_v2.json",
    "contracts/regulatory_provisional_answer_keys_v2.json",
    "contracts/regulatory_source_proposals.json",
    "contracts/regulatory_independent_review_v2.json",
)
STATES = ("unreviewed", "reviewer_labeled", "disputed", "adjudicated", "approved_for_evaluation")


def manifest():
    values = {p: (ROOT / p).read_bytes() for p in INPUTS}
    benchmark = strict_json(values[INPUTS[0]].decode(), 1048576)
    research = strict_json(values[INPUTS[1]].decode(), 1048576)
    cases = benchmark["cases"]
    if len(cases) != 31 or len({c["id"] for c in cases}) != 31:
        raise ValueError("regulatory_benchmark_identity_invalid")
    return dict(
        schema_version="trueflag.regulatory-review-manifest.v1",
        file_sha256={p: hashlib.sha256(raw).hexdigest() for p, raw in values.items()},
        scope=benchmark["scope"],
        cases=[
            dict(
                id=c["id"],
                question=c["question"],
                kind=c["kind"],
                request=c.get("request"),
                information_need=c["information_need"],
            )
            for c in cases
        ],
        source_versions=research["sources"],
        notice="Unreviewed source registry; no source approval or relevance labels supplied.",
    )


class RegulatoryLabel(Contract):
    question_relevance: Literal["relevant", "not_relevant", "unable_to_assess"]
    relevant_source_section_keys: tuple[str, ...] = Field(max_length=30)
    preferred_ranking: tuple[str, ...] = Field(max_length=30)
    expected_status: Literal["available", "partial", "unavailable", "uncertain"]
    authority_classes: tuple[Authority, ...] = Field(max_length=4)
    applicability_notes: str = Field(min_length=1, max_length=2000)
    missing_sources: tuple[str, ...] = Field(max_length=20)
    citation_support: Literal["supported", "partial", "unsupported", "unable_to_assess"]
    exceptions_preserved: StrictBool | None
    abstention_required: StrictBool | None
    contradictory_interpretations: str | None = Field(default=None, max_length=2000)
    rationale: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def unique_ranking(self):
        keys, ranking = self.relevant_source_section_keys, self.preferred_ranking
        if (
            len(set(keys)) != len(keys)
            or len(set(ranking)) != len(ranking)
            or not set(ranking) <= set(keys)
        ):
            raise ValueError("regulatory_label_ranking_invalid")
        return self


class ReviewSubmission(Contract):
    schema_version: Literal["trueflag.regulatory-review-submission.v1"]
    manifest_sha256: SHA256
    registry_sha256: SHA256
    case_id: str = Field(min_length=1, max_length=100)
    action: Literal["label", "dispute", "adjudicate", "approve_for_evaluation"]
    actor_id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,80}$")
    basis: Literal["independent_human", "synthetic_fixture"]
    qualifications_reference: str = Field(min_length=1, max_length=200)
    independent: StrictBool
    submitted_at: AwareDatetime
    label: RegulatoryLabel | None = None
    rationale: str = Field(min_length=1, max_length=2000)


def blank_packet():
    current = manifest()
    return dict(
        manifest=current,
        manifest_sha256=digest(current),
        registry_status="unapproved",
        sources_approved=0,
        cases=[
            dict(case_id=c["id"], state="unreviewed", independent_label=None)
            for c in current["cases"]
        ],
        expert_reference_metrics=None,
    )


def replay(events, registry, *, current=None):
    """Validate every historical transition; a string state or checkbox is not proof."""
    current = current or manifest()
    if type(events) is not list or len(events) > 500:
        raise ValueError("regulatory_review_history_limit")
    state = {
        c["id"]: dict(
            state="unreviewed", reviewers={}, adjudicator=None, label=None, owner=None, basis=None
        )
        for c in current["cases"]
    }
    previous = None
    last_time = None
    roles = {
        "label": "reviewer",
        "dispute": "reviewer",
        "adjudicate": "adjudicator",
        "approve_for_evaluation": "evaluation_owner",
    }
    known = {
        key + ":" + s["section"]
        for key, source in current["source_versions"].items()
        for s in source["sections"]
    }
    for event in events:
        body = {k: v for k, v in event.items() if k != "event_sha256"}
        if (
            set(event) != {"previous_sha256", "submission", "event_sha256"}
            or digest(body) != event["event_sha256"]
            or event["previous_sha256"] != previous
        ):
            raise ValueError("regulatory_review_history_integrity")
        item = ReviewSubmission.model_validate(event["submission"])
        if item.manifest_sha256 != digest(current) or item.registry_sha256 != digest(registry):
            raise ValueError("regulatory_review_binding_mismatch")
        if item.case_id not in state or last_time is not None and item.submitted_at < last_time:
            raise ValueError("regulatory_review_identity_or_time_invalid")
        if item.actor_id in registry.get("excluded_authors", []) or not item.independent:
            raise ValueError("regulatory_reviewer_not_independent")
        member = registry.get("members", {}).get(item.actor_id, {})
        required_status = (
            "approved_by_human_owner"
            if item.basis == "independent_human"
            else "synthetic_test_only"
        )
        if (
            registry.get("status") != required_status
            or roles[item.action] not in member.get("roles", [])
            or member.get("qualifications_reference") != item.qualifications_reference
        ):
            raise ValueError("regulatory_reviewer_not_authorized")
        row = state[item.case_id]
        if row["basis"] not in (None, item.basis) or row["state"] == "approved_for_evaluation":
            raise ValueError("regulatory_review_frozen_or_mixed_basis")
        if item.label and not set(item.label.relevant_source_section_keys) <= known:
            raise ValueError("regulatory_label_unknown_source_version")
        if item.action == "label":
            if (
                item.label is None
                or row["adjudicator"] is not None
                or item.actor_id in row["reviewers"]
            ):
                raise ValueError("regulatory_label_transition_invalid")
            row["reviewers"][item.actor_id] = item.label.model_dump(mode="json")
            row["state"] = (
                "reviewer_labeled"
                if row["state"] != "disputed"
                and len({digest(v) for v in row["reviewers"].values()}) == 1
                else "disputed"
            )
        elif item.action == "dispute":
            if not row["reviewers"] or row["adjudicator"] is not None or item.label is not None:
                raise ValueError("regulatory_dispute_transition_invalid")
            row["state"] = "disputed"
        elif item.action == "adjudicate":
            if (
                not row["reviewers"]
                or row["adjudicator"] is not None
                or item.actor_id in row["reviewers"]
                or item.label is None
            ):
                raise ValueError("regulatory_adjudication_not_independent")
            row.update(
                state="adjudicated",
                adjudicator=item.actor_id,
                label=item.label.model_dump(mode="json"),
            )
        else:
            if (
                row["state"] != "adjudicated"
                or item.actor_id in row["reviewers"]
                or item.actor_id == row["adjudicator"]
                or item.label is not None
            ):
                raise ValueError("regulatory_evaluation_approval_invalid")
            row.update(state="approved_for_evaluation", owner=item.actor_id)
        row["basis"] = item.basis
        previous, last_time = event["event_sha256"], item.submitted_at
    return dict(
        manifest_sha256=digest(current),
        registry_sha256=digest(registry),
        head_sha256=previous,
        cases=state,
        counts={s: sum(r["state"] == s for r in state.values()) for s in STATES},
        source_publication_authorized=False,
    )


def append_event(events, submission, registry):
    body = dict(
        previous_sha256=events[-1]["event_sha256"] if events else None,
        submission=ReviewSubmission.model_validate(submission).model_dump(mode="json"),
    )
    event = dict(**body, event_sha256=digest(body))
    # Match the exclusive-create writer exactly, including escaped Unicode and indentation.
    if len((json.dumps(event, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()) > 65536:
        raise ValueError("regulatory_review_event_size_limit")
    replay(events + [event], registry)
    return event


def expert_metrics(events, registry, observations):
    current = manifest()
    reviewed = replay(events, registry, current=current)
    gate = all(
        r["state"] == "approved_for_evaluation" and r["basis"] == "independent_human"
        for r in reviewed["cases"].values()
    )
    report = dict(
        status="blocked_pending_independent_review",
        review_counts=reviewed["counts"],
        manifest_sha256=digest(current),
        review_head_sha256=reviewed["head_sha256"],
        precision_at_5=None,
        recall_at_5=None,
        mrr=None,
        reviewed_claim_support=None,
        legal_quality_certified=False,
        source_publication_authorized=False,
    )
    if not gate:
        return report
    cases = {c["id"]: c for c in current["cases"]}
    if (
        type(observations) is not list
        or len(observations) != len(cases)
        or {o["id"] for o in observations} != set(cases)
    ):
        raise ValueError("regulatory_observation_identities_invalid")
    p, rec, rr = [], [], []
    negatives = violations = 0
    for obs in observations:
        label = reviewed["cases"][obs["id"]]["label"]
        if obs.get("manifest_sha256") != digest(current):
            raise ValueError("regulatory_observation_version_mismatch")
        rows = obs["returned"]
        if type(rows) is not list or len(rows) > 5:
            raise ValueError("regulatory_observation_results_invalid")
        returned = []
        for row in rows:
            source = current["source_versions"].get(row["source_key"])
            section = (
                next((s for s in source["sections"] if s["section"] == row["section"]), None)
                if source
                else None
            )
            if (
                source is None
                or section is None
                or not section.get("text_sha256")
                or row.get("raw_sha256") != source["raw_sha256"]
                or row.get("text_sha256") != section["text_sha256"]
            ):
                raise ValueError("regulatory_observation_source_version_mismatch")
            returned.append(row["source_key"] + ":" + row["section"])
        if type(returned) is not list or len(returned) > 5 or len(set(returned)) != len(returned):
            raise ValueError("regulatory_observation_results_invalid")
        for key in returned:
            source, separator, section = key.partition(":")
            if (
                not separator
                or source not in current["source_versions"]
                or section
                not in {s["section"] for s in current["source_versions"][source]["sections"]}
            ):
                raise ValueError("regulatory_observation_source_invalid")
        relevant = set(label["relevant_source_section_keys"])
        if (
            cases[obs["id"]]["kind"] != "security_control"
            and label["question_relevance"] != "unable_to_assess"
        ):
            if relevant:
                hits = len(set(returned) & relevant)
                p.append(hits / 5)
                rec.append(hits / len(relevant))
                rr.append(next((1 / (i + 1) for i, k in enumerate(returned) if k in relevant), 0))
            else:
                negatives += bool(returned)
        violations += label["expected_status"] == "unavailable" and bool(returned)
    report.update(
        status="independent_reference_measurement_not_legal_certification",
        precision_at_5=statistics.mean(p) if p else None,
        recall_at_5=statistics.mean(rec) if rec else None,
        mrr=statistics.mean(rr) if rr else None,
        question_denominator=len(p),
        observation_count=len(observations),
        unexpected_negative_results=negatives,
        unavailable_result_violations=violations,
        labels_basis="independent_human_adjudicated",
    )
    return report
