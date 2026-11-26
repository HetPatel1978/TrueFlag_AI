// @vitest-environment jsdom
// Explicit contract fixtures; real backend/browser acceptance is separate.
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { ApiError } from './api';
import { DraftWorkspace } from './drafts';
import type { DraftDetail, DraftStatus } from './draft-api';
import {
  investigationClient,
  type CaseContext,
  type Evidence,
  type InvestigationFactory,
  type PacketDetail,
  type Transaction,
} from './investigation-api';

const window = { start: '2025-10-03T00:00:00Z', end: '2026-01-01T00:00:00Z' };
const reference = {
  record_version_id: '11111111-1111-4111-8111-111111111111',
  identity_id: 'identity',
  source_version_id: 'source-version',
  kind: 'transaction',
  version: 1,
  sha256: 'a'.repeat(64),
};
const transaction: Transaction = {
  reference,
  account_handle: null,
  counterparty_handle: null,
  amount: '37.12345678',
  currency: 'USD',
  event_at: window.start,
  original_time: 'explicit_offset',
  event_kind: 'transfer',
  direction: 'credit',
  channel: 'not_recorded',
  reverses_handle: null,
  settlement_status: 'not_recorded',
};
const context: Evidence<CaseContext> = {
  data: {
    case_id: 'case',
    snapshot_token: 'synthetic-fixture-token',
    selected_assessment_id: null,
    model_signal: null,
    available_categories: ['transaction'],
    missing_categories: [],
    account_handles: [],
  },
  snapshot: {
    id: 'snapshot',
    sha256: 'b'.repeat(64),
    case_version: 1,
    evidence_revision: 1,
    access_revision: 1,
  },
  sources: [],
  evidence: [reference],
  coverage: {
    status: 'complete_declared_window',
    unknown_time_excluded: 0,
    outside_window_excluded: 0,
    limitations: [],
  },
};
const parent = {
  run_id: 'verified-parent',
  status: 'succeeded',
  attempts: 1,
  error_code: null,
  human_review_required: true,
  mode: 'deterministic_evidence_only',
  packet: { run_id: 'verified-parent', outcome: 'packet_ready' },
  verification: {
    status: 'source_numeric_reference_checks_passed',
    packet_sha256: 'c'.repeat(64),
  },
} as PacketDetail;
const pending: DraftStatus = {
  draft_run_id: 'draft',
  status: 'pending',
  attempts: 0,
  error_code: null,
  mode: 'offline_simulation',
  live_provider_used: false,
  human_review_required: true,
};
const completed: DraftDetail = {
  ...pending,
  status: 'succeeded',
  attempts: 1,
  draft: {
    content_sha256: 'e'.repeat(64),
    draft_run_id: 'draft',
    investigation_run_id: 'verified-parent',
    manifest_sha256: 'd'.repeat(64),
    packet_sha256: 'c'.repeat(64),
    outcome: 'draft_ready',
    findings: [
      {
        claim_type: 'observed_fact',
        reference_id: reference.record_version_id,
        supporting_evidence: [reference.record_version_id],
        contradictory_evidence: [],
        summary: transaction,
      },
    ],
    hypotheses: [],
    questions: ['obtain_complete_requested_window'],
    unresolved_questions: [],
    next_steps: ['human_review'],
    missing_evidence: [],
    conflicts: [],
    limitations: ['synthetic_observations_only'],
    provenance: {
      provider: 'deterministic_fake',
      model: 'trueflag-fake-selection.v1',
      prompt_version: 'prompt-fixture',
      prompt_sha256: 'e'.repeat(64),
      configuration_sha256: 'f'.repeat(64),
      parent_manifest_sha256: 'd'.repeat(64),
    },
    verification: 'source_reference_numeric_checks_passed',
    semantic_review: 'pending_human_review',
    regulatory_context: 'unavailable_unapproved',
    simulation: true,
    live_provider_used: false,
  },
};

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});
function setup(packet: PacketDetail | null = parent) {
  const signals: AbortSignal[] = [];
  const api = {
    draftHistory: vi
      .fn()
      .mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 }),
    draftSubmit: vi.fn().mockResolvedValue(pending),
    draftDetail: vi.fn().mockResolvedValue(completed),
    transactions: vi.fn().mockResolvedValue({
      ...context,
      data: { items: [transaction], total: 1, next_cursor: null },
    }),
  };
  const factory: InvestigationFactory = (signal) => {
    if (signal) signals.push(signal);
    return api as unknown as ReturnType<InvestigationFactory>;
  };
  const invalidate = vi.fn();
  const view = render(
    <DraftWorkspace
      id="case"
      api={factory}
      context={context}
      packet={packet}
      invalidate={invalidate}
    />,
  );
  return { api, view, invalidate, signals };
}
const generate = () =>
  fireEvent.click(
    screen.getByRole('button', {
      name: 'Generate Simulated Investigation Draft',
    }),
  );

it('renders a verified Claude result with live provenance (contract fixture only)', async () => {
  const { api } = setup();
  const live = structuredClone(completed);
  live.mode = 'claude_live';
  live.live_provider_used = true;
  live.draft!.simulation = false;
  live.draft!.live_provider_used = true;
  live.draft!.provenance.provider = 'anthropic';
  live.draft!.provenance.model = 'claude-sonnet-5-5';
  api.draftDetail.mockResolvedValue(live);
  generate();
  await screen.findByRole('heading', { name: 'Conclusion' });
  expect(screen.getByText(/Claude \(claude-sonnet-5-5\)/)).toBeTruthy();
  expect(screen.queryByText('Claude AI — Live')).toBeNull();
  expect(
    screen.queryByText('No live model interpretation is present.'),
  ).toBeNull();
});

it.each(['approval_required', 'request_expired'] as const)(
  'explains the research %s gate without enabling generation',
  async (research_status) => {
    const draftSubmit = vi.fn();
    const api = (() => ({
      draftCapabilities: vi.fn().mockResolvedValue({
        provider: 'unavailable',
        regulatory_grounding_enabled: false,
        research_status,
      }),
      draftHistory: vi
        .fn()
        .mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 }),
      draftSubmit,
    })) as unknown as InvestigationFactory;
    render(
      <DraftWorkspace
        id="case"
        api={api}
        context={context}
        packet={parent}
        invalidate={vi.fn()}
      />,
    );
    const button = await screen.findByRole('button', {
      name:
        research_status === 'approval_required'
          ? 'Owner approval required'
          : 'New approval request required',
    });
    expect(button.hasAttribute('disabled')).toBe(true);
    expect(
      screen.queryByText(/No authorized provider is available/),
    ).toBeNull();
    expect(draftSubmit).not.toHaveBeenCalled();
  },
);

const reviewFixture = (overrides: Record<string, unknown> = {}) => ({
  draft_run_id: 'inapp-run',
  case_id: 'case-0000-0000',
  phase: 'awaiting_approval',
  can_approve: true,
  is_approver: true,
  model: 'claude-sonnet-5-5',
  data_scope: 'synthetic_only',
  max_input_tokens: 32768,
  max_output_tokens: 4096,
  timeout_seconds: 120,
  maximum_requests: 1,
  automatic_retries: false,
  reservation_usd: '2.14',
  cumulative_cap_usd: '10.00',
  spent_usd: '0',
  expires_at: new Date(Date.now() + 900_000).toISOString(),
  approve_before: new Date(Date.now() + 750_000).toISOString(),
  financial_facts: [
    {
      reference_id: 'f',
      observed_total: '10020.00000000',
      observed_count: 12,
      currency: 'USD',
      window: null,
    },
  ],
  transactions: 12,
  model_signal: { score: 0.6489, model_version: 'v1' },
  missing_evidence: ['settlement_status'],
  limitations: ['synthetic_observations_only'],
  regulatory_status: 'UNAPPROVED RESEARCH — NOT PRODUCTION REGULATORY GUIDANCE',
  regulatory_sources: [
    {
      reference_id: 'r',
      section: '1020.320',
      approval_status: 'unapproved_research',
      historical_as_of: '2026-11-02',
      text_sha256: 'a'.repeat(64),
      source_url:
        'https://www.ecfr.gov/api/versioner/v1/full/2026-11-02/title-31.xml',
    },
  ],
  request_sha256: 'd'.repeat(64),
  request_bytes: 35160,
  request: { model: 'claude-sonnet-5-5' },
  ...overrides,
});

function inapp(status: string, review = reviewFixture()) {
  const researchStart = vi.fn().mockResolvedValue({
    ...pending,
    draft_run_id: 'inapp-run',
    mode: 'claude_live',
  });
  const researchApprove = vi.fn().mockResolvedValue({
    ...pending,
    draft_run_id: 'inapp-run',
    mode: 'claude_live',
  });
  const researchCancel = vi
    .fn()
    .mockResolvedValue({ ...pending, status: 'invalidated' });
  const researchReview = vi.fn().mockResolvedValue(review);
  const draftSubmit = vi.fn();
  const api = (() => ({
    draftCapabilities: vi.fn().mockResolvedValue({
      provider: 'unavailable',
      regulatory_grounding_enabled: false,
      research_status: status,
      research_run_id: status === 'awaiting_approval' ? 'inapp-run' : null,
      research_can_approve: review.is_approver,
    }),
    draftHistory: vi
      .fn()
      .mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 }),
    draftDetail: vi
      .fn()
      .mockResolvedValue({ ...completed, draft_run_id: 'inapp-run' }),
    researchStart,
    researchReview,
    researchApprove,
    researchCancel,
    draftSubmit,
  })) as unknown as InvestigationFactory;
  render(
    <DraftWorkspace
      id="case"
      api={api}
      context={context}
      packet={parent}
      invalidate={vi.fn()}
    />,
  );
  return {
    researchStart,
    researchApprove,
    researchCancel,
    researchReview,
    draftSubmit,
  };
}

it('Generate prepares the exact request for review and never sends it by itself', async () => {
  const calls = inapp('generate_ready');
  fireEvent.click(
    await screen.findByRole('button', { name: 'Generate investigation' }),
  );
  await screen.findByRole('region', { name: 'AI Request Review' });
  expect(calls.researchStart).toHaveBeenCalledTimes(1);
  expect(calls.researchStart.mock.calls[0][1]).toEqual({
    investigation_run_id: 'verified-parent',
    expected_packet_sha256: 'c'.repeat(64),
  });
  await screen.findByText('d'.repeat(64));
  expect(
    screen.getByText(
      /Unapproved research · Not production regulatory guidance/,
    ),
  ).toBeTruthy();
  expect(calls.researchApprove).not.toHaveBeenCalled();
  expect(calls.draftSubmit).not.toHaveBeenCalled();
});

it('Approve & Run Once sends only the displayed hash, once, even on double click', async () => {
  const calls = inapp('awaiting_approval');
  const approve = await screen.findByRole('button', {
    name: 'Approve & Run Once',
  });
  fireEvent.click(approve);
  fireEvent.click(approve);
  await waitFor(() => expect(calls.researchApprove).toHaveBeenCalledTimes(1));
  expect(calls.researchApprove.mock.calls[0][2]).toBe('d'.repeat(64));
  expect(calls.researchApprove.mock.calls[0][3]).toBe('approve-inapp-run');
  await waitFor(() =>
    expect(
      screen.queryByRole('region', { name: 'AI Request Review' }),
    ).toBeNull(),
  );
});

it('a user who may not approve spending sees Pending Owner Approval and no approve action', async () => {
  const calls = inapp(
    'awaiting_approval',
    reviewFixture({ can_approve: false, is_approver: false }),
  );
  await screen.findByText(/Pending Owner Approval/);
  expect(
    screen.queryByRole('button', { name: 'Approve & Run Once' }),
  ).toBeNull();
  expect(calls.researchApprove).not.toHaveBeenCalled();
});

it('an expired request cannot be approved and offers Refresh Request', async () => {
  const calls = inapp(
    'awaiting_approval',
    reviewFixture({ phase: 'request_expired', can_approve: false }),
  );
  const refresh = await screen.findByRole('button', {
    name: 'Refresh Request',
  });
  expect(
    screen.queryByRole('button', { name: 'Approve & Run Once' }),
  ).toBeNull();
  fireEvent.click(refresh);
  // A fresh snapshot and a new exact request, which needs its own approval.
  await waitFor(() => expect(calls.researchStart).toHaveBeenCalledTimes(1));
  expect(calls.researchApprove).not.toHaveBeenCalled();
});

it('Cancel retires the request without approving it', async () => {
  const calls = inapp('awaiting_approval');
  fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
  await waitFor(() => expect(calls.researchCancel).toHaveBeenCalledTimes(1));
  expect(calls.researchApprove).not.toHaveBeenCalled();
});

describe('offline simulation workbench', () => {
  it('requires a verified packet and never auto-generates on mount', async () => {
    const { api } = setup(null);
    await screen.findByText(
      'No simulated investigation drafts have been requested.',
    );
    expect(
      screen
        .getByRole('button', { name: 'Generate Simulated Investigation Draft' })
        .hasAttribute('disabled'),
    ).toBe(true);
    expect(screen.getByText('Offline simulation')).toBeTruthy();
    expect(api.draftSubmit).not.toHaveBeenCalled();
  });
  it('shows real job processing then verified simulated content and explicit boundaries', async () => {
    const { api } = setup();
    api.draftDetail.mockResolvedValueOnce({
      ...pending,
      status: 'running',
      attempts: 1,
      draft: null,
    });
    generate();
    await screen.findByText('Processing', { exact: true });
    fireEvent.click(screen.getByRole('button', { name: 'Check draft status' }));
    await screen.findByRole('heading', { name: 'Conclusion' });
    expect(screen.getByText(/not a live LLM result/)).toBeTruthy();
    expect(
      screen.getAllByText('Offline simulation', { exact: true }).length,
    ).toBeGreaterThan(0);
    expect(
      screen.queryByText(
        /No regulatory source or legal citation has been applied/,
      ),
    ).toBeNull();
    expect(screen.queryByText(/hallucination score/i)).toBeNull();
  });
  it('prevents double submission and uses stable packet-bound idempotency after retries', async () => {
    const { api } = setup();
    let resolve!: (v: DraftStatus) => void;
    api.draftSubmit.mockReturnValueOnce(
      new Promise<DraftStatus>((r) => {
        resolve = r;
      }),
    );
    const button = screen.getByRole('button', {
      name: 'Generate Simulated Investigation Draft',
    });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(api.draftSubmit).toHaveBeenCalledTimes(1);
    await act(async () => resolve(pending));
    await screen.findByRole('heading', { name: 'Conclusion' });
    generate();
    await waitFor(() => expect(api.draftSubmit).toHaveBeenCalledTimes(2));
    expect(api.draftSubmit.mock.calls[0]).toEqual([
      'case',
      {
        investigation_run_id: 'verified-parent',
        expected_packet_sha256: 'c'.repeat(64),
      },
      'offline-verified-parent',
    ]);
    expect(api.draftSubmit.mock.calls[1][2]).toBe(
      api.draftSubmit.mock.calls[0][2],
    );
  });
  it('inspects a current authorized supporting record and restores keyboard focus', async () => {
    setup();
    generate();
    const link = await screen.findByRole('button', {
      name: 'Open transaction record T1',
    });
    link.focus();
    fireEvent.click(link);
    await screen.findByRole('region', { name: 'Supporting record details' });
    await screen.findByText('Record provenance');
    fireEvent.click(screen.getByRole('button', { name: 'Close record' }));
    expect(
      screen.queryByRole('region', { name: 'Supporting record details' }),
    ).toBeNull();
    expect(document.activeElement).toBe(link);
  });
  it.each([401, 403, 404, 409, 503])(
    'hides completed content after denial or uncertainty %s',
    async (status) => {
      const { api, invalidate } = setup();
      generate();
      await screen.findByRole('heading', { name: 'Conclusion' });
      api.draftDetail.mockRejectedValueOnce(
        new ApiError(status, 2, status === 503 ? 'clock_uncertainty' : ''),
      );
      fireEvent.click(
        screen.getByRole('button', { name: 'Check draft status' }),
      );
      await waitFor(() => expect(invalidate).toHaveBeenCalled());
      expect(screen.queryByRole('heading', { name: 'Conclusion' })).toBeNull();
    },
  );
  it('does not invalidate evidence when offline simulation is disabled', async () => {
    const { api, invalidate } = setup();
    api.draftHistory.mockRejectedValueOnce(
      new ApiError(503, 0, 'simulation_unavailable'),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Refresh draft history' }),
    );
    await screen.findByText(
      /Offline simulation is unavailable in this environment/,
    );
    expect(invalidate).not.toHaveBeenCalled();
    expect(
      screen
        .getByRole('button', { name: 'Generate Simulated Investigation Draft' })
        .hasAttribute('disabled'),
    ).toBe(true);
  });
  it('does not publish terminal failures or non-simulation responses', async () => {
    const { api } = setup();
    api.draftDetail.mockResolvedValueOnce({
      ...pending,
      status: 'failed',
      error_code: 'verification_failed',
      draft: null,
    });
    generate();
    await screen.findByRole('alert');
    expect(screen.queryByRole('heading', { name: 'Conclusion' })).toBeNull();
    api.draftDetail.mockResolvedValueOnce({
      ...completed,
      draft: { ...completed.draft!, simulation: false },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Check draft status' }));
    await screen.findByText(/outside the verified provider contract/);
    expect(screen.queryByRole('heading', { name: 'Conclusion' })).toBeNull();
  });
  it('reports a rejected AI response format, not an unavailable service', async () => {
    const { api } = setup();
    api.draftDetail.mockResolvedValueOnce({
      ...pending,
      status: 'failed',
      error_code: 'invalid_provider_output',
      draft: null,
    });
    generate();
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain(
      'The AI response did not match the required format, so no findings were accepted',
    );
    expect(alert.textContent).not.toContain('unavailable');
    expect(screen.queryByRole('heading', { name: 'Conclusion' })).toBeNull();
  });
  it('bounds polling to 40 checks and aborts on unmount without browser persistence', async () => {
    vi.useFakeTimers();
    const storage = vi.spyOn(Storage.prototype, 'setItem');
    const { api, view, signals } = setup();
    api.draftDetail.mockResolvedValue({ ...pending, draft: null });
    await act(async () => generate());
    for (let i = 0; i < 41; i++)
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
    expect(api.draftDetail).toHaveBeenCalledTimes(40);
    const calls = api.draftDetail.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000);
    });
    expect(api.draftDetail).toHaveBeenCalledTimes(calls);
    view.unmount();
    expect(signals.every((s) => s.aborted)).toBe(true);
    expect(storage).not.toHaveBeenCalled();
  });
  it('can resume immutable history without requesting a new draft', async () => {
    const { api } = setup();
    api.draftHistory.mockResolvedValue({
      items: [
        {
          ...pending,
          created_at: window.end,
          case_version: 1,
          evidence_revision: 2,
          access_revision: 3,
        },
      ],
      total: 1,
      limit: 10,
      offset: 0,
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Refresh draft history' }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'Open simulated draft' }),
    );
    await screen.findByRole('heading', { name: 'Conclusion' });
    expect(api.draftSubmit).not.toHaveBeenCalled();
  });
});

it('typed client submits only the immutable parent/hash through authenticated no-store transport', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(pending), {
      status: 202,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
  const controller = new AbortController();
  const client = investigationClient(
    'synthetic-test-token',
    controller.signal,
    vi.fn(),
  );
  await client.draftSubmit(
    'case',
    {
      investigation_run_id: 'verified-parent',
      expected_packet_sha256: 'c'.repeat(64),
    },
    'offline-verified-parent',
  );
  const [path, init] = fetchMock.mock.calls[0];
  expect(path).toBe('/api/v1/cases/case/investigation-drafts');
  expect(init?.cache).toBe('no-store');
  expect(JSON.parse(init?.body as string)).toEqual({
    investigation_run_id: 'verified-parent',
    expected_packet_sha256: 'c'.repeat(64),
  });
});

it('a run that finished while the page was open offers Generate new investigation', async () => {
  const caps = {
    provider: 'unavailable',
    regulatory_grounding_enabled: false,
    research_run_id: 'inapp-run',
    research_can_approve: true,
  };
  const draftCapabilities = vi
    .fn()
    .mockResolvedValueOnce({ ...caps, research_status: 'running' })
    .mockResolvedValue({
      ...caps,
      research_status: 'generate_ready',
      research_run_phase: 'succeeded',
    });
  const api = (() => ({
    draftCapabilities,
    draftHistory: vi
      .fn()
      .mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 }),
    draftDetail: vi
      .fn()
      .mockResolvedValue({ ...completed, draft_run_id: 'inapp-run' }),
    researchStart: vi.fn(),
    researchReview: vi.fn(),
  })) as unknown as InvestigationFactory;
  render(
    <DraftWorkspace
      id="case"
      api={api}
      context={context}
      packet={parent}
      invalidate={vi.fn()}
    />,
  );
  await screen.findByRole('button', { name: 'Generate new investigation' });
  // The stale "running" state was refreshed once from the server, not guessed.
  expect(draftCapabilities).toHaveBeenCalledTimes(2);
  expect(screen.queryByText('Investigation in progress')).toBeNull();
});
