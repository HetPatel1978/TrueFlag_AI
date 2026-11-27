"""Import the jointly generated synthetic demo into the active local workspace."""

import json
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
DEMO = ROOT / "runtime/investigation-demo-20261120-v1"


def attach_inside():
    from app.core.database import make_engine
    from app.models import User
    from app.services.synthetic_demo_cases import SyntheticDemoEvidenceService
    from sqlalchemy import select, text
    from sqlalchemy.orm import Session

    config = json.loads(Path("/local-config/config.json").read_text())
    requested = json.load(sys.stdin)
    if set(requested) != {"priority", "ordinary", "incomplete"}:
        raise ValueError("unexpected_demo_scenarios")
    engine = make_engine(config["database_url"])
    with engine.connect() as conn:
        identity = str(conn.scalar(text("SELECT system_identifier FROM pg_control_system()")))
        dbname = conn.scalar(text("SELECT current_database()"))
        revision = conn.scalar(text("SELECT version_num FROM alembic_version"))
    if (
        identity != str(config["expected_cluster"])
        or identity == str(config["forbidden_cluster"])
        or dbname != config["database"]
        or revision != "0019_upload_sessions"
    ):
        raise RuntimeError("isolated_database_verification_failed")
    with Session(engine) as session:
        actor = session.scalar(
            select(User.id).where(
                User.username == config["username"], User.active.is_(True), User.role == "admin"
            )
        )
    if actor is None:
        raise RuntimeError("local_demo_actor_unavailable")
    service = SyntheticDemoEvidenceService(engine)
    results = [service.attach_uploaded_case(actor, UUID(requested[key]), key) for key in requested]
    engine.dispose()
    print(json.dumps({"attached": results}))


def main():
    import httpx
    import rehearse_database_recovery as recovery

    marker = recovery.load(ROOT / "runtime/local-app/current.json")
    directory = (ROOT / marker["directory"]).resolve(strict=True)
    if not directory.is_relative_to((ROOT / "runtime/local-app").resolve()):
        raise RuntimeError("invalid_local_runtime")
    state = recovery.load(directory / "state.json")
    recovery.verify_container(state)
    config = recovery.load(directory / "config/config.json")
    ownership = recovery.load(directory / "ownership.json")
    receipt_path = DEMO / "local-receipt.json"
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    with httpx.Client(base_url=config["backend_url"], trust_env=False, timeout=70) as client:

        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.is_error:
                raise RuntimeError(f"{method} {path.split('?')[0]}: HTTP {response.status_code}")
            return response.json()

        login = request(
            "POST",
            "/api/v1/auth/token",
            json={"username": config["username"], "password": config["login_password"]},
        )
        client.headers["Authorization"] = "Bearer " + login["access_token"]
        workspace = request("GET", "/api/v1/upload-sessions")
        active = workspace["active"]
        if not active or not active["can_upload"]:
            raise RuntimeError("active_upload_workspace_unavailable")
        if receipt.get("session_id") and receipt["session_id"] != active["id"]:
            raise RuntimeError("active_upload_workspace_changed")
        receipt["session_id"] = active["id"]
        save()
        if "upload_id" not in receipt:
            uploaded = request(
                "POST",
                "/api/v1/batch-uploads",
                content=(DEMO / "investigation-demo.csv").read_bytes(),
                headers={
                    "Content-Type": "text/csv",
                    "Idempotency-Key": "synthetic-demo-upload-v1-" + active["id"],
                    "X-Upload-Session-ID": active["id"],
                },
            )
            receipt["upload_id"] = uploaded["upload_id"]
            save()
        upload_id = receipt["upload_id"]
        if "preview" not in receipt:
            preview = request(
                "POST",
                f"/api/v1/batch-uploads/{upload_id}/validations",
                json={"units": "baseline_source_units"},
            )
            if (preview["total_rows"], preview["valid_rows"], preview["invalid_rows"]) != (3, 3, 0):
                raise RuntimeError("synthetic_validation_not_three_valid_rows")
            receipt["preview"] = preview
            save()
        preview = receipt["preview"]
        if "import_id" not in receipt:
            approval = {
                key: preview[key]
                for key in (
                    "upload_sha256",
                    "mapping_sha256",
                    "mapping_version",
                    "validator_version",
                    "units",
                )
            }
            approval.update(approve_valid_rows=True, validation_version=preview["version"])
            imported = request(
                "POST",
                f"/api/v1/batch-uploads/{upload_id}/validations/{preview['validation_id']}/imports",
                json=approval,
                headers={"Idempotency-Key": "synthetic-demo-import-v1-" + active["id"]},
            )
            receipt["import_id"] = imported["import_id"]
            save()
        import_id = receipt["import_id"]
        for _ in range(36):
            imported = request("GET", f"/api/v1/batch-imports/{import_id}")
            if imported["status"] in ("completed", "partially_completed", "failed"):
                break
            time.sleep(2)
        if imported["status"] != "completed" or imported["created_rows"] != 3:
            raise RuntimeError("demo_import_not_completed_with_three_new_cases")
        rows = request("GET", f"/api/v1/batch-imports/{import_id}/rows?limit=10")["items"]
        if len(rows) != 3 or any(row["status"] != "created" for row in rows):
            raise RuntimeError("unexpected_demo_import_receipts")
        cases = dict(
            zip(
                ("priority", "ordinary", "incomplete"),
                (row["case_id"] for row in sorted(rows, key=lambda row: row["row_number"])),
                strict=True,
            )
        )
        receipt["cases"] = cases
        save()
        attach = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                ownership["container"],
                "python",
                "-B",
                "/workspace/scripts/prepare_uploaded_demo.py",
                "--attach-inside",
            ],
            input=json.dumps(cases),
            capture_output=True,
            text=True,
            timeout=90,
        )
        if attach.returncode:
            raise RuntimeError("synthetic_evidence_attachment_failed")
        receipt["evidence"] = json.loads(attach.stdout)["attached"]
        save()
        if "batch_id" not in receipt:
            batch = request(
                "POST",
                f"/api/v1/batch-imports/{import_id}/assessments",
                json={
                    "start_assessment": True,
                    "import_validation_sha256": imported["validation_sha256"],
                    "policy": "Balanced",
                },
                headers={"Idempotency-Key": "synthetic-demo-assess-v1-" + active["id"]},
            )
            receipt["batch_id"] = batch["batch_id"]
            save()
        batch_id = receipt["batch_id"]
        for _ in range(45):
            batch = request("GET", f"/api/v1/batch-assessments/{batch_id}")
            if batch["status"] in ("completed", "partially_completed", "failed", "stopped"):
                break
            time.sleep(3)
        print(
            json.dumps(
                {
                    "cases": cases,
                    "import_id": import_id,
                    "batch_id": batch_id,
                    "assessment_status": batch["status"],
                    "completed": batch["succeeded"],
                    "failed": batch["failed_manual_review"],
                }
            )
        )


if __name__ == "__main__":
    try:
        attach_inside() if "--attach-inside" in sys.argv else main()
    except Exception as exc:
        print(
            "Synthetic demo setup stopped:",
            str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__,
        )
        raise SystemExit(1) from None
