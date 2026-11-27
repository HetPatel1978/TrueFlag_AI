"""Demo case catalog v2: reproducible generated evidence, CSV/declaration agreement, binding."""

import csv
import io
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.orm import Session
from test_csv_imports import base_upload as base_upload_fixture
from test_csv_imports import imports as imports_fixture

from app.schemas.alerts import AlertFeatures
from app.schemas.csv_uploads import COLUMNS
from app.services import demo_case_catalog as catalog
from app.services.evidence import EvidenceConflict
from app.services.synthetic_evidence import (
    bundle_manifest,
    generate_scenario,
    reconciliation,
)

base_upload = base_upload_fixture
imports = imports_fixture
DEMO_CSV = Path(__file__).resolve().parents[2] / "docs/demo/trueflag_demo_cases.csv"


@pytest.mark.parametrize("case_id", list(catalog.CASES))
def test_every_case_regenerates_exactly_through_the_generator(case_id):
    bundle = catalog.bundle(case_id)
    # Evidence admission regenerates every bundle; the catalog must survive that unchanged.
    again = generate_scenario(
        bundle.scenario_id,
        bundle.seed,
        bundle.profile,
        source_revision=bundle.source_revision,
        as_of=bundle.as_of,
    )
    assert bundle_manifest(again) == bundle_manifest(bundle)
    assert reconciliation(bundle)["status"] == "declared_synthetic_inputs"
    assert reconciliation(bundle)["transaction_derived_fields"] == []
    assert AlertFeatures.model_validate(bundle.declarations).model_dump() == bundle.declarations
    assert case_id.startswith("SYN-")


def test_catalog_profile_leaves_other_scenarios_on_the_default_generator():
    other = UUID("0665ed81-3b5c-4778-821d-9f45b221abec")
    bundle = generate_scenario(other, 17, catalog.CATALOG_PROFILE)
    assert catalog.bundle_for_scenario(other) is None
    assert sum(r.kind == "transaction" for r in bundle.records) == 12
    # A catalog scenario with a different seed or time is not the catalog bundle.
    case = catalog.scenario_id("SYN-01-STRUCTURING")
    assert bundle_manifest(generate_scenario(case, 1, catalog.CATALOG_PROFILE)) != bundle_manifest(
        catalog.bundle("SYN-01-STRUCTURING")
    )


def test_case_stories_are_visible_in_the_generated_evidence():
    structuring = catalog.bundle("SYN-01-STRUCTURING")
    cash = [
        r.amount
        for r in structuring.records
        if r.kind == "transaction" and r.channel == "cashlike" and r.direction == "credit"
    ]
    assert len(cash) == 10 and all(Decimal("9000") < a < Decimal("10000") for a in cash)
    funnel = catalog.bundle("SYN-03-FUNNEL")
    senders = {
        r.counterparty_key
        for r in funnel.records
        if r.kind == "transaction" and r.direction == "credit"
    }
    assert len(senders) == 25
    dormant = catalog.bundle("SYN-07-DORMANT")
    first = min(r.event_at for r in dormant.records if r.kind == "transaction")
    assert (dormant.as_of - first).days <= 14
    partial = catalog.bundle("SYN-06-PARTIAL")
    assert partial.coverage == "partial" and partial.declarations["income"] is None
    income = catalog.bundle("SYN-08-INCOME")
    spend = sum(r.amount for r in income.records if r.kind == "transaction" and r.channel == "card")
    assert spend > 3 * Decimal(income.declarations["income"])


@pytest.mark.skipif(not DEMO_CSV.exists(), reason="docs CSV is not part of staged copies")
def test_committed_csv_matches_the_catalog_in_template_order():
    rows = list(csv.DictReader(io.StringIO(DEMO_CSV.read_text(encoding="utf-8"))))
    assert list(rows[0]) == list(COLUMNS)
    assert [r["source_id"] for r in rows] == list(catalog.CASES)
    for row in rows:
        expected = catalog.csv_row(row["source_id"])
        assert row == {k: "" if expected[k] is None else str(expected[k]) for k in COLUMNS}


@pytest.mark.postgres
def test_uploaded_catalog_case_binds_and_rejects_altered_inputs(imports):
    from test_synthetic_demo_cases import import_scenario

    from app.services.synthetic_demo_cases import SyntheticDemoEvidenceService

    env = imports
    bundle, case_id, _ = import_scenario(env, "SYN-04-SAVER")
    service = SyntheticDemoEvidenceService(env["engine"])
    with pytest.raises(EvidenceConflict):
        service.attach_uploaded_case(env["actor_id"], case_id, "SYN-01-STRUCTURING")
    result = service.attach_uploaded_case(env["actor_id"], case_id, "SYN-04-SAVER")
    assert result == {"case_id": str(case_id), "scenario": "SYN-04-SAVER", "already_linked": False}
    with Session(env["engine"]) as session:
        from app.models.evidence import EvidenceCaseBinding

        assert session.get(EvidenceCaseBinding, case_id) is not None
