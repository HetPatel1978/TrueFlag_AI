import { afterEach, describe, expect, it, vi } from 'vitest';
import { currentUser, health, signIn } from './api';

afterEach(() => vi.unstubAllGlobals());

describe('API boundary', () => {
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
    expect(fetcher.mock.calls[0][0]).toBe('/api/v1/auth/token');
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
