// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { UploadWorkspace, type UploadSession } from './upload-workspace';

const active: UploadSession = {
  id: '11111111-1111-4111-8111-111111111111',
  created_at: '2026-11-18T12:00:00Z',
  upload_count: 1,
  case_count: 2,
  can_upload: true,
  uploads: [
    {
      upload_id: 'upload-1',
      created_at: '2026-11-18T12:00:00Z',
      status: 'completed',
      resume_route: '#/batch/import/receipt',
    },
  ],
};
const user = { id: 'user', username: 'owner', role: 'admin' as const };
const workspace = (value: UploadSession | null = active, version = 1) => ({
  active: value,
  version,
  items: value ? [{ id: value.id, created_at: value.created_at }] : [],
  total: value ? 1 : 0,
  offset: 0,
  limit: 20,
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = '';
});
function mount(denied = vi.fn()) {
  return render(
    <UploadWorkspace
      token="private-test-token"
      user={user}
      onDenied={denied}
      route="#/"
    >
      {(s) => <div>Cases scoped to {s.id}</div>}
    </UploadWorkspace>,
  );
}

it('restores a persisted session after remount without browser-storing protected state', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(workspace()))),
  );
  const first = mount();
  await screen.findByText(/2 cases/);
  expect(screen.getByText(`Cases scoped to ${active.id}`)).toBeTruthy();
  first.unmount();
  mount();
  await screen.findByText(/2 cases/);
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
});

it('requires explicit confirmation and sends an idempotency key before starting an empty session', async () => {
  const next = {
    ...active,
    id: '22222222-2222-4222-8222-222222222222',
    case_count: 0,
    upload_count: 0,
    uploads: [],
  };
  const fetcher = vi.fn(
    async (_url: string, init?: RequestInit) =>
      new Response(
        JSON.stringify(
          init?.method === 'POST' ? workspace(next, 2) : workspace(),
        ),
      ),
  );
  vi.stubGlobal('fetch', fetcher);
  mount();
  await screen.findByText(/2 cases/);
  fireEvent.click(screen.getByText('New session'));
  expect(fetcher).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByText('Confirm new session'));
  await screen.findByText(/0 cases/);
  const call = fetcher.mock.calls.find((c) => c[1]?.method === 'POST')!;
  expect(JSON.parse(call[1]!.body as string)).toEqual({ version: 1 });
  expect(
    (call[1]!.headers as Record<string, string>)['Idempotency-Key'],
  ).toBeTruthy();
  expect(window.location.hash).toBe('#/batch/new');
});

it('does not create a session when confirmation is cancelled', async () => {
  const fetcher = vi.fn(async () => new Response(JSON.stringify(workspace())));
  vi.stubGlobal('fetch', fetcher);
  mount();
  await screen.findByText(/2 cases/);
  fireEvent.click(screen.getByText('New session'));
  fireEvent.click(screen.getByText('Cancel'));
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it('hides protected children on permission revocation and calls the denial handler', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(workspace())))
    .mockResolvedValue(new Response('{}', { status: 403 }));
  vi.stubGlobal('fetch', fetcher);
  const denied = vi.fn();
  mount(denied);
  await screen.findByText(/2 cases/);
  fireEvent(window, new Event('focus'));
  await waitFor(() => expect(denied).toHaveBeenCalledWith(403));
  expect(screen.queryByText(`Cases scoped to ${active.id}`)).toBeNull();
});

it('keeps archived receipts expandable and does not render raw feature data', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(workspace()))),
  );
  mount();
  await screen.findByText(/2 cases/);
  // History stays hidden behind the session menu until requested.
  expect(screen.queryByText('Resume upload 1')).toBeNull();
  fireEvent.click(screen.getByText('Session history'));
  const link = screen.getByText('Resume upload 1');
  expect(link.getAttribute('href')).toBe('#/batch/import/receipt');
  expect(link.closest('.session-history')).toBeTruthy();
});

it('shows an empty authorized workspace without falling back to unscoped case requests', async () => {
  const fetcher = vi.fn(
    async () => new Response(JSON.stringify(workspace(null))),
  );
  vi.stubGlobal('fetch', fetcher);
  mount();
  await screen.findByText('No uploaded cases available');
  expect(screen.queryByText(`Cases scoped to ${active.id}`)).toBeNull();
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it('refreshes the case count when an import finishes (no route change)', async () => {
  const { SESSION_CHANGED } = await import('./upload-workspace');
  let count = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify(workspace({ ...active, case_count: count })),
        ),
    ),
  );
  mount();
  await screen.findByText(/0 cases/);
  count = 8;
  window.dispatchEvent(new Event(SESSION_CHANGED));
  await screen.findByText(/8 cases/);
});
