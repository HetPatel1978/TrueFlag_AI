"""Admin-only balance metadata and immutable-ledger accounting; no inference activation."""

from datetime import datetime, timezone

from sqlalchemy import select, text

from app.models import AuditEvent, User
from app.services.evidence import EvidenceBlocked, EvidenceNotFound, atomic, audit
from app.services.luminal_balance import BalanceUnavailable, LuminalBalanceClient
from app.services.provider_budget import call_limit, spend_limit
from app.services.provider_finance import (
    AUTHORIZATION_SHA256,
    financial_authorization,
    floor_projection,
    month_totals,
    receipt_totals,
    reservation_totals,
)
from app.services.snapshot_clock import ClockUnavailable, SnapshotTime

PREFIX = "evidence.investigation.provider."


class ProviderUsageService:
    def __init__(self, engine, settings, *, balance_client=None):
        self.engine, self.settings = engine, settings
        self.balance_client = balance_client or LuminalBalanceClient()

    def _admin(self, session, actor):
        if (
            session.scalar(
                select(User.id).where(User.id == actor, User.active.is_(True), User.role == "admin")
            )
            is None
        ):
            raise EvidenceNotFound("provider_admin_required")

    def _view(self, session, actor):
        self._admin(session, actor)
        calls, reserved = reservation_totals(session)
        receipts, estimated = receipt_totals(session)
        month_calls, month_estimated = month_totals(session, datetime.now(timezone.utc))
        latest = session.scalar(
            select(AuditEvent)
            .where(AuditEvent.action.in_([PREFIX + "balance_observed", PREFIX + "balance_failed"]))
            .order_by(AuditEvent.details["observed_second"].as_integer().desc())
            .limit(1)
        )
        balance = None
        if (
            latest
            and latest.action == PREFIX + "balance_observed"
            and latest.details.get("financial_authorization_sha256") == AUTHORIZATION_SHA256
        ):
            balance = {key: latest.details[key] for key in ("reported_balance_usd", "observed_at")}
        clock_ok = True
        try:
            observation = SnapshotTime(self.engine).observe()
            now = datetime.fromtimestamp(observation.second, timezone.utc)
            if latest and latest.details.get("clock_epoch") != observation.epoch:
                balance = None
        except ClockUnavailable:
            clock_ok, now = False, None
        historical_floor = (
            self.settings.investigation_provider_financial_policy == "prepaid_floor_v2"
        )
        if historical_floor:
            projection = floor_projection(
                self.settings, balance if clock_ok else None, reserved, now=now
            )
        else:
            projection = dict(
                minimum_balance_usd=None,
                safety_buffer_usd=None,
                projected_headroom_usd=None,
                dispatch_allowed=False,
                floor_guaranteed=False,
                blocked_reasons=["probe_bootstrap_unverified", "request_charge_bound_unverified"],
            )
        if not clock_ok:
            projection["blocked_reasons"].append("clock_health_unavailable")
        if not self.settings.investigation_external_enabled:
            projection["blocked_reasons"].append("provider_disabled")
        if not self.settings.investigation_provider_contract_verified:
            projection["blocked_reasons"].append("provider_contract_unverified")
        return dict(
            schema_version="trueflag.provider-usage.v2",
            provider="luminal",
            state="blocked",
            financial_policy=self.settings.investigation_provider_financial_policy,
            financial_authorization_sha256=AUTHORIZATION_SHA256 if historical_floor else None,
            financial_authorization_verified=historical_floor
            and financial_authorization(self.settings) is not None,
            owner_reported_balance_usd="997.00" if historical_floor else None,
            owner_reported_balance_verified=False,
            indicative_spending_ceiling_usd=str(spend_limit(self.settings)),
            reported_balance_usd=balance["reported_balance_usd"] if balance else None,
            balance_observed_at=balance["observed_at"] if balance else None,
            balance_basis="provider_reported_not_settled_or_reserved",
            inference_attempts=calls,
            inference_attempts_this_month=month_calls,
            estimated_usage_cost_this_month_usd=format(month_estimated.normalize(), "f"),
            retained_reservations_usd=format(reserved.normalize(), "f"),
            estimated_usage_cost_usd=format(estimated.normalize(), "f"),
            usage_receipts_with_estimates=receipts,
            unreconciled_attempts=max(0, calls - receipts),
            outside_usage_usd=None,
            vendor_settled_cost_usd=None,
            refresh_enabled=historical_floor
            and self.settings.investigation_provider_balance_lookup_enabled
            and bool(self.settings.investigation_provider_api_key.get_secret_value()),
            authorized_call_limit=call_limit(self.settings),
            last_refresh_status=latest.details.get("reason", "provider_reported_balance_observed")
            if latest
            else "not_observed",
            **projection,
        )

    @atomic
    def status(self, session, actor):
        result = self._view(session, actor)
        audit(
            session,
            actor,
            "investigation.provider.usage_viewed",
            "luminal-provider-usage",
            financial_policy=self.settings.investigation_provider_financial_policy,
        )
        return result

    @atomic
    def refresh(self, session, actor):
        self._admin(session, actor)
        if (
            self.settings.investigation_provider_financial_policy != "prepaid_floor_v2"
            or not self.settings.investigation_provider_balance_lookup_enabled
            or financial_authorization(self.settings) is None
        ):
            raise EvidenceBlocked("provider_balance_lookup_disabled")
        observed = SnapshotTime(self.engine).observe()
        session.execute(text("SELECT pg_advisory_xact_lock(82341721)"))
        recent = session.scalar(
            select(AuditEvent.id)
            .where(
                AuditEvent.action.in_([PREFIX + "balance_observed", PREFIX + "balance_failed"]),
                AuditEvent.details["observed_second"].as_integer() >= observed.second - 60,
            )
            .limit(1)
        )
        if recent:
            raise EvidenceBlocked("provider_balance_refresh_limited")
        try:
            result = self.balance_client.read(
                self.settings.investigation_provider_api_key, authorized=True
            )
            reason = None
        except BalanceUnavailable as error:
            result, reason = None, str(error)
        # A source of metadata may be contacted only after the first role check;
        # results are never published after role revocation or an epoch change.
        self._admin(session, actor)
        after = SnapshotTime(self.engine).observe()
        if observed.epoch != after.epoch:
            raise EvidenceBlocked("provider_clock_changed")
        fields = dict(
            financial_authorization_sha256=AUTHORIZATION_SHA256,
            observed_second=after.second,
            clock_epoch=after.epoch,
        )
        if result is None:
            audit(
                session,
                actor,
                "investigation.provider.balance_failed",
                "luminal-prepaid-v2",
                **fields,
                reason=reason,
            )
        else:
            audit(
                session,
                actor,
                "investigation.provider.balance_observed",
                "luminal-prepaid-v2",
                **fields,
                reported_balance_usd=result["reported_balance_usd"],
                observed_at=datetime.fromtimestamp(after.second, timezone.utc).isoformat(),
            )
        session.flush()
        view = self._view(session, actor)
        view["last_refresh_status"] = reason or "provider_reported_balance_observed"
        return view
