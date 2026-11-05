"""31-case candidate evaluation; no official approval/release or independent labels."""

import copy
import importlib.util
import json
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session
from test_regulatory_approval_gate import candidate as candidate_fixture
from test_regulatory_approval_gate import candidate_search

from app.models import Case, User
from app.models.references import CorpusRelease, ReferenceApproval, ReferenceChunk
from app.schemas.references import ReferenceQuery
from app.services.evidence import EvidenceNotFound, EvidenceUnavailable
from app.services.reference_parser import extract

candidate = candidate_fixture
ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def data():
    return module("prepare_regulatory_benchmark_v2").build()


def test_exact_31_unique_cases_and_frozen_baseline():
    builder = module("prepare_regulatory_benchmark_v2")
    artifacts = data()
    builder.write_artifacts(artifacts, check=True)
    benchmark = artifacts[builder.BENCHMARK]
    cases = benchmark["cases"]
    assert len(cases) == len({c["id"] for c in cases}) == 31
    assert [c["id"] for c in cases[:19]] == [
        c["id"] for c in builder.load("contracts/regulatory_independent_review.json")["cases"]
    ]
    assert sum(c["kind"] == "existing_question" for c in cases) == 7
    assert sum(c["kind"] == "security_control" for c in cases) == 12
    assert sum(c["kind"] == "new_scenario" for c in cases) == 12
    assert all(set(c["groups"]) <= set(benchmark["groups"]) for c in cases)
    assert len({c["question"] for c in cases}) == 31
    for name, expected in benchmark["baseline_sha256"].items():
        assert builder.sha((ROOT / name).read_bytes()) == expected
    for case in cases:
        if case["kind"] != "security_control":
            ReferenceQuery(**case["request"])


def test_review_is_blank_blind_and_bound_to_benchmark_and_research():
    builder = module("prepare_regulatory_benchmark_v2")
    artifacts = data()
    review = artifacts[builder.REVIEW]
    assert not builder.reviewer_data_present(review)
    assert review["benchmark_sha256"] == builder.sha(builder.encoded(artifacts[builder.BENCHMARK]))
    assert review["provisional_research_sha256"] == builder.sha(
        builder.encoded(artifacts[builder.ANSWERS])
    )
    for case in review["cases"]:
        assert set(case["independent_label"]) == set(builder.LABEL_FIELDS)
        assert all(value is None for value in case["independent_label"].values())
        assert "proposed_relevance_labels" not in case


@pytest.mark.parametrize(
    "field", ["reviewer_id", "rationale", "adjudication_status", "relevant_source_section_keys"]
)
def test_partial_review_cannot_be_overwritten_or_accepted_as_blank(tmp_path, field):
    builder = module("prepare_regulatory_benchmark_v2")
    artifacts = data()
    (tmp_path / "contracts").mkdir()
    review = copy.deepcopy(artifacts[builder.REVIEW])
    review["cases"][0]["independent_label"][field] = "private human work"
    path = tmp_path / builder.REVIEW
    path.write_bytes(builder.encoded(review))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="partial independent reviewer"):
        builder.write_artifacts(artifacts, root=tmp_path)
    assert path.read_bytes() == before and len(list((tmp_path / "contracts").iterdir())) == 1


def test_all_proposed_answers_have_exact_source_versions_and_qualifications():
    builder = module("prepare_regulatory_benchmark_v2")
    artifacts = data()
    answer = artifacts[builder.ANSWERS]
    assert answer["approved_sources"] == answer["independently_adjudicated_cases"] == 0
    assert len(answer["cases"]) == 31
    for case in answer["cases"]:
        assert case["required_abstention"] and case["unresolved_reviewer_questions"]
        assert case["exceptions_and_qualifications"] and case["research_provenance"]
        for ref in case["source_references"]:
            source = answer["sources"][ref["source_key"]]
            assert ref["source_raw_sha256"] == source["raw_sha256"]
            assert ref["authority"] == source["authority"]
            assert ref["relevant_locator"] and ref["source_locator"]
            if ref["source_key"] != builder.DATED:
                section = next(s for s in source["sections"] if s["section"] == ref["section"])
                assert ref["section_text_sha256"] == section["text_sha256"]
                assert ref["start_byte"] == section["start_byte"]
    dated = answer["sources"][builder.DATED]
    assert dated["issued_date"] == "2025-10-09"
    assert dated["status"] == "research_only_not_admitted_not_approved"
    assert dated["effective_from"] is dated["verified_through"] is None
    assert (
        datetime.fromisoformat(dated["retrieved_at"])
        .astimezone(ZoneInfo("America/New_York"))
        .date()
        .isoformat()
        == "2026-11-04"
    )
    assert answer["sources"][builder.FAQ]["publication_date"] is None


def test_real_dated_research_bytes_and_frozen_section_locators():
    builder = module("prepare_regulatory_benchmark_v2")
    registry = builder.source_registry()
    dated = registry[builder.DATED]
    folder = ROOT / "assets/local/regulatory/research_v2"
    if not folder.is_dir():
        pytest.skip("official research review copies not available")
    original = ROOT / dated["research_provenance"]["original_path"]
    landing = ROOT / dated["research_provenance"]["landing_path"]
    assert original.read_bytes().startswith(b"%PDF-")
    assert builder.sha(original.read_bytes()) == dated["raw_sha256"]
    assert builder.sha(landing.read_bytes()) == dated["issuance_evidence"]["raw_sha256"]
    assert b"October 09, 2025" in landing.read_bytes()
    for key in [builder.ECFR, builder.FAQ]:
        source = registry[key]
        review = json.loads((ROOT / source["review_copy"]).read_bytes())
        for section in review["sections"]:
            raw = section["body_text"].encode()
            assert builder.sha(raw) == section["text_sha256"]
            assert len(raw) == section["end_byte"] - section["start_byte"]


def test_metrics_do_not_hide_excluded_sources_or_double_count_groups():
    metrics = module("regulatory_benchmark_metrics")
    cases = [{"id": "one", "groups": ["A", "B", "C"]}]
    keys = {
        "one": dict(
            proposed_relevance_labels=["a:x", "excluded:y"],
            candidate_eligible_source_section_keys=["a:x"],
            expected_status={"candidate": "partial"},
        )
    }
    observations = {"one": {"returned": [{"source_key": "a", "section": "x"}]}}
    result = metrics.question_metrics(cases, keys, observations)
    assert result["precision_at_5"] == 0.2 and result["recall_at_5"] == 0.5
    assert result["mrr"] == 1 and result["unique_questions"] == 1
    assert result["independently_adjudicated_metrics"] is None
    assert result["answered_unavailable_cases"] is None
    assert (
        metrics.operations(
            [dict(latency_ms=2, sql_query_count=2), dict(latency_ms=1, sql_query_count=1)]
        )["latency_ms_p95"]
        == 2
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_ids",
        "missing_observation",
        "missing_label",
        "duplicate_results",
        "oversize",
        "empty_labels",
    ],
)
def test_metrics_reject_identity_and_denominator_corruption(mutation):
    metrics = module("regulatory_benchmark_metrics")
    cases = [{"id": "one"}]
    keys = {
        "one": dict(
            proposed_relevance_labels=["a:x"],
            candidate_eligible_source_section_keys=["a:x"],
            expected_status={"candidate": "available"},
        )
    }
    observations = {"one": {"returned": [{"source_key": "a", "section": "x"}]}}
    if mutation == "duplicate_ids":
        cases *= 2
    elif mutation == "missing_observation":
        observations = {}
    elif mutation == "missing_label":
        keys = {}
    elif mutation == "empty_labels":
        keys["one"]["proposed_relevance_labels"] = []
    elif mutation == "duplicate_results":
        observations["one"]["returned"] *= 2
    else:
        observations["one"]["returned"] = [{"source_key": "a", "section": str(i)} for i in range(6)]
    with pytest.raises(ValueError):
        metrics.question_metrics(cases, keys, observations)


@contextmanager
def measured(engine):
    counter = {"sql_query_count": 0}

    def count(*_):
        counter["sql_query_count"] += 1

    def timeout(session, transaction, connection):
        if connection.dialect.name == "postgresql":
            connection.execute(text("SET LOCAL statement_timeout = '5s'"))

    event.listen(engine, "before_cursor_execute", count)
    event.listen(Session, "after_begin", timeout)
    start = time.perf_counter()
    try:
        yield counter
    finally:
        counter["latency_ms"] = (time.perf_counter() - start) * 1000
        event.remove(engine, "before_cursor_execute", count)
        event.remove(Session, "after_begin", timeout)


def query(env, request, *, scope=None, exclude=()):
    with measured(env["engine"]) as observation:
        rows = candidate_search(env, request, scope=scope, exclude=exclude)
    observation["returned"] = rows
    return observation


@pytest.mark.postgres
def test_all_31_candidate_cases_and_runtime_gate(candidate):
    builder = module("prepare_regulatory_benchmark_v2")
    metrics = module("regulatory_benchmark_metrics")
    artifacts = data()
    benchmark, answers = artifacts[builder.BENCHMARK], artifacts[builder.ANSWERS]
    env = candidate
    keys = {c["id"]: c for c in answers["cases"]}
    questions = [c for c in benchmark["cases"] if c["kind"] != "security_control"]
    observations, runtime, controls = {}, [], []
    violations = reference_errors = reference_total = 0
    source = answers["sources"][builder.ECFR]
    for case in questions:
        obs = query(env, case["request"], scope=case["test_scope"])
        observations[case["id"]] = obs
        for row in obs["returned"]:
            violations += row["source_key"] != builder.ECFR or bool(case["test_scope"])
            section = next(s for s in source["sections"] if s["section"] == row["section"])
            reference_total += 1
            reference_errors += (
                row["raw_sha256"] != source["raw_sha256"]
                or row["text_sha256"] != section["text_sha256"]
            )
        with measured(env["engine"]) as production:
            result = env["service"].retrieve_reference_context(
                env["admin"], env["case"], ReferenceQuery(**case["request"])
            )
        assert result.status == "unavailable" and not result.passages
        production.update(id=case["id"], status=result.status)
        runtime.append(production)
    # Execute explicit technical controls. Legal amendment validity is never simulated as truth.
    for case in (c for c in benchmark["cases"] if c["kind"] == "security_control"):
        identity, p = case["id"], case["procedure"]
        observation = dict(id=identity, passed=True)
        if identity in {"wrong-jurisdiction", "wrong-entity", "wrong-date"}:
            obs = query(env, {"query": p["query"]}, scope=p["test_scope"])
            assert not obs["returned"]
            observation.update(obs)
        elif identity == "superseded":
            obs = query(env, {"section": p["section"]}, exclude=(p["test_exclusion"],))
            assert not obs["returned"]
            observation.update(
                obs,
                coverage="candidate_exclusion_simulation; real synthetic successor covered by test_references",
            )
        elif identity == "withdrawn":
            continue  # Last, so it cannot alter the question corpus or other control outcomes.
        elif identity == "exceptions":
            obs = query(env, {"section": "1020.320"})
            assert len(obs["returned"]) == 1
            with Session(env["engine"]) as session:
                body = session.scalar(
                    select(ReferenceChunk.body_text).where(
                        ReferenceChunk.version_id == env["versions"][builder.ECFR],
                        ReferenceChunk.section == "1020.320",
                    )
                )
            assert (
                "robbery or burglary" in body
                and "17 CFR 240.17f-1" in body
                and "Confidentiality" in body
            )
            observation.update(obs, full_section_preserved=True)
        elif identity == "embedded-instructions":
            parsed = extract(p["attack_fixture"].encode(), "text/plain")
            assert parsed["chunks"][0]["body_text"] == p["attack_fixture"]
            observation.update(
                instructions_executed=False,
                coverage="parser-data boundary only; no future LLM safety claim",
            )
        elif identity in {"forged-reference", "unauthorized"}:
            path = f"/api/v1/cases/{env['case']}/references"
            if identity == "forged-reference":
                response = env["client"].get(
                    path + "/" + str(uuid5(NAMESPACE_URL, "unissued-v2")),
                    headers=env["team"]["auth"]["admin"],
                )
            else:
                response = env["client"].post(
                    path + "/search",
                    json={"section": "1020.320"},
                    headers=env["team"]["auth"]["analysttwo"],
                )
            assert response.status_code == 404
            observation.update(http_status=404)
        else:
            obs = query(env, {k: v for k, v in p.items() if k in {"section", "query"}})
            assert not obs["returned"]
            observation.update(obs)
        controls.append(observation)
    env["service"].withdraw(env["admin"], version_id=env["versions"][builder.ECFR])
    withdrawn = query(env, {"section": "1020.320"})
    assert not withdrawn["returned"]
    controls.append(dict(id="withdrawn", passed=True, **withdrawn))
    assert len(controls) == 12 and violations == reference_errors == 0
    with Session(env["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(ReferenceApproval)) == 0
        assert session.scalar(select(func.count()).select_from(CorpusRelease)) == 0

    def subset(items):
        identities = {c["id"] for c in items}
        return metrics.question_metrics(
            items, {i: keys[i] for i in identities}, {i: observations[i] for i in identities}
        )

    report = dict(
        status="UNREVIEWED_ENGINEERING_DIAGNOSTICS_ONLY",
        unique_cases=31,
        benchmark_sha256=builder.sha(builder.encoded(benchmark)),
        provisional_answer_sha256=builder.sha(builder.encoded(answers)),
        independent_labels=0,
        approved_official_sources=0,
        published_official_releases=0,
        all_19_questions=subset(questions),
        original_7_queries=subset(questions[:7]),
        applicable_candidate_questions=subset(
            [c for c in questions if keys[c["id"]]["candidate_eligible_source_section_keys"]]
        ),
        citation_support=dict(
            source_reference_integrity_checked=reference_total,
            source_reference_integrity_errors=reference_errors,
            source_reference_integrity_coverage=(reference_total - reference_errors)
            / reference_total
            if reference_total
            else None,
            independently_reviewed_claim_support_coverage=None,
            unreviewed_answer_keys=31,
        ),
        applicability=dict(
            technical_filter_violations=violations,
            technical_correct_returned_sources=reference_total,
            independently_reviewed_legal_applicability=None,
        ),
        approved_only_runtime=dict(
            queries=len(runtime), correctly_unavailable=len(runtime), disclosed_passages=0
        ),
        security=dict(
            controls=12,
            passed=12,
            unauthorized_disclosures=0,
            wrong_scope_results=0,
            forged_citations_accepted=0,
            parser_instruction_boundary_violations=0,
            llm_prompt_injection_safety="not_testable_no_LLM",
        ),
        candidate_operations=metrics.operations(
            list(observations.values()) + [c for c in controls if "latency_ms" in c]
        ),
        runtime_operations=metrics.operations(runtime),
        limits=dict(
            returned_rows_per_query=5,
            query_characters=256,
            query_words=40,
            statement_timeout_seconds=5,
            corpus="7 selected immutable sections; only 2 temporally eligible eCFR sections",
            execution="2 CPUs / 3 GiB / isolated clone schemas",
        ),
        observations=observations,
        controls=controls,
        runtime_observations=runtime,
    )
    print("REGULATORY_V2_REPORT:" + json.dumps(report, sort_keys=True))


@pytest.mark.postgres
def test_v2_api_auth_revocation_failure_and_strict_limits(candidate, monkeypatch):
    env = candidate
    service = env["service"]
    path = f"/api/v1/cases/{env['case']}/references/search"
    body = {"section": "1020.320"}
    assert env["client"].post(path, json=body).status_code == 401
    assert (
        env["client"].post(path, json=body, headers=env["team"]["auth"]["analysttwo"]).status_code
        == 404
    )
    for invalid in [
        dict(query="x" * 257),
        dict(query="suspicious", limit=6),
        dict(section="1020.320", version_id=str(env["versions"]["ecfr-us-banks"])),
    ]:
        assert (
            env["client"].post(path, json=invalid, headers=env["team"]["auth"]["admin"]).status_code
            == 422
        )
    for change in ["case_assignment", "user_revocation"]:
        with Session(env["engine"]) as session, session.begin():
            analyst = UUID(env["team"]["users"]["analyst"])
            if change == "case_assignment":
                session.get(Case, env["case"]).assigned_to = UUID(
                    env["team"]["users"]["analysttwo"]
                )
            else:
                session.get(Case, env["case"]).assigned_to = analyst
                session.get(User, analyst).active = False
        with pytest.raises(EvidenceNotFound):
            service.retrieve_reference_context(analyst, env["case"], ReferenceQuery(**body))
    # Existing immutable source/audit boundaries stay fail-closed on a read-side audit failure.
    import app.services.references as reference_module

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic-audit-failure")

    monkeypatch.setattr(reference_module, "audit", broken)
    with pytest.raises(EvidenceUnavailable, match="^evidence_operation_unavailable$"):
        service.retrieve_reference_context(env["admin"], env["case"], ReferenceQuery(**body))
