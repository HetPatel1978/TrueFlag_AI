// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { StrictMode } from 'react';
import App, { type ApiFactory } from './App';
import {
  ApiError,
  type AssessmentDetail,
  type Case,
  type Client,
  type Job,
} from './api';
import { CaseView, Dashboard, Explanation, Workflow } from './workbench';
import { Receipts, type Receipt } from './receipts';

const record: Case = {
  id: '11111111-1111-4111-8111-111111111111',
  alert_id: 'alert',
  source_id: 'synthetic-component-case',
  assigned_to: 'user',
  status: 'open',
  disposition: null,
  version: 2,
  created_at: '2026-11-01T00:00:00Z',
  priority: 'High',
  assessment_status: 'not_requested',
  latest_job_id: null,
};
const user = { id: 'user', username: 'analyst', role: 'analyst' as const };
const pending: Job = {
  job_id: 'job',
  case_id: record.id,
  run_id: 'run',
  status: 'pending',
  attempts: 0,
  policy: 'Balanced',
  assessment_id: null,
  failure_code: null,
  fallback_route: null,
  human_decision_required: true,
};
// Explicitly synthetic UI fixtures; real RF/SHAP acceptance runs separately through Chromium/Linux.
const detail: AssessmentDetail = {
  assessment_id: 'assessment',
  case_id: record.id,
  alert_id: 'alert',
  run_id: 'run',
  version: 1,
  case_version: 2,
  processed_at: record.created_at,
  score: 0.25,
  model_version: 'synthetic-component-model',
  model_sha256: 'a'.repeat(64),
  selected_policy: 'Balanced',
  policy_version: 'synthetic-policy',
  recommended_route: 'retain_human_review',
  input_sha256: 'b'.repeat(64),
  content_sha256: 'c'.repeat(64),
  human_decision_required: true,
  input_provenance: {
    feature_contract_version: 'synthetic-contract',
    contract_sha256: 'd'.repeat(64),
    ingestion_input_sha256: 'e'.repeat(64),
    hash_schema: 'synthetic-hash',
  },
  policy_trace: {
    threshold: 0.2,
    priority_group: 'High',
    override_reason: null,
    routing_reason: 'above',
    policy_sha256: 'f'.repeat(64),
  },
  explanation: {
    status: 'verified',
    base_value: 0.2,
    features: Array.from({ length: 27 }, (_, i) => ({
      name: i === 0 ? 'income' : `syntheticFeature${i}`,
      contribution: i === 0 ? 0.06 : i === 1 ? -0.01 : 0,
      direction:
        i === 0 ? 'raises_score' : i === 1 ? 'lowers_score' : 'no_contribution',
      missing: i === 0,
    })),
    ranking: [],
    reconstruction_residual: 0,
    method: {
      algorithm: 'Exact TreeSHAP',
      output_space: 'SAR-positive predict_proba score',
      positive_class_label: 1,
      library_version: '0.51.0',
    },
    verification: {
      status: 'verified',
      verifier: 'synthetic-verifier',
      reconstruction_atol: 1e-6,
      runtime_dependencies: {},
    },
  },
};
function apiWith(overrides: Partial<Client> = {}) {
  const base: Client = {
    cases: vi
      .fn()
      .mockResolvedValue({ items: [record], total: 1, limit: 20, offset: 0 }),
    overview: vi.fn().mockResolvedValue(record),
    history: vi
      .fn()
      .mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 }),
    detail: vi.fn().mockResolvedValue(detail),
    job: vi.fn().mockResolvedValue(pending),
    submit: vi.fn().mockResolvedValue(pending),
    ...overrides,
  };
  return { service: base, api: (() => base) as ApiFactory };
}
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = '';
});

describe('authorized dashboard', () => {
  it('honors case read Retry-After and clears a transient error after successful recovery', async () => {
    vi.useFakeTimers();
    const overview = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(429, 30))
      .mockResolvedValue(record);
    const { api } = apiWith({ overview });
    render(<CaseView id={record.id} workflow={false} api={api} user={user} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(
      screen.getByRole('heading', { name: 'Updates paused' }),
    ).toBeTruthy();
    expect(
      screen
        .getByRole('button', { name: 'Retry in 30s' })
        .hasAttribute('disabled'),
    ).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(29999);
    });
    expect(overview).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(overview).toHaveBeenCalledTimes(2);
    expect(
      screen.queryByRole('heading', { name: 'Unable to load' }),
    ).toBeNull();
    expect(
      screen.getByRole('heading', { name: `Case ${record.id.slice(0, 8)}` }),
    ).toBeTruthy();
  });
  it('renders loading followed by authorized rows and backend query parameters', async () => {
    const { api, service } = apiWith();
    render(<Dashboard api={api} user={user} />);
    expect(screen.getByText('Loading authorized cases…')).toBeTruthy();
    expect(
      await screen.findByRole('link', { name: 'Case 11111111' }),
    ).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Search cases'), {
      target: { value: 'needle' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() =>
      expect(service.cases).toHaveBeenLastCalledWith(
        expect.objectContaining({}),
      ),
    );
    expect(vi.mocked(service.cases).mock.calls.at(-1)![0].get('search')).toBe(
      'needle',
    );
    fireEvent.change(screen.getByLabelText('Priority'), {
      target: { value: 'High' },
    });
    await waitFor(() =>
      expect(
        vi.mocked(service.cases).mock.calls.at(-1)![0].get('priority'),
      ).toBe('High'),
    );
    expect(screen.queryByLabelText('Assignment')).toBeNull();
  });
  it('shows empty/error/retry states without invented rows', async () => {
    const cases = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(503))
      .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
    const { api } = apiWith({ cases });
    render(<Dashboard api={api} user={user} />);
    expect(await screen.findByRole('alert')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('No matching cases')).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Case 11111111' })).toBeNull();
  });
  it('exposes oversight assignment filters and bounded page navigation', async () => {
    const { api, service } = apiWith({
      cases: vi.fn().mockResolvedValue({
        items: [record],
        total: 25,
        limit: 20,
        offset: 0,
      }),
    });
    render(<Dashboard api={api} user={{ ...user, role: 'supervisor' }} />);
    expect(screen.getByLabelText('Assignment')).toBeTruthy();
    await screen.findByRole('link', { name: 'Case 11111111' });
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    await waitFor(() =>
      expect(vi.mocked(service.cases).mock.calls.at(-1)![0].get('offset')).toBe(
        '20',
      ),
    );
  });
});

describe('verified feature attribution', () => {
  it('does not overwrite a selected historical result with a late initial response', async () => {
    let resolve!: (value: AssessmentDetail) => void;
    const delayed = new Promise<AssessmentDetail>((done) => {
      resolve = done;
    });
    const newest = {
      ...detail,
      assessment_id: 'newest',
      version: 2,
      model_version: 'newest-model',
    };
    const older = { ...detail, model_version: 'chosen-historical-model' };
    const { api } = apiWith({
      history: vi.fn().mockResolvedValue({
        items: [newest, older],
        total: 2,
        limit: 10,
        offset: 0,
      }),
      detail: vi
        .fn()
        .mockImplementation((_case, id) =>
          id === 'newest' ? delayed : Promise.resolve(older),
        ),
    });
    render(<CaseView id={record.id} workflow={false} api={api} user={user} />);
    fireEvent.change(await screen.findByLabelText('Assessment version'), {
      target: { value: older.assessment_id },
    });
    expect(await screen.findByText('chosen-historical-model')).toBeTruthy();
    await act(async () => {
      resolve(newest);
    });
    expect(screen.getByText('chosen-historical-model')).toBeTruthy();
    expect(screen.queryByText('newest-model')).toBeNull();
  });
  it('shows signed contributions, missing indicator, model identity and human boundary', () => {
    render(<Explanation value={detail} />);
    expect(screen.getByTestId('rf-score').textContent).toBe('25.0%');
    expect(screen.getByText('+6.0 pp')).toBeTruthy();
    expect(screen.getByText('−1.0 pp')).toBeTruthy();
    expect(screen.getByText('missing')).toBeTruthy();
    expect(
      screen.getByText(/Model signal for analyst review, not proof/),
    ).toBeTruthy();
    expect(screen.getByText('synthetic-component-model')).toBeTruthy();
    expect(
      screen.getByRole('list', { name: 'Contributing Risk Factors' }).children
        .length,
    ).toBe(3);
    fireEvent.click(screen.getByRole('button', { name: 'Show all 27' }));
    expect(
      screen.getByRole('list', { name: 'Contributing Risk Factors' }).children
        .length,
    ).toBe(27);
  });
  it('does not silently display an unverified or non-finite result', () => {
    render(<Explanation value={{ ...detail, score: NaN }} />);
    expect(screen.getByRole('alert').textContent).toContain('unavailable');
    expect(screen.queryByTestId('rf-score')).toBeNull();
  });
});

describe('durable asynchronous workflow', () => {
  it('preserves an uncertain run/key across view changes within the same memory session', async () => {
    const receipts = new Map<string, Receipt>();
    const submit = vi.fn().mockRejectedValue(new ApiError(503));
    const { api } = apiWith({ submit });
    const view = render(
      <Receipts.Provider value={receipts}>
        <Workflow api={api} record={record} />
      </Receipts.Provider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Request assessment' }));
    await screen.findByRole('alert');
    view.unmount();
    render(
      <Receipts.Provider value={receipts}>
        <Workflow api={api} record={record} />
      </Receipts.Provider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Retry same request' }));
    await screen.findByRole('alert');
    expect(submit.mock.calls[0]).toEqual(submit.mock.calls[1]);
  });
  it('uses stable run/key/body on uncertain transport retry and prevents duplicate active submits', async () => {
    const submit = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(503))
      .mockResolvedValue(pending);
    const { api } = apiWith({ submit });
    render(
      <StrictMode>
        <Workflow api={api} record={record} />
      </StrictMode>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Request assessment' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Retry same request' }));
    await screen.findByText(/Request received/);
    expect(submit.mock.calls[0]).toEqual(submit.mock.calls[1]);
    expect(Object.keys(submit.mock.calls[0][1]).sort()).toEqual([
      'expected_version',
      'policy',
      'run_id',
    ]);
    expect(
      (
        screen.getByRole('button', {
          name: 'Assessment in progress',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
  it('stops on conflicts and requires a fresh case view', async () => {
    const { api, service } = apiWith({
      submit: vi.fn().mockRejectedValue(new ApiError(409)),
    });
    render(<Workflow api={api} record={record} />);
    fireEvent.click(screen.getByRole('button', { name: 'Request assessment' }));
    expect(
      await screen.findByRole('link', { name: 'Reload case details' }),
    ).toBeTruthy();
    expect(service.submit).toHaveBeenCalledTimes(1);
  });
  it('honors request throttling before exposing a retry', async () => {
    vi.useFakeTimers();
    const { api } = apiWith({
      submit: vi.fn().mockRejectedValue(new ApiError(429, 3)),
    });
    render(<Workflow api={api} record={record} />);
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', { name: 'Request assessment' }),
      );
    });
    expect(
      (
        screen.getByRole('button', {
          name: 'Retry same request',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(
      (
        screen.getByRole('button', {
          name: 'Retry same request',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
  });
  it('shows actual Running/Completed states and stops polling after completion', async () => {
    vi.useFakeTimers();
    const job = vi
      .fn()
      .mockResolvedValueOnce({ ...pending, status: 'running', attempts: 1 })
      .mockResolvedValue({
        ...pending,
        status: 'succeeded',
        assessment_id: 'assessment',
      });
    const { api } = apiWith({ job });
    render(<Workflow api={api} record={{ ...record, latest_job_id: 'job' }} />);
    await act(async () => {});
    expect(
      screen.getByText(/Assessment and contributing factors are being checked/),
    ).toBeTruthy();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(
      screen.getByRole('link', { name: 'View verified results →' }),
    ).toBeTruthy();
    const count = job.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(job).toHaveBeenCalledTimes(count);
  });
  it('bounds downtime polling and cleans timers on unmount', async () => {
    vi.useFakeTimers();
    const { api, service } = apiWith();
    const view = render(
      <Workflow api={api} record={{ ...record, latest_job_id: 'job' }} />,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(310000);
    });
    expect(screen.getByText(/Automatic status checks are paused/)).toBeTruthy();
    expect(vi.mocked(service.job).mock.calls.length).toBeLessThanOrEqual(60);
    view.unmount();
    const count = vi.mocked(service.job).mock.calls.length;
    await vi.advanceTimersByTimeAsync(60000);
    expect(service.job).toHaveBeenCalledTimes(count);
  });
  it('retains manual review on terminal failures and never displays fabricated results', async () => {
    const { api } = apiWith({
      job: vi.fn().mockResolvedValue({
        ...pending,
        status: 'failed',
        failure_code: 'processing_unavailable',
        fallback_route: 'manual_review',
      }),
    });
    render(<Workflow api={api} record={{ ...record, latest_job_id: 'job' }} />);
    expect(await screen.findByText('Manual review required.')).toBeTruthy();
    expect(screen.queryByTestId('rf-score')).toBeNull();
  });
  it('does not poll faster than Retry-After after service failures', async () => {
    vi.useFakeTimers();
    const job = vi.fn().mockRejectedValue(new ApiError(429, 30));
    const { api } = apiWith({ job });
    render(<Workflow api={api} record={{ ...record, latest_job_id: 'job' }} />);
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(29000);
    });
    expect(job).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(job).toHaveBeenCalledTimes(2);
  });
});

it('clears protected state on sign-out and assignment denial even with a late response', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      if (path.startsWith('/api/v1/upload-sessions'))
        return new Response(
          JSON.stringify({
            version: 1,
            active: {
              id: 'uploaded-session',
              created_at: record.created_at,
              case_count: 1,
              upload_count: 1,
              uploads: [],
              can_upload: false,
            },
            items: [],
            total: 0,
            offset: 0,
            limit: 20,
          }),
        );
      if (path.endsWith('/auth/session') && init?.method !== 'POST')
        return new Response('{}', { status: 401 });
      if (path.endsWith('/auth/session'))
        return new Response(
          JSON.stringify({ access_token: 'synthetic-token' }),
        );
      if (path.endsWith('/auth/me')) return new Response(JSON.stringify(user));
      if (path.includes('/overview') || path.includes('/workflow'))
        return new Response('{}', { status: 404 });
      return new Response(
        JSON.stringify({ items: [record], total: 1, limit: 20, offset: 0 }),
      );
    }),
  );
  render(<App />);
  fireEvent.change(await screen.findByLabelText('Username'), {
    target: { value: 'analyst' },
  });
  fireEvent.change(screen.getByLabelText('Password'), {
    target: { value: 'synthetic-password' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  fireEvent.click(await screen.findByRole('link', { name: 'Case 11111111' }));
  await act(async () => {
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
  expect(
    await screen.findByRole('heading', { name: 'Information unavailable' }),
  ).toBeTruthy();
  expect(screen.queryByRole('link', { name: 'Case 11111111' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
  expect(
    await screen.findByRole('heading', { name: 'Welcome back' }),
  ).toBeTruthy();
});
