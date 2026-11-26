"""Deterministic fictional evidence, explicit declarations, no labels or saved predictions."""

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid5

from app.schemas.alerts import AlertFeatures
from app.schemas.evidence import (
    AccountObservation,
    CustomerObservation,
    RelationshipObservation,
    SyntheticBundle,
    TransactionObservation,
)
from app.services.ingestion import digest


def generate_scenario(
    scenario_id: UUID,
    seed: int,
    profile: str = "normal",
    *,
    source_revision: int = 1,
    as_of: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc),
) -> SyntheticBundle:
    if type(scenario_id) is not UUID or type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise ValueError("Invalid synthetic configuration")
    if (
        type(source_revision) is not int
        or not 1 <= source_revision <= 100
        or as_of.utcoffset() is None
    ):
        raise ValueError("Invalid synthetic configuration")
    rng = random.Random(seed)
    income = (
        None
        if profile in ("missing_income", "g1_partial_customer")
        else Decimal("0")
        if profile == "zero_income"
        else Decimal("72000")
    )
    customer = CustomerObservation(
        key="kyc-primary",
        subject_key="party-main",
        alias="SYN-CUSTOMER-" + uuid5(scenario_id, "customer").hex[:8],
        observed_at=as_of - timedelta(days=100),
        annual_income=income,
        currency="USD",
        kyc_score=5 if profile in ("g1_high_kyc", "g1_demo_priority") else 1 if profile == "g1_ordinary" else 3,
    )
    account = AccountObservation(
        key="account-main",
        alias="SYN-ACCOUNT-" + uuid5(scenario_id, "account").hex[:8],
        currency="USD",
        opened_at=as_of - timedelta(days=365),
    )
    counterparty = AccountObservation(
        key="account-counterparty",
        alias="SYN-ACCOUNT-" + uuid5(scenario_id, "counterparty").hex[:8],
        currency="USD",
        opened_at=as_of - timedelta(days=200),
    )
    relationship = RelationshipObservation(
        key="holder-main",
        customer_key=customer.key,
        account_key=account.key,
        observed_at=customer.observed_at,
    )
    records = [customer, account, counterparty, relationship]
    if profile.startswith("g1_") or profile == "g1_demo_priority":
        records.append(
            AccountObservation(
                key="account-secondary",
                alias="SYN-ACCOUNT-" + uuid5(scenario_id, "secondary").hex[:8],
                currency="USD",
                opened_at=as_of - timedelta(days=180),
            )
        )
    if profile == "g1_related":
        records.append(
            RelationshipObservation(
                key="holder-related",
                customer_key=customer.key,
                account_key=counterparty.key,
                observed_at=customer.observed_at,
            )
        )
    for n in range(12):
        event = (
            as_of - timedelta(hours=12 - n)
            if profile == "burst"
            else as_of - timedelta(days=2 + n * 3)
        )
        currency = "CAD" if profile == "multi_currency" and n % 2 else "USD"
        amount = Decimal(rng.randint(100, 9999)) / 100
        if profile == "decimal_precision" and n == 0:
            amount = Decimal("0.12345678")
        if source_revision > 1 and n == 0:
            amount += Decimal(source_revision - 1)
        if profile == "burst":
            amount += Decimal("1000")
        if profile in ("g1_concentration", "g1_demo_priority"):
            amount = Decimal("1000") if n < 10 else Decimal("10")
        if profile == "g1_related":
            amount = Decimal("250")
        if profile == "g1_flow_change":
            amount = Decimal("100") if n < 6 else Decimal("1500")
            event = as_of - timedelta(days=60 - n if n < 6 else 12 - n)
        offset = (
            event.astimezone(timezone(timedelta(hours=-5 if n % 2 else -4)))
            if profile == "timezone_offsets"
            else event
        )
        records.append(
            TransactionObservation(
                key=f"txn-{n}",
                account_key=account.key,
                counterparty_key="account-secondary"
                if (profile in ("g1_concentration", "g1_demo_priority") and n >= 10)
                or (
                    profile.startswith("g1_")
                    and profile not in ("g1_related", "g1_concentration")
                    and n % 6 == 5
                )
                else counterparty.key,
                amount=amount,
                currency=currency,
                event_at=None if profile == "timezone_unknown" and n == 0 else offset,
                original_time="2025-11-02T01:30:00"
                if profile == "timezone_unknown" and n == 0
                else offset.isoformat(),
                event_kind="transfer"
                if profile == "g1_related"
                else "payment"
                if n % 3 == 0
                else "purchase",
                direction=("credit" if n < 6 else "debit")
                if profile == "g1_flow_change"
                else "credit"
                if n % 3 == 0
                else "debit",
                channel="internal"
                if profile == "g1_related"
                else "cashlike"
                if n % 3 == 0
                else "card",
            )
        )
    if profile == "corrections":
        original = records[4]
        records.append(original)  # Exact duplicate delivery; not another economic event.
        records.append(
            TransactionObservation(
                key="reversal-first",
                account_key=account.key,
                counterparty_key=counterparty.key,
                amount=original.amount,
                currency=original.currency,
                event_at=as_of - timedelta(hours=1),
                original_time=(as_of - timedelta(hours=1)).isoformat(),
                event_kind="reversal",
                direction="debit",
                channel="internal",
                reverses_key=original.key,
            )
        )
    if profile == "inconsistent_kyc":
        records.append(
            customer.model_copy(
                update={
                    "key": "kyc-conflicting",
                    "annual_income": Decimal("12000"),
                    "observed_at": as_of - timedelta(days=1),
                }
            )
        )
    if profile in ("partial", "unavailable"):
        records = [r for r in records if r.kind != "transaction"] + (
            [] if profile == "unavailable" else records[4:8]
        )
    if profile == "out_of_order":
        records.reverse()
    # Explicit scenario declarations, never a fill operation for absent source features.
    declarations = {
        "kycRiskScore": customer.kyc_score,
        "income": None if income is None else int(income),
        "tenureMonths": 12,
        "creditScore": 650,
        "state": "QZ",
        "nbrPurchases90d": 8,
        "avgTxnSize90d": 50,
        "totalSpend90d": 400,
        "nbrDistinctMerch90d": 2,
        "nbrMerchCredits90d": 0,
        "nbrMerchCreditsRndDollarAmt90d": 0,
        "totalMerchCred90d": 0,
        "nbrMerchCreditsWoOffsettingPurch": 0,
        "nbrPayments90d": 4,
        "totalPaymentAmt90d": 200,
        "overpaymentAmt90d": 0,
        "overpaymentInd90d": 0,
        "nbrCustReqRefunds90d": 0,
        "totalRefundsToCust90d": 0,
        "nbrPaymentsCashLike90d": 4,
        "maxRevolveLine": 3000,
        "indOwnsHome": 0,
        "nbrInquiries1y": 1,
        "nbrCollections3y": 0,
        "nbrWebLogins90d": 8,
        "nbrPointRed90d": 0,
        "PEP": 0,
    }
    if profile == "g1_demo_priority":
        from app.services.synthetic_demo_profile import demo_declarations

        declarations = demo_declarations(declarations, seed)
    if profile == "incomplete_features":
        del declarations["nbrCollections3y"]
    return SyntheticBundle(
        scenario_id=scenario_id,
        seed=seed,
        profile=profile,
        source_revision=source_revision,
        as_of=as_of,
        window_start=as_of - timedelta(days=90),
        coverage="unavailable"
        if profile == "unavailable"
        else "partial"
        if profile in ("partial", "timezone_unknown")
        else "complete_declared_window",
        records=tuple(records),
        declarations=declarations,
    )


def canonical_record(record):
    payload = record.model_dump(mode="json")
    for key in ("event_at", "observed_at", "opened_at"):
        if payload.get(key) is not None:
            payload[key] = datetime.fromisoformat(payload[key]).astimezone(timezone.utc).isoformat()
    for key in ("amount", "annual_income"):
        if payload.get(key) is not None:
            payload[key] = format(Decimal(payload[key]).normalize(), "f")
    return payload


def canonical_records(bundle):
    unique = {}
    for record in bundle.records:
        payload = canonical_record(record)
        if record.key in unique and unique[record.key] != payload:
            raise ValueError("Conflicting duplicate record")
        unique[record.key] = payload
    return {key: unique[key] for key in sorted(unique)}


def bundle_manifest(bundle):
    return {
        **bundle.model_dump(mode="json", exclude={"records", "declarations", "profile"}),
        "config_sha256": digest(
            {"profile": bundle.profile, "seed": bundle.seed, "version": bundle.config_version}
        ),
        "declarations_sha256": digest(bundle.declarations),
        "record_sha256": {key: digest(value) for key, value in canonical_records(bundle).items()},
    }


def reconciliation(bundle):
    fields = AlertFeatures.model_fields
    missing = sorted(set(fields) - bundle.declarations.keys())
    valid = not missing
    if valid:
        try:
            AlertFeatures.model_validate(bundle.declarations)
        except ValueError:
            valid = False
    return {
        "status": "declared_synthetic_inputs" if valid else "blocked",
        "fields": {
            n: "declared_synthetic_input" if n in bundle.declarations else "missing" for n in fields
        },
        "missing_fields": missing,
        "transaction_derived_fields": [],
        "unresolved_semantics": [
            "collections_window_conflict",
            "source_currency_unspecified",
            "source_codebooks_unspecified",
        ],
        "dictionary_sha256": bundle.dictionary_sha256,
    }
