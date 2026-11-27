"""Versioned synthetic catalog and bounded setup over existing application services.

No HTTP routes, model implementation, arbitrary bundles, environment file or network.
"""

import csv
import hashlib
import hmac
import io
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.release import require_compatible
from app.models import Alert, Case
from app.models import AssessmentWorker as WorkerIdentity
from app.schemas.alerts import FEATURE_CONTRACT_VERSION, AlertFeatures
from app.schemas.evidence import DICTIONARY_SHA
from app.schemas.evidence_read import AnalyticsRequest, Window
from app.services.assessment_jobs import AssessmentJobService
from app.services.evidence import EvidenceBlocked, EvidenceService, actor_lock
from app.services.evidence_read import EvidenceReadService
from app.services.ingestion import digest
from app.services.snapshot_clock import SnapshotTime
from app.services.synthetic_evidence import bundle_manifest, canonical_records, generate_scenario

CATALOG_VERSION = "trueflag.connected-scenarios.v1"
AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)
DEFAULT_SEED = 1701
NAMESPACE = uuid5(NAMESPACE_URL, CATALOG_VERSION)


@dataclass(frozen=True)
class Scenario:
    key: str
    profile: str
    purpose: str
    revision: int = 1
    lifecycle: str = "none"


CATALOG = (
    Scenario("ordinary", "g1_ordinary", "Ordinary observed activity; no criminal label"),
    Scenario("velocity", "burst", "Twelve events in twelve hours"),
    Scenario(
        "related_transfers", "g1_related", "Repeated transfers to a declared co-owned account"
    ),
    Scenario(
        "concentration", "g1_concentration", "Ten large observations to one of two counterparties"
    ),
    Scenario(
        "flow_change", "g1_flow_change", "Earlier incoming versus recent outgoing observations"
    ),
    Scenario("high_kyc", "g1_high_kyc", "Declared KYC 5; preserve Coverage protection"),
    Scenario("partial_customer", "g1_partial_customer", "Income and expected activity unavailable"),
    Scenario("missing_income", "missing_income", "Missing income is not observed zero"),
    Scenario("zero_income", "zero_income", "Explicit recorded zero income"),
    Scenario("corrections", "corrections", "Duplicate delivery and matched reversal"),
    Scenario("conflicting_kyc", "inconsistent_kyc", "Two contradictory income observations"),
    Scenario("incomplete_history", "partial", "Only four observed events; no whole-history claim"),
    Scenario(
        "source_revision", "normal", "Revised event; original alert features stay immutable", 2
    ),
    Scenario(
        "source_revocation",
        "normal",
        "Explicit post-setup revocation exercise",
        lifecycle="revocation",
    ),
    Scenario("multi_currency", "multi_currency", "Separate USD/CAD totals; no inferred FX"),
    Scenario("unknown_time", "timezone_unknown", "Unresolved timestamp excluded from timed totals"),
)


def scenario_bundle(key, seed=DEFAULT_SEED, revision=None):
    if type(key) is not str or type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise EvidenceBlocked("invalid_scenario_selection")
    spec = next((s for s in CATALOG if s.key == key), None)
    if spec is None or (
        revision is not None and (type(revision) is not int or not 1 <= revision <= spec.revision)
    ):
        raise EvidenceBlocked("invalid_scenario_selection")
    return generate_scenario(
        uuid5(NAMESPACE, f"{seed}:{key}"),
        seed,
        spec.profile,
        source_revision=spec.revision if revision is None else revision,
        as_of=AS_OF,
    )


def feature_origins(bundle):
    """All RF values are declarations; evidence observations are separate references."""
    path = (
        Path(__file__).resolve().parents[3] / "assets/local/baseline/contracts/data_dictionary.csv"
    )
    try:
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != DICTIONARY_SHA:
            raise ValueError()
        dictionary = {
            r["field"]: r for r in csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        }
        if not set(AlertFeatures.model_fields) <= dictionary.keys():
            raise ValueError()
    except (OSError, ValueError, KeyError):
        raise EvidenceBlocked("approved_feature_dictionary_unavailable") from None
    manifest = bundle_manifest(bundle)
    fields = {}
    for name in AlertFeatures.model_fields:
        unit = (
            "count"
            if name.startswith("nbr")
            else "months"
            if name == "tenureMonths"
            else "scenario_USD_not_verified_original_currency"
            if name
            in {
                "income",
                "avgTxnSize90d",
                "totalSpend90d",
                "totalMerchCred90d",
                "totalPaymentAmt90d",
                "overpaymentAmt90d",
                "totalRefundsToCust90d",
                "maxRevolveLine",
            }
            else "recorded_category"
            if name == "state"
            else "declared_score_or_indicator"
        )
        metadata = dictionary[name]
        fields[name] = {
            "origin": "unavailable"
            if bundle.declarations.get(name) is None
            else "declared_synthetic",
            "input_origin": "declared_synthetic",
            "value": bundle.declarations.get(name),
            "scenario_unit": unit,
            "unit": metadata["unit"],
            "definition": metadata["definition"],
            "definition_status": metadata["definition_status"],
            "dictionary_source": metadata["source_reference"],
            "uncertainty": metadata["uncertainty"],
            "dictionary_window": metadata["window"],
            "window": "90d"
            if "90d" in name
            else "1y"
            if "1y" in name
            else "unresolved_3y_vs_original_dictionary"
            if name == "nbrCollections3y"
            else "not_recorded",
            "source": "scenario_declarations",
            "declarations_sha256": manifest["declarations_sha256"],
            "transaction_derived": False,
        }
    return {
        "version": CATALOG_VERSION,
        "scenario_id": str(bundle.scenario_id),
        "source_revision": bundle.source_revision,
        "feature_contract": FEATURE_CONTRACT_VERSION,
        "dictionary_sha256": bundle.dictionary_sha256,
        "generator_version": bundle.generator_version,
        "source_sha256": digest(manifest),
        "fields": fields,
        "observed_records": manifest["record_sha256"],
        "limitations": [
            "RF declarations are not reconciled transaction aggregates",
            "Original currency/codebooks/collections window remain provisional",
            "No credit, income or KYC inferred from transactions",
        ],
    }


def expected_activity(bundle, *, currency="USD", start=None, end=None, net=False):
    """Independent fixture oracle over canonical source records, not service output."""
    start, end = start or bundle.window_start, end or bundle.as_of
    records = canonical_records(bundle)
    rows = {
        k: r
        for k, r in records.items()
        if r["kind"] == "transaction"
        and r["currency"] == currency
        and r["event_at"] is not None
        and start <= datetime.fromisoformat(r["event_at"]) < end
    }
    excluded = set()
    for key, row in rows.items():
        if net and row["event_kind"] == "reversal":
            target = rows.get(row["reverses_key"])
            if (
                target
                and target["event_kind"] != "reversal"
                and row["amount"] == target["amount"]
                and row["direction"] != target["direction"]
                and row["account_key"] == target["account_key"]
            ):
                excluded.update((key, row["reverses_key"]))
    rows = [r for k, r in rows.items() if k not in excluded]
    by_party, by_day = defaultdict(Decimal), Counter()
    for row in rows:
        by_party[row["counterparty_key"]] += Decimal(row["amount"])
        by_day[datetime.fromisoformat(row["event_at"]).date().isoformat()] += 1
    return {
        "count": len(rows),
        "incoming": str(
            sum((Decimal(r["amount"]) for r in rows if r["direction"] == "credit"), Decimal(0))
        ),
        "outgoing": str(
            sum((Decimal(r["amount"]) for r in rows if r["direction"] == "debit"), Decimal(0))
        ),
        "total": str(sum((Decimal(r["amount"]) for r in rows), Decimal(0))),
        "counterparties": {k: str(v) for k, v in sorted(by_party.items())},
        "daily_counts": dict(sorted(by_day.items())),
        "currency": currency,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "coverage": bundle.coverage,
        "net": net,
    }


def preview(seed=DEFAULT_SEED):
    return [
        {
            "key": s.key,
            "purpose": s.purpose,
            "lifecycle": s.lifecycle,
            "bundle_sha256": digest(bundle_manifest(scenario_bundle(s.key, seed))),
            "feature_origins": feature_origins(scenario_bundle(s.key, seed)),
            "expected": {
                c: expected_activity(scenario_bundle(s.key, seed), currency=c)
                for c in sorted(
                    {
                        r.currency
                        for r in scenario_bundle(s.key, seed).records
                        if r.kind == "transaction"
                    }
                )
            },
        }
        for s in CATALOG
    ]


class ConnectedScenarioService:
    """Explicit dev-only target guard plus existing per-operation authorization.

    Exact cluster/database identities must come from protected operator-owned state,
    never an HTTP body. No automatic investigation or source revocation side effects.
    """

    def __init__(
        self,
        engine,
        settings,
        *,
        development,
        expected_cluster,
        forbidden_cluster,
        expected_database,
    ):
        if (
            development is not True
            or expected_cluster == forbidden_cluster
            or not str(expected_database).startswith("tf_g0_3_primary_")
        ):
            raise EvidenceBlocked("isolated_development_required")
        self.engine, self.settings = engine, settings
        self.expected = (str(expected_cluster), str(expected_database))
        self.foundation = EvidenceService(engine)
        self.queue = AssessmentJobService(engine)
        self.reader = EvidenceReadService(engine, settings)

    def gate(self, actor_id):
        require_compatible(self.engine)
        with Session(self.engine) as session, session.begin():
            identity = (
                str(session.scalar(text("SELECT system_identifier FROM pg_control_system()"))),
                str(session.scalar(text("SELECT current_database()"))),
            )
            if identity != self.expected:
                raise EvidenceBlocked("isolated_development_required")
            actor_lock(session, actor_id, write=True)
        return SnapshotTime(self.engine).observe()

    def apply(self, actor_id, key, seed=DEFAULT_SEED):
        self.gate(actor_id)
        final = scenario_bundle(key, seed)
        source = self.foundation.register_source(actor_id, final.scenario_id)
        initial = scenario_bundle(key, seed, revision=1)
        release = self.foundation.admit_version(actor_id, source, initial)
        case_id = self.foundation.create_case(actor_id, release)
        for revision in range(2, final.source_revision + 1):
            self.gate(actor_id)
            release = self.foundation.admit_version(
                actor_id, source, scenario_bundle(key, seed, revision)
            )
            self.foundation.link_version(actor_id, case_id, release)
        self.gate(actor_id)
        with Session(self.engine) as session:
            case = session.get(Case, case_id)
            alert = session.get(Alert, case.alert_id)
            version, alert_id, input_sha = case.version, alert.id, alert.input_sha256
        run = uuid5(final.scenario_id, "assessment:Coverage:v1")
        job, _ = self.queue.enqueue(
            actor_id=actor_id,
            case_id=case_id,
            expected_version=version,
            run_id=run,
            idempotency_key="g1_" + run.hex,
            policy="Coverage",
            capacity=32,
            request_audit=True,
        )
        return {
            "catalog": CATALOG_VERSION,
            "key": key,
            "scenario_id": str(final.scenario_id),
            "source_id": str(source),
            "source_version_id": str(release),
            "case_id": str(case_id),
            "alert_id": str(alert_id),
            "input_sha256": input_sha,
            "job": job,
            "feature_origins": feature_origins(initial),
        }

    def ensure_worker(self, actor_id, token):
        """Reuse only the matching active identity; never rotate or reactivate it."""
        self.gate(actor_id)
        if (
            type(token) is not str
            or len(token) != 64
            or any(c not in "0123456789abcdef" for c in token)
        ):
            raise EvidenceBlocked("invalid_scenario_worker_token")
        with Session(self.engine) as session:
            worker = session.scalar(
                select(WorkerIdentity).where(WorkerIdentity.name == "g1-scenario-worker")
            )
            if worker:
                if (
                    not worker.active
                    or worker.provisioned_by != actor_id
                    or not hmac.compare_digest(
                        worker.token_sha256, hashlib.sha256(token.encode()).hexdigest()
                    )
                ):
                    raise EvidenceBlocked("scenario_worker_conflict")
                return worker.id
        return self.queue.register_worker(admin_id=actor_id, name="g1-scenario-worker", token=token)

    def verify_activity(self, actor_id, key, case_id, seed=DEFAULT_SEED):
        self.gate(actor_id)
        bundle = scenario_bundle(key, seed)
        context = self.reader.get_case_context(actor_id, case_id)
        expected_source = uuid5(actor_id, str(bundle.scenario_id))
        if (
            len(context.sources) != 1
            or context.sources[0].source_id != expected_source
            or context.sources[0].version != bundle.source_revision
            or context.sources[0].sha256 != digest(bundle_manifest(bundle))
        ):
            raise EvidenceBlocked("scenario_case_mismatch")
        observed = {}
        for currency in sorted({r.currency for r in bundle.records if r.kind == "transaction"}):
            oracle = expected_activity(bundle, currency=currency)
            query = AnalyticsRequest(
                snapshot=context.data.snapshot_token,
                calculation="incoming_outgoing",
                currency=currency,
                window=Window(start=bundle.window_start, end=bundle.as_of),
            )
            result = self.reader.calculate_activity(actor_id, case_id, query).data
            if (
                result.observed_count != oracle["count"]
                or result.observed_total != Decimal(oracle["total"])
                or result.incoming_total != Decimal(oracle["incoming"])
                or result.outgoing_total != Decimal(oracle["outgoing"])
            ):
                raise EvidenceBlocked("scenario_numeric_verification_failed")
            observed[currency] = result.model_dump(mode="json")
        return observed

    def revoke_source(self, actor_id, key, case_id, seed=DEFAULT_SEED):
        self.gate(actor_id)
        if key != "source_revocation":
            raise EvidenceBlocked("revocation_scenario_required")
        source_id = uuid5(actor_id, str(scenario_bundle(key, seed).scenario_id))
        self.foundation.set_source_access(actor_id, case_id, source_id, False)
