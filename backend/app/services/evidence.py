"""Internal, synthetic-only evidence boundary. No network, uploads or inference side effects."""

from datetime import datetime, timezone
from decimal import Decimal
from functools import wraps
from uuid import UUID, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Alert, AuditEvent, User
from app.models.evidence import (
    CaseEvidenceLink,
    CaseEvidenceState,
    EvidenceAccount,
    EvidenceCaseBinding,
    EvidenceCustomer,
    EvidenceIdentity,
    EvidenceRecordVersion,
    EvidenceRelationship,
    EvidenceSource,
    EvidenceSourceAccess,
    EvidenceSourceVersion,
    EvidenceTransaction,
)
from app.schemas.alerts import FEATURE_CONTRACT_VERSION, AlertFeatures, AlertIngestionInput
from app.schemas.evidence import SyntheticBundle
from app.services.assessments import _locked_case
from app.services.ingestion import digest, ingest_alert_in_transaction
from app.services.synthetic_evidence import (
    bundle_manifest,
    canonical_records,
    generate_scenario,
    reconciliation,
)

PAYLOADS = {
    "customer": EvidenceCustomer,
    "account": EvidenceAccount,
    "relationship": EvidenceRelationship,
    "transaction": EvidenceTransaction,
}
REFERENCES = {
    "customer_key": ("customer_id", "customer"),
    "account_key": ("account_id", "account"),
    "counterparty_key": ("counterparty_id", "account"),
    "reverses_key": ("reverses_id", "transaction"),
}
CONFIGURATION_FIELDS = {
    "scenario_id",
    "seed",
    "profile",
    "source_revision",
    "as_of",
    "generator_version",
    "config_version",
    "dictionary_sha256",
}


class EvidenceError(Exception):
    """Stable, value-free codes only at the service boundary."""


class EvidenceNotFound(EvidenceError):
    pass


class EvidenceConflict(EvidenceError):
    pass


class EvidenceBlocked(EvidenceError):
    pass


class EvidenceUnavailable(EvidenceError):
    pass


def atomic(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        try:
            with Session(self.engine, expire_on_commit=False) as session, session.begin():
                if session.bind.dialect.name != "postgresql":
                    raise EvidenceUnavailable("postgresql_required")
                session.execute(text("SET LOCAL lock_timeout='2s'"))
                session.execute(text("SET LOCAL statement_timeout='5s'"))
                session.execute(text("SET LOCAL idle_in_transaction_session_timeout='15s'"))
                return method(self, session, *args, **kwargs)
        except EvidenceError:
            raise
        except Exception:
            raise EvidenceUnavailable("evidence_operation_unavailable") from None

    return call


def audit(session, actor, action, resource, **details):
    session.add(
        AuditEvent(
            actor_id=actor,
            action="evidence." + action,
            resource_id=str(resource),
            details=details,
        )
    )


def actor_lock(session, actor, *, write):
    if type(actor) is not UUID:
        raise EvidenceNotFound("evidence_not_found")
    user = session.scalar(
        select(User).where(User.id == actor, User.active.is_(True)).with_for_update()
    )
    roles = ("admin",) if write else ("admin", "supervisor", "analyst")
    if user is None or user.role not in roles:
        raise EvidenceNotFound("evidence_not_found")


def source_lock(session, actor, source_id):
    if type(source_id) is not UUID:
        raise EvidenceNotFound("evidence_not_found")
    source = session.scalar(
        select(EvidenceSource)
        .where(EvidenceSource.id == source_id, EvidenceSource.owner_id == actor)
        .with_for_update()
    )
    if source is None:
        raise EvidenceNotFound("evidence_not_found")
    return source


def case_lock(session, actor, case_id):
    if type(case_id) is not UUID:
        raise EvidenceNotFound("evidence_not_found")
    try:
        return _locked_case(session, actor, case_id)
    except Exception:
        raise EvidenceNotFound("evidence_not_found") from None


def checked_bundle(bundle):
    # Frozen Pydantic instances can still contain mutable dictionaries. Revalidate and regenerate.
    if not isinstance(bundle, SyntheticBundle):
        raise EvidenceBlocked("invalid_synthetic_bundle")
    bundle = SyntheticBundle.model_validate_json(bundle.model_dump_json())
    regenerated = generate_scenario(
        bundle.scenario_id,
        bundle.seed,
        bundle.profile,
        source_revision=bundle.source_revision,
        as_of=bundle.as_of,
    )
    if bundle_manifest(bundle) != bundle_manifest(regenerated):
        raise EvidenceBlocked("unsupported_synthetic_content")
    return bundle


def payload_values(payload, identities):
    values = {k: v for k, v in payload.items() if k not in {"key", "kind"}}
    for key in ("event_at", "observed_at", "opened_at"):
        if values.get(key) is not None:
            values[key] = datetime.fromisoformat(values[key])
    for key, (column, kind) in REFERENCES.items():
        if key not in values:
            continue
        reference = values.pop(key)
        if reference is None:
            values[column] = None
        elif reference not in identities or identities[reference].kind != kind:
            raise EvidenceBlocked("invalid_source_reference")
        else:
            values[column] = identities[reference].id
    return values


def verify_release(session, release):
    """Independent typed-row reconstruction; compare against the frozen generator manifest."""
    config = release.configuration
    bundle = generate_scenario(
        UUID(config["scenario_id"]),
        config["seed"],
        config["profile"],
        source_revision=release.version,
        as_of=datetime.fromisoformat(config["as_of"]),
    )
    manifest = bundle_manifest(bundle)
    if (
        release.manifest != manifest
        or release.configuration != bundle.model_dump(mode="json", include=CONFIGURATION_FIELDS)
        or release.content_sha256 != digest(manifest)
        or release.declarations != bundle.declarations
        or release.reconciliation != reconciliation(bundle)
        or release.coverage != bundle.coverage
        or release.as_of != bundle.as_of
        or release.window_start != bundle.window_start
        or session.get(EvidenceSource, release.source_id).scenario_id != bundle.scenario_id
    ):
        raise EvidenceUnavailable("evidence_integrity_failure")
    identities = {
        row.id: row
        for row in session.scalars(
            select(EvidenceIdentity).where(EvidenceIdentity.source_id == release.source_id)
        )
    }
    rows = session.scalars(
        select(EvidenceRecordVersion).where(EvidenceRecordVersion.source_version_id == release.id)
    ).all()
    expected = canonical_records(bundle)
    if len(rows) != len(expected):
        raise EvidenceUnavailable("evidence_integrity_failure")
    for row in rows:
        identity = identities[row.identity_id]
        payload = session.get(PAYLOADS[row.kind], row.id)
        reference = expected.get(identity.record_key)
        if (
            payload is None
            or reference is None
            or row.content_sha256 != digest(reference)
            or row.kind != reference["kind"]
        ):
            raise EvidenceUnavailable("evidence_integrity_failure")
        values = payload_values(reference, {i.record_key: i for i in identities.values()})
        for name, value in values.items():
            actual = getattr(payload, name)
            if name in ("amount", "annual_income") and value is not None:
                value = Decimal(value)
            if actual != value:
                raise EvidenceUnavailable("evidence_integrity_failure")
    return bundle, rows


class EvidenceService:
    """Local admin admission; authorized case readers see explicitly granted manifests only."""

    def __init__(self, engine):
        self.engine = engine

    @atomic
    def register_source(self, session, actor_id, scenario_id):
        actor_lock(session, actor_id, write=True)
        if type(scenario_id) is not UUID:
            raise EvidenceBlocked("invalid_scenario_identity")
        existing = session.scalar(
            select(EvidenceSource).where(
                EvidenceSource.owner_id == actor_id, EvidenceSource.scenario_id == scenario_id
            )
        )
        if existing is not None:
            return existing.id
        count = session.scalar(
            select(func.count())
            .select_from(EvidenceSource)
            .where(EvidenceSource.owner_id == actor_id)
        )
        if count >= 100:
            raise EvidenceBlocked("source_capacity_exceeded")
        source = EvidenceSource(
            id=uuid5(actor_id, str(scenario_id)), owner_id=actor_id, scenario_id=scenario_id
        )
        session.add(source)
        session.flush()
        audit(session, actor_id, "source_registered", source.id, classification="synthetic")
        return source.id

    @atomic
    def admit_version(self, session, actor_id, source_id, bundle):
        actor_lock(session, actor_id, write=True)
        source = source_lock(session, actor_id, source_id)
        bundle = checked_bundle(bundle)
        if source.scenario_id != bundle.scenario_id:
            raise EvidenceBlocked("scenario_source_mismatch")
        manifest = bundle_manifest(bundle)
        prior = session.scalar(
            select(EvidenceSourceVersion).where(
                EvidenceSourceVersion.source_id == source_id,
                EvidenceSourceVersion.version == bundle.source_revision,
            )
        )
        if prior:
            if prior.content_sha256 != digest(manifest):
                raise EvidenceConflict("source_version_conflict")
            verify_release(session, prior)
            return prior.id
        latest = (
            session.scalar(
                select(func.max(EvidenceSourceVersion.version)).where(
                    EvidenceSourceVersion.source_id == source_id
                )
            )
            or 0
        )
        if bundle.source_revision != latest + 1:
            raise EvidenceConflict("source_version_not_next")
        records = canonical_records(bundle)
        identities = {
            row.record_key: row
            for row in session.scalars(
                select(EvidenceIdentity).where(EvidenceIdentity.source_id == source_id)
            )
        }
        for key, payload in records.items():
            if key not in identities:
                identities[key] = EvidenceIdentity(
                    id=uuid5(source_id, key),
                    source_id=source_id,
                    record_key=key,
                    kind=payload["kind"],
                )
                session.add(identities[key])
            elif identities[key].kind != payload["kind"]:
                raise EvidenceConflict("record_kind_conflict")
        session.flush()
        release = EvidenceSourceVersion(
            id=uuid5(source_id, "release:" + str(bundle.source_revision)),
            source_id=source_id,
            version=bundle.source_revision,
            content_sha256=digest(manifest),
            manifest=manifest,
            configuration=bundle.model_dump(mode="json", include=CONFIGURATION_FIELDS),
            declarations=bundle.declarations,
            reconciliation=reconciliation(bundle),
            coverage=bundle.coverage,
            window_start=bundle.window_start,
            as_of=bundle.as_of,
            admitted_by=actor_id,
        )
        session.add(release)
        session.flush()
        for key, payload in records.items():
            identity = identities[key]
            previous = session.scalar(
                select(EvidenceRecordVersion)
                .where(EvidenceRecordVersion.identity_id == identity.id)
                .order_by(EvidenceRecordVersion.version.desc())
                .limit(1)
            )
            row = EvidenceRecordVersion(
                id=uuid5(identity.id, "version:" + str(previous.version + 1 if previous else 1)),
                source_id=source_id,
                source_version_id=release.id,
                identity_id=identity.id,
                kind=identity.kind,
                version=previous.version + 1 if previous else 1,
                content_sha256=digest(payload),
                supersedes_id=previous.id if previous else None,
            )
            session.add(row)
            session.flush()
            session.add(
                PAYLOADS[identity.kind](
                    record_version_id=row.id,
                    source_id=source_id,
                    kind=identity.kind,
                    **payload_values(payload, identities),
                )
            )
        session.flush()
        verify_release(session, release)
        audit(
            session,
            actor_id,
            "source_version_admitted",
            release.id,
            source_id=str(source_id),
            sha256=release.content_sha256,
            version=release.version,
            records=len(records),
        )
        return release.id

    def _release(self, session, release_id):
        if type(release_id) is not UUID:
            raise EvidenceNotFound("evidence_not_found")
        release = session.get(EvidenceSourceVersion, release_id)
        if release is None:
            raise EvidenceNotFound("evidence_not_found")
        return release

    def _binding(self, session, actor, case_id, source_id):
        source_lock(session, actor, source_id)
        case_lock(session, actor, case_id)
        binding = session.get(EvidenceCaseBinding, case_id)
        if binding is None or binding.source_id != source_id:
            raise EvidenceNotFound("evidence_not_found")
        return binding

    def _link(self, session, actor, case_id, release):
        access = session.get(EvidenceSourceAccess, (case_id, release.source_id))
        if access is None or not access.active:
            raise EvidenceNotFound("evidence_not_found")
        _, rows = verify_release(session, release)
        changed = 0
        for row in rows:
            link = session.get(CaseEvidenceLink, (case_id, row.id))
            if link is None:
                session.add(
                    CaseEvidenceLink(
                        case_id=case_id,
                        record_version_id=row.id,
                        source_id=row.source_id,
                        kind=row.kind,
                        changed_by=actor,
                    )
                )
                changed += 1
            elif not link.active:
                link.active = True
                link.changed_by = actor
                link.changed_at = datetime.now(timezone.utc)
                changed += 1
        if changed:
            state = session.get(CaseEvidenceState, case_id)
            state.evidence_revision += 1
            state.access_revision += 1
            audit(
                session,
                actor,
                "versions_linked",
                case_id,
                release_id=str(release.id),
                records=changed,
                evidence_revision=state.evidence_revision,
                access_revision=state.access_revision,
            )

    @atomic
    def create_case(self, session, actor_id, release_id):
        actor_lock(session, actor_id, write=True)
        release = self._release(session, release_id)
        source_lock(session, actor_id, release.source_id)
        bundle, _ = verify_release(session, release)
        if release.reconciliation["status"] != "declared_synthetic_inputs":
            raise EvidenceBlocked("incomplete_feature_support")
        binding = session.scalar(
            select(EvidenceCaseBinding).where(EvidenceCaseBinding.source_id == release.source_id)
        )
        if binding:
            case = case_lock(session, actor_id, binding.case_id)
            alert = session.get(Alert, case.alert_id)
            if alert.features != bundle.declarations:
                raise EvidenceConflict("bound_case_input_conflict")
            return binding.case_id
        body = AlertIngestionInput(
            source_id="synthetic-evidence-v1-" + release.source_id.hex,
            data_classification="synthetic",
            feature_contract_version=FEATURE_CONTRACT_VERSION,
            features=AlertFeatures.model_validate(bundle.declarations),
        )
        receipt, created = ingest_alert_in_transaction(session, body, body.source_id, actor_id)
        if not created:
            raise EvidenceConflict("existing_case_binding_forbidden")
        case_id = UUID(receipt["case_id"])
        alert = session.get(Alert, UUID(receipt["alert_id"]))
        session.add(
            EvidenceCaseBinding(
                case_id=case_id,
                source_id=release.source_id,
                source_version_id=release.id,
                actor_id=actor_id,
                input_sha256=alert.input_sha256,
            )
        )
        session.add(CaseEvidenceState(case_id=case_id, evidence_revision=0, access_revision=1))
        session.flush()
        session.add(
            EvidenceSourceAccess(
                case_id=case_id,
                source_id=release.source_id,
                active=True,
                changed_by=actor_id,
            )
        )
        session.flush()
        audit(
            session,
            actor_id,
            "case_bound",
            case_id,
            source_id=str(release.source_id),
            source_version_id=str(release.id),
            input_sha256=alert.input_sha256,
        )
        self._link(session, actor_id, case_id, release)
        return case_id

    @atomic
    def link_version(self, session, actor_id, case_id, release_id):
        actor_lock(session, actor_id, write=True)
        release = self._release(session, release_id)
        self._binding(session, actor_id, case_id, release.source_id)
        self._link(session, actor_id, case_id, release)

    @atomic
    def set_source_access(self, session, actor_id, case_id, source_id, active):
        actor_lock(session, actor_id, write=True)
        if type(active) is not bool:
            raise EvidenceBlocked("invalid_access_flag")
        self._binding(session, actor_id, case_id, source_id)
        access = session.get(EvidenceSourceAccess, (case_id, source_id))
        if access.active != active:
            access.active = active
            access.changed_by = actor_id
            access.changed_at = datetime.now(timezone.utc)
            state = session.get(CaseEvidenceState, case_id)
            state.access_revision += 1
            audit(
                session,
                actor_id,
                "source_granted" if active else "source_revoked",
                case_id,
                source_id=str(source_id),
                access_revision=state.access_revision,
            )

    @atomic
    def revoke_links(self, session, actor_id, case_id, source_id, record_ids):
        actor_lock(session, actor_id, write=True)
        if (
            type(record_ids) is not tuple
            or not 1 <= len(record_ids) <= 200
            or any(type(i) is not UUID for i in record_ids)
            or len(set(record_ids)) != len(record_ids)
        ):
            raise EvidenceBlocked("invalid_link_selection")
        self._binding(session, actor_id, case_id, source_id)
        changed = 0
        for record_id in record_ids:
            link = session.get(CaseEvidenceLink, (case_id, record_id))
            if link is None or link.source_id != source_id:
                raise EvidenceNotFound("evidence_not_found")
            if link.active:
                link.active = False
                link.changed_by = actor_id
                link.changed_at = datetime.now(timezone.utc)
                changed += 1
        if changed:
            state = session.get(CaseEvidenceState, case_id)
            state.evidence_revision += 1
            state.access_revision += 1
            audit(
                session,
                actor_id,
                "links_revoked",
                case_id,
                records=changed,
                evidence_revision=state.evidence_revision,
                access_revision=state.access_revision,
            )

    @atomic
    def manifest(self, session, actor_id, case_id):
        actor_lock(session, actor_id, write=False)
        case = case_lock(session, actor_id, case_id)
        alert = session.get(Alert, case.alert_id)
        binding = session.get(EvidenceCaseBinding, case_id)
        state = session.get(CaseEvidenceState, case_id)
        result = {
            "case_id": str(case_id),
            "evidence_revision": state.evidence_revision if state else 0,
            "access_revision": state.access_revision if state else 0,
            "coverage": "unavailable",
            "sources": [],
            "records": [],
        }
        # Grant predicate is applied before projecting or counting record metadata.
        rows = session.scalars(
            select(EvidenceRecordVersion)
            .join(CaseEvidenceLink, CaseEvidenceLink.record_version_id == EvidenceRecordVersion.id)
            .join(
                EvidenceSourceAccess,
                (EvidenceSourceAccess.case_id == CaseEvidenceLink.case_id)
                & (EvidenceSourceAccess.source_id == CaseEvidenceLink.source_id),
            )
            .where(
                CaseEvidenceLink.case_id == case_id,
                CaseEvidenceLink.active.is_(True),
                EvidenceSourceAccess.active.is_(True),
            )
            .order_by(EvidenceRecordVersion.id)
            .limit(1001)
        ).all()
        if len(rows) > 1000:
            raise EvidenceBlocked("manifest_capacity_exceeded")
        linked = {r.id for r in rows}
        releases = sorted({r.source_version_id for r in rows}, key=str)
        latest = None
        latest_complete = False
        for release_id in releases:
            release = self._release(session, release_id)
            bundle, members = verify_release(session, release)
            complete = {r.id for r in members}.issubset(linked)
            visible_identity_ids = {r.identity_id for r in members if r.id in linked}
            visible_keys = set(
                session.scalars(
                    select(EvidenceIdentity.record_key).where(
                        EvidenceIdentity.id.in_(visible_identity_ids)
                    )
                )
            )
            visible_observations = [r for r in bundle.records if r.key in visible_keys]
            if latest is None or release.version > latest.version:
                latest, latest_complete = release, complete
            result["sources"].append(
                {
                    "source_id": str(release.source_id),
                    "source_version_id": str(release.id),
                    "version": release.version,
                    "sha256": release.content_sha256,
                    "coverage": release.coverage,
                    "membership_complete": complete,
                    "window_start": bundle.window_start.isoformat(),
                    "as_of": bundle.as_of.isoformat(),
                    "reconciliation": release.reconciliation,
                    "synthetic": True,
                    "is_case_creation_release": binding is not None
                    and binding.source_version_id == release.id,
                    "case_input_reconciliation": "matches_declared_inputs"
                    if release.declarations == alert.features
                    else "differs_from_immutable_case_input",
                    "quality_flags": {
                        "unknown_transaction_timezone": any(
                            r.kind == "transaction" and r.event_at is None
                            for r in visible_observations
                        ),
                        "multiple_transaction_currencies": len(
                            {r.currency for r in visible_observations if r.kind == "transaction"}
                        )
                        > 1,
                        "multiple_kyc_observations": len(
                            [r for r in visible_observations if r.kind == "customer"]
                        )
                        > 1,
                        "declared_features_are_not_ledger_derivations": True,
                    },
                }
            )
        if latest:
            result["coverage"] = latest.coverage if latest_complete else "partial"
        superseded = {r.supersedes_id for r in rows if r.supersedes_id is not None}
        for row in rows:
            result["records"].append(
                {
                    "record_version_id": str(row.id),
                    "identity_id": str(row.identity_id),
                    "source_version_id": str(row.source_version_id),
                    "kind": row.kind,
                    "version": row.version,
                    "sha256": row.content_sha256,
                    "supersedes_id": str(row.supersedes_id) if row.supersedes_id else None,
                    "superseded_in_manifest": row.id in superseded,
                }
            )
        audit(
            session,
            actor_id,
            "manifest_read",
            case_id,
            records=len(rows),
            evidence_revision=result["evidence_revision"],
            access_revision=result["access_revision"],
        )
        return result
