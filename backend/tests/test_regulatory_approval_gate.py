"""Private candidate diagnostics ONLY. Never approve versions, create releases or expose text."""

import hashlib
import importlib.util
import json
import statistics
import time
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.models.references import (
    CorpusRelease,
    ReferenceApproval,
    ReferenceChunk,
    ReferenceDocument,
    ReferenceSource,
    ReferenceVersion,
)
from app.schemas.references import (
    AS_OF,
    KNOWLEDGE_CUTOFF,
    DocumentSpec,
    ReferenceQuery,
    VersionSpec,
)
from app.services.reference_parser import extract
from app.services.references import ReferenceService, _withdrawn

ROOT = Path(__file__).resolve().parents[2]


def packet_module():
    spec = importlib.util.spec_from_file_location(
        "review_packet", ROOT / "scripts/prepare_regulatory_review_packet.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_19_independent_labels_are_blank_and_hash_bound():
    packet = packet_module().build_packet()
    assert len(packet["cases"]) == len({case["id"] for case in packet["cases"]}) == 19
    assert (
        json.loads((ROOT / "contracts/regulatory_independent_review.json").read_bytes()) == packet
    )
    for case in packet["cases"]:
        label = case["independent_label"]
        assert label["adjudication_status"] == "unreviewed"
        assert all(value is None for key, value in label.items() if key != "adjudication_status")
        assert "relevant_sections" not in case and case["procedure"]


def test_partial_reviewer_work_cannot_be_overwritten():
    module = packet_module()
    packet = module.build_packet()
    assert not module.reviewer_data_present(packet)
    packet["cases"][0]["independent_label"]["rationale"] = "Human review in progress"
    assert module.reviewer_data_present(packet)


@pytest.fixture
def candidate(platform, case_team):
    if platform[1].dialect.name != "postgresql":
        pytest.skip("real PostgreSQL required")
    private = ROOT / "assets/local/regulatory/proposed"
    if not private.is_dir():
        pytest.skip("actual official source proposals unavailable")
    client, engine, settings, _ = platform
    settings.app_env = "development"
    settings.regulatory_context_id = None
    service = ReferenceService(engine, settings)
    admin = UUID(case_team["users"]["admin"])
    proposal = json.loads((ROOT / "contracts/regulatory_source_proposals.json").read_bytes())
    versions = {}
    for source, filename, media in zip(
        proposal["sources"],
        ["ecfr-bank-2026-11-02.xml", "fincen-sar-faqs.html"],
        ["application/xml", "text/html"],
        strict=True,
    ):
        source_id = service.register_source(
            admin, source["key"], source["publisher"], urlsplit(source["url"]).hostname
        )
        doc = DocumentSpec(
            key=source["key"],
            title=source["title"],
            url=source["url"],
            authority=source["authority"],
        )
        # A fixed TEST observation timestamp, not an assertion about the original HTTP fetch time.
        spec = VersionSpec(
            media_type=media,
            raw_sha256=source["raw_sha256"],
            sections=tuple(s["section"] for s in source["sections"]),
            retrieved_at=datetime(2026, 11, 4, 12, tzinfo=timezone.utc),
            temporal_basis=source["temporal_basis"],
            snapshot_date=source["snapshot_date"],
            verified_through=source["verified_through"],
        )
        versions[source["key"]] = service.admit(
            admin, source_id, doc, spec, (private / filename).read_bytes()
        )
    return dict(
        client=client,
        engine=engine,
        settings=settings,
        service=service,
        admin=admin,
        case=UUID(case_team["ids"][0]),
        team=case_team,
        versions=versions,
    )


def candidate_search(env, request, *, scope=None, exclude=()):
    """Test-only preview query, deliberately NOT the production publication/read capability."""
    values = dict(
        as_of=AS_OF,
        knowledge_cutoff=KNOWLEDGE_CUTOFF,
        jurisdiction="US",
        entity="us_bank",
        language="en",
    )
    values.update(scope or {})
    if isinstance(values["as_of"], str):
        values["as_of"] = date.fromisoformat(values["as_of"])
    context = SimpleNamespace(**values)
    query = ReferenceQuery(**request)
    vector = func.to_tsvector(literal_column("'english'::regconfig"), ReferenceChunk.body_text)
    statement = (
        select(
            ReferenceDocument.key,
            ReferenceChunk.section,
            ReferenceVersion.raw_sha256,
            ReferenceChunk.text_sha256,
        )
        .join(ReferenceVersion, ReferenceChunk.version_id == ReferenceVersion.id)
        .join(ReferenceDocument, ReferenceVersion.document_id == ReferenceDocument.id)
        .join(ReferenceSource, ReferenceDocument.source_id == ReferenceSource.id)
        .where(
            ReferenceVersion.id.in_(tuple(env["versions"].values())),
            env["service"]._applicable(context),
            ~_withdrawn(source=ReferenceSource.id, version=ReferenceVersion.id),
        )
    )
    if exclude:
        statement = statement.where(ReferenceDocument.key.not_in(exclude))
    order = [ReferenceChunk.section, ReferenceChunk.id]
    with Session(env["engine"]) as session:
        if query.section:
            statement = statement.where(ReferenceChunk.section == query.section)
        else:
            terms = func.websearch_to_tsquery(literal_column("'english'::regconfig"), query.query)
            if session.scalar(select(func.numnode(terms))) == 0:
                return []
            statement = statement.where(vector.op("@@")(terms))
            order.insert(0, func.ts_rank_cd(vector, terms).desc())
        return [
            dict(
                source_key=r.key,
                section=r.section,
                raw_sha256=r.raw_sha256,
                text_sha256=r.text_sha256,
            )
            for r in session.execute(statement.order_by(*order).limit(query.limit))
        ]


def query_rows(env, request, **kwargs):
    start = time.perf_counter()
    rows = candidate_search(env, request, **kwargs)
    return rows, (time.perf_counter() - start) * 1000


@pytest.mark.postgres
def test_isolated_candidate_diagnostics_all_review_cases(candidate):
    env = candidate
    original = json.loads((ROOT / "contracts/regulatory_evaluation_proposals.json").read_bytes())
    packet = packet_module().build_packet()
    observations = []
    precision = []
    recall = []
    ranks = []
    elapsed = []
    eligible_precision = []
    eligible_recall = []
    eligible_ranks = []
    violations = 0
    for definition in original["cases"]:
        rows, latency = query_rows(env, definition["request"])
        elapsed.append(latency)
        expected = set(definition["relevant_sections"])
        hits = len({r["section"] for r in rows} & expected)
        p = hits / 5
        r = hits / len(expected)
        rank = next((1 / (i + 1) for i, row in enumerate(rows) if row["section"] in expected), 0)
        precision.append(p)
        recall.append(r)
        ranks.append(rank)
        if definition["expected_authority"] == "binding_regulation":
            eligible_precision.append(p)
            eligible_recall.append(r)
            eligible_ranks.append(rank)
        violations += sum(row["source_key"] != "ecfr-us-banks" for row in rows)
        observations.append(
            dict(
                id=definition["id"],
                kind="unreviewed_candidate_query",
                returned=rows,
                latency_ms=latency,
                labels="engineering_proposals_not_independent_ground_truth",
            )
        )
    for case in packet["cases"][7:]:
        procedure = case["procedure"]
        identity = case["id"]
        if identity in {"wrong-jurisdiction", "wrong-entity", "wrong-date"}:
            rows, latency = query_rows(
                env, {"query": procedure["query"]}, scope=procedure["test_scope"]
            )
            assert not rows
            elapsed.append(latency)
            observations.append(
                dict(id=identity, kind="candidate_scope_control", returned=rows, latency_ms=latency)
            )
        elif identity == "superseded":
            rows, latency = query_rows(
                env, {"section": procedure["section"]}, exclude=(procedure["test_exclusion"],)
            )
            assert not rows
            elapsed.append(latency)
            observations.append(
                dict(
                    id=identity,
                    kind="simulated_candidate_exclusion_only",
                    returned=rows,
                    latency_ms=latency,
                    limitation=procedure["limitation"],
                )
            )
        elif identity == "withdrawn":
            # Execute last: immutable withdrawal of an UNAPPROVED version in this disposable schema.
            continue
        elif identity == "embedded-instructions":
            text = procedure["attack_fixture"].encode()
            parsed = extract(text, "text/plain")
            assert parsed["chunks"][0]["body_text"] == procedure["attack_fixture"]
            observations.append(
                dict(
                    id=identity,
                    kind="synthetic_parser_control_only",
                    instructions_executed=False,
                    limitation=procedure["limitation"],
                )
            )
        elif identity in {"forged-reference", "unauthorized"}:
            auth = env["team"]["auth"]["admin" if identity == "forged-reference" else "analysttwo"]
            base = f"/api/v1/cases/{env['case']}/references"
            if identity == "forged-reference":
                response = env["client"].get(
                    base + "/" + str(uuid5(NAMESPACE_URL, "trueflag.unissued.reference")),
                    headers=auth,
                )
            else:
                response = env["client"].post(
                    base + "/search", json={"query": procedure["query"]}, headers=auth
                )
            assert response.status_code == 404
            observations.append(
                dict(
                    id=identity,
                    kind="actual_protected_api_control",
                    http_status=response.status_code,
                )
            )
        else:
            request = {k: v for k, v in procedure.items() if k in {"section", "query"}}
            rows, latency = query_rows(env, request)
            elapsed.append(latency)
            if identity in {"empty", "ambiguous", "unapproved-guidance"}:
                assert not rows
            if identity == "exceptions":
                assert len(rows) == 1
                with Session(env["engine"]) as session:
                    body = session.scalar(
                        select(ReferenceChunk.body_text).where(
                            ReferenceChunk.version_id == env["versions"]["ecfr-us-banks"],
                            ReferenceChunk.section == "1020.320",
                        )
                    )
                    assert "Exceptions" in body and "(d)" in body
            observations.append(
                dict(
                    id=identity,
                    kind="candidate_technical_control",
                    returned=rows,
                    latency_ms=latency,
                )
            )
    env["service"].withdraw(env["admin"], version_id=env["versions"]["ecfr-us-banks"])
    rows, latency = query_rows(env, {"section": "1020.320"})
    assert not rows
    observations.append(
        dict(
            id="withdrawn",
            kind="unapproved_candidate_withdrawal",
            returned=rows,
            latency_ms=latency,
        )
    )
    elapsed.append(latency)
    assert len(observations) == 19 and violations == 0
    with Session(env["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(ReferenceApproval)) == 0
        assert session.scalar(select(func.count()).select_from(CorpusRelease)) == 0
    report = dict(
        status="UNREVIEWED_CANDIDATE_DIAGNOSTICS_ONLY",
        cases=19,
        independent_labels=0,
        approved_sources=0,
        published_releases=0,
        draft_all_7_questions=dict(
            precision_at_5=statistics.mean(precision),
            recall_at_5=statistics.mean(recall),
            mrr=statistics.mean(ranks),
        ),
        draft_3_ecfr_questions=dict(
            precision_at_5=statistics.mean(eligible_precision),
            recall_at_5=statistics.mean(eligible_recall),
            mrr=statistics.mean(eligible_ranks),
        ),
        filter_violations=violations,
        timed_queries=len(elapsed),
        latency_ms_p50=statistics.median(elapsed),
        latency_ms_p95=sorted(elapsed)[min(len(elapsed) - 1, int(len(elapsed) * 0.95))],
        legal_quality_approved=False,
        source_proposal_sha256=packet["source_proposal_sha256"],
        review_packet_sha256=hashlib.sha256(
            (ROOT / "contracts/regulatory_independent_review.json").read_bytes()
        ).hexdigest(),
        observations=observations,
    )
    print("REGULATORY_CANDIDATE_REPORT:" + json.dumps(report, sort_keys=True))


@pytest.mark.postgres
def test_unapproved_official_versions_unavailable_to_api_and_direct_tool(candidate):
    env = candidate
    service = env["service"]
    request = ReferenceQuery(section="1020.320")
    direct = service.retrieve_reference_context(env["admin"], env["case"], request)
    assert direct.status == "unavailable" and not direct.passages
    response = env["client"].post(
        f"/api/v1/cases/{env['case']}/references/search",
        json={"section": "1020.320"},
        headers=env["team"]["auth"]["admin"],
    )
    assert response.status_code == 200 and response.json()["passages"] == []
    assert "2588950c5c16" not in response.text and "Reports by banks" not in response.text
    forged = {"section": "1020.320", "version_id": str(env["versions"]["ecfr-us-banks"])}
    assert (
        env["client"]
        .post(
            f"/api/v1/cases/{env['case']}/references/search",
            json=forged,
            headers=env["team"]["auth"]["admin"],
        )
        .status_code
        == 422
    )
    env["settings"].regulatory_context_id = env["versions"]["ecfr-us-banks"]
    denied = env["client"].post(
        f"/api/v1/cases/{env['case']}/references/search",
        json={"section": "1020.320"},
        headers=env["team"]["auth"]["admin"],
    )
    assert denied.status_code == 404
    with Session(env["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(ReferenceApproval)) == 0
        assert session.scalar(select(func.count()).select_from(CorpusRelease)) == 0
