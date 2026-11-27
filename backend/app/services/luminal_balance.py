"""Read-only fixed-host balance lookup. A reported balance is not a spending lock."""

import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

BALANCE_URL = "https://flash.luminal.cloud/v1/balance"
MAX_BALANCE_BYTES = 16384


class BalanceUnavailable(Exception):
    """Stable, value-free errors only; provider bodies and credentials are never logged."""


def money(value):
    if type(value) not in (str, int, Decimal) or isinstance(value, bool):
        raise BalanceUnavailable("balance_invalid_amount")
    if not re.fullmatch(r"[0-9]{1,10}(?:\.[0-9]{1,12})?", str(value)):
        raise BalanceUnavailable("balance_invalid_amount")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise BalanceUnavailable("balance_invalid_amount") from None
    if not result.is_finite() or result < 0:
        raise BalanceUnavailable("balance_invalid_amount")
    return result


def normalize_balance(value):
    if type(value) is not dict:
        raise BalanceUnavailable("balance_schema_unverified")
    # Never infer dollars from an unqualified balance, credits or integer cents.
    if "balance_usd" in value and "balance" not in value:
        amount = money(value["balance_usd"])
        if value.get("currency", "USD") != "USD":
            raise BalanceUnavailable("balance_currency_unverified")
    elif "balance" in value and value.get("currency") == "USD" and "balance_usd" not in value:
        amount = money(value["balance"])
    else:
        raise BalanceUnavailable("balance_units_unverified")
    return {
        "reported_balance_usd": str(amount),
        "currency": "USD",
        "balance_basis": "provider_reported_not_atomic_available_funds",
        "billing_settlement_verified": False,
        "account_wide_atomic_floor_verified": False,
    }


class LuminalBalanceClient:
    def __init__(self, *, transport=None, schema_observer=None):
        self.transport = transport
        self.schema_observer = schema_observer

    def read(self, secret, *, authorized=False):
        if authorized is not True or not secret.get_secret_value():
            raise BalanceUnavailable("balance_lookup_disabled")
        deadline = time.monotonic() + 8
        try:
            with httpx.Client(
                transport=self.transport,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(3),
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            ) as client:
                with client.stream(
                    "GET",
                    BALANCE_URL,
                    headers={
                        "Authorization": "Bearer " + secret.get_secret_value(),
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                ) as response:
                    if response.status_code != 200:
                        raise BalanceUnavailable("balance_http_rejected")
                    if (
                        response.headers.get("content-type", "").split(";")[0].strip().lower()
                        != "application/json"
                        or response.headers.get("content-encoding", "identity").lower()
                        != "identity"
                    ):
                        raise BalanceUnavailable("balance_invalid_envelope")
                    raw = bytearray()
                    for chunk in response.iter_bytes(chunk_size=1):
                        if time.monotonic() > deadline:
                            raise BalanceUnavailable("balance_lookup_unavailable")
                        raw.extend(chunk)
                        if len(raw) > MAX_BALANCE_BYTES:
                            raise BalanceUnavailable("balance_response_limit")

            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise BalanceUnavailable("balance_invalid_envelope")
                    result[key] = value
                return result

            value = json.loads(raw, parse_float=Decimal, object_pairs_hook=unique)
            if self.schema_observer is not None:
                allowed = {
                    "balance",
                    "balance_usd",
                    "balance_cents",
                    "balance_dollars",
                    "currency",
                    "credits",
                    "available_balance",
                    "available_balance_usd",
                    "balance_micro_usd",
                    "unit",
                }
                self.schema_observer(
                    {
                        key: type(value[key]).__name__
                        for key in allowed
                        if isinstance(value, dict) and key in value
                    }
                )
            result = normalize_balance(value)
            result["observed_at"] = datetime.now(timezone.utc).isoformat()
            result["clock_attested"] = False
            return result
        except BalanceUnavailable:
            raise
        except Exception:
            raise BalanceUnavailable("balance_lookup_unavailable") from None
