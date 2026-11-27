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
    inputs += [
        "missing_evidence:" + c for c in get("missing_evidence") or [] if c in EVIDENCE_TERMS
    ]
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


# ---- v5: case-specific terms and deterministic evidence-pattern terms ----------------------
#
# v1-v4 records keep the functions above unchanged (their stored inputs re-run through
# map_terms/rank exactly as recorded). v5 changes three things for new records only:
#  1. Inputs present in every case are dropped: the four missing-evidence codes the packet
#     always lists, and the counterparty-concentration calculation (computed for every case
#     with transactions). They are kept in the record as "dropped_inputs" for transparency.
#  2. Evidence-pattern terms come from fixed rules over the case's own transactions (no AI).
#  3. Ranking scores each section by the weighted distinct query terms it contains (pattern
#     terms 3, other case terms 1), then ts_rank_cd, ordered numerically. (rank() above sorts
#     its text-formatted score, so a score of 10 or more sorts below single-digit scores;
#     it is kept as-is so v1-v4 records still re-run identically.)

ALWAYS_PRESENT_INPUTS = (
    "calculation:counterparty_concentration",
    "missing_evidence:comparable_expected_activity",
    "missing_evidence:curated_documents",
    "missing_evidence:sampling_metadata",
    "missing_evidence:settlement_status",
)
PATTERN_WEIGHT = 3
CASE_TERM_WEIGHT = 1

REPORTING_THRESHOLD = Decimal("10000")
NEAR_THRESHOLD_FLOOR = Decimal("9000")  # within 10% below the USD 10,000 currency report level
NEAR_THRESHOLD_MIN_COUNT = 3
RAPID_HOURS = 48
RAPID_MIN_SHARE = Decimal("0.90")
RAPID_MIN_PAIRS = 3
MANY_SOURCES_MIN = 10
INCOME_MULTIPLE = Decimal("3")
DORMANT_MIN_DAYS = 60
DORMANT_MIN_EVENTS = 10

# Rule -> (plain description with threshold, regulatory terms). Fixed, reviewed table.
PATTERN_RULES = {
    "cash_below_reporting_threshold": (
        f"At least {NEAR_THRESHOLD_MIN_COUNT} cash-like deposits of USD 9,000 to 9,999.99 "
        "(just below the USD 10,000 currency transaction report level)",
        "structured currency reports aggregation",
    ),
    "rapid_in_out": (
        f"At least {RAPID_MIN_PAIRS} incoming amounts each followed within {RAPID_HOURS} hours "
        "by an outgoing amount of 90-100% of it",
        "transfer transmittal originator beneficiary",
    ),
    "many_sources": (
        f"Incoming amounts from at least {MANY_SOURCES_MIN} distinct counterparties",
        "multiple sources aggregate aggregation",
    ),
    "activity_above_declared_income": (
        "Outgoing amounts in the window, annualized, at least "
        f"{INCOME_MULTIPLE}x the declared annual income",
        "diligence beneficial ownership profile",
    ),
    "dormant_then_active": (
        f"No activity for the first {DORMANT_MIN_DAYS}+ days of the window, then at least "
        f"{DORMANT_MIN_EVENTS} transactions",
        "ongoing monitoring update risk",
    ),
}


def _get(item, name):
    return item.get(name) if isinstance(item, dict) else getattr(item, name)


def _moment(value):
    from datetime import datetime

    return datetime.fromisoformat(value) if isinstance(value, str) else value


def evidence_patterns(packet, declared_income):
    """Fired rules for this case, in fixed rule order: [{rule, observed, threshold}].

    Uses only the packet's own USD transactions with a recorded time and the alert's
    declared annual income; nothing is inferred when data is missing."""
    if not isinstance(packet, dict):
        packet = packet.model_dump(mode="json")
    rows = [
        t
        for t in packet.get("transactions") or []
        if _get(t, "currency") == "USD" and _get(t, "event_at") is not None
    ]
    rows.sort(key=lambda t: _moment(_get(t, "event_at")))
    credits = [t for t in rows if _get(t, "direction") == "credit"]
    debits = [t for t in rows if _get(t, "direction") == "debit"]

    def amount(t):
        return Decimal(str(_get(t, "amount")))

    def when(t):
        return _moment(_get(t, "event_at"))

    fired = []
    near = [
        t
        for t in credits
        if _get(t, "channel") == "cashlike"
        and NEAR_THRESHOLD_FLOOR <= amount(t) < REPORTING_THRESHOLD
    ]
    if len(near) >= NEAR_THRESHOLD_MIN_COUNT:
        fired.append(
            dict(
                rule="cash_below_reporting_threshold",
                observed=str(len(near)),
                threshold=str(NEAR_THRESHOLD_MIN_COUNT),
            )
        )

    used, pairs = set(), 0
    for credit in credits:
        for index, debit in enumerate(debits):
            hours = (when(debit) - when(credit)).total_seconds() / 3600
            if (
                index not in used
                and 0 < hours <= RAPID_HOURS
                and amount(credit) * RAPID_MIN_SHARE <= amount(debit) <= amount(credit)
            ):
                used.add(index)
                pairs += 1
                break
    if pairs >= RAPID_MIN_PAIRS:
        fired.append(dict(rule="rapid_in_out", observed=str(pairs), threshold=str(RAPID_MIN_PAIRS)))

    sources = {_get(t, "counterparty_handle") for t in credits} - {None}
    if len(sources) >= MANY_SOURCES_MIN:
        fired.append(
            dict(rule="many_sources", observed=str(len(sources)), threshold=str(MANY_SOURCES_MIN))
        )

    window = next((_get(_get(f, "result"), "window") for f in packet.get("facts") or []), None)
    if window is not None:
        start, end = _moment(_get(window, "start")), _moment(_get(window, "end"))
        days = Decimal(str((end - start).total_seconds())) / Decimal(86400)
        if declared_income is not None and Decimal(str(declared_income)) > 0 and days > 0:
            outgoing = sum((amount(t) for t in debits), Decimal(0))
            annualized = (outgoing * Decimal(365) / days).quantize(Decimal("1"))
            limit = (Decimal(str(declared_income)) * INCOME_MULTIPLE).quantize(Decimal("1"))
            if annualized >= limit:
                fired.append(
                    dict(
                        rule="activity_above_declared_income",
                        observed=str(annualized),
                        threshold=str(limit),
                    )
                )
        if rows:
            quiet = (when(rows[0]) - start).days
            if quiet >= DORMANT_MIN_DAYS and len(rows) >= DORMANT_MIN_EVENTS:
                fired.append(
                    dict(
                        rule="dormant_then_active",
                        observed=f"{quiet} days quiet, {len(rows)} transactions",
                        threshold=f"{DORMANT_MIN_DAYS} days, {DORMANT_MIN_EVENTS} transactions",
                    )
                )
    return fired


def case_inputs_v5(packet, declared_income):
    """v5 inputs: top-3 drivers, fired evidence patterns, case-specific gaps and conflicts.

    Returns (inputs, patterns, dropped); inputs present in every case are dropped."""
    full = case_inputs(packet)
    dropped = [i for i in full if i in ALWAYS_PRESENT_INPUTS]
    kept = [i for i in full if i not in ALWAYS_PRESENT_INPUTS]
    patterns = evidence_patterns(packet, declared_income)
    drivers = [i for i in kept if i.startswith("risk_driver:")]
    others = [i for i in kept if not i.startswith("risk_driver:")]
    inputs = drivers + ["evidence_pattern:" + p["rule"] for p in patterns] + others
    return list(dict.fromkeys(inputs))[:20], patterns, dropped


def weighted_terms_v5(inputs):
    """Unique (term, weight) pairs: evidence-pattern terms weigh 3, other case terms 1."""
    weights = {}
    for item in inputs:
        kind, _, key = item.partition(":")
        if kind == "evidence_pattern":
            phrase, weight = PATTERN_RULES.get(key, (None, ""))[1], PATTERN_WEIGHT
        elif kind == "risk_driver":
            phrase, weight = FEATURE_TERMS.get(key), CASE_TERM_WEIGHT
        else:
            phrase, weight = EVIDENCE_TERMS.get(key), CASE_TERM_WEIGHT
        for word in (phrase or "").split():
            if _WORD.match(word):
                weights[word] = max(weights.get(word, 0), weight)
    ordered = sorted(weights.items(), key=lambda kv: -kv[1])  # stable: pattern terms first
    return ordered[:MAX_TERMS]


def rank_v5(session, chunks, weighted, limit=TOP_K):
    """Sections by weighted distinct-term coverage, then ts_rank_cd; numeric ordering.

    The score is coverage + r/(1+r) (r = ts_rank_cd), so coverage always decides first and
    ts_rank_cd only breaks ties. Fewer than ``limit`` results are returned as-is."""
    if not weighted or any(not _WORD.match(t) for t, _ in weighted):
        raise ValueError("invalid_retrieval_terms")
    rows = session.execute(
        text(
            """WITH c AS (
                 SELECT section, to_tsvector('english', body_text) AS v
                 FROM jsonb_to_recordset(CAST(:chunks AS jsonb)) AS c(section text, body_text text)
               ), t AS (
                 SELECT term, weight FROM jsonb_to_recordset(CAST(:terms AS jsonb))
                   AS t(term text, weight int)
               ), s AS (
                 SELECT c.section,
                        sum(CASE WHEN c.v @@ to_tsquery('english', t.term) THEN t.weight
                                 ELSE 0 END) AS coverage,
                        ts_rank_cd(c.v, to_tsquery('english', :query)) AS r
                 FROM c CROSS JOIN t GROUP BY c.section, c.v
               ), scored AS (
                 SELECT section, round((coverage + r / (1 + r))::numeric, 6) AS value
                 FROM s WHERE coverage > 0
               )
               SELECT section, to_char(value, 'FM999990.000000') AS score,
                      (SELECT count(*) FROM scored) AS matched
               FROM scored ORDER BY value DESC, section LIMIT :limit"""
        ),
        {
            "chunks": json.dumps(
                [{"section": c["section"], "body_text": c["body_text"]} for c in chunks]
            ),
            "terms": json.dumps([{"term": t, "weight": w} for t, w in weighted]),
            "query": or_query([t for t, _ in weighted]),
            "limit": limit,
        },
    ).all()
    return [(r.section, r.score) for r in rows], (rows[0].matched if rows else 0)
