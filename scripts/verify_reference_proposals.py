"""Verify locally curated OFFICIAL bytes against proposed hashes. No approval or network."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.reference_parser import approved_url, extract, sha  # noqa: E402


def verify():
    proposal_bytes = (ROOT / "contracts/regulatory_source_proposals.json").read_bytes()
    proposal = json.loads(proposal_bytes)
    labels_bytes = (ROOT / "contracts/regulatory_evaluation_proposals.json").read_bytes()
    labels = json.loads(labels_bytes)
    assert proposal["publication_status"] == "blocked_pending_human_approval"
    assert labels["review_status"] == "proposed" and labels["reviewer"] is None
    assert labels["source_manifest_sha256"] == sha(proposal_bytes)
    evidence = proposal["validity_evidence"]
    metadata_bytes = (
        ROOT / "assets/local/regulatory/proposed/ecfr-title31-metadata.json"
    ).read_bytes()
    assert sha(metadata_bytes) == evidence["sha256"]
    title = next(item for item in json.loads(metadata_bytes)["titles"] if item["number"] == 31)
    assert title["up_to_date_as_of"] == evidence["up_to_date_as_of"] == proposal["scope"]["as_of"]
    specs = [("ecfr-bank-2026-11-02.xml", "application/xml"), ("fincen-sar-faqs.html", "text/html")]
    sources = []
    for source, (filename, media) in zip(proposal["sources"], specs, strict=True):
        approved_url(source["url"])
        result = extract((ROOT / "assets/local/regulatory/proposed" / filename).read_bytes(), media)
        assert result["raw_sha256"] == source["raw_sha256"]
        assert result["extracted_sha256"] == source["extracted_sha256"]
        chunks = {chunk["section"]: chunk for chunk in result["chunks"]}
        for section in source["sections"]:
            assert all(chunks[section["section"]][key] == value for key, value in section.items())
        sources.append(
            {
                "key": source["key"],
                "selected_sections": len(source["sections"]),
                "integrity": "verified",
                "approval": "pending",
            }
        )
    return {
        "status": "proposed_source_integrity_verified",
        "source_proposal_sha256": sha(proposal_bytes),
        "evaluation_proposal_sha256": sha(labels_bytes),
        "sources": sources,
        "publication_approved": False,
        "legal_quality_approved": False,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), sort_keys=True))
    except Exception:
        print(json.dumps({"status": "FAIL", "reason": "source_proposal_integrity_unavailable"}))
        raise SystemExit(1) from None
