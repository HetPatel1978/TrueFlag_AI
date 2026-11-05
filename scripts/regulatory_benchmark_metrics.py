"""Pure engineering-proposal diagnostics, isolated from production retrieval and approvals."""

import statistics


def question_metrics(cases, keys, observations):
    """Never accept duplicate/missing IDs or treat empty relevance as perfect recall."""
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)) or set(ids) != set(keys) or set(ids) != set(observations):
        raise ValueError("Mismatched evaluation identities")
    precision, recall, ranks = [], [], []
    available = unavailable = false_abstentions = unavailable_with_passages = partial = 0
    for case in cases:
        key = keys[case["id"]]
        relevant = set(key["proposed_relevance_labels"])
        if not relevant:
            raise ValueError("Question requires explicit proposed relevance or exclusion labels")
        rows = observations[case["id"]]["returned"]
        returned = [r["source_key"] + ":" + r["section"] for r in rows]
        if len(returned) > 5 or len(returned) != len(set(returned)):
            raise ValueError("Unbounded or duplicate candidate results")
        hits = set(returned) & relevant
        precision.append(len(hits) / 5)
        recall.append(len(hits) / len(relevant))
        ranks.append(next((1 / (i + 1) for i, k in enumerate(returned) if k in relevant), 0))
        eligible = set(key["candidate_eligible_source_section_keys"])
        if key["expected_status"]["candidate"] == "unavailable":
            unavailable += not returned
            unavailable_with_passages += bool(returned)
        else:
            available += bool(set(returned) & eligible)
            false_abstentions += not bool(set(returned) & eligible)
        partial += bool(hits) and len(hits) < len(relevant)
    return dict(
        label_basis="engineering_proposals_not_independent_ground_truth",
        unique_questions=len(ids),
        precision_at_5=statistics.mean(precision) if precision else None,
        recall_at_5=statistics.mean(recall) if recall else None,
        mrr=statistics.mean(ranks) if ranks else None,
        candidate_coverage=dict(
            correctly_unavailable_queries=unavailable,
            unavailable_queries_returning_passages=unavailable_with_passages,
            available_or_partial_queries_with_relevant_passages=available,
            false_abstentions=false_abstentions,
            partial_source_coverage=partial,
        ),
        answered_unavailable_cases=None,
        answer_generation="not_implemented; retrieval observations are not generated legal answers",
        independently_adjudicated_metrics=None,
    )


def operations(observations):
    latencies = sorted(o["latency_ms"] for o in observations)
    counts = [o["sql_query_count"] for o in observations]
    return dict(
        timed_queries=len(latencies),
        latency_ms_p50=statistics.median(latencies) if latencies else None,
        latency_ms_p95=latencies[max(0, (95 * len(latencies) + 99) // 100 - 1)]
        if latencies
        else None,
        sql_query_count=sum(counts),
        sql_query_count_min=min(counts) if counts else None,
        sql_query_count_max=max(counts) if counts else None,
        query_counter="SQLAlchemy cursor executions, including SET LOCAL timeout statements",
    )
