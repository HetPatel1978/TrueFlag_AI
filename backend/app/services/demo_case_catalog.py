"""Eight explicitly labeled synthetic demo cases: alert inputs plus matching generated evidence.

Story (demo only): a fictional investment firm's cash management account with direct deposit,
bill pay, peer-to-peer wallet transfers and bank transfers. All identifiers are synthetic
(``SYN-``); no real people, firms or account numbers.

Each case has two separate parts that are never derived from each other:

* ``declarations`` - the 27 frozen model inputs uploaded through Admin > CSV imports. They are
  card-account style aggregates from the model's training contract (datarobot_provisional_v1).
* ``records`` - generated customer, account and transaction observations that tell the
  case's story in Review evidence. ``reconciliation()["transaction_derived_fields"]`` stays
  empty: the inputs are declared, not calculated from these transactions.

The model, policies, thresholds and verification rules are unchanged; only these inputs were
chosen, and their scores come from the real frozen model.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from app.schemas.alerts import FEATURE_CONTRACT_VERSION
from app.schemas.evidence import (
    AccountObservation,
    CustomerObservation,
    RelationshipObservation,
    SyntheticBundle,
    TransactionObservation,
)

CATALOG_VERSION = "trueflag.demo-cases.v2"
CATALOG_NAMESPACE = uuid5(NAMESPACE_URL, CATALOG_VERSION)
CATALOG_PROFILE = "g1_demo_catalog"
AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)
WINDOW_DAYS = 90

# Unchanged training-contract defaults; each case overrides only what its story needs.
BASE_INPUTS = {
    "kycRiskScore": 1,
    "income": 52000,
    "tenureMonths": 36,
    "creditScore": 720,
    "state": "MA",
    "nbrPurchases90d": 10,
    "avgTxnSize90d": 70,
    "totalSpend90d": 700,
    "nbrDistinctMerch90d": 6,
    "nbrMerchCredits90d": 1,
    "nbrMerchCreditsRndDollarAmt90d": 0,
    "totalMerchCred90d": 30,
    "nbrMerchCreditsWoOffsettingPurch": 0,
    "nbrPayments90d": 3,
    "totalPaymentAmt90d": 400,
    "overpaymentAmt90d": 0,
    "overpaymentInd90d": 0,
    "nbrCustReqRefunds90d": 0,
    "totalRefundsToCust90d": 0,
    "nbrPaymentsCashLike90d": 0,
    "maxRevolveLine": 12000,
    "indOwnsHome": 1,
    "nbrInquiries1y": 2,
    "nbrCollections3y": 0,
    "nbrWebLogins90d": 7,
    "nbrPointRed90d": 1,
    "PEP": 0,
}

CASES = {
    "SYN-01-STRUCTURING": dict(
        title="Cash-like deposits kept just under reporting thresholds",
        inputs=dict(
            kycRiskScore=2,
            income=48000,
            nbrPaymentsCashLike90d=10,
            nbrPayments90d=10,
            totalPaymentAmt90d=92000,
            nbrMerchCreditsRndDollarAmt90d=8,
            nbrMerchCredits90d=9,
            totalMerchCred90d=8600,
        ),
        tenure_months=36,
    ),
    "SYN-02-PASSTHROUGH": dict(
        title="Money arrives and leaves within one to two days via P2P wallets",
        inputs=dict(
            kycRiskScore=2,
            income=61000,
            nbrPurchases90d=25,
            totalSpend90d=8000,
            nbrPayments90d=8,
            totalPaymentAmt90d=60000,
            overpaymentAmt90d=8000,
            nbrPaymentsCashLike90d=3,
            nbrWebLogins90d=70,
        ),
        tenure_months=36,
    ),
    "SYN-03-FUNNEL": dict(
        title="Many small incoming transfers from many senders, then large outgoing transfers",
        inputs=dict(
            kycRiskScore=2,
            income=39000,
            nbrMerchCredits90d=48,
            totalMerchCred90d=24000,
            nbrMerchCreditsWoOffsettingPurch=32,
            nbrDistinctMerch90d=140,
            nbrPurchases90d=150,
            totalSpend90d=43000,
            avgTxnSize90d=287,
        ),
        tenure_months=36,
    ),
    "SYN-04-SAVER": dict(
        title="Ordinary saver: salary direct deposit, bills and small transfers",
        inputs=dict(kycRiskScore=1, income=68000, tenureMonths=84),
        tenure_months=84,
    ),
    "SYN-05-HIGHKYC": dict(
        title="High customer risk rating (KYC 4) with normal activity",
        inputs=dict(kycRiskScore=4, income=75000, tenureMonths=60, creditScore=760),
        tenure_months=60,
    ),
    "SYN-06-PARTIAL": dict(
        title="Suspicious-looking activity but only part of the history is available",
        inputs=dict(
            kycRiskScore=3,
            income=None,
            nbrPaymentsCashLike90d=6,
            nbrPayments90d=7,
            totalPaymentAmt90d=31000,
            nbrWebLogins90d=40,
        ),
        tenure_months=36,
    ),
    "SYN-07-DORMANT": dict(
        title="Long-dormant account that suddenly becomes very active",
        inputs=dict(
            kycRiskScore=1,
            income=58000,
            tenureMonths=232,
            nbrWebLogins90d=70,
            nbrPurchases90d=100,
            totalSpend90d=9000,
            avgTxnSize90d=150,
            nbrPayments90d=12,
            totalPaymentAmt90d=9000,
            nbrPaymentsCashLike90d=5,
            nbrInquiries1y=9,
            nbrMerchCredits90d=1,
            totalMerchCred90d=2500,
        ),
        tenure_months=232,
    ),
    "SYN-08-INCOME": dict(
        title="Activity far above declared income",
        inputs=dict(
            kycRiskScore=2,
            income=21000,
            totalSpend90d=72000,
            nbrPurchases90d=130,
            avgTxnSize90d=554,
            totalPaymentAmt90d=60000,
            nbrPayments90d=6,
            maxRevolveLine=25000,
            nbrDistinctMerch90d=45,
            nbrCollections3y=2,
            nbrInquiries1y=7,
        ),
        tenure_months=36,
    ),
}


def declarations(case_id):
    inputs = {**BASE_INPUTS, **CASES[case_id]["inputs"]}
    return {name: inputs[name] for name in BASE_INPUTS}


def scenario_id(case_id):
    return uuid5(CATALOG_NAMESPACE, case_id)


def _hex8(case_id, label):
    return uuid5(scenario_id(case_id), label).hex[:8]


class _Builder:
    """Deterministic record builder for one case (no randomness, exact decimals)."""

    def __init__(self, case_id, *, income, kyc, tenure_months):
        self.case_id = case_id
        self.records = []
        self.accounts = set()
        self.customer = CustomerObservation(
            key="kyc-primary",
            subject_key="party-main",
            alias="SYN-CUSTOMER-" + _hex8(case_id, "customer"),
            observed_at=AS_OF - timedelta(days=100),
            annual_income=None if income is None else Decimal(income),
            currency="USD",
            kyc_score=kyc,
        )
        self.records.append(self.customer)
        self.account("account-main", days_open=tenure_months * 30 + 10)
        self.records.append(
            RelationshipObservation(
                key="holder-main",
                customer_key="kyc-primary",
                account_key="account-main",
                observed_at=self.customer.observed_at,
            )
        )
        self.count = 0

    def account(self, key, days_open=400):
        if key not in self.accounts:
            self.accounts.add(key)
            self.records.append(
                AccountObservation(
                    key=key,
                    alias="SYN-ACCOUNT-" + _hex8(self.case_id, key),
                    currency="USD",
                    opened_at=AS_OF - timedelta(days=days_open),
                )
            )
        return key

    def txn(self, days_before, amount, *, kind, direction, channel, counterparty=None, hour=15):
        event = AS_OF - timedelta(days=days_before) + timedelta(hours=hour - 24)
        if counterparty is not None:
            self.account(counterparty)
        self.count += 1
        self.records.append(
            TransactionObservation(
                key=f"txn-{self.count:03d}",
                account_key="account-main",
                counterparty_key=counterparty,
                amount=Decimal(str(amount)),
                currency="USD",
                event_at=event,
                original_time=event.isoformat(),
                event_kind=kind,
                direction=direction,
                channel=channel,
            )
        )


def _salary_and_bills(b, salary, bills):
    for n in range(6):  # biweekly direct deposit
        b.txn(
            5 + 14 * n,
            salary,
            kind="transfer",
            direction="credit",
            channel="internal",
            counterparty="payroll-employer",
        )
    for n, amount in enumerate(bills):  # bill pay
        b.txn(
            8 + 11 * n,
            amount,
            kind="payment",
            direction="debit",
            channel="internal",
            counterparty=f"biller-{n % 3 + 1}",
        )
    b.txn(
        20,
        "45.00",
        kind="transfer",
        direction="debit",
        channel="internal",
        counterparty="p2p-wallet-a",
    )
    b.txn(
        52,
        "60.00",
        kind="transfer",
        direction="credit",
        channel="internal",
        counterparty="p2p-wallet-a",
    )


def _records(case_id, inputs):
    b = _Builder(
        case_id,
        income=inputs["income"],
        kyc=inputs["kycRiskScore"],
        tenure_months=CASES[case_id]["tenure_months"],
    )
    if case_id == "SYN-01-STRUCTURING":
        # Ten cash-like deposits just under USD 10,000, then transfers out to one bank account.
        for n, amount in enumerate(
            ["9400", "9850", "9600", "9900", "9700", "9550", "9800", "9450", "9650", "9750"]
        ):
            b.txn(85 - 8 * n, amount, kind="payment", direction="credit", channel="cashlike")
        for days, amount in ((45, "38000"), (12, "46000")):
            b.txn(
                days,
                amount,
                kind="transfer",
                direction="debit",
                channel="internal",
                counterparty="external-bank-1",
            )
    elif case_id == "SYN-02-PASSTHROUGH":
        # Six cycles: funds arrive from one P2P wallet and leave within 1-2 days to another.
        for n, (amount_in, amount_out) in enumerate(
            [
                ("9500", "9420"),
                ("10200", "10110"),
                ("9800", "9750"),
                ("10000", "9930"),
                ("9700", "9640"),
                ("10400", "10320"),
            ]
        ):
            start = 80 - 13 * n
            b.txn(
                start,
                amount_in,
                kind="transfer",
                direction="credit",
                channel="internal",
                counterparty="p2p-wallet-a",
            )
            b.txn(
                start - 1 - n % 2,
                amount_out,
                kind="transfer",
                direction="debit",
                channel="internal",
                counterparty="p2p-wallet-b",
            )
    elif case_id == "SYN-03-FUNNEL":
        # Forty small credits from twenty-five senders, then three large transfers to one account.
        for n in range(40):
            amount = Decimal(120 + (n * 37) % 460)
            b.txn(
                88 - 2 * n,
                amount,
                kind="transfer",
                direction="credit",
                channel="internal",
                counterparty=f"sender-{n % 25 + 1:02d}",
            )
        for days, amount in ((30, "7800"), (16, "7950"), (3, "8100")):
            b.txn(
                days,
                amount,
                kind="transfer",
                direction="debit",
                channel="internal",
                counterparty="external-bank-1",
            )
    elif case_id == "SYN-04-SAVER":
        _salary_and_bills(
            b, "2650.00", ["1450.00", "180.40", "96.15", "1450.00", "212.80", "88.60", "1450.00"]
        )
    elif case_id == "SYN-05-HIGHKYC":
        _salary_and_bills(
            b, "3100.00", ["1800.00", "240.10", "110.35", "1800.00", "198.75", "92.40", "1800.00"]
        )
    elif case_id == "SYN-06-PARTIAL":
        # Only four events are available for the requested window (partial coverage).
        for days, amount, direction, channel, cp in (
            (70, "6000", "credit", "cashlike", None),
            (64, "5800", "debit", "internal", "p2p-wallet-a"),
            (40, "6200", "credit", "cashlike", None),
            (33, "6100", "debit", "internal", "p2p-wallet-a"),
        ):
            b.txn(
                days,
                amount,
                kind="payment" if channel == "cashlike" else "transfer",
                direction=direction,
                channel=channel,
                counterparty=cp,
            )
    elif case_id == "SYN-07-DORMANT":
        # No activity for 75 days of the window, then a large credit and a burst of spending.
        b.txn(
            14,
            "25000",
            kind="transfer",
            direction="credit",
            channel="internal",
            counterparty="external-bank-2",
        )
        for n in range(18):
            b.txn(
                13 - n % 12,
                Decimal(300 + (n * 53) % 410),
                kind="purchase",
                direction="debit",
                channel="card",
                counterparty=f"merchant-{n % 6 + 1}",
                hour=9 + n % 10,
            )
        for days, amount in ((5, "4000"), (2, "5000")):
            b.txn(
                days,
                amount,
                kind="transfer",
                direction="debit",
                channel="internal",
                counterparty="p2p-wallet-a",
            )
    elif case_id == "SYN-08-INCOME":
        # Declared income USD 21,000 a year; about USD 72,000 of card spend in 90 days.
        for n in range(6):
            b.txn(
                84 - 14 * n,
                "10000",
                kind="transfer",
                direction="credit",
                channel="internal",
                counterparty="external-bank-1",
            )
        for n in range(30):
            b.txn(
                88 - 3 * n,
                Decimal(1800 + (n * 97) % 900),
                kind="purchase",
                direction="debit",
                channel="card",
                counterparty=f"merchant-{n % 10 + 1}",
            )
    return b.records


def bundle(case_id):
    if case_id not in CASES:
        raise KeyError(case_id)
    inputs = declarations(case_id)
    return SyntheticBundle(
        scenario_id=scenario_id(case_id),
        seed=0,
        profile=CATALOG_PROFILE,
        source_revision=1,
        as_of=AS_OF,
        window_start=AS_OF - timedelta(days=WINDOW_DAYS),
        coverage="partial" if case_id == "SYN-06-PARTIAL" else "complete_declared_window",
        records=tuple(_records(case_id, inputs)),
        declarations=inputs,
    )


def bundle_for_scenario(scenario):
    """The catalog bundle whose scenario ID this is, or None (any other ID)."""
    for case_id in CASES:
        if scenario_id(case_id) == scenario:
            return bundle(case_id)
    return None


def csv_row(case_id):
    return {
        "source_id": case_id,
        "data_classification": "synthetic",
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        **declarations(case_id),
    }
