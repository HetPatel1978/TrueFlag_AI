import { useState, type ReactNode } from 'react';
import { label } from './api';
import { featureLabel } from './terminology';
import type {
  DraftFinding,
  ResearchRetrieval,
  SimulationDraft,
} from './draft-api';
import type { Transaction } from './investigation-api';
import { StatusBadge } from './ui';
import { money as formatMoney, scorePercent } from './format';
import { Timestamp } from './display';

/* ---------- pure helpers (unit tested) ---------- */

/** Exact decimal text -> currency symbol with 2 decimals (half away from zero), no float math. */
export function money(value: string | null, currency: string): string {
  if (value === null || !/^-?\d+(\.\d+)?$/.test(value)) return 'Not available';
  return formatMoney(value, currency);
}

/** One short value for a transaction: "Out · Purchase". */
export function directionShort(direction: string, kind: string) {
  const d = isIncoming(direction)
    ? 'In'
    : direction === 'debit' || direction === 'outgoing'
      ? 'Out'
      : label(direction);
  return `${d} · ${label(kind)}`;
}

/** Compact T-ranges: [1,2,3,5] -> "T1–T3, T5". */
export function ranges(numbers: number[]): string[] {
  const sorted = [...new Set(numbers)].sort((a, b) => a - b);
  const out: string[] = [];
  for (let i = 0; i < sorted.length; i++) {
    let j = i;
    while (j + 1 < sorted.length && sorted[j + 1] === sorted[j] + 1) j++;
    out.push(i === j ? `T${sorted[i]}` : `T${sorted[i]}–T${sorted[j]}`);
    i = j;
  }
  return out;
}

export type KeyFinding = {
  n: number;
  text: string;
  /** Verified finding reference IDs merged into this line. */
  findingIds: string[];
  /** Supporting transaction record IDs. */
  records: string[];
};

const isIncoming = (direction: string) =>
  direction === 'credit' || direction === 'incoming';

type Calc = Extract<DraftFinding, { claim_type: 'calculated_fact' }>;
type Observed = Extract<DraftFinding, { claim_type: 'observed_fact' }>;
type Signal = Extract<DraftFinding, { claim_type: 'model_signal' }>;

/**
 * Verified findings -> at most 5 numbered lines. Calculated facts carrying the same
 * amount, count, currency and window are one line (e.g. volume + concentration).
 */
export function mergeFacts(findings: DraftFinding[], limit = 5): KeyFinding[] {
  const lines: Omit<KeyFinding, 'n'>[] = [];
  const groups = new Map<string, Calc[]>();
  for (const f of findings)
    if (f.claim_type === 'calculated_fact') {
      const r = f.summary.result;
      const key = [
        r.observed_total,
        r.observed_count,
        r.currency,
        r.window.start,
        r.window.end,
      ].join('|');
      groups.set(key, [...(groups.get(key) ?? []), f]);
    }
  for (const group of groups.values()) {
    const r = group[0].summary.result;
    const parts = [
      `${r.observed_count} transaction${r.observed_count === 1 ? '' : 's'}`,
      money(r.observed_total, r.currency),
    ];
    const concentration = group
      .map((f) => f.summary.result.concentration)
      .find((c) => c.length > 0);
    if (concentration?.length === 1) parts.push('100% with one counterparty');
    else if (concentration && concentration.length > 1) {
      const share = concentration[0].share_of_observed_amount;
      parts.push(
        share
          ? `${Math.round(Number(share) * 100)}% with the largest of ${concentration.length} counterparties`
          : `${concentration.length} counterparties`,
      );
    }
    if (
      r.incoming_total !== null &&
      r.outgoing_total !== null &&
      group.some((f) => f.summary.result.calculation === 'incoming_outgoing')
    )
      parts.push(
        `in ${money(r.incoming_total, r.currency)} / out ${money(r.outgoing_total, r.currency)}`,
      );
    lines.push({
      text: parts.join(', '),
      findingIds: group.map((f) => f.reference_id),
      records: [...new Set(group.flatMap((f) => f.supporting_evidence))],
    });
  }
  const observed = findings.filter(
    (f): f is Observed => f.claim_type === 'observed_fact',
  );
  const observedRecords = [
    ...new Set(observed.flatMap((f) => f.supporting_evidence)),
  ];
  // Selected transactions already inside a merged total are folded into that line.
  const host = lines.find(
    (line) =>
      observedRecords.length > 0 &&
      observedRecords.every((r) => line.records.includes(r)),
  );
  if (host) {
    const incoming = observed.filter((f) =>
      isIncoming(f.summary.direction),
    ).length;
    host.text += `; selected amounts ${observed
      .map((f) => money(f.summary.amount, f.summary.currency))
      .join(
        ', ',
      )} (${incoming} incoming, ${observed.length - incoming} outgoing)`;
    host.findingIds.push(...observed.map((f) => f.reference_id));
  } else if (observed.length) {
    const incoming = observed.filter((f) =>
      isIncoming(f.summary.direction),
    ).length;
    const amounts = observed.map((f) =>
      money(f.summary.amount, f.summary.currency),
    );
    lines.push({
      text:
        observed.length === 1
          ? `Selected transaction: ${amounts[0]} ${isIncoming(observed[0].summary.direction) ? 'incoming' : 'outgoing'}`
          : `${observed.length} selected transactions (${incoming} incoming, ${observed.length - incoming} outgoing), amounts ${amounts.join(', ')}`,
      findingIds: observed.map((f) => f.reference_id),
      records: [...new Set(observed.flatMap((f) => f.supporting_evidence))],
    });
  }
  const signal = findings.find(
    (f): f is Signal => f.claim_type === 'model_signal',
  );
  if (signal)
    lines.push({
      text: `Model risk score ${scorePercent(signal.summary.score)} — a model signal, not proof or a probability of crime`,
      findingIds: [signal.reference_id],
      records: [],
    });
  return lines.slice(0, limit).map((line, i) => ({ ...line, n: i + 1 }));
}

/** Only indicators backed by at least one supporting record. */
export function supportedIndicators(
  draft: Pick<SimulationDraft, 'hypotheses'>,
) {
  return draft.hypotheses.filter((h) => h.supporting_evidence.length > 0);
}

const tokens = (code: string) =>
  new Set(
    code
      .split('_')
      .filter(
        (t) => t.length > 3 && !['obtain', 'review', 'resolve'].includes(t),
      ),
  );

/** All missing evidence (items are short) and next steps that do not repeat one of them. */
export function missingAndNext(
  draft: Pick<
    SimulationDraft,
    'missing_evidence' | 'conflicts' | 'questions' | 'unresolved_questions'
  >,
) {
  const missing = [...new Set([...draft.missing_evidence, ...draft.conflicts])];
  const steps = [
    ...new Set([...draft.questions, ...draft.unresolved_questions]),
  ].filter((q) => {
    const words = tokens(q);
    return !missing.some(
      (m) => [...tokens(m)].filter((t) => words.has(t)).length >= 1,
    );
  });
  // Every missing-evidence item is shown; next steps only fill room up to 3 bullets.
  return {
    missing,
    steps: steps.slice(0, Math.max(0, 3 - missing.length)),
  };
}

export function sectionTitle(text: string) {
  const match = /^\W*\s*1020\.\d{3}\s+(.+?)\.(?:\s|$)/.exec(text.trim());
  return match ? match[1] : '';
}

export type SourceRow = {
  id: string; // R1..
  referenceId: string;
  section: string;
  title: string;
  rank?: number;
  score?: string;
  sent: boolean;
  cited: boolean;
  usedIn: number[];
};

/** Plain reason a retrieved source is not in the main Regulatory basis list. */
export const notUsedReason = (s: SourceRow) =>
  s.sent ? 'Not cited by the AI' : 'Not sent: request size limit';

/** Human label for one retrieval input ("risk_driver:totalSpend90d" -> "Total spending · 90 days"). */
/** Plain names of the deterministic evidence-pattern rules (retrieval v5). */
export const PATTERN_LABELS: Readonly<Record<string, string>> = Object.freeze({
  cash_below_reporting_threshold:
    'Cash deposits just below the $10,000 report level',
  rapid_in_out: 'Money out within 48 hours of money in',
  many_sources: 'Incoming money from many senders',
  activity_above_declared_income: 'Outgoing activity above declared income',
  dormant_then_active: 'Quiet account that became active',
});

export function inputLabel(input: string) {
  const [kind, key = ''] = input.split(':');
  if (kind === 'evidence_pattern') return PATTERN_LABELS[key] ?? label(key);
  return kind === 'risk_driver' ? featureLabel(key) : label(key);
}

/** Retrieved sources with R numbering by rank, and which findings use each one. */
export function sourceRows(
  draft: SimulationDraft,
  keyFindings: KeyFinding[],
): SourceRow[] {
  const cited = new Set(
    (draft.regulatory_citations ?? []).map((c) => c.reference_id),
  );
  const links = draft.finding_citations ?? [];
  const usedIn = (ref: string) =>
    keyFindings
      .filter((k) =>
        links.some(
          (l) =>
            l.regulatory_citation === ref &&
            k.findingIds.includes(l.finding_reference_id),
        ),
      )
      .map((k) => k.n);
  const retrieval = draft.retrieval;
  if (retrieval)
    return retrieval.results.map((r, i) => ({
      id: `R${i + 1}`,
      referenceId: r.reference_id,
      section: r.section,
      title: r.title,
      rank: r.rank,
      score: r.score,
      sent: r.sent,
      cited: cited.has(r.reference_id),
      usedIn: usedIn(r.reference_id),
    }));
  return (draft.regulatory_citations ?? []).map((c, i) => ({
    id: `R${i + 1}`,
    referenceId: c.reference_id,
    section: c.section,
    title: sectionTitle(c.text),
    sent: true,
    cited: true,
    usedIn: usedIn(c.reference_id),
  }));
}

/**
 * Indicator text. A coverage gap names the missing evidence only when the data shows it:
 * settlement status is listed as missing and every supporting record is a transaction whose
 * settlement status is not recorded. Otherwise the plain indicator label is kept.
 */
export function indicatorText(
  h: SimulationDraft['hypotheses'][number],
  draft: Pick<SimulationDraft, 'missing_evidence'>,
  transactions: Transaction[],
) {
  if (
    h.question_code === 'coverage_gap_requires_more_evidence' &&
    draft.missing_evidence.includes('settlement_status') &&
    h.supporting_evidence.length > 0 &&
    h.supporting_evidence.every(
      (id) =>
        transactions.find((t) => t.reference.record_version_id === id)
          ?.settlement_status === 'not_recorded',
    )
  )
    return 'Settlement status unknown for';
  return label(h.question_code);
}

export function systemSummary(
  draft: SimulationDraft,
  keyFindings: KeyFinding[],
) {
  const missing = [...draft.missing_evidence, ...draft.conflicts]
    .slice(0, 2)
    .map((m) => label(m).toLowerCase());
  if (draft.outcome === 'abstained')
    return `Not enough evidence to support a finding. The AI abstained${missing.length ? `; missing evidence includes ${missing.join(' and ')}` : ''}.`;
  const lead = keyFindings[0]?.text;
  return lead
    ? `${lead}.`
    : 'Verified observations were selected for analyst review.';
}

/* ---------- card ---------- */

type Props = {
  draft: SimulationDraft;
  status: string;
  requestedAt?: string;
  transactions: Transaction[];
  inspect: (recordId: string) => void;
  openTransactions: () => void;
  header: ReactNode;
};

export function InvestigationResult({
  draft,
  status,
  requestedAt,
  transactions,
  inspect,
  openTransactions,
  header,
}: Props) {
  // Traceability: a finding (F1..) or a source (R1..) lights up everything linked to it.
  const [hover, setHover] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const trace = hover ?? pinned;
  const traceProps = (key: string) => ({
    onMouseEnter: () => setHover(key),
    onMouseLeave: () => setHover(null),
    onFocus: () => setHover(key),
    onBlur: () => setHover(null),
  });
  // The model score is an assessment signal, not an investigation finding (Assess tab, rail).
  const merged = mergeFacts(
    draft.findings.filter((f) => f.claim_type !== 'model_signal'),
  );
  // When the system summary restates the first finding, that finding is shown once, as the
  // conclusion (n = 0); the list continues with the next item, renumbered from 1.
  const leadsSummary =
    draft.outcome !== 'abstained' && status !== 'failed' && merged.length > 0;
  const keyFindings: KeyFinding[] = leadsSummary
    ? [
        { ...merged[0], n: 0 },
        ...merged.slice(1).map((k, i) => ({ ...k, n: i + 1 })),
      ]
    : merged;
  const lead = leadsSummary ? keyFindings[0] : undefined;
  const listed = keyFindings.filter((k) => k.n > 0);
  const sources = sourceRows(draft, keyFindings);
  const indicators = supportedIndicators(draft);
  const { missing, steps } = missingAndNext(draft);
  const tIndex = new Map(
    transactions.map((t, i) => [t.reference.record_version_id, i + 1]),
  );
  const perFinding = (draft.finding_citations ?? []).length > 0;
  const scrollTo = (id: string) => {
    setPinned((current) => (current === id ? null : id));
    const row = document.getElementById(`source-${id}`);
    row?.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
    row?.focus();
  };
  const tChips = (records: string[]) => {
    const numbered = records
      .map((r) => tIndex.get(r))
      .filter((n): n is number => n !== undefined);
    if (!numbered.length) return null;
    if (numbered.length <= 3)
      return numbered
        .sort((a, b) => a - b)
        .map((n) => {
          const record = transactions[n - 1].reference.record_version_id;
          return (
            <button
              key={`T${n}`}
              className="cite-chip"
              aria-label={`Open transaction record T${n}`}
              onClick={() => inspect(record)}
            >
              T{n}
            </button>
          );
        });
    return ranges(numbered).map((r) => (
      <button
        key={r}
        className="cite-chip"
        aria-label={`Show transactions ${r}`}
        onClick={openTransactions}
      >
        {r}
      </button>
    ));
  };
  // Indicator text reads as a list: "T1, T2" or "T1-T3, T5", never chips separated by a space.
  const commaChips = (records: string[]) =>
    tChips(records)?.flatMap((chip, i) =>
      i
        ? [
            <span key={`sep-${i}`} className="chip-sep">
              {', '}
            </span>,
            chip,
          ]
        : [chip],
    );
  const rChips = (refs: string[]) =>
    sources
      .filter((s) => refs.includes(s.referenceId))
      .map((s) => (
        <button
          key={s.id}
          className="cite-chip source"
          aria-label={`Show regulatory source ${s.id}, 31 CFR § ${s.section}`}
          onClick={() => scrollTo(s.id)}
        >
          {s.id}
        </button>
      ));
  const linksFor = (k: KeyFinding) =>
    (draft.finding_citations ?? [])
      .filter((l) => k.findingIds.includes(l.finding_reference_id))
      .map((l) => l.regulatory_citation);
  const findingTraced = (k: KeyFinding) =>
    trace === `F${k.n}` ||
    (trace !== null &&
      sources.some(
        (s) =>
          s.id === trace &&
          (s.usedIn.includes(k.n) || linksFor(k).includes(s.referenceId)),
      ));
  const sourceTraced = (s: SourceRow) =>
    trace === s.id ||
    (trace !== null &&
      trace.startsWith('F') &&
      s.usedIn.includes(Number(trace.slice(1))));
  const conclusionTraced =
    trace === 'F0' ||
    (trace !== null &&
      sources.some(
        (s) =>
          s.id === trace && ((!perFinding && s.cited) || s.usedIn.includes(0)),
      ));
  const usedInText = (n: number) => (n === 0 ? 'Conclusion' : `Finding ${n}`);
  // Main view: only sources the AI cited; the rest are listed once, collapsed, with a reason.
  const used = sources.filter((s) => s.cited || s.usedIn.length > 0);
  const others = sources.filter((s) => !s.cited && s.usedIn.length === 0);
  const rankText = (s: SourceRow) =>
    s.rank !== undefined
      ? `Rank ${s.rank} · text-match score ${s.score ? Number(s.score).toFixed(2) : '–'}`
      : undefined;
  const research = draft.regulatory_context === 'research_unapproved';
  const outcome =
    status === 'failed'
      ? 'failed'
      : draft.outcome === 'abstained'
        ? 'abstained'
        : 'completed';
  const live = draft.live_provider_used;
  return (
    <section className="panel ai-result" aria-labelledby="ai-result-title">
      {header}
      <div className="ai-result-status">
        <StatusBadge value={outcome} />
        <StatusBadge value="verified" />
        <span className="muted">
          {live ? 'Claude (claude-sonnet-5-5)' : 'Offline simulation'}
          {requestedAt ? (
            <>
              {' '}
              · requested <Timestamp value={requestedAt} />
            </>
          ) : null}
        </span>
        {research && sources.length === 0 && <ResearchBadge />}
      </div>

      <div
        className={`ai-result-block${conclusionTraced ? ' is-traced' : ''}`}
        {...(lead ? traceProps('F0') : {})}
      >
        <h4>Conclusion</h4>
        <p className="ai-conclusion">
          {systemSummary(draft, merged)}
          {lead && (
            <span className="chips">
              {tChips(lead.records)}
              {rChips(linksFor(lead))}
            </span>
          )}
        </p>
        <p className="hint">System summary (built from verified results)</p>
      </div>

      {(listed.length > 0 || !lead) && (
        <div className="ai-result-block">
          <h4>Key findings</h4>
          {listed.length ? (
            <ol className="key-findings">
              {listed.map((k) => (
                <li
                  key={k.n}
                  className={findingTraced(k) ? 'is-traced' : undefined}
                  {...traceProps(`F${k.n}`)}
                >
                  <span>{k.text}</span>
                  <span className="chips">
                    {tChips(k.records)}
                    {rChips(linksFor(k))}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">No supported findings were returned.</p>
          )}
        </div>
      )}

      {sources.length > 0 && (
        <div className="ai-result-block">
          <h4>Regulatory basis {research && <ResearchBadge />}</h4>
          <ul className="source-rows">
            {used.map((s) => (
              <li
                key={s.id}
                id={`source-${s.id}`}
                tabIndex={-1}
                title={rankText(s)}
                className={sourceTraced(s) ? 'is-traced' : undefined}
                {...traceProps(s.id)}
              >
                <b>{s.id}</b>
                <span className="source-title">
                  § {s.section}
                  {s.title && <> {s.title}</>}
                </span>
                <span className="used-in">
                  {`Used in: ${s.usedIn.length ? s.usedIn.map(usedInText).join(', ') : 'Conclusion'}`}
                </span>
              </li>
            ))}
          </ul>
          {others.length > 0 && (
            <details className="also-retrieved">
              <summary>Also retrieved ({others.length})</summary>
              <ul className="source-rows">
                {others.map((s) => (
                  <li
                    key={s.id}
                    id={`source-${s.id}`}
                    tabIndex={-1}
                    title={rankText(s)}
                  >
                    <b>{s.id}</b>
                    <span className="source-title">
                      § {s.section}
                      {s.title && <> {s.title}</>}
                    </span>
                    <span className="used-in muted">{notUsedReason(s)}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
          <RetrievalNote retrieval={draft.retrieval} />
        </div>
      )}

      {indicators.length > 0 && (
        <div className="ai-result-block">
          <h4>
            Potential risk indicators{' '}
            <span className="hint">
              · unconfirmed hypotheses, not factual allegations
            </span>
          </h4>
          <ul className="plain-list">
            {indicators.map((h) => (
              <li key={h.question_code}>
                {indicatorText(h, draft, transactions)}{' '}
                <span className="chips chip-list">
                  {commaChips(h.supporting_evidence)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(missing.length > 0 || steps.length > 0) && (
        <div className="ai-result-block">
          <h4>Missing evidence</h4>
          <ul className="plain-list inline-list">
            {missing.map((m) => (
              <li key={m}>{label(m)}</li>
            ))}
            {steps.map((q) => (
              <li key={q}>Next step: {label(q)}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function RetrievalNote({
  retrieval,
}: {
  retrieval?: ResearchRetrieval | null;
}) {
  if (!retrieval)
    return (
      <p className="hint">
        Retrieved with the earlier fixed query “suspicious transactions” (2
        sections). Per-case retrieval and per-finding links apply to new runs.
      </p>
    );
  const strong = retrieval.strong_matches;
  return (
    <>
      <details className="retrieval-how">
        <summary>
          How sources were retrieved · Top {retrieval.results.length} of{' '}
          {retrieval.total_chunks} sections ·{' '}
          {retrieval.weighted_terms
            ? 'case-term ranking'
            : 'text-match ranking'}
        </summary>
        <p className="hint">
          {retrieval.total_chunks} sections searched
          {strong !== undefined
            ? ` · ${strong} strong match${strong === 1 ? '' : 'es'} (results below 25% of the top score dropped)`
            : ` · top ${retrieval.results.length} kept`}
          {retrieval.matched_chunks < 3 &&
            ` · only ${retrieval.matched_chunks} matched the query (not padded)`}
        </p>
        <p className="hint">Query words: {retrieval.terms.join(', ')}</p>
        <p className="hint">
          From case inputs: {retrieval.inputs.map(inputLabel).join(', ')}
        </p>
        {retrieval.patterns && (
          <p className="hint">
            Evidence patterns found:{' '}
            {retrieval.patterns.length
              ? retrieval.patterns
                  .map(
                    (p) =>
                      `${PATTERN_LABELS[p.rule] ?? label(p.rule)} (${p.observed}; rule: ${p.threshold})`,
                  )
                  .join('; ')
              : 'none'}
            . Sections containing more of these words rank first; pattern words
            count three times, then the text-match score breaks ties.
          </p>
        )}
        {retrieval.dropped_inputs && retrieval.dropped_inputs.length > 0 && (
          <p className="hint">
            Left out because every case has them:{' '}
            {retrieval.dropped_inputs.map(inputLabel).join(', ')}
          </p>
        )}
        {retrieval.excerpt_cap_bytes !== undefined && (
          <p className="hint">
            Each source was sent to the AI as an excerpt of its most relevant
            lines (up to {retrieval.excerpt_cap_bytes.toLocaleString('en-US')}{' '}
            bytes per section).
          </p>
        )}
      </details>
    </>
  );
}

/** Required label on research-only regulatory content (kept verbatim), as a small badge. */
function ResearchBadge() {
  return (
    <span className="research-badge" role="note">
      Unapproved research · Not production regulatory guidance
    </span>
  );
}
