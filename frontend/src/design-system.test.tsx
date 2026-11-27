// @vitest-environment jsdom
// Presentation contract fixtures only; Chromium separately verifies real persisted results.
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import App from './App';
import {
  TERMS,
  FEATURE_LABELS,
  decimalMoney,
  displayLabel,
} from './terminology';
import { PageHeader, StatusBadge } from './ui';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = '';
});
describe('business presentation contracts', () => {
  it('uses analyst language without claiming an actual laundering probability', () => {
    expect(TERMS.assessment).toBe('Alert Risk Assessment');
    expect(TERMS.drivers).toBe('Key Risk Drivers');
    expect(TERMS.summary).toBe('Investigation Summary');
    expect(TERMS.recommendation).toBe('Review Recommendation');
    expect(Object.keys(FEATURE_LABELS)).toHaveLength(27);
    expect(new Set(Object.values(FEATURE_LABELS)).size).toBe(27);
    expect(FEATURE_LABELS.nbrCollections3y).toBe(
      'Collections · source period unconfirmed',
    );
  });
  it.each([
    ['9007199254740993.00000001', 'USD', 'USD 9,007,199,254,740,993.00000001'],
    ['-1234.56000000', 'CAD', 'CAD -1,234.56000000'],
    ['0.00000000', 'EUR', 'EUR 0.00000000'],
    [null, 'GBP', 'Not available'],
  ])(
    'preserves exact decimal scale and missing/zero distinction: %s',
    (value, currency, expected) => {
      expect(decimalMoney(value, currency!)).toBe(expected);
    },
  );
  it('changes processing presentation without changing the stored state', () => {
    const { container } = render(<StatusBadge value="succeeded" />);
    expect(screen.getByText('Completed')).toBeTruthy();
    expect(container.querySelector('.succeeded')).toBeTruthy();
    expect(displayLabel('abstained')).toBe('Further evidence needed');
    expect(displayLabel('review_reduction_candidate')).toBe(
      'Review prioritization suggested',
    );
  });
  it('provides a semantic header and functional contextual action', () => {
    const action = vi.fn();
    render(
      <PageHeader
        title="Supporting Evidence"
        eyebrow="CASE REVIEW"
        description="Available source records"
        actions={<button onClick={action}>Refresh evidence</button>}
      />,
    );
    expect(
      screen.getByRole('heading', { level: 1, name: 'Supporting Evidence' }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh evidence' }));
    expect(action).toHaveBeenCalledOnce();
  });
});

it.each(['analyst', 'supervisor', 'admin'])(
  'exposes working scoped navigation for %s without placeholder destinations',
  async (role) => {
    const id = '11111111-1111-4111-8111-111111111111';
    const user = { id: 'actor', role, username: 'synthetic-analyst' };
    const record = {
      id,
      source_id: 'synthetic-contract-case',
      alert_id: 'alert',
      assigned_to: 'actor',
      priority: 'High',
      status: 'open',
      disposition: null,
      version: 2,
      created_at: '2026-01-01T00:00:00Z',
      assessment_status: 'not_requested',
      latest_job_id: null,
    };
    window.location.hash = `/cases/${id}`;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string, init?: RequestInit) => {
        if (path.endsWith('/auth/session') && init?.method !== 'POST')
          return new Response('{}', { status: 401 });
        return new Response(
          JSON.stringify(
            path.endsWith('/auth/session')
              ? { access_token: 'synthetic-unit-token' }
              : path.endsWith('/auth/me')
                ? user
                : path.endsWith('/overview') || path.endsWith('/workflow')
                  ? record
                  : path.endsWith('/internal/release')
                    ? { release: { build_id: 'unknown' }, status: 'ready' }
                    : { items: [], total: 0, limit: 10, offset: 0 },
          ),
        );
      }),
    );
    render(<App />);
    fireEvent.change(await screen.findByLabelText('Username'), {
      target: { value: 'synthetic-analyst' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'synthetic-unit-password' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    const navigation = within(
      await screen.findByRole('navigation', { name: 'Workspace navigation' }),
    );
    await screen.findByRole('navigation', { name: 'Case workflow' });
    expect(
      navigation.getByRole('link', { name: 'Cases' }).getAttribute('href'),
    ).toBe('#/');
    expect(
      within(screen.getByRole('navigation', { name: 'Case workflow' }))
        .getByRole('link', { name: /AI Investigation/ })
        .getAttribute('href'),
    ).toBe(`#/cases/${id}/investigation`);
    expect(
      within(screen.getByRole('navigation', { name: 'Case workflow' }))
        .getByRole('link', { name: /Assess Alert/ })
        .getAttribute('aria-current'),
    ).toBe('step');
    expect(navigation.queryByRole('link', { name: 'Imports' }) !== null).toBe(
      false,
    );
    expect(
      navigation.queryByRole('link', { name: 'Administration' }) !== null,
    ).toBe(role === 'admin');
    expect(
      navigation.queryByRole('link', { name: 'Review Queue' }) !== null,
    ).toBe(role !== 'analyst');
    expect(
      navigation.queryByRole('link', { name: 'Investigation' }),
    ).toBeNull();
    expect(
      within(screen.getByRole('navigation', { name: 'Case workflow' }))
        .getAllByRole('link')
        .map((a) => a.querySelector('strong')?.textContent),
    ).toEqual([
      'Assess Alert',
      'Review Evidence',
      'AI Investigation',
      'Human Decision',
    ]);
    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(
      screen.queryByRole('navigation', { name: 'Workspace navigation' }),
    ).toBeNull();
    await screen.findByRole('heading', { name: 'Welcome back' });
  },
);
