// @vitest-environment jsdom
import {
  cleanup,
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import App from './App';
import {
  endBrowserSession,
  restoreBrowserSession,
  rememberedRenewalDelay,
} from './session';

const user = {
  id: 'synthetic-user',
  username: 'synthetic-analyst',
  role: 'analyst',
};
const restored = { access_token: 'synthetic-memory-token', user };
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  sessionStorage.clear();
  localStorage.clear();
  vi.unstubAllGlobals();
  window.location.hash = '';
});
function rememberedToken(expires: number) {
  return (
    'synthetic.' +
    btoa(
      JSON.stringify({
        sid: '11111111-1111-4111-8111-111111111111',
        exp: expires,
      }),
    ) +
    '.signature'
  );
}
function backend(status = 200) {
  return vi.fn(async (path: string) => {
    if (path.startsWith('/api/v1/upload-sessions'))
      return new Response(
        JSON.stringify({
          version: 1,
          active: {
            id: 'uploaded-session',
            created_at: '2026-11-18T12:00:00Z',
            case_count: 0,
            upload_count: 0,
            uploads: [],
            can_upload: false,
          },
          items: [],
          total: 0,
          offset: 0,
          limit: 20,
        }),
      );
    if (path === '/api/v1/auth/session')
      return new Response(JSON.stringify(restored), { status });
    if (path === '/api/v1/auth/me') return new Response(JSON.stringify(user));
    return new Response(
      JSON.stringify({ items: [], total: 0, limit: 20, offset: 0 }),
    );
  });
}
it('restores a validated session without showing the login form or browser-storing credentials', async () => {
  const fetcher = backend();
  vi.stubGlobal('fetch', fetcher);
  render(<App />);
  expect(screen.getByText('Restoring your session…')).toBeTruthy();
  expect(screen.queryByLabelText('Password')).toBeNull();
  await screen.findByRole('button', { name: 'Sign out' });
  expect(fetcher.mock.calls[0][0]).toBe('/api/v1/auth/session');
  expect(localStorage.length + sessionStorage.length).toBe(0);
});
it('expired or absent browser sessions show login', async () => {
  vi.stubGlobal('fetch', backend(401));
  render(<App />);
  await screen.findByLabelText('Username');
  expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull();
});
it('session service failure hides the workspace and supports retry instead of silently discarding it', async () => {
  const fetcher = backend(503);
  vi.stubGlobal('fetch', fetcher);
  render(<App />);
  await screen.findByRole('heading', {
    name: 'Session verification unavailable',
  });
  expect(screen.queryByLabelText('Password')).toBeNull();
  fetcher.mockImplementation(backend());
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  await screen.findByRole('button', { name: 'Sign out' });
});
it('logout clears the remote cookie before allowing a fresh login', async () => {
  const fetcher = backend();
  vi.stubGlobal('fetch', fetcher);
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
  await screen.findByLabelText('Username');
  expect(
    fetcher.mock.calls.some(([path]) => path === '/api/v1/auth/session/logout'),
  ).toBe(true);
  expect(sessionStorage.length).toBe(0);
});
it('an interrupted logout cannot restore the old session after a refresh', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')));
  await expect(endBrowserSession()).rejects.toThrow();
  expect(sessionStorage.getItem('trueflag.signout.pending')).toBe('1');
  const fetcher = vi.fn().mockResolvedValue(new Response('{}'));
  vi.stubGlobal('fetch', fetcher);
  expect(await restoreBrowserSession(new AbortController().signal)).toBeNull();
  expect(fetcher.mock.calls[0][0]).toBe('/api/v1/auth/session/logout');
  expect(sessionStorage.length).toBe(0);
});
it('rejects malformed successful responses without exposing a workspace', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response('{"access_token":"invalid"}')),
  );
  render(<App />);
  await screen.findByRole('heading', {
    name: 'Session verification unavailable',
  });
  expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull();
});
it('aborts restoration when the application unmounts', async () => {
  let signal: AbortSignal | undefined;
  vi.stubGlobal(
    'fetch',
    vi.fn((_path, init) => {
      signal = init.signal;
      return new Promise(() => {});
    }),
  );
  const view = render(<App />);
  view.unmount();
  await waitFor(() => expect(signal?.aborted).toBe(true));
});

it('schedules renewal only for remembered sessions, without treating token claims as authorization', () => {
  expect(rememberedRenewalDelay('not-a-token')).toBeNull();
  expect(
    rememberedRenewalDelay('synthetic.' + btoa('{"exp":123}') + '.signature'),
  ).toBeNull();
  const seconds = Math.floor(Date.now() / 1000);
  expect(rememberedRenewalDelay(rememberedToken(seconds - 10))).toBe(0);
  expect(
    rememberedRenewalDelay(rememberedToken(seconds + 120)),
  ).toBeGreaterThan(58000);
});

it('renews remembered access before expiry and keeps the current workspace', async () => {
  vi.useFakeTimers();
  const seconds = Math.floor(Date.now() / 1000);
  let restores = 0;
  const fallback = backend();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string) => {
      if (path === '/api/v1/auth/session') {
        restores++;
        return new Response(
          JSON.stringify({
            access_token: rememberedToken(
              seconds + (restores === 1 ? 120 : 3600),
            ),
            user,
          }),
        );
      }
      return fallback(path);
    }),
  );
  render(<App />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  const search = screen.getByLabelText('Search cases');
  fireEvent.change(search, { target: { value: 'retained-draft' } });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60000);
  });
  expect(restores).toBe(2);
  expect(screen.getByRole('button', { name: 'Sign out' })).toBeTruthy();
  expect(
    (screen.getByLabelText('Search cases') as HTMLInputElement).value,
  ).toBe('retained-draft');
  expect(screen.queryByLabelText('Password')).toBeNull();
  expect(localStorage.length + sessionStorage.length).toBe(0);
});

it('hides the workspace on renewal failure and shows login if retry finds a revoked session', async () => {
  vi.useFakeTimers();
  const seconds = Math.floor(Date.now() / 1000);
  let restores = 0;
  const fallback = backend();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string) => {
      if (path === '/api/v1/auth/session') {
        restores++;
        if (restores === 1)
          return new Response(
            JSON.stringify({
              access_token: rememberedToken(seconds + 120),
              user,
            }),
          );
        return new Response('{}', { status: restores === 2 ? 503 : 401 });
      }
      return fallback(path);
    }),
  );
  render(<App />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60000);
  });
  expect(
    screen.getByRole('heading', { name: 'Session verification unavailable' }),
  ).toBeTruthy();
  expect(screen.queryByLabelText('Search cases')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(screen.getByLabelText('Password')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull();
});

it('logout cancels an in-flight renewal so it cannot restore access afterward', async () => {
  vi.useFakeTimers();
  const seconds = Math.floor(Date.now() / 1000);
  let restores = 0;
  let finish: ((value: Response) => void) | undefined;
  let renewalSignal: AbortSignal | undefined;
  const fallback = backend();
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      if (path === '/api/v1/auth/session/logout')
        return Promise.resolve(new Response('{}'));
      if (path === '/api/v1/auth/session') {
        restores++;
        if (restores === 1)
          return Promise.resolve(
            new Response(
              JSON.stringify({
                access_token: rememberedToken(seconds + 120),
                user,
              }),
            ),
          );
        renewalSignal = init?.signal as AbortSignal;
        return new Promise<Response>((resolve) => {
          finish = resolve;
        });
      }
      return fallback(path);
    }),
  );
  render(<App />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60000);
  });
  expect(restores).toBe(2);
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
  await act(async () => {
    finish?.(
      new Response(
        JSON.stringify({ access_token: rememberedToken(seconds + 3600), user }),
      ),
    );
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(renewalSignal?.aborted).toBe(true);
  expect(screen.getByLabelText('Password')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull();
});

it('bounds automatic renewal when the client clock is ahead of issued token timestamps', async () => {
  vi.useFakeTimers();
  const seconds = Math.floor(Date.now() / 1000);
  let restores = 0;
  const fallback = backend();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string) => {
      if (path === '/api/v1/auth/session') {
        restores++;
        return new Response(
          JSON.stringify({ access_token: rememberedToken(seconds - 10), user }),
        );
      }
      return fallback(path);
    }),
  );
  render(<App />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(restores).toBe(1);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60000);
  });
  expect(restores).toBe(2);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(restores).toBe(2);
});
