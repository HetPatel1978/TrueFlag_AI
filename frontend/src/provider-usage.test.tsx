// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProviderUsage } from './provider-usage';

const fixture = () => ({
  schema_version: 'trueflag.provider-usage.v2',
  state: 'blocked',
  dispatch_allowed: false,
  floor_guaranteed: false,
  minimum_balance_usd: '200.0',
  safety_buffer_usd: '1.0',
  indicative_spending_ceiling_usd: '797.0',
  reported_balance_usd: null,
  balance_observed_at: null,
  projected_headroom_usd: null,
  retained_reservations_usd: '0',
  estimated_usage_cost_usd: '0',
  inference_attempts: 0,
  unreconciled_attempts: 0,
  refresh_enabled: false,
  blocked_reasons: [
    'current_balance_unverified',
    'outside_account_usage_unbounded',
  ],
});
const response = (value = fixture()) => ({
  ok: true,
  status: 200,
  json: async () => value,
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
describe('administrator provider usage', () => {
  it('collapses Luminal to one line with this-month and all-time labels inside', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        response({
          ...fixture(),
          inference_attempts: 4,
          inference_attempts_this_month: 1,
          estimated_usage_cost_this_month_usd: '0.05',
          estimated_usage_cost_usd: '0.20',
        } as unknown as ReturnType<typeof fixture>),
      ),
    );
    const view = render(
      <ProviderUsage token="synthetic-session" onDenied={vi.fn()} />,
    );
    await screen.findByText('1 this month · 4 all time');
    const card = view.container.querySelector('details.provider-collapsed');
    expect(card?.hasAttribute('open')).toBe(false);
    expect(card?.querySelector('summary')?.textContent).toBe(
      'Luminal · Blocked · Not used for AI investigations',
    );
    expect(
      screen.getByText(
        /\$0\.05 this month · \$0\.20 of \$797\.0 cap \(all time\)/,
      ),
    ).toBeTruthy();
  });
  it('shows the new bounded probe policy without a withdrawn balance floor', async () => {
    const updated = {
      ...fixture(),
      financial_policy: 'bounded_probe_v3',
      minimum_balance_usd: null,
      safety_buffer_usd: null,
      indicative_spending_ceiling_usd: '1.00',
      blocked_reasons: ['probe_bootstrap_unverified'],
    };
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          response(updated as unknown as ReturnType<typeof fixture>),
        ),
    );
    render(<ProviderUsage token="synthetic-session" onDenied={vi.fn()} />);
    await screen.findByText(/paid requests blocked until/);
    expect(screen.queryByText('Minimum preserved balance')).toBeNull();
    expect(screen.getByText('$1.00')).toBeTruthy();
    expect(
      screen.getByText(/exact-payload compatibility probe is not ready/),
    ).toBeTruthy();
  });
  it('uses protected backend data and shows blocked unknown balance without a fake 997 balance', async () => {
    const fetcher = vi.fn().mockResolvedValue(response());
    vi.stubGlobal('fetch', fetcher);
    render(<ProviderUsage token="synthetic-session" onDenied={vi.fn()} />);
    await screen.findByText(/paid requests blocked until/);
    expect(screen.getByText('$200.0')).toBeTruthy();
    expect(screen.queryByText('$997')).toBeNull();
    expect(
      (
        screen.getByRole('button', {
          name: 'Refresh provider balance',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(fetcher.mock.calls[0][0]).toBe('/api/v1/internal/provider-usage');
    expect(fetcher.mock.calls[0][1].headers.Authorization).toBe(
      'Bearer synthetic-session',
    );
    expect(screen.queryByRole('button', { name: /Generate/ })).toBeNull();
  });
  it('refresh is an explicit POST, not automatic polling', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(response({ ...fixture(), refresh_enabled: true }));
    vi.stubGlobal('fetch', fetcher);
    render(<ProviderUsage token="synthetic-session" onDenied={vi.fn()} />);
    await screen.findByText(/paid requests blocked until/);
    // Only provider calls count; the research panel lists its sources separately.
    const provider = () =>
      fetcher.mock.calls.filter(([url]) =>
        String(url).startsWith('/api/v1/internal/provider-usage'),
      );
    expect(provider()).toHaveLength(1);
    fireEvent.click(
      screen.getByRole('button', { name: 'Refresh provider balance' }),
    );
    await waitFor(() => expect(provider()).toHaveLength(2));
    expect(provider()[1][0]).toBe(
      '/api/v1/internal/provider-usage/balance-refresh',
    );
    expect(provider()[1][1].method).toBe('POST');
  });
  it.each([401, 403])(
    'clears financial state and propagates HTTP %s revocation',
    async (status) => {
      const denied = vi.fn();
      // The single page-level refresh lives in the top bar; a denied load must clear state.
      const fetcher = vi
        .fn()
        .mockResolvedValueOnce({ ok: false, status, headers: new Headers() });
      vi.stubGlobal('fetch', fetcher);
      render(<ProviderUsage token="synthetic-session" onDenied={denied} />);
      await waitFor(() => expect(denied).toHaveBeenCalledWith(status));
      expect(screen.queryByText('$200.0')).toBeNull();
    },
  );
  it('rejects malformed data and never renders arbitrary API fields', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          response({ ...fixture(), minimum_balance_usd: 'private-marker' }),
        ),
    );
    render(<ProviderUsage token="synthetic-session" onDenied={vi.fn()} />);
    await screen.findByRole('alert');
    expect(screen.queryByText(/private-marker/)).toBeNull();
  });
  it('aborts on logout/unmount', () => {
    const fetcher = vi.fn().mockImplementation(() => new Promise(() => {}));
    vi.stubGlobal('fetch', fetcher);
    const view = render(
      <ProviderUsage token="synthetic-session" onDenied={vi.fn()} />,
    );
    view.unmount();
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
  });
  it('shows an unsuccessful refresh without reflecting provider diagnostics', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        response({
          ...fixture(),
          last_refresh_status: 'private-vendor-diagnostic',
        } as ReturnType<typeof fixture>),
      ),
    );
    render(<ProviderUsage token="synthetic-session" onDenied={vi.fn()} />);
    await screen.findByText(/latest provider balance could not be verified/);
    expect(screen.queryByText(/private-vendor-diagnostic/)).toBeNull();
  });
});
