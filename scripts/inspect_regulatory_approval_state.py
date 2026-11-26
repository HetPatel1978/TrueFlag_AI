"""Read only approval counts from the verified isolated local app database."""

import json
from pathlib import Path

from app.core.database import make_engine
from app.models.references import ReferenceApproval, ReferenceDocument, ReferenceVersion
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session


def main():
    config = json.loads(Path("/local-config/config.json").read_text())
    engine = make_engine(config["database_url"])
    with engine.connect() as connection:
        identity = str(connection.scalar(text("SELECT system_identifier FROM pg_control_system()")))
        name = connection.scalar(text("SELECT current_database()"))
    if (
        identity != str(config["expected_cluster"])
        or identity == str(config["forbidden_cluster"])
        or name != config["database"]
    ):
        raise RuntimeError("isolated_database_required")
    with Session(engine) as session:
        approvals = session.scalar(
            select(func.count())
            .select_from(ReferenceApproval)
            .join(ReferenceVersion, ReferenceVersion.id == ReferenceApproval.version_id)
            .join(ReferenceDocument, ReferenceDocument.id == ReferenceVersion.document_id)
            .where(ReferenceDocument.origin == "official_curated")
        )
        print(
            json.dumps(
                {"isolated_database_verified": True, "official_version_approvals": approvals}
            )
        )
    engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Approval inventory unavailable; details withheld.")
        raise SystemExit(1) from None
