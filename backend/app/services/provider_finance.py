"""Versioned prepaid policy and existing immutable-ledger projections. No inference."""

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import Numeric, case, cast, func, select, text

from app.models.investigation_drafts import DraftAttempt, DraftReceipt, DraftRun
from app.services.ingestion import digest

FINANCIAL_VERSION = "prepaid_floor_v2"
AUTHORIZATION_SHA256 = "325d4dc7770f35606023fbd4c3a0738ee700ee1ad79b6499f09393ec4afdbe18"
AUTHORIZATION_PATH = (
    Path(__file__).resolve().parents[1] / "policies/luminal_financial_authorization_v2.json"
)
PROVIDER_LEDGER_LOCK = 82341722


def lock_reservations(session):
    """Serialize provider-wide admission before reading or reserving paid attempts."""
    session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": PROVIDER_LEDGER_LOCK})


def financial_authorization(settings):
    try:
        record = json.loads(AUTHORIZATION_PATH.read_bytes())
        if (
            digest(record) != AUTHORIZATION_SHA256
            or getattr(settings, "investigation_provider_financial_authorization_sha256", "")
            != AUTHORIZATION_SHA256
        ):
            return None
        return record
    except Exception:
        return None


def reservation_totals(session, approval_id=None, *, provider="luminal"):
    if provider not in {"luminal", "anthropic"}:
        raise ValueError("unsupported_provider")
    incoming = cast(DraftRun.configuration["input_usd_per_million"].as_string(), Numeric)
    outgoing = cast(DraftRun.configuration["output_usd_per_million"].as_string(), Numeric)
    rate = case((incoming > outgoing, incoming), else_=outgoing)
    query = (
        select(
            func.count(DraftAttempt.id),
            func.coalesce(
                func.sum(
                    case(
                        (
                            DraftRun.configuration["provider"].as_string() == "anthropic",
                            cast(DraftRun.configuration["max_cost_usd"].as_string(), Numeric),
                        ),
                        else_=(DraftAttempt.input_reservation + DraftAttempt.output_reservation)
                        * rate
                        / 1_000_000,
                    )
                ),
                0,
            ),
        )
        .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
        .where(DraftRun.configuration["provider"].as_string() == provider)
    )
    if approval_id is not None:
        query = query.where(DraftRun.configuration["approval_id"].as_string() == approval_id)
    calls, reserved = session.execute(query).one()
    return calls, Decimal(str(reserved))


def month_totals(session, now, *, provider="luminal"):
    """Attempts created since the start of ``now``'s UTC month and their usage estimates."""
    start = now.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = session.execute(
        select(DraftAttempt.created_at, DraftReceipt.usage)
        .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
        .outerjoin(DraftReceipt, DraftReceipt.attempt_id == DraftAttempt.id)
        .where(DraftRun.configuration["provider"].as_string() == provider)
    ).all()
    count, known = 0, Decimal(0)
    for created, usage in rows:
        created = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        if created < start:
            continue
        count += 1
        try:
            value = Decimal(str((usage or {})["cost_usd"]))
            if value.is_finite() and value >= 0:
                known += value
        except (KeyError, InvalidOperation, TypeError, ValueError):
            continue
    return count, known


def receipt_totals(session):
    # Keep estimates separate from reservations; receipts are not settled invoices.
    receipts = session.scalars(
        select(DraftReceipt)
        .join(DraftAttempt, DraftAttempt.id == DraftReceipt.attempt_id)
        .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
        .where(DraftRun.configuration["provider"].as_string() == "luminal")
    ).yield_per(100)
    known = Decimal(0)
    count = 0
    for receipt in receipts:
        try:
            usage = receipt.usage or {}
            if usage.get("basis") != "provider_reported_tokens_configured_rate_estimate":
                continue
            value = Decimal(str(usage["cost_usd"]))
            if not value.is_finite() or value < 0:
                continue
            known += value
            count += 1
        except (KeyError, InvalidOperation, TypeError, ValueError):
            continue
    return count, known


def floor_projection(settings, balance, reserved=Decimal(0), upper_cost=None, *, now=None):
    """Diagnostic only. No success path until account-wide atomic controls are verified."""
    floor = Decimal(str(settings.investigation_provider_minimum_balance_usd))
    buffer = Decimal(str(settings.investigation_provider_balance_buffer_usd))
    reasons = []
    record = financial_authorization(settings)
    if record is None:
        reasons.append("financial_authorization_unavailable")
    remaining = None
    if balance is None:
        reasons.append("current_balance_unverified")
    else:
        try:
            value = Decimal(balance["reported_balance_usd"])
            observed = datetime.fromisoformat(balance["observed_at"])
            age = ((now or datetime.now(timezone.utc)) - observed).total_seconds()
            if (
                not value.is_finite()
                or value < 0
                or age < 0
                or age > settings.investigation_provider_balance_max_age_seconds
            ):
                raise ValueError
            remaining = max(Decimal(0), value - floor - buffer - reserved)
            if value - reserved <= floor + buffer:
                reasons.append("balance_floor_reached")
            if upper_cost is not None and (
                type(upper_cost) is not Decimal
                or not upper_cost.is_finite()
                or upper_cost <= 0
                or upper_cost >= remaining
            ):
                reasons.append("projected_balance_floor_breach")
        except (KeyError, TypeError, ValueError, InvalidOperation):
            reasons.append("balance_stale_or_invalid")
    if upper_cost is None:
        reasons.append("request_charge_bound_unverified")
    reasons.extend(
        [
            "billing_settlement_unverified",
            "outside_account_usage_unbounded",
            "provider_atomic_floor_unverified",
        ]
    )
    return dict(
        minimum_balance_usd=str(floor),
        safety_buffer_usd=str(buffer),
        projected_headroom_usd=str(remaining) if remaining is not None else None,
        dispatch_allowed=False,
        floor_guaranteed=False,
        blocked_reasons=reasons,
    )
