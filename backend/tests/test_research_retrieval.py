"""Per-case research retrieval: real PostgreSQL ts_rank_cd over the real hash-verified
31 CFR Part 1020 snapshot (24 sections). No mocked ranking."""

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.services import research_retrieval as rr
from app.services.research_demo import ResearchEvidenceService

PACKET = Path(__file__).parent / "fixtures" / "research_replay" / "packet.json"
MODEL_FEATURES = [
    "kycRiskScore", "income", "tenureMonths", "creditScore", "state", "nbrPurchases90d",
    "avgTxnSize90d", "totalSpend90d", "nbrDistinctMerch90d", "nbrMerchCredits90d",
    "nbrMerchCreditsRndDollarAmt90d", "totalMerchCred90d", "nbrMerchCreditsWoOffsettingPurch",
    "nbrPayments90d", "totalPaymentAmt90d", "overpaymentAmt90d", "overpaymentInd90d",
    "nbrCustReqRefunds90d", "totalRefundsToCust90d", "nbrPaymentsCashLike90d",
    "maxRevolveLine", "indOwnsHome", "nbrInquiries1y", "nbrCollections3y", "nbrWebLogins90d",
    "nbrPointRed90d", "PEP",
]


def packet_with(drivers, missing=("settlement_status",)):
    """The recorded packet, with only the model's score-raising drivers replaced."""
    value = json.loads(PACKET.read_text())
    value["model_signal"]["explanation"]["features"] = [
        {"name": n, "contribution": 0.1 - i / 100, "direction": "raises_score", "missing": False}
        for i, n in enumerate(drivers)
    ]
    value["missing_evidence"] = list(missing)
    value["facts"] = []
    return value


# ---- field-to-term mapping (pure) --------------------------------------------------------


def test_every_model_feature_maps_to_plain_regulatory_terms():
    assert set(rr.FEATURE_TERMS) == set(MODEL_FEATURES)
    for name in MODEL_FEATURES:
        terms = rr.map_terms(["risk_driver:" + name])
        assert terms and all(t.isalpha() and t.islower() for t in terms)
        assert name.lower() not in terms  # model field names never reach the query


@pytest.mark.parametrize(
    "item, expected",
    [
        ("risk_driver:nbrPaymentsCashLike90d", {"cash", "currency", "transaction"}),
        ("risk_driver:totalRefundsToCust90d", {"refund", "return", "funds"}),
        ("calculation:counterparty_concentration", {"counterparty", "transfer"}),
        ("missing_evidence:comparable_expected_activity", {"due", "diligence", "profile"}),
    ],
)
def test_mapping_examples(item, expected):
    assert expected <= set(rr.map_terms([item]))


def test_unknown_inputs_contribute_nothing_and_terms_are_unique():
    assert rr.map_terms(["risk_driver:notAFeature", "other:x"]) == []
    terms = rr.map_terms(["risk_driver:nbrCustReqRefunds90d", "risk_driver:totalRefundsToCust90d"])
    assert terms == ["refund", "return", "funds"]


def test_case_inputs_take_the_top_three_score_raising_drivers_in_order():
    inputs = rr.case_inputs(json.loads(PACKET.read_text()))
    assert inputs[:3] == [
        "risk_driver:totalMerchCred90d",
        "risk_driver:totalSpend90d",
        "risk_driver:nbrMerchCredits90d",
    ]
    assert "calculation:counterparty_concentration" in inputs
    assert "missing_evidence:settlement_status" in inputs


def test_query_uses_or_semantics():
    assert rr.or_query(["cash", "refund"]) == "cash | refund"
    with pytest.raises(ValueError):
        rr.or_query(["cash & refund"])
    with pytest.raises(ValueError):
        rr.or_query([])


# ---- real PostgreSQL ranking over the real snapshot ----------------------------------------


@pytest.fixture(scope="module")
def session():
    url = os.environ.get("TRUEFLAG_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("PostgreSQL test database required")
    engine = create_engine(url)
    with Session(engine) as value:
        yield value
    engine.dispose()


@pytest.fixture(scope="module")
def corpus():
    service = object.__new__(ResearchEvidenceService)
    _, chunks = service._corpus()  # raw/extracted snapshot hashes are verified here
    return chunks


def retrieve(session, corpus, inputs):
    ranked, matched = rr.rank(session, corpus, rr.or_query(rr.map_terms(inputs)))
    return ranked, matched


def test_the_whole_verified_snapshot_is_searched(corpus):
    assert len(corpus) == 24
    assert {"1020.210", "1020.310", "1020.320", "1020.620"} <= {c["section"] for c in corpus}


def test_cases_with_different_risk_drivers_retrieve_different_sections(session, corpus):
    cash = rr.case_inputs(packet_with(["nbrPaymentsCashLike90d", "totalSpend90d"]))
    political = rr.case_inputs(packet_with(["PEP", "income"]))
    first, _ = retrieve(session, corpus, cash)
    second, _ = retrieve(session, corpus, political)
    assert first and second
    assert {s for s, _ in first} != {s for s, _ in second}


def test_results_are_top_three_by_positive_score_in_rank_order(session, corpus):
    ranked, matched = retrieve(session, corpus, rr.case_inputs(json.loads(PACKET.read_text())))
    assert 1 <= len(ranked) <= 3 and matched >= len(ranked)
    scores = [float(score) for _, score in ranked]
    assert all(s > 0 for s in scores) and scores == sorted(scores, reverse=True)


def test_a_long_query_with_one_matching_term_never_returns_zero_rows(session, corpus):
    terms = ["zebra", "quokka", "narwhal", "axolotl", "pangolin", "okapi", "currency"]
    ranked, matched = rr.rank(session, corpus, rr.or_query(terms))
    assert ranked and matched >= 1


def test_fewer_matches_than_three_are_returned_without_padding(session, corpus):
    ranked, matched = rr.rank(session, corpus, rr.or_query(["subpoena"]))
    assert 1 <= len(ranked) == matched < 3


def test_no_matching_term_returns_nothing(session, corpus):
    ranked, matched = rr.rank(session, corpus, rr.or_query(["zebra", "quokka"]))
    assert ranked == [] and matched == 0


def test_titles_come_from_the_section_text(corpus):
    by = {c["section"]: rr.title_of(c["body_text"]) for c in corpus}
    assert by["1020.320"] == "Reports by banks of suspicious transactions"
    assert by["1020.310"] == "Reports of transactions in currency"


def test_passage_budget_keeps_rank_order_and_reports_unsent_sections(corpus):
    sizes = {c["section"]: len(c["body_text"].encode()) for c in corpus}
    big = [s for s, n in sorted(sizes.items(), key=lambda kv: -kv[1])[:3]]
    assert sum(sizes[s] for s in big) > rr.PASSAGE_BUDGET_BYTES  # the case that needs a budget
    assert max(sizes.values()) <= rr.PASSAGE_BUDGET_BYTES  # rank 1 always fits


# ---- administrator corpus view and read-only test retrieval -------------------------------


def test_free_text_query_terms_use_the_case_word_rule():
    assert rr.query_terms("Cash CURRENCY, cash; a 10k transfer!") == [
        "cash",
        "currency",
        "transfer",
    ]
    assert rr.query_terms("12 ab §") == []
    assert len(" ".join(rr.query_terms(" ".join(f"word{c}x" for c in "abc" * 40)))) <= 256


def _open_service(monkeypatch):
    service = object.__new__(ResearchEvidenceService)
    monkeypatch.setattr(service, "_environment", lambda session: None, raising=False)
    return service


def test_corpus_view_reports_the_verified_snapshot(monkeypatch):
    view = _open_service(monkeypatch).corpus_view(None)
    assert view["sections"] == 24
    assert view["snapshot_date"] == "2026-11-02"
    assert view["fingerprint_verified"] is True
    assert view["status"] == "unapproved_research_only"
    assert view["top_k"] == 3


def test_test_retrieval_ranks_like_case_retrieval(monkeypatch, session, corpus):
    service = _open_service(monkeypatch)
    found = service.test_retrieval(session, "cash currency transaction")
    expected, matched = rr.rank(session, corpus, rr.or_query(["cash", "currency", "transaction"]))
    assert [(r["section"], r["score"]) for r in found["results"]] == expected
    assert [r["rank"] for r in found["results"]] == list(range(1, len(expected) + 1))
    assert found["matched_sections"] == matched and found["total_sections"] == 24
    assert service.test_retrieval(session, "12 §")["results"] == []


def test_corpus_routes_are_blocked_outside_the_research_environment():
    from types import SimpleNamespace

    from app.services.evidence import EvidenceBlocked

    service = object.__new__(ResearchEvidenceService)
    service.settings = SimpleNamespace(academic_research_enabled=False, app_env="local")
    with pytest.raises(EvidenceBlocked):
        service.corpus_view(None)
    with pytest.raises(EvidenceBlocked):
        service.test_retrieval(None, "cash")


# ---- relative-score threshold (25% of the top score) ---------------------------------------


def test_strong_matches_drop_results_below_a_quarter_of_the_top_score():
    ranked = [("1020.410", "1.900000"), ("1020.320", "0.475000"), ("1020.310", "0.474999")]
    assert rr.strong_matches(ranked) == ranked[:2]  # exactly 25% stays; below is dropped
    assert rr.strong_matches(ranked[:1]) == ranked[:1]  # the top result always stays
    assert rr.strong_matches([]) == []
    assert rr.MIN_RELATIVE_SCORE == "0.25"


def test_wire_transfer_recordkeeping_keeps_only_the_strong_match(monkeypatch, session, corpus):
    found = _open_service(monkeypatch).test_retrieval(session, "wire transfer recordkeeping")
    assert [r["section"] for r in found["results"]] == ["1020.410"]
    assert found["strong_matches"] == 1 and found["min_relative_score"] == "0.25"
    unfiltered, _ = rr.rank(session, corpus, rr.or_query(found["terms"]))
    assert len(unfiltered) > 1  # the threshold, not the query, removed the weaker sections


def test_new_case_retrieval_stores_the_threshold_and_v2_records_rerun_unchanged(
    monkeypatch, session, corpus
):
    from uuid import uuid4

    from app.schemas.research_demo import ResearchRetrieval, ResearchRetrievalV2

    service = _open_service(monkeypatch)
    monkeypatch.setattr(service, "_scope", lambda *a: None, raising=False)
    monkeypatch.setattr(service, "_citation", lambda *a: _Citation(), raising=False)
    inputs = rr.case_inputs(packet_with(["nbrPaymentsCashLike90d", "totalSpend90d"]))
    run = uuid4()
    _, _, new = service._retrieve(session, None, uuid4(), run, inputs)
    assert isinstance(new, ResearchRetrievalV2)
    assert new.min_relative_score == "0.25" and new.strong_matches == len(new.results)
    top = float(new.results[0].score)
    assert all(float(r.score) >= 0.25 * top for r in new.results)
    _, _, legacy = service._retrieve(
        session, None, uuid4(), run, inputs, relative=False, excerpts=False
    )
    assert type(legacy) is ResearchRetrieval  # v2 records keep the original top-3 rule
    assert "min_relative_score" not in legacy.model_dump()
    expected, _ = rr.rank(session, corpus, legacy.query)
    assert [(r.section, r.score) for r in legacy.results] == expected


class _Citation:
    reference_id = __import__("uuid").uuid4()


# ---- bounded excerpts (binding v4) --------------------------------------------------------


def test_a_section_that_fits_is_sent_whole():
    body = "§ 1020.999 Short section.\n(a)\nGeneral.\nCash transactions are recorded."
    text, spans = rr.excerpt(body, ["0.1"] * 4, cap=4000)
    assert text == body and spans == [(0, len(body.encode()))]


def test_excerpt_keeps_the_heading_and_best_lines_in_document_order_within_the_cap():
    lines = ["§ 1020.999 Long section."]
    lines += [f"Filler line {n} " + "x" * 300 for n in range(20)]
    lines[5] = "(a)"
    lines[6] = "Cash currency transaction records are retained " + "y" * 250
    lines[15] = "Currency transfer line " + "z" * 250
    body = "\n".join(lines)
    scores = ["0.000000"] * len(lines)
    scores[6], scores[15] = "0.300000", "0.100000"
    text, spans = rr.excerpt(body, scores, cap=1000)
    assert len(text.encode()) <= 1000
    parts = text.split(rr.EXCERPT_GAP)
    assert parts[0] == lines[0]  # heading always kept
    assert parts[1] == "(a)\n" + lines[6]  # best line with its short label line
    assert parts[2] == lines[15]  # next-best line, document order
    data = body.encode()
    assert rr.EXCERPT_GAP.join(data[s:e].decode() for s, e in spans) == text


def test_new_case_retrieval_sends_every_strong_match_as_a_bounded_excerpt(
    monkeypatch, session, corpus
):
    import hashlib
    from uuid import uuid4

    from app.schemas.research_demo import ResearchExcerptCitation, ResearchRetrievalV3

    service = _open_service(monkeypatch)
    monkeypatch.setattr(service, "_scope", lambda *a: None, raising=False)
    # The 8a8b6f51 demo inputs: v3 left § 1020.315 unsent (request size limit).
    inputs = [
        "risk_driver:totalMerchCred90d",
        "risk_driver:totalSpend90d",
        "calculation:counterparty_concentration",
        "missing_evidence:comparable_expected_activity",
        "missing_evidence:curated_documents",
        "missing_evidence:sampling_metadata",
    ]
    run = uuid4()
    case = uuid4()
    query, passages, retrieval = service._retrieve(session, None, case, run, inputs)
    assert isinstance(retrieval, ResearchRetrievalV3) and retrieval.excerpt_cap_bytes == 4000
    assert all(r.sent for r in retrieval.results)  # every strong match reaches the AI
    assert len(passages) == len(retrieval.results) == retrieval.strong_matches
    by_section = {c["section"]: c["body_text"] for c in corpus}
    for result, passage in zip(retrieval.results, passages):
        assert isinstance(passage, ResearchExcerptCitation)
        assert passage.reference_id == result.reference_id
        sent = passage.text.encode()
        assert len(sent) == result.excerpt_bytes <= 4000
        assert hashlib.sha256(sent).hexdigest() == result.excerpt_sha256 == passage.excerpt_sha256
        full = by_section[result.section].encode()
        assert passage.section_text_bytes == result.text_bytes == len(full)
        rebuilt = rr.EXCERPT_GAP.join(full[s.start : s.end].decode() for s in result.excerpt_spans)
        assert rebuilt == passage.text  # the stored spans say exactly what was sent
    # Deterministic: re-running gives the identical record, as verification requires.
    assert service._retrieve(session, None, case, run, inputs) == (query, passages, retrieval)
    # v3 records (threshold, full sections) still re-run with their own rule and shape.
    _, _, v3 = service._retrieve(session, None, case, run, inputs, excerpts=False)
    assert type(v3).__name__ == "ResearchRetrievalV2"
    assert not v3.results[1].sent  # unchanged: the v3 record still shows it was not sent
