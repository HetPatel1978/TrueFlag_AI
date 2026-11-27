"""Build the demo case set from app.services.demo_case_catalog and check it offline.

Writes:
  docs/demo/trueflag_demo_cases.csv     upload file for Admin > CSV imports (template order)
  docs/demo/evidence/<case>.json        the generated evidence each case is bound to
  docs/demo/demo_cases_offline.json     offline results: real frozen RF score, policy routes,
                                        SHAP drivers and the system's per-case retrieval

Scoring uses the frozen RF/policy/SHAP artifacts unchanged. Retrieval uses the system's own
case_inputs/map_terms/rank/strong_matches over the hash-verified corpus; ts_rank_cd runs in a
READ ONLY transaction on the native runtime's *test* database and touches no table.
No AI provider is called. Run with the Windows runtime interpreter (.venv-windows).
"""

import csv
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
OUT = ROOT / "docs/demo"
POLICIES = ("Efficiency", "Balanced", "Coverage")


def write_inputs():
    from app.schemas.csv_uploads import COLUMNS
    from app.services import demo_case_catalog as catalog
    from app.services.synthetic_evidence import bundle_manifest, canonical_records

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evidence").mkdir(exist_ok=True)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    for case_id in catalog.CASES:
        row = catalog.csv_row(case_id)
        writer.writerow({k: "" if row[k] is None else row[k] for k in COLUMNS})
        bundle = catalog.bundle(case_id)
        evidence = {
            "catalog_version": catalog.CATALOG_VERSION,
            "case_id": case_id,
            "title": catalog.CASES[case_id]["title"],
            "note": "Generated synthetic evidence. Bound to the uploaded case by "
            "scripts/attach_demo_evidence.py; model inputs are declared, not derived from it.",
            "coverage": bundle.coverage,
            "window_start": bundle.window_start.isoformat(),
            "as_of": bundle.as_of.isoformat(),
            "manifest": bundle_manifest(bundle),
            "records": canonical_records(bundle),
        }
        (OUT / "evidence" / f"{case_id}.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=False) + "\n", encoding="utf-8"
        )
    (OUT / "trueflag_demo_cases.csv").write_bytes(buffer.getvalue().encode("utf-8"))


def packet_like(bundle, drivers):
    """The packet fields retrieval reads, as the packet producer would set them."""
    transactions = [r for r in bundle.records if r.kind == "transaction"]
    missing = {
        "comparable_expected_activity",
        "curated_documents",
        "sampling_metadata",
        "settlement_status",
    }
    window = {"start": bundle.window_start.isoformat(), "end": bundle.as_of.isoformat()}
    return {
        "model_signal": {"explanation": {"features": drivers}},
        # As in the packet: every in-window transaction, and facts that carry the window.
        "transactions": [
            {
                "amount": str(t.amount),
                "currency": t.currency,
                "event_at": t.event_at.isoformat(),
                "direction": t.direction,
                "channel": t.channel,
                "counterparty_handle": t.counterparty_key,
            }
            for t in transactions
            if t.event_at is not None and bundle.window_start <= t.event_at < bundle.as_of
        ],
        # Concentration is calculated whenever the window has transactions.
        "facts": [{"result": {"concentration": [1] if transactions else [], "window": window}}],
        "missing_evidence": sorted(missing),
        "conflicts": [],
    }


def offline_results():
    os.chdir(ROOT / "backend")
    import windows_runtime
    from app.services import demo_case_catalog as catalog
    from app.services import research_retrieval as rr
    from app.services.research_demo import ResearchEvidenceService
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from trueflag_ml.explainability import ExplanationService
    from trueflag_ml.policy import RiskPolicyEngine
    from trueflag_ml.scoring import RFScoringService, ScoringRecord

    ids = list(catalog.CASES)
    records = [ScoringRecord(i, catalog.declarations(i)) for i in ids]
    scores = RFScoringService().score_batch(records)
    policy = RiskPolicyEngine()
    explanations = ExplanationService(lambda _id: True).explain_batch(records)
    holder = ResearchEvidenceService.__new__(ResearchEvidenceService)
    ResearchEvidenceService._catalog(holder)
    chunks = holder._corpus_chunks
    titles = {c["section"]: rr.title_of(c["body_text"]) for c in chunks}
    _, state = windows_runtime.current()
    engine = create_engine(state["test_url"])
    results = {}
    with Session(engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        for case_id, score, explanation in zip(ids, scores, explanations):
            inputs = catalog.declarations(case_id)
            bundle = catalog.bundle(case_id)
            features = [
                {
                    "name": f.name,
                    "contribution": f.contribution,
                    "direction": f.direction,
                    "missing": f.missing,
                }
                for f in explanation.features
            ]
            raising = sorted(
                (f for f in features if f["direction"] == "raises_score" and not f["missing"]),
                key=lambda f: (-f["contribution"], f["name"]),
            )
            packet = packet_like(bundle, features)
            # Before: the v4 rule (unchanged for stored v1-v4 records).
            case_inputs = rr.case_inputs(packet)
            terms = rr.map_terms(case_inputs)
            ranked, matched = rr.rank(session, chunks, rr.or_query(terms))
            strong = rr.strong_matches(ranked)
            # After: the v5 rule used for new records.
            inputs_v5, patterns, dropped = rr.case_inputs_v5(packet, inputs["income"])
            weighted = rr.weighted_terms_v5(inputs_v5)
            ranked_v5, matched_v5 = rr.rank_v5(session, chunks, weighted)
            strong_v5 = rr.strong_matches(ranked_v5)
            routes = {}
            for mode in POLICIES:
                recommendation = policy.evaluate(score, mode, kyc_risk_score=inputs["kycRiskScore"])
                routes[mode] = recommendation.recommended_route
            transactions = [r for r in bundle.records if r.kind == "transaction"]
            results[case_id] = {
                "title": catalog.CASES[case_id]["title"],
                "score": score.score,
                "processing_status": score.processing_status,
                "priority": "High" if inputs["kycRiskScore"] >= 3 else "Standard",
                "kyc": inputs["kycRiskScore"],
                "routes": routes,
                "thresholds": dict(policy.settings.thresholds),
                "explanation_status": explanation.status,
                "top_drivers": [(f["name"], round(f["contribution"], 4)) for f in raising[:3]],
                "evidence": {
                    "coverage": bundle.coverage,
                    "transactions": len(transactions),
                    "expected_packet": "abstained"
                    if bundle.coverage != "complete_declared_window" or not transactions
                    else "packet_ready",
                },
                "retrieval_v4_before": {
                    "inputs": case_inputs,
                    "query": " ".join(terms),
                    "matched_sections": int(matched),
                    "strong_matches": [
                        {"section": s, "score": sc, "title": titles[s]} for s, sc in strong
                    ],
                },
                "retrieval_inputs": inputs_v5,
                "dropped_inputs": dropped,
                "patterns_fired": patterns,
                "retrieval_query": " ".join(t for t, _ in weighted),
                "weighted_terms": [[t, w] for t, w in weighted],
                "matched_sections": int(matched_v5),
                "strong_matches": [
                    {"section": s, "score": sc, "title": titles[s]} for s, sc in strong_v5
                ],
            }
    engine.dispose()
    tops = sorted({r["strong_matches"][0]["section"] for r in results.values()})
    every = sorted({m["section"] for r in results.values() for m in r["strong_matches"]})
    before = sorted(
        {r["retrieval_v4_before"]["strong_matches"][0]["section"] for r in results.values()}
    )
    summary = {
        "retrieval_rule": "v5 (binding v5)",
        "distinct_top_sections": tops,
        "distinct_strong_sections": every,
        "v4_distinct_top_sections": before,
    }
    (OUT / "demo_cases_offline.json").write_text(
        json.dumps({"summary": summary, "cases": results}, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return summary, results


def main():
    write_inputs()
    summary, results = offline_results()
    for case_id, r in results.items():
        print(
            f"{case_id:<20} score {r['score']:.4f} {r['priority']:<8} "
            f"{'/'.join(v[:6] for v in r['routes'].values())} "
            f"v4 {[m['section'] for m in r['retrieval_v4_before']['strong_matches']]} "
            f"v5 {[m['section'] for m in r['strong_matches']]} "
            f"rules {[p['rule'] for p in r['patterns_fired']]} {r['evidence']['expected_packet']}"
        )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
