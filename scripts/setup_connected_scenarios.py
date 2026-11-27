"""Preview by default; apply only to a protected G1 rehearsal target. No .env loading.

Run from the repository virtualenv. Admission only enqueues assessments; --process
explicitly runs the existing Linux worker and verifies stored results/analytics.
No external providers, migrations, role changes, deletion or overwrite.
"""

import argparse
import json
import secrets
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path("/workspace") if sys.platform == "linux" else Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]


def inside(args):
    import rehearse_database_recovery as r
    from app.core.config import Settings
    from app.core.database import make_engine
    from app.services.connected_scenarios import ConnectedScenarioService
    from app.workers.assessment_worker import AssessmentWorker

    state, url, control = r.inside_connection()
    control.dispose()
    engine = make_engine(url.set(database=state["database"]).render_as_string(hide_password=False))
    # Never consult changed .env values or provider credentials.
    settings = Settings(
        _env_file=None,
        database_url=engine.url.render_as_string(hide_password=False),
        jwt_secret=secrets.token_urlsafe(48),
    )
    service = ConnectedScenarioService(
        engine,
        settings,
        development=True,
        expected_cluster=state["isolated_system_identifier"],
        forbidden_cluster=state["source"]["system_identifier"],
        expected_database=state["database"],
    )
    actor = args.actor
    service.gate(actor)
    receipt = service.apply(actor, args.scenario, args.seed)
    if args.process:
        worker_file = Path("/recovery/scenario-worker-token")
        if not worker_file.exists():
            worker_file.write_text(secrets.token_hex(32), encoding="ascii")
        token = worker_file.read_text(encoding="ascii")
        service.ensure_worker(actor, token)
        worker = AssessmentWorker(service.queue, token)
        # One renewable, execution-bounded worker step fits the host's 240-second
        # command budget. Do not drain up to 32 individual 120-second jobs here.
        job = service.queue.get(
            actor_id=actor,
            case_id=UUID(receipt["case_id"]),
            job_id=UUID(receipt["job"]["job_id"]),
        )
        if job["status"] not in {"succeeded", "failed"}:
            worker.run_once()
        receipt["job"] = service.queue.get(
            actor_id=actor, case_id=UUID(receipt["case_id"]), job_id=UUID(receipt["job"]["job_id"])
        )
        receipt["observed_analytics"] = service.verify_activity(
            actor, args.scenario, UUID(receipt["case_id"]), args.seed
        )
    # Feature declarations are synthetic, but keep full receipts in the protected directory.
    r.save(Path("/recovery") / ("scenario-" + args.scenario + ".json"), receipt)
    engine.dispose()
    print(
        json.dumps(
            {
                "scenario": args.scenario,
                "case_id": receipt["case_id"],
                "job_status": receipt["job"]["status"],
                "synthetic": True,
            }
        )
    )


def main():
    from app.services.connected_scenarios import CATALOG, DEFAULT_SEED, preview

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--process", action="store_true")
    parser.add_argument("--scenario", choices=[s.key for s in CATALOG])
    parser.add_argument("--actor", type=UUID)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    if not args.apply:
        if args.process or args.actor or args.inside:
            parser.error("Explicit --apply is required")
        rows = preview(args.seed)
        print(
            json.dumps(
                [r for r in rows if not args.scenario or r["key"] == args.scenario], indent=2
            )
        )
        return 0
    if not args.scenario or not args.actor:
        parser.error("--apply requires --scenario and --actor")
    if args.inside:
        inside(args)
        return 0
    import rehearse_database_recovery as r

    marker = r.load(ROOT / "runtime/g1/current.json")
    directory = (ROOT / marker["directory"]).resolve(strict=True)
    if not directory.is_relative_to((ROOT / "runtime/g1").resolve()):
        raise ValueError("isolated_development_required")
    state = r.load(directory / "state.json")
    command = r.linux_args(state, directory)[
        :-4
    ]  # verifies ownership, cluster image, network, volume
    command += [
        "python",
        "-B",
        "/workspace/scripts/setup_connected_scenarios.py",
        "--inside",
        "--apply",
        "--scenario",
        args.scenario,
        "--actor",
        str(args.actor),
        "--seed",
        str(args.seed),
    ]
    if args.process:
        command.append("--process")
    outcome = r.run(command, accept_failure=True, timeout=240)
    # Child prints fixed structured summaries; never relay raw errors/stacks.
    for line in outcome.stdout.decode().splitlines():
        if line.startswith("{"):
            message = json.loads(line)
            print(
                json.dumps(
                    {
                        k: message[k]
                        for k in ("scenario", "case_id", "job_status", "synthetic", "error_type")
                        if k in message
                    }
                )
            )
    return outcome.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Class only: no feature values, SQL, credentials or provider configuration.
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
