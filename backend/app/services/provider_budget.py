"""Candidate preparation ceiling; uncertain outcomes retain their full reservation."""

from decimal import Decimal, InvalidOperation

from app.services.provider_finance import financial_authorization

MAX_PROVIDER_CALLS = 3
MAX_PROVIDER_SPEND_USD = Decimal("1.00")


def call_limit(settings):
    value = getattr(settings, "investigation_provider_call_limit", 0)
    return value if type(value) is int and 1 <= value <= MAX_PROVIDER_CALLS else 0


def spend_limit(settings):
    try:
        value = Decimal(str(settings.investigation_provider_spend_limit_usd))
        if not value.is_finite() or value <= 0:
            return Decimal(0)
        policy = getattr(settings, "investigation_provider_financial_policy", None)
        if policy == "legacy_probe_v1":
            return min(value, MAX_PROVIDER_SPEND_USD)
        if policy == "bounded_probe_v3":
            # The previous $200 floor is withdrawn. The unchanged original
            # probe package remains bounded to its $1 reservation ceiling.
            return min(value, MAX_PROVIDER_SPEND_USD)
        if policy == "prepaid_floor_v2":
            record = financial_authorization(settings)
            if record is None:
                return Decimal(0)
            floor = Decimal(str(settings.investigation_provider_minimum_balance_usd))
            return max(
                Decimal(0),
                min(
                    value,
                    Decimal(record["indicative_maximum_additional_spend_usd"]),
                    Decimal(record["reported_balance_usd"]) - floor,
                ),
            )
    except (AttributeError, InvalidOperation, TypeError, ValueError):
        pass
    return Decimal(0)


def finance_dispatch_allowed(settings):
    # The existing legacy branch is retained for offline fixtures only. The new
    # v3 policy removes the floor, but still cannot dispatch until a safe exact-
    # payload compatibility bootstrap and provider billing bounds are verified.
    return getattr(settings, "investigation_provider_financial_policy", None) == "legacy_probe_v1"
