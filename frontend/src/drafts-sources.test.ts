import { describe, expect, it } from 'vitest';
import { excerptText, fullSourceTexts } from './drafts';
import type { SimulationDraft } from './draft-api';
import type { ResearchPassage } from './investigation-api';

const section = (n: string, body: string) => `§ 1020.${n} Title ${n}.\n${body}`;
const texts = {
  r220: section(
    '220',
    'Line one about records.\nLine two.\nLine three about cash.',
  ),
  r315: section('315', 'Exempt persons.'),
  r210: section('210', 'Program.'),
};
const bytes = (s: string) => new TextEncoder().encode(s).length;
const passage = (id: string, n: string, text: string): ResearchPassage => ({
  reference_id: id,
  section: `1020.${n}`,
  text,
  source_url:
    'https://www.ecfr.gov/api/versioner/v1/full/2026-11-02/title-31.xml',
  publisher: 'eCFR',
  historical_as_of: '2026-11-02',
  raw_sha256: 'a'.repeat(64),
  text_sha256: 'b'.repeat(64),
  approval_status: 'unapproved_research',
  origin: 'official_public_research',
});
const heading = texts.r220.split('\n')[0];
const line3 = 'Line three about cash.';
const start3 = bytes(texts.r220) - bytes(line3);
const result = (
  id: string,
  rank: number,
  n: string,
  text: string,
  extra = {},
) => ({
  reference_id: id,
  rank,
  section: `1020.${n}`,
  title: `Title ${n}`,
  score: '1.000000',
  chunk_sha256: 'c'.repeat(64),
  text_bytes: bytes(text),
  sent: true,
  ...extra,
});

describe('Full source text', () => {
  it('rebuilds the exact excerpt sent from its byte ranges', () => {
    expect(
      excerptText(texts.r220, [
        { start: 0, end: bytes(heading) },
        { start: start3, end: bytes(texts.r220) },
      ]),
    ).toBe(`${heading}\n[…]\n${line3}`);
  });

  it('lists every retrieved source with its full text, cited ones first', () => {
    const draft = {
      retrieval: {
        results: [
          result('r220', 1, '220', texts.r220, {
            excerpt_bytes: bytes(heading) + 7 + bytes(line3),
            excerpt_spans: [
              { start: 0, end: bytes(heading) },
              { start: start3, end: bytes(texts.r220) },
            ],
          }),
          result('r315', 2, '315', texts.r315, { sent: false }),
          result('r210', 3, '210', texts.r210),
        ],
      },
      source_texts: [
        {
          reference_id: 'r220',
          section: '1020.220',
          chunk_sha256: 'c'.repeat(64),
          text: texts.r220,
        },
        {
          reference_id: 'r315',
          section: '1020.315',
          chunk_sha256: 'c'.repeat(64),
          text: texts.r315,
        },
        {
          reference_id: 'r210',
          section: '1020.210',
          chunk_sha256: 'c'.repeat(64),
          text: texts.r210,
        },
      ],
    } as unknown as SimulationDraft;
    const rows = fullSourceTexts(draft, [passage('r210', '210', texts.r210)]);
    expect(rows.map((r) => [r.rId, r.cited])).toEqual([
      ['R3', true],
      ['R1', false],
      ['R2', false],
    ]);
    expect(rows[1].text).toBe(texts.r220); // full section text, not only the excerpt
    expect(rows[1].sentNote).toMatch(
      /^Sent to the AI as an excerpt \(\d+ of \d+ bytes\)$/,
    );
    expect(rows[1].excerpt).toBe(`${heading}\n[…]\n${line3}`);
    expect(rows[2].sentNote).toBe('Not sent to the AI (request size limit)');
    expect(rows[0].sentNote).toBe('Sent to the AI in full');
    expect(rows[0].url).toMatch(/^https:\/\/www\.ecfr\.gov\/api\/versioner\//);
  });

  it('earlier runs without stored section texts list the cited passages, as before', () => {
    const draft = { retrieval: null } as unknown as SimulationDraft;
    const rows = fullSourceTexts(draft, [passage('x', '320', 'Text.')]);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      section: '1020.320',
      cited: true,
      text: 'Text.',
    });
  });
});
