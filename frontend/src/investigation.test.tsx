// @vitest-environment jsdom
// Explicit contract fixtures only. Real persisted evidence/model acceptance runs separately.
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import type { ApiFactory } from './App';
import { ApiError, type Case, type Client } from './api';
import { InvestigationView } from './investigation';
import {
  InvestigationReceipts,
  type CaseContext,
  type Evidence,
  type InvestigationFactory,
  type PacketDetail,
  type PacketReceipt,
  type Reference,
} from './investigation-api';

const id = '11111111-1111-4111-8111-111111111111';
const record: Case = {
  id,
  alert_id: 'alert',
  source_id: 'synthetic-component-evidence',
  assigned_to: 'analyst',
  status: 'open',
  disposition: null,
  version: 1,
  created_at: '2026-01-01T00:00:00Z',
  priority: 'High',
  assessment_status: 'pending',
  latest_job_id: 'job',
};
const reference: Reference = {
  record_version_id: 'record',
  identity_id: 'identity',
  source_version_id: 'release',
  kind: 'customer',
  version: 1,
  sha256: 'a'.repeat(64),
};
const window = { start: '2025-10-03T00:00:00Z', end: '2026-01-01T00:00:00Z' };
const context: Evidence<CaseContext> = {
  data: {
    case_id: id,
    snapshot_token: 'synthetic-component-token',
    selected_assessment_id: null,
    model_signal: null,
    available_categories: [
      'customer',
      'account',
      'relationship',
      'transaction',
    ],
    missing_categories: [],
    account_handles: ['account'],
  },
  snapshot: {
    id: 'snapshot',
    sha256: 'b'.repeat(64),
    case_version: 1,
    evidence_revision: 1,
    access_revision: 2,
  },
  sources: [
    {
      source_id: 'source',
      source_version_id: 'release',
      version: 1,
      sha256: 'a'.repeat(64),
      coverage: 'complete_declared_window',
      window,
      membership_complete: true,
      case_input_reconciliation: 'matches_declared_inputs',
    },
  ],
  evidence: [reference],
  coverage: {
    status: 'complete_declared_window',
    unknown_time_excluded: 0,
    outside_window_excluded: 0,
    limitations: ['synthetic_observations_only'],
  },
};
const fact = {
  calculation: 'incoming_outgoing',
  status: 'complete_declared_window',
  currency: 'USD' as const,
  window,
  treatment: 'gross_observations',
  observed_count: 1,
  observed_total: '0.12345678',
  incoming_total: '0',
  outgoing_total: '0.12345678',
  reversal_observations: 0,
  unmatched_reversals: 0,
  verified_reversal_pairs_excluded: 0,
  buckets: [{ window, observed_count: 1, observed_total: '0.12345678' }],
  concentration: [
    {
      counterparty_handle: 'counterparty',
      observed_count: 1,
      observed_total: '0.12345678',
      share_of_observed_amount: '1.0000000000000000',
    },
  ],
};
const pending = {
  run_id: 'run',
  status: 'pending' as const,
  attempts: 0,
  error_code: null,
  human_review_required: true as const,
  mode: 'deterministic_evidence_only' as const,
};
const completed: PacketDetail = {
  ...pending,
  status: 'abstained',
  packet: {
    run_id: 'run',
    manifest_sha256: 'c'.repeat(64),
    mode: 'deterministic_evidence_only',
    outcome: 'abstained',
    transactions: [],
    facts: [
      {
        reference_id: 'fact',
        input_record_ids: ['record'],
        result: fact,
        coverage: context.coverage,
      },
    ],
    model_signal: null,
    evidence: [reference],
    questions: ['obtain_complete_requested_window'],
    missing_evidence: ['comparable_expected_activity'],
    conflicts: ['contradictory_kyc_observations'],
    limitations: ['synthetic_observations_only'],
    abstentions: ['no_money_laundering_violation_or_sar_conclusion'],
    provider_used: false,
    regulatory_citations: [],
    human_review_required: true,
  },
  verification: {
    status: 'source_numeric_reference_checks_passed',
    verifier: 'trueflag.source-packet-verifier.v1',
    manifest_sha256: 'c'.repeat(64),
    packet_sha256: 'd'.repeat(64),
    human_semantic_review_required: true,
  },
};

function setup() {
  const envelope = <T,>(data: T) => ({ ...context, data });
  const api = {
    context: vi.fn().mockResolvedValue(context),
    customers: vi.fn().mockResolvedValue(
      envelope({
        items: [
          {
            reference,
            customer_handle: 'customer',
            alias: 'SYN-CUSTOMER-missing',
            observed_at: window.start,
            annual_income: null,
            currency: 'USD',
            declared_kyc_score: 3,
            contradictory_observations: true,
            expected_activity_status: 'not_recorded',
            age_days_at_source_as_of: 100,
          },
          {
            reference: { ...reference, record_version_id: 'zero' },
            customer_handle: 'other',
            alias: 'SYN-CUSTOMER-zero',
            observed_at: window.start,
            annual_income: '0',
            currency: 'USD',
            declared_kyc_score: 1,
            contradictory_observations: false,
            expected_activity_status: 'not_recorded',
            age_days_at_source_as_of: 100,
          },
        ],
        total: 2,
        next_cursor: null,
      }),
    ),
    related: vi.fn().mockResolvedValue(
      envelope({
        items: [
          {
            reference: { ...reference, kind: 'account' },
            kind: 'account',
            account_handle: 'account',
            customer_handle: null,
            alias: 'SYN-ACCOUNT-12345678',
            currency: 'USD',
            relation: null,
            observed_at: null,
            opened_at: window.start,
          },
        ],
        total: 1,
        next_cursor: null,
      }),
    ),
    transactions: vi.fn().mockResolvedValue(
      envelope({
        items: [
          {
            reference: { ...reference, kind: 'transaction' },
            account_handle: 'account',
            counterparty_handle: 'counterparty',
            amount: '0.12345678',
            currency: 'USD',
            event_at: window.start,
            original_time: window.start,
            event_kind: 'purchase',
            direction: 'debit',
            channel: 'card',
            reverses_handle: null,
            settlement_status: 'not_recorded',
          },
        ],
        total: 26,
        next_cursor: 'next-cursor',
      }),
    ),
    activity: vi.fn().mockResolvedValue(envelope(fact)),
    history: vi
      .fn()
      .mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 }),
    submit: vi.fn().mockResolvedValue(pending),
    detail: vi.fn().mockResolvedValue(completed),
    draftHistory: vi
      .fn()
      .mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 }),
    draftSubmit: vi.fn(),
    draftDetail: vi.fn(),
  };
  const detailSignals: AbortSignal[] = [];
  const factory: InvestigationFactory = (signal) => ({
    ...api,
    detail: (caseId, runId) => {
      detailSignals.push(signal!);
      return api.detail(caseId, runId);
    },
  });
  const modelApi: ApiFactory = () =>
    ({
      history: vi
        .fn()
        .mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 }),
    }) as unknown as Client;
  const receipts = new Map<string, PacketReceipt>();
  const view = render(
    <InvestigationReceipts.Provider value={receipts}>
      <InvestigationView
        record={record}
        api={factory}
        modelApi={modelApi}
        renderModel={() => null}
      />
    </InvestigationReceipts.Provider>,
  );
  return { api, view, receipts, detailSignals };
}
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('investigation workspace', () => {
  it('starts one offline investigation after the evidence packet is verified', async () => {
    const { api } = setup();
    api.draftSubmit.mockResolvedValue({ draft_run_id: 'synthetic-draft' });
    api.draftDetail.mockResolvedValue({ status: 'failed', draft: null });
    await screen.findByText('SYN-CUSTOMER-missing');
    fireEvent.click(
      screen.getByRole('button', { name: 'AI-Assisted Findings' }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Generate investigation' }),
    );
    await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.draftSubmit).toHaveBeenCalledTimes(1));
    expect(api.draftSubmit.mock.calls[0][1].investigation_run_id).toBe('run');
  });
  it('shows one actionable empty state and defers disabled tools/history until expanded', async () => {
    const { api } = setup();
    api.context.mockResolvedValue({
      ...context,
      sources: [],
      evidence: [],
      coverage: { ...context.coverage, status: 'unavailable' },
      data: {
        ...context.data,
        available_categories: [],
        missing_categories: [
          'customer',
          'account',
          'relationship',
          'transaction',
        ],
      },
    });
    await screen.findByRole('heading', { name: 'Supporting records needed' });
    expect(
      screen
        .getByRole('link', { name: 'View risk assessment' })
        .getAttribute('href'),
    ).toBe(`#/cases/${id}`);
    expect(
      screen.queryByRole('button', { name: 'Generate summary' }),
    ).toBeNull();
    expect(
      screen.queryByRole('navigation', { name: 'Investigation sections' }),
    ).toBeNull();
    expect(api.history).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole('button', { name: 'Show details and history' }),
    );
    expect(screen.getByText('Assessment and evidence version')).toBeTruthy();
    expect(screen.getByText('Missing evidence · 4 categories')).toBeTruthy();
  });
  it('bounds activity reads and stops downstream requests after unmount', async () => {
    const { api, view } = setup();
    await screen.findByText('SYN-CUSTOMER-missing');
    let releaseTransactions = () => {};
    let releaseActivity = () => {};
    api.transactions.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          releaseTransactions = () =>
            resolve({
              ...context,
              data: { items: [], total: 0, next_cursor: null },
            });
        }),
    );
    api.activity.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          releaseActivity = () => resolve({ ...context, data: fact });
        }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Transaction Activity Analysis' }),
    );
    await waitFor(() => expect(api.transactions).toHaveBeenCalledTimes(1));
    expect(api.activity).not.toHaveBeenCalled();
    await act(async () => releaseTransactions());
    await waitFor(() => expect(api.activity).toHaveBeenCalledTimes(1));
    view.unmount();
    await act(async () => releaseActivity());
    expect(api.activity).toHaveBeenCalledTimes(1);
  });
  it('shows missing versus zero income, source provenance and honest pending assessment state', async () => {
    setup();
    await screen.findByText('SYN-CUSTOMER-missing');
    expect(screen.getByText('Not recorded (missing, not zero)')).toBeDefined();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'View all customer and account records',
      }),
    );
    expect(screen.getByText('USD 0')).toBeDefined();
    expect(screen.getByText(/Processing status: Pending/)).toBeDefined();
    fireEvent.click(
      screen.getByRole('button', { name: 'Supporting Evidence' }),
    );
    expect(
      screen.getByText('Source v1 · Complete for the stated period'),
    ).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Customer Profile' }));
    await screen.findByText('SYN-CUSTOMER-missing');
    expect(screen.getByText(/Conflicting customer observations/)).toBeDefined();
  });
  it('renders exact backend decimals, velocity, concentration and bounded cursor pagination', async () => {
    const { api } = setup();
    await screen.findByText('SYN-CUSTOMER-missing');
    fireEvent.click(
      screen.getByRole('button', { name: 'Transaction Activity Analysis' }),
    );
    await screen.findByText('Transaction observations');
    await waitFor(() => expect(api.activity).toHaveBeenCalledTimes(3));
    expect(
      (await screen.findAllByText('USD 0.12345678')).length,
    ).toBeGreaterThan(0);
    fireEvent.click(
      screen.getByRole('button', { name: 'Next transaction page' }),
    );
    await waitFor(() =>
      expect(api.transactions).toHaveBeenLastCalledWith(
        id,
        expect.objectContaining({
          cursor: 'next-cursor',
          limit: 25,
          snapshot: context.data.snapshot_token,
        }),
      ),
    );
  });
  it('reuses an uncertain submission key and displays only server-verified abstention results', async () => {
    const { api } = setup();
    await screen.findByText('SYN-CUSTOMER-missing');
    fireEvent.click(
      screen.getByRole('button', { name: 'Investigation Summary' }),
    );
    await screen.findByText('No investigation summaries in your history.');
    api.submit.mockRejectedValueOnce(new ApiError(0));
    fireEvent.click(screen.getByRole('button', { name: 'Generate summary' }));
    await screen.findByRole('alert');
    const first = api.submit.mock.calls[0];
    fireEvent.click(screen.getByRole('button', { name: 'Generate summary' }));
    await screen.findByText('Investigation Summary · Further evidence needed');
    expect(api.submit.mock.calls[1]).toEqual(first);
    expect(first[1]).toMatchObject({
      without_assessment_reason: 'unavailable',
      expected_evidence_revision: 1,
      currencies: ['USD'],
    });
    expect(JSON.stringify(first[1])).not.toContain('model_score');
    expect(
      screen.getByText(/Regulatory guidance has not been applied/),
    ).toBeDefined();
  });
  it('clears visible source evidence and aborts context rechecks after a clock safety error', async () => {
    const { api } = setup();
    await screen.findByText('SYN-CUSTOMER-missing');
    api.transactions.mockRejectedValueOnce(
      new ApiError(503, 2, 'clock_uncertainty'),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Transaction Activity Analysis' }),
    );
    await screen.findByText(/Service temporarily unavailable/);
    expect(screen.queryByText('SYN-CUSTOMER-missing')).toBeNull();
    expect(
      screen.queryByRole('button', { name: 'Generate summary' }),
    ).toBeNull();
  });
  it.each([403, 409, 422])(
    'withholds evidence after permission or snapshot failure %s',
    async (status) => {
      const { api } = setup();
      await screen.findByText('SYN-CUSTOMER-missing');
      api.transactions.mockRejectedValueOnce(new ApiError(status));
      fireEvent.click(
        screen.getByRole('button', { name: 'Transaction Activity Analysis' }),
      );
      await screen.findByRole('heading', { name: 'Investigation unavailable' });
      expect(screen.queryByText('SYN-CUSTOMER-zero')).toBeNull();
    },
  );
  it('aborts status requests on unmount and never automatically resubmits a mutation', async () => {
    const { api, view, detailSignals } = setup();
    await screen.findByText('SYN-CUSTOMER-missing');
    api.detail.mockImplementation(() => new Promise(() => {}));
    fireEvent.click(
      screen.getByRole('button', { name: 'Investigation Summary' }),
    );
    await screen.findByText('No investigation summaries in your history.');
    fireEvent.click(screen.getByRole('button', { name: 'Generate summary' }));
    await screen.findByText('Checking summary progress…');
    expect(api.submit).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(detailSignals.every((s) => s.aborted)).toBe(true);
  });
  it('clears source observations when a periodic authorization revision changes', async () => {
    const timers = vi.spyOn(globalThis.window, 'setTimeout');
    const { api } = setup();
    await screen.findByText('SYN-CUSTOMER-missing');
    const revoked = {
      ...context,
      snapshot: {
        ...context.snapshot,
        sha256: 'e'.repeat(64),
        access_revision: 3,
      },
      sources: [],
      data: {
        ...context.data,
        available_categories: [],
        missing_categories: [
          'customer',
          'account',
          'transaction',
          'relationship',
        ],
      },
    };
    api.context.mockResolvedValue(revoked);
    const callback = timers.mock.calls.find(
      ([, delay]) => delay === 15000,
    )?.[0];
    expect(typeof callback).toBe('function');
    await act(async () => {
      if (typeof callback === 'function') callback();
    });
    await waitFor(() =>
      expect(screen.queryByText('SYN-CUSTOMER-missing')).toBeNull(),
    );
    expect(
      screen.getByText(/No accessible supporting records are linked/),
    ).toBeDefined();
  });
  it('rejects reversed windows locally without requesting invented financial calculations', async () => {
    const { api } = setup();
    await screen.findByText('SYN-CUSTOMER-missing');
    fireEvent.click(
      screen.getByRole('button', { name: 'Transaction Activity Analysis' }),
    );
    await waitFor(() => expect(api.activity).toHaveBeenCalledTimes(3));
    fireEvent.change(screen.getByLabelText('Window end, exclusive (UTC)'), {
      target: { value: '2020-01-01T00:00' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Apply evidence window' }),
    );
    await screen.findByText(/Choose a valid UTC window/);
    expect(api.activity).toHaveBeenCalledTimes(3);
  });
});
