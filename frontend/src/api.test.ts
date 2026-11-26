import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  client,
  currentUser,
  health,
  pollDelay,
  signIn,
} from './api';

afterEach(() => vi.unstubAllGlobals());

describe('API boundary', () => {
  it('accepts the server-assigned supervisor role', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          id: '1',
          username: 'supervisor',
          role: 'supervisor',
        }),
      }),
    );
    expect((await currentUser('test-token')).role).toBe('supervisor');
  });
  it('reports actual backend liveness', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) }),
    );
    expect(await health()).toBe(true);
  });
  it('does not disguise a service failure as healthy', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 503 }),
    );
    await expect(health()).rejects.toThrow('503');
  });
  it('sends credentials only to the authentication endpoint', async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: 'test-token' }),
    });
    vi.stubGlobal('fetch', fetcher);
    expect(await signIn('analyst', 'test-password')).toBe('test-token');
    expect(fetcher.mock.calls[0][0]).toBe('/api/v1/auth/session');
    expect(fetcher.mock.calls[0][1].credentials).toBe('same-origin');
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      username: 'analyst',
      password: 'test-password',
    });
  });
  it('rejects forged or unknown role responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ id: '1', username: 'analyst', role: 'root' }),
      }),
    );
    await expect(currentUser('test-token')).rejects.toThrow('Invalid account');
  });
  it('returns a neutral authentication error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 401 }),
    );
    await expect(signIn('unknown', 'incorrect')).rejects.toThrow(
      'Sign-in failed',
    );
  });
});

describe('protected API transport', () => {
  it.each([401, 403, 404])(
    'clears access on %s without reflecting server errors',
    async (status) => {
      vi.stubGlobal(
        'fetch',
        vi
          .fn()
          .mockResolvedValue(new Response('private-stack-secret', { status })),
      );
      const denied = vi.fn();
      const api = client(
        'synthetic-token',
        new AbortController().signal,
        denied,
      );
      await expect(api.overview('case')).rejects.toBeInstanceOf(ApiError);
      expect(denied).toHaveBeenCalledWith(status);
    },
  );
  it.each([409, 429, 503])(
    'preserves safe retry metadata for %s',
    async (status) => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          new Response('private-content', {
            status,
            headers: { 'Retry-After': '30' },
          }),
        ),
      );
      const api = client(
        'synthetic-token',
        new AbortController().signal,
        vi.fn(),
      );
      await expect(api.job('job')).rejects.toMatchObject({
        status,
        retryAfter: 30,
      });
    },
  );
  it('requests summaries rather than raw predictors and never supplies a score', async () => {
    const fetcher = vi.fn().mockImplementation(async () => new Response('{}'));
    vi.stubGlobal('fetch', fetcher);
    const api = client(
      'synthetic-token',
      new AbortController().signal,
      vi.fn(),
    );
    await api.overview('case');
    expect(fetcher.mock.calls[0][0]).toBe('/api/v1/cases/case/overview');
    await api.submit(
      'case',
      { expected_version: 1, run_id: 'synthetic-run', policy: 'Balanced' },
      'stable-test-key',
    );
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({
      expected_version: 1,
      run_id: 'synthetic-run',
      policy: 'Balanced',
    });
    expect(fetcher.mock.calls[1][1].headers['Idempotency-Key']).toBe(
      'stable-test-key',
    );
    expect(fetcher.mock.calls[1][1].cache).toBe('no-store');
  });
  it('bounds polling and pauses for excessive retry hints', () => {
    expect(pollDelay(0)).toBe(2000);
    expect(pollDelay(60)).toBe(60000);
    expect(pollDelay(61)).toBeNull();
  });
});
