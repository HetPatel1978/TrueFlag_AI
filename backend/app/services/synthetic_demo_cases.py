"""Explicitly generated synthetic cases and source-bound uploaded evidence."""

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.models import Alert, CSVImport, CSVImportRow
from app.models.evidence import CaseEvidenceState, EvidenceCaseBinding, EvidenceSourceAccess
from app.schemas.alerts import FEATURE_CONTRACT_VERSION, AlertFeatures, AlertIngestionInput
from app.services.evidence import (
    EvidenceBlocked,
    EvidenceConflict,
    EvidenceNotFound,
    EvidenceService,
    actor_lock,
    atomic,
    audit,
    case_lock,
    source_lock,
    verify_release,
)
from app.services.ingestion import fingerprints
from app.services.synthetic_evidence import generate_scenario

DEMO_NAMESPACE = uuid5(NAMESPACE_URL, "trueflag.uploaded-synthetic-demo.v1")
DEMO_AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)
SPECS = {
    "priority": (48, "g1_demo_priority"),
    "ordinary": (1701, "g1_ordinary"),
    "incomplete": (1701, "partial"),
}


def demo_bundle(key):
    if type(key) is not str or key not in SPECS:
        raise EvidenceBlocked("unknown_demo_scenario")
    seed, profile = SPECS[key]
    return generate_scenario(uuid5(DEMO_NAMESPACE, key), seed, profile, as_of=DEMO_AS_OF)


def demo_source_id(bundle):
    return "synthetic-upload-demo-v1-" + bundle.scenario_id.hex


class SyntheticDemoEvidenceService(EvidenceService):
    """Bind only exact, owned demo imports; arbitrary existing cases remain unsupported."""

    @atomic
    def attach_uploaded_case(self, session, actor_id, case_id, scenario):
        actor_lock(session, actor_id, write=True)
        case = case_lock(session, actor_id, case_id)
        bundle = demo_bundle(scenario)
        alert = session.get(Alert, case.alert_id)
        imported = session.scalar(
            select(CSVImportRow.case_id)
            .join(CSVImport, CSVImport.id == CSVImportRow.import_id)
            .where(
                CSVImportRow.case_id == case_id,
                CSVImportRow.alert_id == case.alert_id,
                CSVImportRow.status == "created",
                CSVImport.actor_id == actor_id,
                CSVImport.status.in_(["completed", "partially_completed"]),
            )
        )
        if imported is None:
            raise EvidenceNotFound("demo_import_not_found")
        if (
            alert is None
            or alert.data_classification != "synthetic"
            or alert.feature_contract_version != FEATURE_CONTRACT_VERSION
            or alert.source_id != demo_source_id(bundle)
            or alert.features != bundle.declarations
        ):
            raise EvidenceConflict("demo_source_mismatch")
        body = AlertIngestionInput(
            source_id=alert.source_id,
            data_classification="synthetic",
            feature_contract_version=FEATURE_CONTRACT_VERSION,
            features=AlertFeatures.model_validate(bundle.declarations),
        )
        if fingerprints(body)[0] != alert.input_sha256:
            raise EvidenceConflict("demo_input_fingerprint_mismatch")

        # These operations share this exact transaction, including the source and audit writes.
        source_id = self.register_source.__wrapped__(self, session, actor_id, bundle.scenario_id)
        release_id = self.admit_version.__wrapped__(self, session, actor_id, source_id, bundle)
        release = self._release(session, release_id)
        source_lock(session, actor_id, source_id)
        verify_release(session, release)
        if release.reconciliation["status"] != "declared_synthetic_inputs":
            raise EvidenceBlocked("incomplete_feature_support")
        previous = session.get(EvidenceCaseBinding, case_id)
        if previous is not None:
            access = session.get(EvidenceSourceAccess, (case_id, source_id))
            if previous.source_id != source_id or previous.input_sha256 != alert.input_sha256:
                raise EvidenceConflict("demo_case_binding_conflict")
            if access is None or not access.active:
                raise EvidenceNotFound("evidence_not_found")
            # Never silently restore revoked individual links on a repeat request.
            return {"case_id": str(case_id), "scenario": scenario, "already_linked": True}
        if (
            session.scalar(
                select(EvidenceCaseBinding.case_id).where(
                    EvidenceCaseBinding.source_id == source_id
                )
            )
            or session.get(CaseEvidenceState, case_id) is not None
        ):
            raise EvidenceConflict("demo_case_binding_conflict")
        session.add(
            EvidenceCaseBinding(
                case_id=case_id,
                source_id=source_id,
                source_version_id=release_id,
                actor_id=actor_id,
                input_sha256=alert.input_sha256,
            )
        )
        session.add(CaseEvidenceState(case_id=case_id, evidence_revision=0, access_revision=1))
        session.flush()
        session.add(
            EvidenceSourceAccess(
                case_id=case_id, source_id=source_id, active=True, changed_by=actor_id
            )
        )
        session.flush()
        audit(
            session,
            actor_id,
            "demo_case_bound",
            case_id,
            source_id=str(source_id),
            source_version_id=str(release_id),
            source_sha256=release.content_sha256,
            origin="generated_synthetic",
            feature_values_are_transaction_derived=False,
        )
        self._link(session, actor_id, case_id, release)
        return {"case_id": str(case_id), "scenario": scenario, "already_linked": False}
