// @vitest-environment jsdom
// Contract-focused UI tests; actual PostgreSQL/Chromium acceptance is separate.
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { ApiError } from './api';
import { HumanCasework, SupervisorQueue } from './human-casework';
import {
  humanCaseworkClient,
  type HumanEntry,
  type HumanPage,
} from './human-casework-api';
import {
  investigationClient,
  type CaseContext,
  type Evidence,
} from './investigation-api';

const user = {
  id: 'analyst-id',
  username: 'analyst',
  role: 'analyst' as const,
};
const reference = {
  record_version_id: 'record-id',
  identity_id: 'identity',
  source_version_id: 'source',
  kind: 'transaction',
  version: 1,
  sha256: 'a'.repeat(64),
};
const context: Evidence<CaseContext> = {
  snapshot: {
    id: 'snapshot',
    sha256: 'b'.repeat(64),
    case_version: 2,
    evidence_revision: 1,
    access_revision: 2,
  },
  data: {
    case_id: 'case',
    snapshot_token: 'synthetic-current-proof',
    selected_assessment_id: null,
    model_signal: null,
    available_categories: ['transaction'],
    missing_categories: [],
    account_handles: [],
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
const page: HumanPage = {
  items: [],
  revision: 0,
  total: 0,
  limit: 20,
  offset: 0,
  open_information_requests: 0,
  pending_escalations: 0,
  resolution: null,
  policy_version: 'trueflag.human-casework.v1',
  allowed_resolutions: ['investigation_completed'],
};
const entry: HumanEntry = {
  id: 'entry',
  case_id: 'case',
  actor_id: user.id,
  author: 'analyst',
  recorded_at: '2026-11-16T14:00:00Z',
  revision: 1,
  kind: 'note',
  parent_id: null,
  content_sha256: 'c'.repeat(64),
  payload: { rationale: 'A documented human note.', supporting_records: [] },
  binding: { case_version: 2, evidence_revision: 1, access_revision: 2 },
  content_status: 'available',
  immutable: true,
};
function setup(value = page, manager = false, decide = false) {
  const client = {
    ...humanCaseworkClient('fixture'),
    history: vi.fn().mockResolvedValue(value),
    submit: vi.fn().mockResolvedValue(entry),
    queue: vi
      .fn()
      .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 }),
  };
  const evidence = {
    ...investigationClient('fixture', new AbortController().signal, () => {}),
    context: vi.fn().mockResolvedValue(context),
  };
  const api = vi.fn<(signal?: AbortSignal) => typeof client>(() => client),
    evidenceApi = vi.fn<(signal?: AbortSignal) => typeof evidence>(
      () => evidence,
    ),
    changed = vi.fn();
  const view = render(
    <HumanCasework
      id="case"
      user={
        manager
          ? { id: 'supervisor', username: 'supervisor', role: 'supervisor' }
          : user
      }
      api={api}
      evidenceApi={evidenceApi}
      changed={changed}
      decide={decide}
    />,
  );
  return { client, evidence, api, evidenceApi, view, changed };
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('Human investigation casework', () => {
  it('loads only authorized persisted casework and no automatic write', async () => {
    const e = setup();
    await screen.findByRole('form', { name: 'Investigation Notes' });
    expect(e.client.history).toHaveBeenCalledWith('case', 0);
    expect(e.client.submit).not.toHaveBeenCalled();
    expect(screen.queryByRole('form', { name: 'Case Resolution' })).toBeNull();
    expect(screen.getByText(/No submitted human casework/)).toBeTruthy();
  });
  it('submits explicit source-bound note with revision and idempotency key', async () => {
    const e = setup();
    const form = await screen.findByRole('form', {
      name: 'Investigation Notes',
    });
    fireEvent.change(screen.getByLabelText('Supporting record'), {
      target: { value: 'record-id' },
    });
    fireEvent.change(within(form).getByLabelText('Investigation note'), {
      target: { value: 'Reviewed source evidence carefully.' },
    });
    fireEvent.submit(form);
    await waitFor(() => expect(e.client.submit).toHaveBeenCalledTimes(1));
    expect(e.client.submit.mock.calls[0][2]).toEqual({
      kind: 'note',
      rationale: 'Reviewed source evidence carefully.',
      supporting_records: [reference],
      snapshot: 'synthetic-current-proof',
      expected_revision: 0,
    });
    expect(e.client.submit.mock.calls[0][1]).toMatch(/^[a-f0-9-]{36}$/);
    expect(localStorage.length + sessionStorage.length).toBe(0);
  });
  it('prevents simultaneous double submissions', async () => {
    const e = setup();
    const form = await screen.findByRole('form', {
      name: 'Investigation Notes',
    });
    e.client.submit.mockReturnValue(new Promise(() => {}));
    fireEvent.change(within(form).getByLabelText('Investigation note'), {
      target: { value: 'Reviewed source evidence carefully.' },
    });
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(e.client.submit).toHaveBeenCalledTimes(1);
  });
  it.each([401, 403, 404, 409, 503])(
    'clears notes and forms on denial %s',
    async (status) => {
      const e = setup({ ...page, items: [entry], total: 1, revision: 1 });
      const form = await screen.findByRole('form', {
        name: 'Investigation Notes',
      });
      e.client.submit.mockRejectedValue(new ApiError(status));
      fireEvent.change(within(form).getByLabelText('Investigation note'), {
        target: { value: 'A new submitted analyst note.' },
      });
      fireEvent.submit(form);
      await waitFor(() =>
        expect(
          screen.queryByRole('form', { name: 'Investigation Notes' }),
        ).toBeNull(),
      );
      expect(screen.queryByText('A documented human note.')).toBeNull();
      expect(screen.getByRole('alert')).toBeTruthy();
    },
  );
  it('withholds revoked source content and renders rationale as plain text', async () => {
    setup({
      ...page,
      total: 2,
      items: [
        {
          ...entry,
          payload: {
            rationale: '<img src=x onerror=alert(1)>',
            supporting_records: [],
          },
        },
        {
          ...entry,
          id: 'withheld',
          payload: null,
          binding: null,
          content_status: 'withheld_source_changed',
        },
      ],
    });
    await screen.findByText('<img src=x onerror=alert(1)>');
    expect(document.querySelector('.human-rationale img')).toBeNull();
    expect(screen.getByText(/Content withheld because source/)).toBeTruthy();
  });
  it('requires confirmation before recording a final supervisor decision', async () => {
    const approval: HumanEntry = {
      ...entry,
      id: 'approval',
      actor_id: 'supervisor',
      kind: 'supervisor_response',
      payload: {
        rationale: 'Approved after independent human review.',
        supporting_records: [],
        decision: 'approve_resolution',
        proposed_outcome: 'investigation_completed',
      },
    };
    const e = setup(
      { ...page, revision: 1, total: 1, items: [approval] },
      true,
    );
    // Only actions valid for the case state and role are offered; pick the resolution.
    fireEvent.change(await screen.findByLabelText('Action'), {
      target: { value: 'resolution' },
    });
    const form = await screen.findByRole('form', { name: 'Case Resolution' });
    fireEvent.change(within(form).getByLabelText('Decision rationale'), {
      target: {
        value: 'The supervisor confirms the documented internal outcome.',
      },
    });
    fireEvent.submit(form);
    const dialog = await screen.findByRole('dialog', {
      name: 'Confirm human decision',
    });
    expect(e.client.submit).not.toHaveBeenCalled();
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Cancel decision' }),
    );
    expect(e.client.submit).not.toHaveBeenCalled();
  });
  it('offers only the actions valid for the case state and role', async () => {
    setup();
    const picker = (await screen.findByLabelText(
      'Action',
    )) as HTMLSelectElement;
    const options = [...picker.options].map((o) => o.textContent);
    expect(options).toEqual([
      'Write note',
      'Request information',
      'Review AI findings',
      'Escalate to supervisor',
      'Link supporting evidence',
    ]);
    expect(picker.value).toBe('note');
  });
  it('preselects the decision action valid for the user when opened from Record decision', async () => {
    setup(page, false, true);
    const picker = (await screen.findByLabelText(
      'Action',
    )) as HTMLSelectElement;
    expect(picker.value).toBe('escalation');
    await screen.findByRole('form', { name: 'Supervisor Escalation' });
  });
  it('loads a verified live AI result for review, labelled as live', async () => {
    const e = setup();
    const live = {
      status: 'succeeded',
      draft_run_id: 'run-live',
      draft: {
        draft_run_id: 'run-live',
        content_sha256: 'a'.repeat(64),
        simulation: false,
        live_provider_used: true,
        findings: [
          {
            reference_id: '12345678-0000-4000-8000-000000000000',
            claim_type: 'observed_fact',
          },
        ],
      },
    };
    e.evidence.draftHistory = vi.fn().mockResolvedValue({
      items: [{ draft_run_id: 'run-live', status: 'succeeded' }],
      total: 1,
      limit: 10,
      offset: 0,
    }) as never;
    e.evidence.draftDetail = vi.fn().mockResolvedValue(live) as never;
    const picker = (await screen.findByLabelText(
      'Action',
    )) as HTMLSelectElement;
    fireEvent.change(picker, { target: { value: 'finding_review' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'Load my latest verified AI findings',
      }),
    );
    await screen.findByRole('form', { name: 'Finding Review Decision' });
    expect(screen.getByText(/Live AI result \(verified\)/)).toBeTruthy();
    expect(
      screen.queryByText(/No completed, verified AI investigation/),
    ).toBeNull();
  });
  it('aborts pending reads on unmount', () => {
    const e = setup();
    const signal = e.api.mock.calls[0][0];
    e.view.unmount();
    expect(signal?.aborted).toBe(true);
  });
  it('shows supervisor queue links using the protected queue contract', async () => {
    const client = {
      ...humanCaseworkClient('fixture'),
      queue: vi.fn().mockResolvedValue({
        items: [
          {
            case_id: 'case',
            escalation_id: 'request',
            author: 'analyst',
            recorded_at: '2026-11-16T14:00:00Z',
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      }),
    };
    render(<SupervisorQueue api={() => client} />);
    await screen.findByRole('link', { name: 'Review case case' });
    expect(client.queue).toHaveBeenCalledWith(0);
  });
});
