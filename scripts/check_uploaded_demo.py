"""Check current evidence contexts for the imported local synthetic demonstration."""

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
marker = json.loads((ROOT / "runtime/local-app/current.json").read_text())
directory = ROOT / marker["directory"]
config = json.loads((directory / "config/config.json").read_text())
receipt = json.loads(
    (ROOT / "runtime/investigation-demo-20261120-v1/local-receipt.json").read_text()
)
with httpx.Client(base_url=config["backend_url"], timeout=20, trust_env=False) as client:
    response = client.post(
        "/api/v1/auth/token",
        json={"username": config["username"], "password": config["login_password"]},
    )
    response.raise_for_status()
    client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
    response = client.get(f"/api/v1/batch-assessments/{receipt['batch_id']}/results?limit=10")
    response.raise_for_status()
    for item in response.json()["items"]:
        assessment = item.get("assessment") or {}
        print(
            json.dumps(
                {
                    "case_id": item["case_id"],
                    "outcome": item["outcome"],
                    "score": assessment.get("score"),
                    "recommendation": assessment.get("recommended_route"),
                }
            )
        )
    for name, case in receipt["cases"].items():
        response = client.get(f"/api/v1/cases/{case}/evidence")
        print(
            json.dumps(
                {
                    "scenario": name,
                    "http_status": response.status_code,
                    "source_count": len(response.json().get("sources", []))
                    if response.is_success
                    else None,
                }
            )
        )
    if "--generate-summary" in sys.argv:
        case = receipt["cases"]["priority"]
        history = client.get(f"/api/v1/cases/{case}/assessments")
        history.raise_for_status()
        assessment = history.json()["items"][0]["assessment_id"]
        response = client.get(
            f"/api/v1/cases/{case}/evidence", params={"assessment_id": assessment}
        )
        response.raise_for_status()
        context = response.json()
        snapshot = context["snapshot"]
        payload = {
            "expected_case_version": snapshot["case_version"],
            "expected_evidence_revision": snapshot["evidence_revision"],
            "expected_access_revision": snapshot["access_revision"],
            "assessment_id": assessment,
            "window": context["sources"][0]["window"],
            "currencies": ["USD"],
        }
        response = client.post(
            f"/api/v1/cases/{case}/investigations",
            json=payload,
            headers={"Idempotency-Key": "synthetic_demo_priority_summary_v1"},
        )
        print(json.dumps({"summary_request_http": response.status_code}))
        response.raise_for_status()
        run_id = response.json()["run_id"]
        for _ in range(20):
            response = client.get(f"/api/v1/cases/{case}/investigations/{run_id}")
            response.raise_for_status()
            result = response.json()
            if result["status"] not in {"pending", "running"}:
                break
            time.sleep(2)
        print(
            json.dumps(
                {
                    "summary_status": result["status"],
                    "verification": (result.get("verification") or {}).get("status"),
                    "mode": result.get("mode"),
                    "run_id": run_id,
                }
            )
        )
