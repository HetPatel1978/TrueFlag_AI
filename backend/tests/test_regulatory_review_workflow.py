"""Protocol fixtures only: no real independent reviewers, labels or approvals created."""

import copy
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.evaluation.regulatory_review import (
    ReviewSubmission,
    append_event,
    blank_packet,
    expert_metrics,
    manifest,
    replay,
)
from app.services.ingestion import digest
from app.services.reference_evaluation import evaluate_reference_cases


def registry():
    return dict(
        status="synthetic_test_only",
        excluded_authors=["fixture_author"],
        members={
            actor: dict(roles=roles, qualifications_reference="SYNTHETIC-NOT-EXPERT")
            for actor, roles in {
                "reviewer_a": ["reviewer", "adjudicator", "evaluation_owner"],
                "reviewer_b": ["reviewer"],
                "adjudicator": ["adjudicator"],
                "owner": ["evaluation_owner"],
                "fixture_author": ["reviewer"],
            }.items()
        },
    )


def label(**changes):
    value = dict(
        question_relevance="relevant",
        relevant_source_section_keys=["ecfr-us-banks:1020.320"],
        preferred_ranking=["ecfr-us-banks:1020.320"],
        expected_status="partial",
        authority_classes=["binding_regulation"],
        applicability_notes="Synthetic protocol fixture only.",
        missing_sources=["uncovered-cross-reference"],
        citation_support="partial",
        exceptions_preserved=None,
        abstention_required=True,
        contradictory_interpretations="Unreviewed fixture disagreement.",
        rationale="Not a legal judgment; test protocol only.",
    )
    return dict(value, **changes)


def submission(action="label", actor="reviewer_a", **changes):
    value = dict(
        schema_version="trueflag.regulatory-review-submission.v1",
        manifest_sha256=digest(manifest()),
        registry_sha256=digest(registry()),
        case_id="sar-bank",
        action=action,
        actor_id=actor,
        basis="synthetic_fixture",
        qualifications_reference="SYNTHETIC-NOT-EXPERT",
        independent=True,
        submitted_at=datetime(2026, 11, 16, tzinfo=timezone.utc).isoformat(),
        label=label() if action in {"label", "adjudicate"} else None,
        rationale="Synthetic test; never independent expert ground truth.",
    )
    return dict(value, **changes)


def test_all_31_review_tasks_start_blank_and_bound_to_original_sources():
    packet = blank_packet()
    assert len(packet["cases"]) == 31 and packet["sources_approved"] == 0
    assert all(
        c["state"] == "unreviewed" and c["independent_label"] is None for c in packet["cases"]
    )
    assert packet["expert_reference_metrics"] is None
    assert len(packet["manifest"]["source_versions"]) == 3


def test_labeled_disputed_adjudicated_and_evaluation_approved_are_distinct():
    roster, events = registry(), []
    for item, state in [
        (submission(), "reviewer_labeled"),
        (
            submission(
                actor="reviewer_b", label=label(rationale="Different fixture interpretation.")
            ),
            "disputed",
        ),
        (submission("adjudicate", "adjudicator"), "adjudicated"),
        (submission("approve_for_evaluation", "owner"), "approved_for_evaluation"),
    ]:
        events.append(append_event(events, item, roster))
        result = replay(events, roster)
        assert result["cases"]["sar-bank"]["state"] == state
        assert result["source_publication_authorized"] is False
    with pytest.raises(ValueError, match="frozen"):
        append_event(events, submission(), roster)


@pytest.mark.parametrize(
    "change",
    [
        dict(manifest_sha256="a" * 64),
        dict(registry_sha256="b" * 64),
        dict(case_id="foreign-case"),
        dict(actor_id="unknown"),
        dict(actor_id="fixture_author"),
        dict(independent=False),
        dict(basis="independent_human"),
        dict(qualifications_reference="not-the-approved-reference"),
        dict(
            label=label(
                relevant_source_section_keys=["invented-source:unknown"], preferred_ranking=[]
            )
        ),
    ],
)
def test_forged_binding_identity_roles_and_source_labels_rejected(change):
    with pytest.raises(ValueError):
        append_event([], submission(**change), registry())


def test_reviewer_cannot_adjudicate_or_approve_own_labels():
    events = [append_event([], submission(), registry())]
    with pytest.raises(ValueError, match="independent"):
        append_event(events, submission("adjudicate"), registry())
    with pytest.raises(ValueError, match="approval_invalid"):
        append_event(events, submission("approve_for_evaluation"), registry())
    events.append(append_event(events, submission("adjudicate", "adjudicator"), registry()))
    with pytest.raises(ValueError, match="approval_invalid"):
        append_event(events, submission("approve_for_evaluation"), registry())


@pytest.mark.parametrize("mutation", ["hash", "previous", "source_version", "time"])
def test_hash_chain_revision_and_clock_order_tampering_fail_closed(mutation):
    events = [append_event([], submission(), registry())]
    events.append(append_event(events, submission("adjudicate", "adjudicator"), registry()))
    events = copy.deepcopy(events)
    if mutation == "hash":
        events[0]["submission"]["rationale"] = "changed"
    else:
        event = events[-1]
        if mutation == "previous":
            event["previous_sha256"] = "f" * 64
        elif mutation == "source_version":
            event["submission"]["manifest_sha256"] = "e" * 64
        else:
            event["submission"]["submitted_at"] = "2025-01-01T00:00:00Z"
        event["event_sha256"] = digest({k: v for k, v in event.items() if k != "event_sha256"})
    with pytest.raises(ValueError):
        replay(events, registry())


def test_explicit_dispute_cannot_be_erased_by_later_matching_label():
    events = [append_event([], submission(), registry())]
    events.append(append_event(events, submission("dispute", "reviewer_b"), registry()))
    events.append(append_event(events, submission(actor="reviewer_b"), registry()))
    assert replay(events, registry())["cases"]["sar-bank"]["state"] == "disputed"


def test_unreviewed_and_synthetic_approvals_never_supply_expert_metrics():
    result = expert_metrics([], registry(), [])
    assert result["precision_at_5"] is None and result["mrr"] is None
    events = []
    for case in manifest()["cases"]:
        for action, actor in [
            ("label", "reviewer_a"),
            ("adjudicate", "adjudicator"),
            ("approve_for_evaluation", "owner"),
        ]:
            events.append(
                append_event(events, submission(action, actor, case_id=case["id"]), registry())
            )
    assert replay(events, registry())["counts"]["approved_for_evaluation"] == 31
    result = expert_metrics(events, registry(), [])
    assert result["status"] == "blocked_pending_independent_review"
    assert result["precision_at_5"] is result["recall_at_5"] is result["mrr"] is None
    assert not result["source_publication_authorized"]


def test_claiming_human_review_with_unbound_string_is_not_accepted():
    with pytest.raises(ValueError, match="bound independent"):
        evaluate_reference_cases(None, None, None, [], review_status="human_reviewed")


@pytest.mark.parametrize("annotation", ["x" * 65536, "\u2603" * 12000], ids=["ascii", "unicode"])
def test_large_missing_source_annotations_cannot_exhaust_review_journal(annotation):
    with pytest.raises(ValueError, match="event_size_limit"):
        append_event([], submission(label=label(missing_sources=[annotation])), registry())


@pytest.mark.parametrize("change", [dict(independent=1), dict(label=label(exceptions_preserved=1))])
def test_review_booleans_are_strict(change):
    with pytest.raises(ValidationError):
        ReviewSubmission.model_validate(submission(**change))
