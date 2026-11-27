// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import type { DraftFinding, SimulationDraft } from './draft-api';
import type { Transaction } from './investigation-api';
import {
  InvestigationResult,
  mergeFacts,
  missingAndNext,
  money,
  ranges,
  sourceRows,
  supportedIndicators,
  systemSummary,
  indicatorText,
} from './investigation-result';

afterEach(cleanup);

const window = { start: '2025-10-03T00:00:00Z', end: '2026-01-01T00:00:00Z' };
const ids = Array.from(
  { length: 12 },
  (_, i) => `00000000-0000-4000-8000-${String(i).padStart(12, '0')}`,
);
const tx = (i: number, direction = 'incoming'): Transaction => ({
  reference: {
    record_version_id: ids[i],
    identity_id: 'i',
    source_version_id: 's',
    kind: 'transaction',
    version: 1,
    sha256: 'a'.repeat(64),
  },
  account_handle: null,
  counterparty_handle: 'cp-1',
  amount: '54.13083333',
  currency: 'USD',
  event_at: window.start,
  original_time: 'explicit_offset',
  event_kind: 'transfer',
  direction,
  channel: 'not_recorded',
  reverses_handle: null,
  settlement_status: 'not_recorded',
});
const activity = (calculation: string, concentration = false) => ({
  calculation,
  status: 'complete_declared_window',
  currency: 'USD' as const,
  window,
  treatment: 'gross_observations',
  observed_count: 12,
  observed_total: '649.57000000',
  incoming_total: '300.00000000',
  outgoing_total: '349.57000000',
  reversal_observations: 0,
  unmatched_reversals: 0,
  verified_reversal_pairs_excluded: 0,
  buckets: [],
  concentration: concentration
    ? [
        {
          counterparty_handle: 'cp-1',
          observed_count: 12,
          observed_total: '649.57000000',
          share_of_observed_amount: '1',
        },
      ]
    : [],
});
const calc = (
  ref: string,
  calculation: string,
  concentration = false,
): DraftFinding =>
  ({
    claim_type: 'calculated_fact',
    reference_id: ref,
    supporting_evidence: ids,
    contradictory_evidence: [],
    summary: {
      reference_id: ref,
      input_record_ids: ids,
      result: activity(calculation, concentration),
      coverage: {
        status: 'complete_declared_window',
        unknown_time_excluded: 0,
        outside_window_excluded: 0,
        limitations: [],
      },
    },
  }) as DraftFinding;

const base: SimulationDraft = {
  content_sha256: 'e'.repeat(64),
  draft_run_id: 'run',
  investigation_run_id: 'parent',
  manifest_sha256: 'd'.repeat(64),
  packet_sha256: 'c'.repeat(64),
  outcome: 'draft_ready',
  findings: [
    calc('fact-volume', 'count_totals'),
    calc('fact-concentration', 'concentration', true),
  ],
  hypotheses: [
    {
      question_code: 'review_observed_concentration',
      supporting_evidence: [ids[0]],
      contradictory_evidence: [],
      uncertainty: 'unconfirmed_requires_human_review',
    },
    {
      question_code: 'coverage_gap_requires_more_evidence',
      supporting_evidence: [],
      contradictory_evidence: [],
      uncertainty: 'unconfirmed_requires_human_review',
    },
  ],
  questions: [
    'obtain_comparable_declared_activity_expectations',
    'review_authorized_source_observations',
  ],
  unresolved_questions: [],
  next_steps: ['human_review'],
  missing_evidence: [
    'comparable_expected_activity',
    'curated_documents',
    'sampling_metadata',
    'settlement_status',
  ],
  conflicts: [],
  limitations: ['synthetic_observations_only'],
  provenance: {
    provider: 'anthropic',
    model: 'claude-sonnet-5-5',
    prompt_version: 'p',
    prompt_sha256: 'e'.repeat(64),
    configuration_sha256: 'f'.repeat(64),
    parent_manifest_sha256: 'd'.repeat(64),
  },
  verification: 'source_reference_numeric_checks_passed',
  semantic_review: 'pending_human_review',
  regulatory_context: 'research_unapproved',
  regulatory_citations: [
    {
      reference_id: 'src-320',
      section: '1020.320',
      text: '§ 1020.320 Reports by banks of suspicious transactions. (a) ...',
      source_url:
        'https://www.ecfr.gov/api/versioner/v1/full/2026-11-02/title-31.xml',
      publisher: 'eCFR',
      historical_as_of: '2026-11-02',
      raw_sha256: 'a'.repeat(64),
      text_sha256: 'b'.repeat(64),
      approval_status: 'unapproved_research',
      origin: 'official_public_research',
    },
  ],
  simulation: false,
  live_provider_used: true,
};
const retrieval = {
  method: 'postgresql_english_ts_rank_cd_or_v1',
  inputs: [
    'risk_driver:nbrPaymentsCashLike90d',
    'missing_evidence:settlement_status',
  ],
  terms: ['cash', 'currency', 'transaction', 'records'],
  query: 'cash | currency | transaction | records',
  total_chunks: 24,
  matched_chunks: 9,
  passage_budget_bytes: 24000,
  results: [
    {
      reference_id: 'src-320',
      rank: 1,
      section: '1020.320',
      title: 'Reports by banks of suspicious transactions',
      score: '0.400000',
      chunk_sha256: 'b'.repeat(64),
      text_bytes: 8107,
      sent: true,
    },
    {
      reference_id: 'src-310',
      rank: 2,
      section: '1020.310',
      title: 'Reports of transactions in currency',
      score: '0.200000',
      chunk_sha256: 'c'.repeat(64),
      text_bytes: 183,
      sent: true,
    },
    {
      reference_id: 'src-410',
      rank: 3,
      section: '1020.410',
      title: 'Records to be made and retained by banks',
      score: '0.100000',
      chunk_sha256: 'd'.repeat(64),
      text_bytes: 16885,
      sent: false,
    },
  ],
};

describe('pure helpers', () => {
  it('formats exact decimals as money with 2 decimals', () => {
    expect(money('649.57000000', 'USD')).toBe('$649.57');
    expect(money('1234.565', 'USD')).toBe('$1,234.57');
    expect(money('0.004', 'EUR')).toBe('€0.00');
  });

  it('merges calculated facts that carry the same numbers into one line', () => {
    const lines = mergeFacts(base.findings);
    expect(lines).toHaveLength(1);
    expect(lines[0].text).toBe(
      '12 transactions, $649.57, 100% with one counterparty',
    );
    expect(lines[0].findingIds).toEqual(['fact-volume', 'fact-concentration']);
    expect(lines[0].records).toHaveLength(12);
  });

  it('keeps facts with different numbers separate and caps the list at 5', () => {
    const other = calc('fact-other', 'velocity');
    (
      other as { summary: { result: { observed_count: number } } }
    ).summary.result.observed_count = 3;
    expect(mergeFacts([...base.findings, other])).toHaveLength(2);
    const many = Array.from({ length: 8 }, (_, i) => {
      const f = calc(`f${i}`, 'count_totals');
      (
        f as { summary: { result: { observed_count: number } } }
      ).summary.result.observed_count = i + 1;
      return f;
    });
    expect(mergeFacts(many)).toHaveLength(5);
  });

  it('folds selected transactions into the total that already contains them', () => {
    const observed = [0, 1].map(
      (i) =>
        ({
          claim_type: 'observed_fact',
          reference_id: ids[i],
          supporting_evidence: [ids[i]],
          contradictory_evidence: [],
          summary: tx(i, i ? 'debit' : 'credit'),
        }) as DraftFinding,
    );
    const lines = mergeFacts([...base.findings, ...observed]);
    expect(lines).toHaveLength(1);
    expect(lines[0].text).toBe(
      '12 transactions, $649.57, 100% with one counterparty; selected amounts $54.13, $54.13 (1 incoming, 1 outgoing)',
    );
  });

  it('hides risk indicators with no supporting record', () => {
    expect(supportedIndicators(base).map((h) => h.question_code)).toEqual([
      'review_observed_concentration',
    ]);
  });

  it('shows every missing item and drops next steps that repeat them', () => {
    const value = missingAndNext(base);
    expect(value.missing).toHaveLength(4); // all items, no "+1 more in Audit details"
    expect(value).not.toHaveProperty('more');
    expect(value.steps).toEqual([]); // no room left within 3 bullets
    const fewer = missingAndNext({
      ...base,
      missing_evidence: ['comparable_expected_activity'],
    });
    expect(fewer.missing).toEqual(['comparable_expected_activity']);
    // The repeating "obtain comparable ... activity" step is dropped; the distinct one stays.
    expect(fewer.steps).toEqual(['review_authorized_source_observations']);
  });

  it('compacts transaction references into ranges', () => {
    expect(ranges([3, 1, 2, 5])).toEqual(['T1–T3', 'T5']);
  });

  it('says plainly when the AI abstained', () => {
    const text = systemSummary({ ...base, outcome: 'abstained' }, []);
    expect(text).toMatch(/^Not enough evidence to support a finding\./);
  });

  it('maps retrieved sources to the findings that use them', () => {
    const draft = {
      ...base,
      retrieval,
      finding_citations: [
        {
          finding_reference_id: 'fact-concentration',
          regulatory_citation: 'src-320',
        },
      ],
    };
    const rows = sourceRows(draft, mergeFacts(draft.findings));
    expect(rows.map((r) => [r.id, r.section, r.usedIn])).toEqual([
      ['R1', '1020.320', [1]],
      ['R2', '1020.310', []],
      ['R3', '1020.410', []],
    ]);
  });
});

describe('AI Investigation Result card', () => {
  const transactions = ids.map((_, i) => tx(i));
  function renderCard(draft: SimulationDraft) {
    const inspect = vi.fn();
    const openTransactions = vi.fn();
    render(
      <InvestigationResult
        draft={draft}
        status="succeeded"
        transactions={transactions}
        inspect={inspect}
        openTransactions={openTransactions}
        header={<h3 id="ai-result-title">AI Investigation Result</h3>}
      />,
    );
    return { inspect, openTransactions };
  }

  it('renders transaction and source citation chips and "Used in" for a per-finding run', () => {
    const { openTransactions } = renderCard({
      ...base,
      retrieval,
      finding_citations: [
        { finding_reference_id: 'fact-volume', regulatory_citation: 'src-320' },
      ],
    });
    // The first finding is the system summary, so it is shown once, as the conclusion.
    const item = screen.getByRole('heading', {
      name: 'Conclusion',
    }).parentElement!;
    expect(within(item).getByText(/12 transactions, \$649.57/)).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Key findings' })).toBeNull();
    fireEvent.click(
      within(item).getByRole('button', { name: 'Show transactions T1–T12' }),
    );
    expect(openTransactions).toHaveBeenCalledTimes(1);
    expect(
      within(item).getByRole('button', { name: /Show regulatory source R1/ }),
    ).toBeTruthy();
    // Main view: only the cited source, one row; rank and score are a tooltip.
    const basis = screen.getByRole('heading', {
      name: /Regulatory basis/,
    }).parentElement!;
    const rows = basis.querySelectorAll(':scope > ul.source-rows > li');
    expect(rows).toHaveLength(1);
    expect(rows[0].textContent).toBe(
      'R1§ 1020.320 Reports by banks of suspicious transactionsUsed in: Conclusion',
    );
    expect(rows[0].getAttribute('title')).toBe(
      'Rank 1 · text-match score 0.40',
    );
    expect(screen.queryByText(/^Rank 1/)).toBeNull();
    // The others: one collapsed line with a plain reason each.
    const also = basis.querySelector('details.also-retrieved')!;
    expect(also.querySelector('summary')!.textContent).toBe(
      'Also retrieved (2)',
    );
    expect(
      within(also as HTMLElement).getByText('Not cited by the AI'),
    ).toBeTruthy();
    expect(
      within(also as HTMLElement).getByText('Not sent: request size limit'),
    ).toBeTruthy();
    // Query and case inputs live in a collapsed section, with human labels only; its
    // summary line carries the ranking note (no separate line under the rows).
    const how = basis.querySelector('details.retrieval-how')!;
    expect(how.querySelector('summary')!.textContent).toBe(
      'How sources were retrieved · Top 3 of 24 sections · text-match ranking',
    );
    expect(basis.querySelector('p.retrieval-note')).toBeNull();
    expect(how.textContent).toContain('24 sections searched · top 3 kept');
    expect(how.textContent).toContain(
      'Query words: cash, currency, transaction, records',
    );
    expect(how.textContent).toContain(
      'From case inputs: Cash-like payments · 90 days, Settlement status',
    );
    expect(how.querySelector('code')).toBeNull();
    expect(basis.textContent).not.toMatch(
      /nbrPaymentsCashLike90d|risk_driver:|\|/i,
    );
    // A v2 record (no stored threshold) shows no strong-match count.
    expect(screen.queryByText(/strong match/)).toBeNull();
    // The research label is a small badge on the title only; no repeated disclaimers.
    expect(
      screen.getAllByText(
        'Unapproved research · Not production regulatory guidance',
      ),
    ).toHaveLength(1);
    expect(
      screen.queryByText(/AI-assisted academic research demonstration/),
    ).toBeNull();
    expect(screen.queryByText(/not a determination of wrongdoing/)).toBeNull();
    expect(
      screen.getByText('System summary (built from verified results)', {
        exact: false,
      }),
    ).toBeTruthy();
  });

  it('highlights the sources a finding uses and the findings a source supports', () => {
    renderCard({
      ...base,
      retrieval,
      finding_citations: [
        { finding_reference_id: 'fact-volume', regulatory_citation: 'src-320' },
      ],
    });
    const item = screen.getByRole('heading', {
      name: 'Conclusion',
    }).parentElement!;
    const r1 = document.getElementById('source-R1')!;
    const r2 = document.getElementById('source-R2')!;
    fireEvent.mouseEnter(item);
    expect(r1.classList.contains('is-traced')).toBe(true);
    expect(r2.classList.contains('is-traced')).toBe(false);
    fireEvent.mouseLeave(item);
    expect(r1.classList.contains('is-traced')).toBe(false);
    fireEvent.click(
      within(item).getByRole('button', { name: /Show regulatory source R1/ }),
    );
    expect(item.classList.contains('is-traced')).toBe(true);
    expect(r1.classList.contains('is-traced')).toBe(true);
  });

  it('never repeats the conclusion as a finding and omits the model score', () => {
    const other = calc('fact-other', 'velocity');
    (
      other as { summary: { result: { observed_count: number } } }
    ).summary.result.observed_count = 3;
    renderCard({ ...base, findings: [...base.findings, other] });
    const conclusion = screen.getByRole('heading', {
      name: 'Conclusion',
    }).parentElement!;
    expect(within(conclusion).getByText(/12 transactions/)).toBeTruthy();
    const list = screen.getByRole('heading', {
      name: 'Key findings',
    }).parentElement!;
    expect(within(list).getAllByRole('listitem')).toHaveLength(1);
    expect(within(list).queryByText(/12 transactions/)).toBeNull();
    expect(within(list).getByText(/^3 transactions/)).toBeTruthy();
    expect(screen.queryByText(/Model risk score/)).toBeNull();
  });

  it('opens an individual record from a T chip', () => {
    const draft = {
      ...base,
      findings: [
        {
          claim_type: 'observed_fact',
          reference_id: ids[2],
          supporting_evidence: [ids[2]],
          contradictory_evidence: [],
          summary: tx(2),
        } as DraftFinding,
      ],
    };
    const { inspect } = renderCard(draft);
    fireEvent.click(
      screen.getByRole('button', { name: 'Open transaction record T3' }),
    );
    expect(inspect).toHaveBeenCalledWith(ids[2]);
  });

  it('older runs cite the overall conclusion and say so', () => {
    renderCard(base);
    expect(screen.getByText('Used in: Conclusion')).toBeTruthy();
    expect(screen.getByText(/earlier fixed query/)).toBeTruthy();
    expect(screen.queryByText(/Also retrieved/)).toBeNull();
  });

  it('a v4 run reports strong matches and that each source was sent as an excerpt', () => {
    renderCard({
      ...base,
      retrieval: {
        ...retrieval,
        method: 'postgresql_english_ts_rank_cd_or_relative_excerpt_v3',
        min_relative_score: '0.25',
        strong_matches: 3,
        excerpt_cap_bytes: 4000,
        inputs: [
          'risk_driver:totalMerchCred90d',
          'calculation:counterparty_concentration',
        ],
        results: retrieval.results.map((r) => ({ ...r, sent: true })),
      },
    });
    const how = document.querySelector('details.retrieval-how')!;
    expect(how.textContent).toContain(
      '24 sections searched · 3 strong matches (results below 25% of the top score dropped)',
    );
    expect(how.textContent).not.toMatch(/\d+ of 24 sections searched/);
    expect(how.textContent).toContain(
      'From case inputs: Merchant credit amount · 90 days, Counterparty concentration',
    );
    expect(how.textContent).toContain('up to 4,000 bytes per section');
    expect(how.textContent).not.toMatch(/totalMerchCred90d/i);
    expect(screen.getAllByText('Not cited by the AI')).toHaveLength(2);
    expect(screen.queryByText(/request size limit/)).toBeNull();
  });

  it('a v5 run names the evidence patterns, their rule and the inputs left out', () => {
    renderCard({
      ...base,
      retrieval: {
        ...retrieval,
        method: 'case_term_coverage_then_ts_rank_cd_relative_excerpt_v4',
        min_relative_score: '0.25',
        strong_matches: 3,
        excerpt_cap_bytes: 4000,
        inputs: [
          'risk_driver:nbrPaymentsCashLike90d',
          'evidence_pattern:cash_below_reporting_threshold',
        ],
        patterns: [
          {
            rule: 'cash_below_reporting_threshold',
            observed: '10',
            threshold: '3',
          },
        ],
        dropped_inputs: [
          'calculation:counterparty_concentration',
          'missing_evidence:settlement_status',
        ],
        weighted_terms: [
          { term: 'structured', weight: 3 },
          { term: 'cash', weight: 1 },
        ],
        results: retrieval.results.map((r) => ({ ...r, sent: true })),
      },
    });
    const how = document.querySelector('details.retrieval-how')!;
    expect(how.querySelector('summary')!.textContent).toBe(
      'How sources were retrieved · Top 3 of 24 sections · case-term ranking',
    );
    expect(how.textContent).toContain(
      'From case inputs: Cash-like payments · 90 days, Cash deposits just below the $10,000 report level',
    );
    expect(how.textContent).toContain(
      'Evidence patterns found: Cash deposits just below the $10,000 report level (10; rule: 3)',
    );
    expect(how.textContent).toContain('pattern words count three times');
    expect(how.textContent).toContain(
      'Left out because every case has them: Counterparty concentration, Settlement status',
    );
    expect(how.textContent).not.toMatch(
      /evidence_pattern:|cash_below_reporting_threshold/,
    );
  });

  it('ends the system summary after the figures', () => {
    const text = systemSummary(base, mergeFacts(base.findings));
    expect(text).toBe('12 transactions, $649.57, 100% with one counterparty.');
  });

  it('names missing settlement status in the coverage gap only when the records show it', () => {
    const gap = {
      question_code: 'coverage_gap_requires_more_evidence' as const,
      supporting_evidence: [ids[0], ids[1]],
      contradictory_evidence: [],
      uncertainty: 'unconfirmed_requires_human_review' as const,
    };
    expect(indicatorText(gap, base, transactions)).toBe(
      'Settlement status unknown for',
    );
    renderCard({ ...base, hypotheses: [gap] });
    const item = screen
      .getByText(/Settlement status unknown for/)
      .closest('li')!;
    expect(item.textContent).toBe('Settlement status unknown for T1, T2');
    // Not listed as missing, or a record that has a settlement status: plain label kept.
    expect(
      indicatorText(
        gap,
        { ...base, missing_evidence: ['curated_documents'] },
        transactions,
      ),
    ).toBe('Coverage gap requires more evidence');
    const settled = transactions.map((t, i) =>
      i === 1 ? { ...t, settlement_status: 'settled' } : t,
    );
    expect(indicatorText(gap, base, settled)).toBe(
      'Coverage gap requires more evidence',
    );
  });

  it('hides indicators without records and shows the hypothesis label once', () => {
    renderCard(base);
    expect(
      screen.getByText('Review observed concentration', { exact: false }),
    ).toBeTruthy();
    expect(
      screen.queryByText(/Coverage gap requires more evidence/),
    ).toBeNull();
    expect(screen.getAllByText(/not factual allegations/)).toHaveLength(1);
  });
});
