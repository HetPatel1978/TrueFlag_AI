"""Reproducible synthetic feature declarations for explicitly labeled demo scenarios."""

import random


def demo_declarations(base, seed):
    """Vary declarations only; they are not calculated from generated transactions."""
    rng = random.Random(seed)
    result = dict(base)
    ranges = {
        "tenureMonths": (2, 6, 12, 24, 48, 120),
        "creditScore": (450, 550, 650, 720, 800),
        "nbrPurchases90d": (2, 8, 20, 60, 150),
        "avgTxnSize90d": (25, 50, 100, 500, 2000),
        "totalSpend90d": (200, 400, 2000, 10000, 50000),
        "nbrDistinctMerch90d": (1, 2, 10, 40),
        "nbrMerchCredits90d": (0, 1, 4, 10, 25),
        "nbrMerchCreditsRndDollarAmt90d": (0, 1, 4, 10),
        "totalMerchCred90d": (0, 100, 1000, 5000, 20000),
        "nbrMerchCreditsWoOffsettingPurch": (0, 1, 4, 10),
        "nbrPayments90d": (1, 4, 12, 30, 60),
        "totalPaymentAmt90d": (100, 200, 1000, 10000, 50000),
        "overpaymentAmt90d": (0, 0, 100, 1000, 10000),
        "overpaymentInd90d": (0, 1),
        "nbrCustReqRefunds90d": (0, 0, 1, 4, 10),
        "totalRefundsToCust90d": (0, 0, 100, 1000, 10000),
        "nbrPaymentsCashLike90d": (0, 1, 4, 10, 25),
        "maxRevolveLine": (500, 3000, 10000, 25000, 50000),
        "indOwnsHome": (0, 1),
        "nbrInquiries1y": (0, 1, 3, 8, 20),
        "nbrCollections3y": (0, 0, 1, 3, 8),
        "nbrWebLogins90d": (0, 8, 20, 60, 150),
        "nbrPointRed90d": (0, 0, 1, 5, 20),
        "PEP": (0, 0, 0, 1),
    }
    for field, choices in ranges.items():
        result[field] = rng.choice(choices)
    return result
