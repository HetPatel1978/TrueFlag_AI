// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ReleaseIdentity } from './release';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('release visibility', () => {
  it('uses the protected endpoint and renders only bounded build identifiers', async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        status: 'ready',
        release: { build_id: 'a'.repeat(64) },
        secret: 'private-marker',
      }),
    });
    vi.stubGlobal('fetch', fetcher);
    render(<ReleaseIdentity token="synthetic-token" onDenied={vi.fn()} />);
    await screen.findByText(/API aaaaaaaaaaaa \(ready\)/);
    expect(fetcher.mock.calls[0][0]).toBe('/api/v1/internal/release');
    expect(fetcher.mock.calls[0][1].headers.Authorization).toBe(
      'Bearer synthetic-token',
    );
    expect(screen.queryByText(/private-marker/)).toBeNull();
  });

  it('rejects malformed responses without rendering arbitrary values', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          status: 'ready',
          release: { build_id: 'private-marker' },
        }),
      }),
    );
    render(<ReleaseIdentity token="synthetic-token" onDenied={vi.fn()} />);
    await screen.findByText(/API unavailable/);
    expect(screen.queryByText(/private-marker/)).toBeNull();
  });

  it.each([401, 403])('rechecks authorization on HTTP %s', async (status) => {
    const denied = vi.fn();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status }));
    render(<ReleaseIdentity token="synthetic-token" onDenied={denied} />);
    await waitFor(() => expect(denied).toHaveBeenCalledWith(status));
  });

  it('treats an older backend without release metadata as unavailable', async () => {
    const denied = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 404 }),
    );
    render(<ReleaseIdentity token="synthetic-token" onDenied={denied} />);
    await screen.findByText(/API unavailable/);
    expect(denied).not.toHaveBeenCalled();
  });

  it('aborts its request when the workspace unmounts', () => {
    const fetcher = vi.fn().mockImplementation(() => new Promise(() => {}));
    vi.stubGlobal('fetch', fetcher);
    const view = render(
      <ReleaseIdentity token="synthetic-token" onDenied={vi.fn()} />,
    );
    view.unmount();
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
  });
});
