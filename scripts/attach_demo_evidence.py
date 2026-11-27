"""Bind the uploaded SYN- demo cases to their generated synthetic evidence (catalog v2).

Run after an administrator has imported docs/demo/trueflag_demo_cases.csv through
Admin > CSV imports. For each imported SYN- case owned by that administrator, this calls
SyntheticDemoEvidenceService.attach_uploaded_case, which re-checks that the uploaded inputs
equal the catalog's declarations (exact fingerprint) before admitting and linking the
evidence in one audited transaction. Repeat runs report "already_linked"; nothing else in
the case changes (no assessment, decision or AI request).

  .venv-windows/Scripts/python.exe -B scripts/attach_demo_evidence.py --username <admin>

Targets the native Windows runtime database by default (runtime/windows/current.json), or
--state <state.json> for an isolated database such as the dry run.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]


def attach(database_url, username):
    from app.core.database import make_engine
    from app.models import Alert, CSVImport, CSVImportRow, User
    from app.services import demo_case_catalog as catalog
    from app.services.synthetic_demo_cases import SyntheticDemoEvidenceService
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    engine = make_engine(database_url)
    try:
        with Session(engine) as session:
            actor = session.scalar(
                select(User.id).where(
                    User.username == username, User.active.is_(True), User.role == "admin"
                )
            )
            if actor is None:
                raise SystemExit("active administrator not found")
            rows = session.execute(
                select(Alert.source_id, CSVImportRow.case_id)
                .join(CSVImportRow, CSVImportRow.alert_id == Alert.id)
                .join(CSVImport, CSVImport.id == CSVImportRow.import_id)
                .where(
                    Alert.source_id.in_(list(catalog.CASES)),
                    CSVImportRow.status == "created",
                    CSVImport.actor_id == actor,
                    CSVImport.status.in_(["completed", "partially_completed"]),
                )
            ).all()
        found = {source: case for source, case in rows}
        service = SyntheticDemoEvidenceService(engine)
        results = []
        for case_id in catalog.CASES:
            if case_id not in found:
                results.append({"source_id": case_id, "status": "not_imported"})
                continue
            outcome = service.attach_uploaded_case(actor, found[case_id], case_id)
            results.append(
                {
                    "source_id": case_id,
                    "case_id": outcome["case_id"],
                    "status": "already_linked" if outcome["already_linked"] else "attached",
                }
            )
        return results
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--username", required=True, help="the administrator who imported the CSV")
    parser.add_argument(
        "--state", help="state.json of an isolated runtime (default: native runtime)"
    )
    options = parser.parse_args()
    if options.state:
        state = json.loads(Path(options.state).read_text())
    else:
        import windows_runtime

        _, state = windows_runtime.current()
    for row in attach(state["database_url"], options.username):
        print(json.dumps(row))


if __name__ == "__main__":
    main()
