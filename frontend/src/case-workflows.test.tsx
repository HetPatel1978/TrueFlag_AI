// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { AssignmentControl, ActivityHistory } from './case-workflows';
import { Dashboard, CaseView } from './workbench';
import { ApiError, type Client } from './api';
import {
  workflowClient,
  type WorkflowCase,
  type WorkflowFactory,
} from './workflow-api';

const record: WorkflowCase = {
  id: '11111111-1111-4111-8111-111111111111',
  alert_id: 'alert',
  source_id: 'synthetic-workflow',
  assigned_to: null,
  assigned_investigator: null,
  status: 'open',
  disposition: null,
  version: 1,
  created_at: '2026-11-01T00:00:00Z',
  priority: 'High',
  assessment_status: 'not_requested',
  latest_job_id: null,
  review_recommendation: null,
  assessment_version: null,
};
const user = { id: 'reader', username: 'analyst', role: 'analyst' as const };
function fixture() {
  const client = {
    queue: vi
      .fn()
      .mockResolvedValue({ items: [record], total: 1, limit: 20, offset: 0 }),
    overview: vi.fn().mockResolvedValue(record),
    directory: vi.fn().mockResolvedValue({
      items: [{ id: 'eligible', username: 'Eligible Analyst' }],
      total: 1,
      limit: 20,
      offset: 0,
      case_version: 1,
    }),
    assign: vi.fn().mockResolvedValue({ ...record, version: 2 }),
    activity: vi.fn().mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
      case_version: 1,
      historical: true,
    }),
  };
  return { client, api: (() => client) as WorkflowFactory };
}
beforeAll(() => {
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute('open');
  };
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute('open', '');
  };
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
describe('case workflows', () => {
  it('uses authorized queue and hides manager scope for analysts', async () => {
    const { api, client } = fixture();
    render(
      <Dashboard api={() => ({}) as Client} workflowApi={api} user={user} />,
    );
    await screen.findByRole('link', { name: 'Case 11111111' });
    expect(client.queue.mock.calls[0][0].get('queue')).toBe('my');
    expect(
      screen.queryByRole('option', { name: 'Unassigned Cases' }),
    ).toBeNull();
    fireEvent.change(screen.getByLabelText('Case Queue'), {
      target: { value: 'processing' },
    });
    await waitFor(() =>
      expect(client.queue.mock.calls.at(-1)?.[0].get('queue')).toBe(
        'processing',
      ),
    );
    expect(screen.getByText('Not assessed')).toBeTruthy();
  });
  it('offers manager scope and renders only a stored recommendation', async () => {
    const { api, client } = fixture();
    client.queue.mockResolvedValue({
      items: [
        {
          ...record,
          review_recommendation: 'retain_human_review',
          assessment_version: 3,
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    });
    render(
      <Dashboard
        api={() => ({}) as Client}
        workflowApi={api}
        user={{ ...user, role: 'supervisor' }}
      />,
    );
    expect(await screen.findByText('Continue analyst review')).toBeTruthy();
    expect(
      screen.queryByText('Assessment v3 · Recommendation only'),
    ).toBeNull();
    expect(
      screen.getByRole('option', { name: 'Unassigned Cases' }),
    ).toBeTruthy();
  });
  it('assigns a directory selection using the exact expected case version once', async () => {
    const { api, client } = fixture();
    const changed = vi.fn();
    render(<AssignmentControl api={api} record={record} changed={changed} />);
    fireEvent.click(
      screen.getByRole('button', { name: 'Assign investigator' }),
    );
    await screen.findByRole('option', { name: 'Eligible Analyst' });
    fireEvent.change(screen.getByLabelText('Assigned Investigator'), {
      target: { value: 'eligible' },
    });
    const confirm = screen.getByRole('button', { name: 'Confirm assignment' });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
    expect(client.assign).toHaveBeenCalledExactlyOnceWith(
      record.id,
      1,
      'eligible',
    );
  });
  it.each([409, 0, 429])(
    'requires fresh state after ambiguous/conflicting mutation %i',
    async (status) => {
      const { api, client } = fixture();
      client.assign.mockRejectedValue(new ApiError(status));
      render(<AssignmentControl api={api} record={record} changed={vi.fn()} />);
      fireEvent.click(
        screen.getByRole('button', { name: 'Assign investigator' }),
      );
      await screen.findByRole('option', { name: 'Eligible Analyst' });
      fireEvent.change(screen.getByLabelText('Assigned Investigator'), {
        target: { value: 'eligible' },
      });
      fireEvent.click(
        screen.getByRole('button', { name: 'Confirm assignment' }),
      );
      expect(
        await screen.findByRole('button', { name: 'Refresh case' }),
      ).toBeTruthy();
      expect(
        screen.queryByRole('button', { name: 'Confirm assignment' }),
      ).toBeNull();
      expect(client.assign).toHaveBeenCalledTimes(1);
    },
  );
  it('blocks a stale assignment directory and aborts on dialog cleanup', async () => {
    const { api, client } = fixture();
    client.directory.mockResolvedValue({ items: [], case_version: 2 });
    render(<AssignmentControl api={api} record={record} changed={vi.fn()} />);
    fireEvent.click(
      screen.getByRole('button', { name: 'Assign investigator' }),
    );
    expect(
      await screen.findByRole('button', { name: 'Refresh case' }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(client.assign).not.toHaveBeenCalled();
  });
  it('projects redacted historical activity without payload rendering', async () => {
    const { api, client } = fixture();
    client.activity.mockResolvedValue({
      items: [
        {
          id: 'event',
          case_id: record.id,
          event_type: 'assignment_changed',
          recorded_at: record.created_at,
          actor: 'redacted',
          outcome: 'recorded',
          case_version: 2,
          assignment_change: 'reassigned',
          historical: true,
          private_notes: 'DO NOT RENDER',
        },
      ],
      total: 21,
      limit: 20,
      offset: 0,
      case_version: 1,
      historical: true,
    });
    render(<ActivityHistory api={api} record={record} />);
    expect(await screen.findByText('Assignment changed')).toBeTruthy();
    expect(screen.getByText(/Another user/)).toBeTruthy();
    expect(screen.queryByText(/Historical/)).toBeNull();
    expect(screen.queryByText('DO NOT RENDER')).toBeNull();
    fireEvent.change(screen.getByLabelText('Event category'), {
      target: { value: 'assignment' },
    });
    await waitFor(() =>
      expect(client.activity).toHaveBeenLastCalledWith(
        record.id,
        'assignment',
        0,
      ),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Show older' }));
    await waitFor(() =>
      expect(client.activity).toHaveBeenLastCalledWith(
        record.id,
        'assignment',
        20,
      ),
    );
  });
  it('appends older activity below instead of paging, with exact local time tooltips', async () => {
    const { api, client } = fixture();
    const event = (n: number) => ({
      id: `event-${n}`,
      case_id: record.id,
      event_type: n === 0 ? 'summary_published' : 'assignment_changed',
      recorded_at: `2026-11-${String(10 + Math.floor(n / 10)).padStart(2, '0')}T10:${String(n % 60).padStart(2, '0')}:00Z`,
      actor: 'you',
      outcome: 'recorded',
      case_version: 1,
      assessment_version: null,
      evidence_revision: null,
      access_revision: null,
      assignment_change: null,
      historical: true,
    });
    client.activity.mockImplementation(
      async (_id: string, _category: string, offset: number) => ({
        items: Array.from({ length: offset ? 5 : 20 }, (_, n) =>
          event(offset ? 20 + n : n),
        ),
        total: 25,
        limit: 20,
        offset,
        case_version: 1,
        historical: true,
      }),
    );
    const view = render(<ActivityHistory api={api} record={record} />);
    expect((await screen.findAllByText('Assignment changed')).length).toBe(19);
    expect(screen.getByText('Evidence summary saved')).toBeTruthy();
    const time = view.container.querySelector('time.has-tip');
    expect(time?.getAttribute('title')).toMatch(/\d{1,2}:\d{2}:\d{2}/);
    expect(screen.getByText('20 of 25 events')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Show older' }));
    await waitFor(() =>
      expect(screen.getAllByText('Assignment changed').length).toBe(24),
    );
    expect(screen.queryByRole('button', { name: 'Show older' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Previous|Next/ })).toBeNull();
  });
  it('does not expose assignment controls to analysts', async () => {
    const { api } = fixture();
    render(
      <CaseView
        api={() =>
          ({
            history: vi
              .fn()
              .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 }),
          }) as unknown as Client
        }
        workflowApi={api}
        user={user}
        id={record.id}
        workflow={false}
      />,
    );
    await screen.findByRole('heading', { name: 'Case 11111111' });
    expect(
      screen.queryByRole('button', { name: 'Assign investigator' }),
    ).toBeNull();
  });
  it('uses authenticated no-store APIs and sanitized denials', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response('{}', { status: 403 }));
    vi.stubGlobal('fetch', fetcher);
    const denied = vi.fn();
    await expect(
      workflowClient('synthetic-session', undefined, denied).activity(
        record.id,
        'all',
        0,
      ),
    ).rejects.toBeInstanceOf(ApiError);
    expect(denied).toHaveBeenCalledWith(403);
    expect(fetcher.mock.calls[0][1]).toMatchObject({
      cache: 'no-store',
      credentials: 'omit',
      headers: { Authorization: 'Bearer synthetic-session' },
    });
  });
});
