"""Exact first-probe bootstrap using the existing provider and immutable ledger."""

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select

from app.evaluation.luminal_probe import prepare_request
from app.evaluation.oracles import verify_fixture
from app.models import User
from app.models.investigation_drafts import (
    DraftAttempt,
    DraftJob,
    DraftRequest,
    DraftRun,
    StoredDraft,
)
from app.schemas.evidence import SyntheticBundle
from app.schemas.investigation_drafts import DRAFT_VERSION, ProviderReply
from app.schemas.investigations import InvestigationPacketBody
from app.schemas.provider_live import LIVE_PROMPT_SHA, LiveProviderConfig
from app.services.evidence import EvidenceBlocked, EvidenceNotFound, atomic
from app.services.ingestion import digest
from app.services.investigation_draft_verifier import minimize, parse_proposal, validate_proposal
from app.services.investigation_drafts import InvestigationDraftService
from app.services.investigation_provider import (
    ProviderFailure,
    ProviderLimit,
    ProviderTimeout,
    strict_json,
)
from app.services.luminal_provider import LuminalProvider, request_body
from app.services.provider_finance import lock_reservations, reservation_totals

PACKAGE_SHA = "338703d5b331f6d98e84e58be4977adb49cf80a269af2fb49cacbe74b0d99183"
PROBE_A_SHA = "135f684427912c0231d0a97f09f7773ff73882e033aed5045fd59fd350c886f6"
AUTHORIZATION_SHA = "1147e4051d11d91ece54a38d3a9070ab6dabfd98ca4dbd2682659620216ba6c1"
AUTHORIZATION_PATH = (
    Path(__file__).resolve().parents[1] / "policies/luminal_probe_a_authorization_v1.json"
)


def _billing_contract_verified():
    # No provider-backed bound or invoice cap is currently established.
    # This cannot be turned on through request data, environment, or API input.
    return False


def _terms_contract_current():
    # Current provider terms have not been verified against the approved versions.
    return False


def _authorization_verified():
    try:
        record = strict_json(AUTHORIZATION_PATH.read_text(encoding="utf-8"), 16384)
        return digest(record) == AUTHORIZATION_SHA
    except Exception:
        return False


class ProbePreflightError(ValueError):
    """A fixed synthetic probe artifact is unavailable or has changed."""


class ProbeInvalidOutput(EvidenceBlocked):
    """The provider returned a structurally invalid candidate response."""


@dataclass(frozen=True)
class VerifiedProbe:
    packet: InvestigationPacketBody
    wire_sha256: str


def verify_probe_a(package_bytes: bytes, wire_bytes: bytes, source_bytes: bytes) -> VerifiedProbe:
    """Validate the exact proposal and synthetic source oracle; never send data."""
    try:
        if any(
            type(value) is not bytes or len(value) > 131072
            for value in (package_bytes, wire_bytes, source_bytes)
        ):
            raise ValueError
        package = strict_json(package_bytes.decode("utf-8"), 131072)
        sources = strict_json(source_bytes.decode("utf-8"), 131072)
        if (
            package["package_sha256"] != PACKAGE_SHA
            or digest({k: v for k, v in package.items() if k != "package_sha256"}) != PACKAGE_SHA
            or hashlib.sha256(wire_bytes).hexdigest() != PROBE_A_SHA
            or package["maximum_external_attempts"] != 3
            or package["application_spend_ceiling_usd"] != "1.00"
        ):
            raise ValueError
        candidates = [item for item in package["probes"] if item["probe"] == "A"]
        if len(candidates) != 1 or candidates[0]["request_sha256"] != PROBE_A_SHA:
            raise ValueError
        bundle = SyntheticBundle.model_validate_json(json.dumps(sources["bundle"]))
        packet = InvestigationPacketBody.model_validate_json(json.dumps(sources["packet"]))
        if digest(bundle.model_dump(mode="json")) != sources["source_sha256"]:
            raise ValueError
        verify_fixture(bundle, UUID(sources["source_id"]), packet)
        rebuilt, projected = prepare_request(packet, "A")
        if (
            rebuilt != wire_bytes
            or packet.model_signal is not None
            or any(candidates[0].get(key) != value for key, value in projected.items())
        ):
            raise ValueError
        return VerifiedProbe(packet=packet, wire_sha256=PROBE_A_SHA)
    except Exception:
        raise ProbePreflightError("approved_probe_invalid") from None


class ProbeBootstrapPreflight:
    """Inspect current authority and the existing ledger without dispatch or reservations.

    A pre-existing compatibility flag is deliberately not consulted. A safe
    one-shot transport and provider-backed charge bound are not yet established;
    this check must never be interpreted as permission to call the provider.
    """

    def __init__(self, engine, settings):
        self.engine = engine
        self.drafts = InvestigationDraftService(engine, settings)

    @atomic
    def inspect(self, session, actor_id, draft_run_id, probe: VerifiedProbe):
        if type(actor_id) is not UUID or type(draft_run_id) is not UUID:
            raise EvidenceNotFound("probe_not_found")
        self.drafts.coordinator._gate(session)
        admin = session.scalar(
            select(User.id).where(User.id == actor_id, User.active.is_(True), User.role == "admin")
        )
        run = session.get(DraftRun, draft_run_id)
        if admin is None or run is None or run.actor_id != actor_id:
            raise EvidenceNotFound("probe_not_found")
        packet = self.drafts._packet(session, run)
        try:
            current_wire, _ = prepare_request(packet, "A")
        except (ValueError, TypeError, ProviderFailure, ProviderLimit):
            return {"status": "blocked", "reason": "approved_case_or_payload_changed"}
        if (
            not isinstance(probe, VerifiedProbe)
            or probe.wire_sha256 != PROBE_A_SHA
            or digest(packet.model_dump(mode="json"))
            != digest(probe.packet.model_dump(mode="json"))
            or hashlib.sha256(current_wire).hexdigest() != PROBE_A_SHA
        ):
            return {"status": "blocked", "reason": "approved_case_or_payload_changed"}
        lock_reservations(session)
        attempts, reserved = reservation_totals(session)
        if attempts:
            return {"status": "blocked", "reason": "prior_luminal_attempt_requires_review"}
        return {
            "status": "blocked",
            "reason": "vendor_charge_bound_and_bootstrap_transport_unverified",
            "prior_attempts": attempts,
            "retained_reservations_usd": str(reserved),
            "external_requests": 0,
        }


class OneAttemptProbeBootstrap:
    """Explicit operator-only probe; no public endpoint or general-provider activation."""

    def __init__(self, engine, settings, *, transport=None):
        self.engine, self.settings = engine, settings
        self.drafts = InvestigationDraftService(engine, settings)
        self.transport = transport

    @staticmethod
    def _minimized(packet):
        return minimize(packet).model_copy(
            update={"financial_facts": [], "evidence_references": []}
        )

    def _enabled(self):
        if not (
            self.settings.investigation_probe_bootstrap_enabled
            and self.settings.investigation_provider_financial_policy == "bounded_probe_v3"
            and self.settings.investigation_provider_api_key.get_secret_value()
            and _authorization_verified()
        ):
            raise EvidenceBlocked("probe_authorization_unavailable")
        if not _billing_contract_verified():
            raise EvidenceBlocked("probe_billing_bound_unverified")
        if not _terms_contract_current():
            raise EvidenceBlocked("probe_terms_version_unverified")

    @staticmethod
    def _admin(session, actor_id):
        if (
            session.scalar(
                select(User.id).where(
                    User.id == actor_id, User.active.is_(True), User.role == "admin"
                )
            )
            is None
        ):
            raise EvidenceNotFound("probe_not_found")

    @atomic
    def _reserve(self, session, actor_id, original_draft_id, worker_token, artifacts):
        self._enabled()
        probe = verify_probe_a(*artifacts)
        self.drafts.coordinator._gate(session)
        clock_epoch = self.drafts.coordinator.reader.clock.observe().epoch
        if type(actor_id) is not UUID or type(original_draft_id) is not UUID:
            raise EvidenceNotFound("probe_not_found")
        self._admin(session, actor_id)
        original = session.get(DraftRun, original_draft_id)
        if original is None or original.actor_id != actor_id:
            raise EvidenceNotFound("probe_not_found")
        packet = self.drafts._packet(session, original)
        wire, projected = prepare_request(packet, "A")
        if (
            digest(packet.model_dump(mode="json")) != digest(probe.packet.model_dump(mode="json"))
            or hashlib.sha256(wire).hexdigest() != PROBE_A_SHA
        ):
            raise EvidenceBlocked("approved_case_or_payload_changed")
        config = LiveProviderConfig.model_validate_json(json.dumps(projected["configuration"]))
        if (
            config.max_attempts != 1
            or config.max_input_tokens != 8192
            or config.max_output_tokens != 512
            or config.max_request_bytes != 8192
            or config.max_cost_usd != Decimal("0.00992256")
        ):
            raise EvidenceBlocked("probe_budget_invalid")
        worker = self.drafts.coordinator._worker(session, worker_token)
        lock_reservations(session)
        attempts, reserved = reservation_totals(session)
        if attempts or reserved + config.max_cost_usd > Decimal("1.00"):
            raise EvidenceBlocked("probe_attempt_already_reserved")
        config_data = config.model_dump(mode="json")
        config_sha = digest(config_data)
        manifest = digest(
            dict(
                parent_run_id=str(original.parent_run_id),
                parent_manifest_sha256=original.parent_manifest_sha256,
                config_sha256=config_sha,
                prompt_sha256=LIVE_PROMPT_SHA,
                schema=DRAFT_VERSION,
            )
        )
        run = DraftRun(
            id=uuid4(),
            parent_run_id=original.parent_run_id,
            actor_id=actor_id,
            parent_manifest_sha256=original.parent_manifest_sha256,
            config_sha256=config_sha,
            manifest_sha256=manifest,
            configuration=config_data,
            prompt_sha256=LIVE_PROMPT_SHA,
        )
        session.add(run)
        session.flush()
        now = self.drafts.coordinator._now(session)
        lease = uuid4()
        job = DraftJob(
            run_id=run.id,
            status="running",
            attempts=1,
            not_before=now,
            worker_id=worker.id,
            lease_token=lease,
            lease_until=now + timedelta(seconds=60),
            deadline=now + timedelta(seconds=30),
        )
        session.add(job)
        session.add(
            DraftRequest(
                actor_id=actor_id,
                idempotency_key="g4-2b-4-exact-probe-a",
                run_id=run.id,
                manifest_sha256=manifest,
            )
        )
        minimized = self._minimized(packet)
        session.add(
            DraftAttempt(
                run_id=run.id,
                attempt=1,
                lease_sha256=digest(str(lease)),
                packet_sha256=minimized.packet_sha256,
                minimized_sha256=digest(minimized.model_dump(mode="json")),
                input_reservation=config.max_input_tokens,
                output_reservation=config.max_output_tokens,
            )
        )
        self.drafts._event(
            session,
            run,
            "provider_reserved",
            attempt=1,
            package_sha256=PACKAGE_SHA,
            request_sha256=PROBE_A_SHA,
            authorization_sha256=AUTHORIZATION_SHA,
            reserved_input=config.max_input_tokens,
            reserved_output=config.max_output_tokens,
            cost_reservation_usd=str(config.max_cost_usd),
            egress=True,
        )
        from app.services.investigation_drafts import DraftClaim

        self.drafts.coordinator.reader.ensure_clock(clock_epoch)
        session.flush()
        return DraftClaim(run.id, worker.id, lease), config

    @atomic
    def _recheck(self, session, worker_token, claim, config):
        self._enabled()
        self.drafts.coordinator._gate(session)
        clock_epoch = self.drafts.coordinator.reader.clock.observe().epoch
        job = self.drafts._leased(session, worker_token, claim)
        run = self.drafts._run(session, job.run_id)
        self._admin(session, run.actor_id)
        packet = self.drafts._packet(session, run)
        minimized = self._minimized(packet)
        attempt = self.drafts._attempt(session, job)
        if (
            attempt is None
            or self.drafts._configuration(run) != config
            or attempt.lease_sha256 != digest(str(claim.lease_token))
            or attempt.packet_sha256 != minimized.packet_sha256
            or attempt.minimized_sha256 != digest(minimized.model_dump(mode="json"))
            or hashlib.sha256(request_body(minimized, config)).hexdigest() != PROBE_A_SHA
        ):
            raise EvidenceBlocked("approved_case_or_payload_changed")
        self.drafts.coordinator.reader.ensure_clock(clock_epoch)
        return minimized

    @atomic
    def _finish(self, session, worker_token, claim, config, reply, elapsed):
        self._enabled()
        self.drafts.coordinator._gate(session)
        clock_epoch = self.drafts.coordinator.reader.clock.observe().epoch
        job = self.drafts._leased(session, worker_token, claim)
        run = self.drafts._run(session, job.run_id)
        self._admin(session, run.actor_id)
        packet = self.drafts._packet(session, run)
        minimized = self._minimized(packet)
        attempt = self.drafts._attempt(session, job)
        if (
            attempt is None
            or self.drafts._configuration(run) != config
            or attempt.lease_sha256 != digest(str(claim.lease_token))
            or attempt.packet_sha256 != minimized.packet_sha256
            or attempt.minimized_sha256 != digest(minimized.model_dump(mode="json"))
            or hashlib.sha256(request_body(minimized, config)).hexdigest() != PROBE_A_SHA
        ):
            raise EvidenceBlocked("approved_case_or_payload_changed")
        reply = ProviderReply.model_validate_json(reply.model_dump_json(warnings="error"))
        expected_cost = (
            reply.usage.input_tokens * config.input_usd_per_million
            + reply.usage.output_tokens * config.output_usd_per_million
        ) / 1_000_000
        if (
            reply.provider != config.provider
            or reply.model != config.model
            or reply.usage.input_tokens > attempt.input_reservation
            or reply.usage.output_tokens > attempt.output_reservation
            or reply.usage.cost_usd != expected_cost
        ):
            raise EvidenceBlocked("probe_response_invalid")
        try:
            proposal = parse_proposal(reply, config)
        except (ValueError, TypeError, ProviderLimit):
            raise ProbeInvalidOutput("probe_invalid_output") from None
        findings = validate_proposal(packet, proposal)
        if (
            not proposal.abstain
            or proposal.financial_observations
            or proposal.unusual_activity
            or proposal.model_signals
            or proposal.supporting_records
            or proposal.risk_indicators
        ):
            raise EvidenceBlocked("probe_unexpected_evidence_claim")
        self.drafts.coordinator.reader.ensure_clock(clock_epoch)
        self.drafts._receipt(session, attempt, "completed", reply, elapsed)
        body = self.drafts._build(run, packet, reply, proposal, findings, attempt).model_dump(
            mode="json"
        )
        body["provenance"]["approval_id"] = "g4-2b-4-exact-probe-a"
        session.add(
            StoredDraft(
                run_id=run.id,
                attempt_id=attempt.id,
                manifest_sha256=run.manifest_sha256,
                content_sha256=digest(body),
                body=body,
            )
        )
        job.status = "abstained"
        self.drafts._clear(job)
        self.drafts._event(
            session,
            run,
            "probe_validated",
            http_status=200,
            model=reply.model,
            usage=reply.usage.model_dump(mode="json"),
            structured_output_valid=True,
            evidence_verified=True,
        )
        self.drafts.coordinator.reader.ensure_clock(clock_epoch)
        session.flush()
        return {
            "status": "validated",
            "http_status": 200,
            "model": reply.model,
            "usage": reply.usage.model_dump(mode="json"),
            "elapsed_ms": elapsed,
            "contract_verified_changed": False,
        }

    @atomic
    def _failure(self, session, worker_token, claim, reason, elapsed, http_status=None, reply=None):
        self.drafts.coordinator._gate(session)
        job = self.drafts._leased(session, worker_token, claim, expired=True)
        run = self.drafts._run(session, job.run_id)
        self.drafts._fail(session, job, reason, retryable=False, reply=reply, elapsed=elapsed)
        self.drafts._event(
            session, run, "probe_failed", http_status=http_status, reservation_retained=True
        )
        return {
            "status": "failed",
            "reason": reason,
            "http_status": http_status,
            "reservation_retained": True,
        }

    def run_once(self, actor_id, original_draft_id, worker_token, artifacts):
        """Reserve once, recheck authority and call the fixed adapter at most once."""
        claim, config = self._reserve(actor_id, original_draft_id, worker_token, artifacts)
        started = time.monotonic()
        reply = None
        try:
            packet = self._recheck(worker_token, claim, config)
            reply = LuminalProvider(self.settings, transport=self.transport)._perform_request(
                packet, config
            )
            if reply.finish_reason != "complete":
                return self._failure(
                    worker_token,
                    claim,
                    "provider_incomplete",
                    int((time.monotonic() - started) * 1000),
                    200,
                    reply,
                )
            return self._finish(
                worker_token, claim, config, reply, int((time.monotonic() - started) * 1000)
            )
        except Exception as error:
            reason = (
                "provider_timeout"
                if isinstance(error, ProviderTimeout)
                else (
                    "invalid_provider_output"
                    if isinstance(error, (ValueError, ProviderLimit, ProbeInvalidOutput))
                    or (
                        isinstance(error, ProviderFailure)
                        and str(error) == "provider_invalid_envelope"
                    )
                    else "provider_unavailable"
                    if isinstance(error, ProviderFailure)
                    else "verification_failed"
                )
            )
            return self._failure(
                worker_token,
                claim,
                reason,
                int((time.monotonic() - started) * 1000),
                getattr(error, "http_status", None) or (200 if reply else None),
                reply,
            )
