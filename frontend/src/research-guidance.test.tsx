// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { ApiError } from './api';
import type { InvestigationFactory } from './investigation-api';
import { ResearchGuidance } from './research-guidance';

afterEach(cleanup);
const notice =
  'AI-assisted academic research demonstration. Regulatory sources have not completed independent compliance approval.';
const result = {
  status: 'research_unapproved',
  publication_approved: false,
  notice,
  passages: [
    {
      reference_id: 'research-ref',
      section: '1020.320',
      text: '<img src=x onerror=alert(1)>Historical public source text.',
      publisher: 'OFR/GPO',
      source_url:
        'https://www.ecfr.gov/api/versioner/v1/full/2026-11-02/title-31.xml',
      historical_as_of: '2026-11-02',
      raw_sha256: 'a'.repeat(64),
      text_sha256: 'b'.repeat(64),
    },
  ],
};
function client(read: ReturnType<typeof vi.fn>) {
  return (() => ({ researchContext: read })) as unknown as InvestigationFactory;
}

it('labels actual research separately and renders source text as escaped text', async () => {
  render(
    <ResearchGuidance
      id="a"
      api={client(vi.fn().mockResolvedValue(result))}
      invalidate={vi.fn()}
    />,
  );
  await screen.findByText(notice);
  expect(
    screen.getByText(/Historical public source text/).querySelector('img'),
  ).toBeNull();
  expect(
    screen.getByRole('region', { name: 'Regulatory Research / Unapproved' }),
  ).toBeTruthy();
  expect(screen.queryByText('Approved Regulatory Guidance')).toBeNull();
});

it('hides research when the backend has no permitted context', async () => {
  const read = vi.fn().mockRejectedValue(new ApiError(404));
  render(<ResearchGuidance id="a" api={client(read)} invalidate={vi.fn()} />);
  await waitFor(() => expect(read).toHaveBeenCalled());
  expect(screen.queryByRole('region')).toBeNull();
});

it('clears the previous case immediately and aborts stale results', async () => {
  const read = vi
    .fn()
    .mockResolvedValueOnce(result)
    .mockImplementationOnce(() => new Promise(() => {}));
  const api = client(read);
  const invalidate = vi.fn();
  const view = render(
    <ResearchGuidance id="a" api={api} invalidate={invalidate} />,
  );
  await screen.findByText(notice);
  view.rerender(<ResearchGuidance id="b" api={api} invalidate={invalidate} />);
  expect(screen.queryByText(notice)).toBeNull();
});

it('clears protected passages when permission is revoked', async () => {
  const invalidate = vi.fn();
  const view = render(
    <ResearchGuidance
      id="a"
      api={client(vi.fn().mockResolvedValue(result))}
      invalidate={invalidate}
    />,
  );
  await screen.findByText(notice);
  view.rerender(
    <ResearchGuidance
      id="a"
      api={client(vi.fn().mockRejectedValue(new ApiError(403)))}
      invalidate={invalidate}
    />,
  );
  await waitFor(() => expect(invalidate).toHaveBeenCalled());
  expect(screen.queryByText(notice)).toBeNull();
});

it('never reclassifies approved or malformed context as research', async () => {
  const read = vi
    .fn()
    .mockResolvedValue({ ...result, publication_approved: true });
  render(<ResearchGuidance id="a" api={client(read)} invalidate={vi.fn()} />);
  await waitFor(() => expect(read).toHaveBeenCalled());
  expect(screen.queryByText(notice)).toBeNull();
});

it('a case without research context does not revoke access to the whole case page', async () => {
  const { investigationClient } = await import('./investigation-api');
  for (const [status, revokes] of [
    [404, false],
    [403, true],
    [401, true],
  ] as const) {
    const onDenied = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response('{"detail":"Evidence resource not found"}', { status }),
        ),
    );
    const read = investigationClient(
      'token',
      new AbortController().signal,
      onDenied,
    ).researchContext;
    await expect(read('case-without-research')).rejects.toBeInstanceOf(
      ApiError,
    );
    expect(onDenied).toHaveBeenCalledTimes(revokes ? 1 : 0);
    // Every other case read keeps the existing page-wide 404 handling.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{}', { status: 404 })),
    );
    await expect(
      investigationClient(
        'token',
        new AbortController().signal,
        onDenied,
      ).draftDetail('c', 'r'),
    ).rejects.toBeInstanceOf(ApiError);
    expect(onDenied).toHaveBeenLastCalledWith(404);
  }
  vi.unstubAllGlobals();
});
