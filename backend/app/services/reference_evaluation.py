"""Measured lexical evaluation. Synthetic/proposed labels never certify legal retrieval quality."""

import statistics
import time
from zoneinfo import ZoneInfo

from app.schemas.references import AS_OF, KNOWLEDGE_CUTOFF, ReferenceQuery


def evaluate_reference_cases(service, actor_id, case_id, cases, *, review_status):
    if review_status not in {"human_reviewed", "test_fixture", "proposed"}:
        raise ValueError("Unknown review status")
    if review_status == "human_reviewed":
        raise ValueError("Use bound independent regulatory review history for expert metrics")
    if review_status == "proposed":
        return {
            "status": "blocked_pending_human_label_review",
            "precision_at_5": None,
            "recall_at_5": None,
            "mrr": None,
            "case_count": len(cases),
        }
    positives, recalls, ranks, latencies = [], [], [], []
    violations = 0
    empty_failures = 0
    for case in cases:
        start = time.perf_counter()
        result = service.retrieve_reference_context(
            actor_id, case_id, ReferenceQuery(**case["request"])
        )
        latencies.append((time.perf_counter() - start) * 1000)
        relevant = set(case["relevant_sections"])
        returned = [p.section for p in result.passages]
        hits = len(set(returned[:5]) & relevant)
        if relevant:
            positives.append(hits / 5)  # Fixed denominator, including absent slots.
            recalls.append(hits / len(relevant))
            ranks.append(
                next((1 / (n + 1) for n, key in enumerate(returned[:5]) if key in relevant), 0)
            )
        elif returned:
            empty_failures += 1
        for p in result.passages:
            if (
                p.jurisdiction != "US"
                or p.entity != "us_bank"
                or p.language != "en"
                or p.authority not in {"binding_regulation", "statute", "guidance"}
                or p.as_of != AS_OF
                or p.context_id != result.context_id
                or p.release_id != result.release_id
                or p.verified_through is None
                or p.verified_through < p.as_of
                or p.publication_date is not None
                and p.publication_date > KNOWLEDGE_CUTOFF
                or p.retrieved_at.astimezone(ZoneInfo("America/New_York")).date() > KNOWLEDGE_CUTOFF
                or not (
                    p.temporal_basis == "official_dated_snapshot"
                    and p.snapshot_date == AS_OF
                    or p.temporal_basis == "reviewed_interval"
                    and p.publication_date is not None
                    and p.effective_from is not None
                    and p.effective_from <= AS_OF
                    and (p.effective_to is None or p.effective_to > AS_OF)
                )
                or p.origin == "synthetic_test"
                and review_status != "test_fixture"
            ):
                violations += 1
    ordered = sorted(latencies)
    return {
        "status": "controlled_fixture_measurement"
        if review_status == "test_fixture"
        else "reviewed_case_measurement",
        "labels": review_status,
        "case_count": len(cases),
        "positive_case_count": len(positives),
        "precision_at_5": statistics.mean(positives) if positives else None,
        "recall_at_5": statistics.mean(recalls) if recalls else None,
        "mrr": statistics.mean(ranks) if ranks else None,
        "filter_violations": violations,
        "expected_empty_failures": empty_failures,
        "latency_ms_p50": statistics.median(ordered) if ordered else None,
        "latency_ms_p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        if ordered
        else None,
        "legal_retrieval_quality_approved": False,
    }
