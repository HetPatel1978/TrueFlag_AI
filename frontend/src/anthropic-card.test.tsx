// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { AnthropicCard } from './anthropic-card';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const usage = {
  provider: 'anthropic',
  status: 'available',
  model: 'claude-sonnet-5-5',
  runs_investigations: true,
  requests_this_month: 3,
  requests_total: 9,
  spent_this_month_usd: '1.20',
  spent_total_usd: '4.10',
  cumulative_cap_usd: '10.00',
  reservation_usd: '2.14',
  approval_rule:
    'Each request is approved individually by a named spending approver; one request per approval, no automatic retries.',
};

it('shows status, model, monthly requests, spend vs the cumulative cap and the approval rule', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue({ ok: true, status: 200, json: async () => usage });
  vi.stubGlobal('fetch', fetcher);
  render(<AnthropicCard token="synthetic-session" onDenied={vi.fn()} />);
  await screen.findByText('claude-sonnet-5-5');
  expect(fetcher.mock.calls[0][0]).toBe(
    '/api/v1/internal/provider-usage/anthropic',
  );
  expect(screen.getByText('Available')).toBeTruthy();
  expect(screen.getByText('Runs AI investigations')).toBeTruthy();
  // Same period labels as the Luminal card: this month, then all time.
  expect(screen.getByText('3 this month · 9 all time')).toBeTruthy();
  expect(
    screen.getByText(
      /\$1\.20 this month · \$4\.10 of \$10\.00 cap \(all time\)/,
    ),
  ).toBeTruthy();
  expect(
    screen.getByText(/one named approver per request · No automatic retries/),
  ).toBeTruthy();
});

it('rejects a malformed view', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ...usage, spent_total_usd: 'private-marker' }),
    }),
  );
  render(<AnthropicCard token="synthetic-session" onDenied={vi.fn()} />);
  await screen.findByRole('alert');
  expect(screen.queryByText(/private-marker/)).toBeNull();
});
