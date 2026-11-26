"""Per-case lexical retrieval over the hash-verified 31 CFR Part 1020 research snapshot.

Model fields (e.g. nbrPaymentsCashLike90d) never appear in regulation text, so each case
input is mapped through a small fixed table to plain regulatory terms. Ranking is the
PostgreSQL English ``ts_rank_cd`` with OR semantics: a text-match score, not a similarity.
"""

import json
import re
from decimal import Decimal

from sqlalchemy import text

# Model feature -> plain regulatory terms. Fixed, reviewed table; no generated vocabulary.
FEATURE_TERMS = {
    "kycRiskScore": "customer identification verification",
    "income": "customer occupation business",
    "tenureMonths": "account opened customer relationship",
    "creditScore": "customer credit",
    "state": "address location",
    "nbrPurchases90d": "transaction purchase",
    "avgTxnSize90d": "transaction amount",
    "totalSpend90d": "transaction amount aggregate",
    "nbrDistinctMerch90d": "merchant counterparty",
    "nbrMerchCredits90d": "credit refund return funds",
    "nbrMerchCreditsRndDollarAmt90d": "credit refund structured amount",
    "totalMerchCred90d": "credit refund return funds",
    "nbrMerchCreditsWoOffsettingPurch": "credit refund return funds",
    "nbrPayments90d": "payment transfer funds",
    "totalPaymentAmt90d": "payment transfer funds amount",
    "overpaymentAmt90d": "overpayment refund return funds",
    "overpaymentInd90d": "overpayment refund return funds",
    "nbrCustReqRefunds90d": "refund return funds",
    "totalRefundsToCust90d": "refund return funds",
    "nbrPaymentsCashLike90d": "cash currency transaction",
    "maxRevolveLine": "credit account",
    "indOwnsHome": "address residence",
    "nbrInquiries1y": "inquiry request",
    "nbrCollections3y": "collection debt",
    "nbrWebLogins90d": "online access account",
    "nbrPointRed90d": "reward redemption",
    "PEP": "senior foreign political figure",
}

# Missing-evidence / conflict / calculation codes -> plain regulatory terms.
EVIDENCE_TERMS = {
    "comparable_expected_activity": "customer due diligence risk profile",
    "curated_documents": "documents records verification",
    "sampling_metadata": "records retained",
    "settlement_status": "transaction records",
    "selected_model_assessment": "monitoring",
    "contradictory_kyc_observations": "customer identification verification information",
    "counterparty_concentration": "counterparty transfer",
}

MAX_DRIVERS = 3
MAX_TERMS = 40
TOP_K = 3
# Results scoring below this fraction of the top result's score are dropped as noise.
# The top result always stays, so any match returns at least one section.
MIN_RELATIVE_SCORE = "0.25"
# Passage text sent to Claude is bounded so the exact request stays within its byte limit.
PASSAGE_BUDGET_BYTES = 24000
_WORD = re.compile(r"^[a-z]{3,24}$")


def case_inputs(packet):
    """Ordered, de-duplicated case inputs taken from the verified investigation packet."""
    if not isinstance(packet, dict):
        packet = packet.model_dump(mode="json")
    inputs = []
    signal = packet.get("model_signal")
    features = ((signal or {}).get("explanation") or {}).get("features") or []
    drivers = sorted(
        (
            f
            for f in features
            if f.get("direction") == "raises_score"
            and not f.get("missing")
            and f.get("name") in FEATURE_TERMS
        ),
        key=lambda f: (-float(f["contribution"]), f["name"]),
    )
    inputs += ["risk_driver:" + f["name"] for f in drivers[:MAX_DRIVERS]]
    get = packet.get
    facts = get("facts") or []
    if any(((f.get("result") or {}).get("concentration")) for f in facts):
        inputs.append("calculation:counterparty_concentration")
    inputs += ["missing_evidence:" + c for c in get("missing_evidence") or [] if c in EVIDENCE_TERMS]
    inputs += ["conflict:" + c for c in get("conflicts") or [] if c in EVIDENCE_TERMS]
    return list(dict.fromkeys(inputs))[:20]


def map_terms(inputs):
    """Case inputs -> unique plain words, in input order. Unknown inputs contribute nothing."""
    words = []
    for item in inputs:
        kind, _, key = item.partition(":")
        phrase = FEATURE_TERMS.get(key) if kind == "risk_driver" else EVIDENCE_TERMS.get(key)
        for word in (phrase or "").split():
            if _WORD.match(word):
                words.append(word)
    return list(dict.fromkeys(words))[:MAX_TERMS]


def query_terms(value):
    """Free-text test query -> unique plain words (same word rule and limits as case terms)."""
    words = [w for w in re.findall(r"[a-z]+", str(value).lower()) if _WORD.match(w)]
    terms = list(dict.fromkeys(words))[:MAX_TERMS]
    while terms and len(" ".join(terms)) > 256:
        terms.pop()
    return terms


def or_query(terms):
    """OR semantics: any single matching term admits a section (never all-terms-required)."""
    if not terms or any(not _WORD.match(t) for t in terms):
        raise ValueError("invalid_retrieval_terms")
    return " | ".join(terms)


def title_of(body_text):
    match = re.match(r"^\W*\s*1020\.[0-9]{3}\s+(.+?)\.(?:\s|$)", body_text.strip())
    return (match.group(1) if match else "")[:200]


def strong_matches(ranked, minimum=MIN_RELATIVE_SCORE):
    """Keep results scoring at least ``minimum`` x the top score, in rank order (exact decimals)."""
    if not ranked:
        return []
    floor = Decimal(ranked[0][1]) * Decimal(minimum)
    return [(section, score) for section, score in ranked if Decimal(score) >= floor]


def rank(session, chunks, query, limit=TOP_K):
    """Top sections by ts_rank_cd > 0. Fewer than ``limit`` is returned as-is, never padded."""
    rows = session.execute(
        text(
            """WITH candidates AS (
                 SELECT * FROM jsonb_to_recordset(CAST(:chunks AS jsonb))
                   AS c(section text, body_text text)
               ), scored AS (
                 SELECT section,
                        ts_rank_cd(to_tsvector('english', body_text),
                                   to_tsquery('english', :query)) AS score
                 FROM candidates
                 WHERE to_tsvector('english', body_text) @@ to_tsquery('english', :query)
               ), matched AS (SELECT count(*) AS n FROM scored WHERE score > 0)
               SELECT section, to_char(round(score::numeric, 6), 'FM999990.000000') AS score,
                      (SELECT n FROM matched) AS matched
               FROM scored WHERE score > 0
               ORDER BY score DESC, section LIMIT :limit"""
        ),
        {
            "chunks": json.dumps(
                [{"section": c["section"], "body_text": c["body_text"]} for c in chunks]
            ),
            "query": query,
            "limit": limit,
        },
    ).all()
    return [(r.section, r.score) for r in rows], (rows[0].matched if rows else 0)


# Bounded excerpts: each strong match is sent as its most query-relevant lines so that every
# strong match fits in the request (3 x 4000 bytes, well under PASSAGE_BUDGET_BYTES).
EXCERPT_CAP_BYTES = 4000
EXCERPT_GAP = "\n[…]\n"
_LABEL_BYTES = 60  # short label lines such as "(a)" or "General." kept before a chosen line


def line_spans(body_text):
    """(start, end) UTF-8 byte offsets of each line, newline excluded."""
    spans, start = [], 0
    for line in body_text.encode().split(b"\n"):
        spans.append((start, start + len(line)))
        start += len(line) + 1
    return spans


def score_lines(session, body_text, query):
    """ts_rank_cd of each line against the same OR query (6 dp text; "0.000000" = no match)."""
    data = body_text.encode()
    lines = [
        {"n": n, "body_text": data[s:e].decode()} for n, (s, e) in enumerate(line_spans(body_text))
    ]
    rows = session.execute(
        text(
            """SELECT n, to_char(round(ts_rank_cd(to_tsvector('english', body_text),
                                  to_tsquery('english', :query))::numeric, 6),
                           'FM999990.000000') AS score
               FROM jsonb_to_recordset(CAST(:lines AS jsonb)) AS c(n int, body_text text)
               ORDER BY n"""
        ),
        {"lines": json.dumps(lines), "query": query},
    ).all()
    return [r.score for r in rows]


def excerpt(body_text, scores, cap=EXCERPT_CAP_BYTES):
    """Deterministic bounded excerpt -> (text, [(start, end), ...]).

    A section that fits is sent whole. Otherwise: the heading line, then matching lines by
    score (ties in document order), each with up to two short label lines before it, while
    the excerpt stays within ``cap`` bytes. Chosen lines are kept in document order;
    non-adjacent runs are joined with a visible "[…]" marker."""
    data = body_text.encode()
    if len(data) <= cap:
        return body_text, [(0, len(data))]
    spans = line_spans(body_text)
    size = lambda n: spans[n][1] - spans[n][0]  # noqa: E731
    gap = len(EXCERPT_GAP.encode())
    chosen = set()

    def cost(extra):
        picked = sorted(chosen | extra)
        runs = 1 + sum(1 for a, b in zip(picked, picked[1:]) if b != a + 1)
        return sum(size(n) for n in picked) + (len(picked) - runs) + gap * (runs - 1)

    if size(0) <= cap:
        chosen.add(0)
    order = sorted(
        (n for n in range(1, len(spans)) if Decimal(scores[n]) > 0),
        key=lambda n: (-Decimal(scores[n]), n),
    )
    for n in order:
        extra = {n}
        for j in (n - 1, n - 2):
            if j > 0 and size(j) <= _LABEL_BYTES and j not in chosen:
                extra.add(j)
            else:
                break
        if cost(extra) <= cap:
            chosen |= extra
        elif n not in chosen and cost({n}) <= cap:
            chosen.add(n)
    picked = sorted(chosen)
    runs = []
    for n in picked:
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    ranges = [(spans[a][0], spans[b][1]) for a, b in runs]
    result = EXCERPT_GAP.join(data[s:e].decode() for s, e in ranges)
    if not ranges or len(result.encode()) > cap:
        raise ValueError("excerpt_unavailable")
    return result, ranges
