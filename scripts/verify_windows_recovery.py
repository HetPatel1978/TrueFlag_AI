"""One synthetic RF job: crash ONLY the owned native supervisor, then recover its lease."""

import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes
from uuid import uuid4

import httpx
from windows_runtime import ROOT, clean_env, connection, current


def main():
    directory, state = current()
    with connection(state) as c:
        before = c.execute("SELECT pg_postmaster_start_time()").fetchone()[0]
    sys.path.insert(0, clean_env(state)["PYTHONPATH"])
    from app.schemas.alerts import FEATURE_CONTRACT_VERSION
    from app.services.connected_scenarios import scenario_bundle

    features = scenario_bundle("missing_income", seed=29415).declarations
    logins = json.loads((directory / "login.json").read_text())
    with httpx.Client(
        base_url=f"http://127.0.0.1:{state['api_port']}", timeout=10, trust_env=False
    ) as client:
        auth = client.post(
            "/api/v1/auth/token",
            json={"username": "windowsadmin", "password": logins["windowsadmin"]["password"]},
        )
        assert auth.status_code == 200
        client.headers["Authorization"] = "Bearer " + auth.json()["access_token"]
        ident = "native-recovery-" + uuid4().hex
        ingested = client.post(
            "/api/v1/alerts",
            headers={"Idempotency-Key": ident},
            json={
                "source_id": ident,
                "data_classification": "synthetic",
                "feature_contract_version": FEATURE_CONTRACT_VERSION,
                "features": features,
            },
        )
        assert ingested.status_code == 201
        case = ingested.json()["case_id"]
        body = {"expected_version": 1, "run_id": str(uuid4()), "policy": "Coverage"}
        accepted = client.post(
            f"/api/v1/cases/{case}/assessments", headers={"Idempotency-Key": ident}, json=body
        )
        assert accepted.status_code == 202
        job_url = accepted.headers["location"]
        deadline = time.monotonic() + 15
        while True:
            value = client.get(job_url).json()
            if value["status"] == "running":
                break
            assert value["status"] == "pending" and time.monotonic() < deadline
            time.sleep(0.05)
        # Hold a handle and verify its creation time, so PID reuse cannot target another app.
        record = json.loads((directory / "supervisor.json").read_text())
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x1001, False, record["pid"])
        assert handle
        try:
            values = [wintypes.FILETIME() for _ in range(4)]
            assert api.GetProcessTimes(handle, *[ctypes.byref(v) for v in values])
            assert ((values[0].dwHighDateTime << 32) | values[0].dwLowDateTime) == record[
                "creation"
            ]
            assert api.TerminateProcess(handle, 1)
        finally:
            api.CloseHandle(handle)
        time.sleep(1)
        with (directory / ("recovery-start-" + uuid4().hex + ".log")).open("ab") as log:
            restarted = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-File",
                    str(ROOT / "scripts/start_trueflag_windows.ps1"),
                    "-Action",
                    "Start",
                ],
                stdout=log,
                stderr=log,
                timeout=65,
            )
        assert restarted.returncode == 0
        deadline = time.monotonic() + 90
        while True:
            result = client.get(job_url)
            assert result.status_code == 200
            value = result.json()
            if value["status"] in ("succeeded", "failed"):
                break
            assert time.monotonic() < deadline
            time.sleep(1)
        assert value["status"] == "succeeded" and value["attempts"] >= 2
        repeated = client.post(
            f"/api/v1/cases/{case}/assessments", headers={"Idempotency-Key": ident}, json=body
        )
        assert repeated.status_code == 202 and repeated.json()["job_id"] == value["job_id"]
        history = client.get(f"/api/v1/cases/{case}/assessments").json()
        assert history["total"] == 1
        case_value = client.get(f"/api/v1/cases/{case}").json()
        assert case_value["status"] == "open" and case_value["disposition"] is None
        detail = client.get(f"/api/v1/cases/{case}/assessments/{value['assessment_id']}").json()
        assert detail["explanation"]["status"] == "verified"
        with connection(state) as c:
            after = c.execute("SELECT pg_postmaster_start_time()").fetchone()[0]
        assert before == after
        report = {
            "running_job_interrupted": True,
            "lease_recovered": True,
            "attempts": value["attempts"],
            "completed_assessments": 1,
            "idempotent_retry": True,
            "postgres_not_restarted": True,
            "case_remains_open": True,
            "shap_verified": True,
            "live_provider_requests": 0,
        }
        (directory / ("recovery-" + uuid4().hex + ".json")).write_text(json.dumps(report, indent=2))
        print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import traceback

        print(
            json.dumps(
                {
                    "status": "failed",
                    "type": type(error).__name__,
                    "lines": [
                        f.lineno
                        for f in traceback.extract_tb(error.__traceback__)
                        if f.filename == __file__
                    ],
                    "live_provider_requests": 0,
                }
            )
        )
        raise SystemExit(1) from None
