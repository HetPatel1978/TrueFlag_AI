// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { RegulatoryResearch, ResearchSources } from './regulatory-research';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('searches protected research metadata and labels unapproved sources', async () => {
  const fetcher = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      status: 'unapproved_research_only',
      results: [
        {
          version_id: 'synthetic-version',
          title: 'Synthetic research',
          publisher: 'Fixture',
          url: 'https://example.test/source',
          origin: 'synthetic_test',
          authority: 'guidance',
          indexed: true,
          independently_approved: false,
          eligible_for_ai_grounding: false,
        },
      ],
    }),
  });
  vi.stubGlobal('fetch', fetcher);
  render(<RegulatoryResearch token="synthetic-session" onDenied={vi.fn()} />);
  // A read-only listing on load reveals the search box only when sources are indexed.
  fireEvent.change(await screen.findByLabelText('Search sources'), {
    target: { value: 'synthetic' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Search research' }));
  await screen.findByText(/Synthetic test · Indexed/);
  expect(fetcher.mock.calls[0][0]).toBe(
    '/api/v1/internal/regulatory-research?q=',
  );
  expect(fetcher.mock.calls[1][0]).toBe(
    '/api/v1/internal/regulatory-research?q=synthetic',
  );
  expect(fetcher.mock.calls[1][1].headers.Authorization).toBe(
    'Bearer synthetic-session',
  );
  expect(screen.queryByRole('link', { name: 'Synthetic research' })).toBeNull();
});

it('does not display entries falsely claiming AI approval', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        status: 'unapproved_research_only',
        results: [
          { independently_approved: true, eligible_for_ai_grounding: true },
        ],
      }),
    }),
  );
  render(<RegulatoryResearch token="synthetic-session" onDenied={vi.fn()} />);
  await screen.findByRole('alert');
  expect(screen.queryByText('Synthetic research')).toBeNull();
});

it('shows one line and no search box when nothing is indexed', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: 'unapproved_research_only', results: [] }),
    }),
  );
  render(<RegulatoryResearch token="synthetic-session" onDenied={vi.fn()} />);
  await screen.findByText(
    'No research sources are indexed in this environment.',
  );
  expect(screen.queryByLabelText('Search sources')).toBeNull();
});

const corpus = {
  status: 'unapproved_research_only',
  title: '31 CFR Part 1020',
  publisher: 'eCFR',
  url: 'https://www.ecfr.gov/api/versioner/v1/full/2026-11-02/title-31.xml',
  snapshot_date: '2026-11-02',
  sections: 24,
  fingerprint_verified: true,
  raw_sha256: 'a'.repeat(64),
  top_k: 3,
};

it('shows the real retrieval corpus first and ranks a test query read-only', async () => {
  const fetcher = vi.fn(async (url: string) => ({
    ok: true,
    status: 200,
    json: async () =>
      url.endsWith('/corpus')
        ? corpus
        : {
            terms: ['cash', 'currency'],
            total_sections: 24,
            matched_sections: 5,
            min_relative_score: '0.25',
            strong_matches: 2,
            results: [
              {
                rank: 1,
                section: '1020.315',
                title: 'Transactions of exempt persons',
                score: '0.300000',
              },
              {
                rank: 2,
                section: '1020.310',
                title: 'Reports of transactions in currency',
                score: '0.200000',
              },
            ],
          },
  }));
  vi.stubGlobal('fetch', fetcher);
  render(<ResearchSources token="synthetic-session" onDenied={vi.fn()} />);
  await screen.findByText(/24 sections · snapshot/);
  expect(screen.getByText(/fingerprint ✓/)).toBeTruthy();
  expect(
    screen.getByText(/text-match \(PostgreSQL ts_rank_cd\), top 3/),
  ).toBeTruthy();
  expect(
    screen.getByText(
      'Unapproved research · Not production regulatory guidance',
    ),
  ).toBeTruthy();
  // The separate metadata index is collapsed and not loaded until opened.
  expect(screen.getByText('Other research sources')).toBeTruthy();
  expect(
    screen.queryByText('No research sources are indexed in this environment.'),
  ).toBeNull();
  fireEvent.change(screen.getByLabelText('Test retrieval'), {
    target: { value: 'cash currency' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Test retrieval' }));
  await screen.findByText('§ 1020.315');
  expect(screen.getByText('0.30')).toBeTruthy();
  expect(
    screen.getByText(/2 strong matches · 5 of 24 sections matched/),
  ).toBeTruthy();
  expect(screen.getByText(/below 25% of the top score dropped/)).toBeTruthy();
  const urls = fetcher.mock.calls.map(([url]) => url);
  expect(urls).toEqual([
    '/api/v1/internal/regulatory-research/corpus',
    '/api/v1/internal/regulatory-research/corpus/search?q=cash%20currency',
  ]);
});

it('rejects a malformed ranking without rendering it', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => ({
      ok: true,
      status: 200,
      json: async () =>
        url.endsWith('/corpus')
          ? corpus
          : {
              terms: ['cash'],
              total_sections: 24,
              matched_sections: 1,
              results: [
                { rank: 1, section: 'private-marker', title: 'x', score: '1' },
              ],
            },
    })),
  );
  render(<ResearchSources token="synthetic-session" onDenied={vi.fn()} />);
  fireEvent.change(await screen.findByLabelText('Test retrieval'), {
    target: { value: 'cash' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Test retrieval' }));
  await screen.findByRole('alert');
  expect(screen.queryByText(/private-marker/)).toBeNull();
});
