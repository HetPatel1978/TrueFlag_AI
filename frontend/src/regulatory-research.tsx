import { useEffect, useState } from 'react';
import { message, request } from './api';
import { formatDate } from './format';

type ResearchResult = {
  version_id: string;
  title: string;
  publisher: string;
  url: string;
  origin: string;
  authority: string;
  indexed: boolean;
  eligible_for_ai_grounding: false;
  independently_approved: false;
};

export function RegulatoryResearch({
  token,
  onDenied,
  signal,
  embedded = false,
}: {
  token: string;
  onDenied: (status: number) => void;
  signal?: AbortSignal;
  embedded?: boolean;
}) {
  const [query, setQuery] = useState('');
  // One read-only listing on load tells whether any source is indexed at all.
  const [search, setSearch] = useState<{
    query: string;
    sequence: number;
  } | null>({ query: '', sequence: 0 });
  const [hasSources, setHasSources] = useState<boolean | null>(null);
  const [rows, setRows] = useState<ResearchResult[] | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  useEffect(() => {
    if (search === null) return;
    const controller = new AbortController();
    void request<{ status: string; results: ResearchResult[] }>(
      `/api/v1/internal/regulatory-research?q=${encodeURIComponent(search.query)}`,
      {
        headers: { Authorization: `Bearer ${token}` },
        signal: signal
          ? AbortSignal.any([signal, controller.signal])
          : controller.signal,
      },
      onDenied,
    )
      .then((result) => {
        if (controller.signal.aborted || signal?.aborted) return;
        if (
          result.status !== 'unapproved_research_only' ||
          !Array.isArray(result.results) ||
          result.results.length > 20 ||
          result.results.some(
            (r) =>
              r.independently_approved !== false ||
              r.eligible_for_ai_grounding !== false,
          )
        ) {
          throw new Error('invalid_research_result');
        }
        if (search.sequence === 0)
          setHasSources(result.results.some((r) => r.indexed));
        else setRows(result.results);
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted && !signal?.aborted)
          setError(message(failure));
      })
      .finally(() => {
        if (!controller.signal.aborted && !signal?.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [search, token, onDenied, signal]);
  function sourceLink(row: ResearchResult) {
    try {
      const url = new URL(row.url);
      return row.origin === 'official_curated' && url.protocol === 'https:'
        ? url.href
        : null;
    } catch {
      return null;
    }
  }
  return (
    <section
      className={embedded ? 'other-sources-body' : 'panel batch-panel'}
      aria-label="Unapproved regulatory research"
    >
      {!embedded && <h2>Regulatory research</h2>}
      {hasSources === false && !error && (
        <p className="muted">
          No research sources are indexed in this environment.
        </p>
      )}
      {hasSources && (
        <>
          <p>
            Unapproved research metadata only. These sources cannot be used as
            AI guidance.
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setBusy(true);
              setRows(null);
              setError('');
              setSearch((previous) => ({
                query: query.trim(),
                sequence: (previous?.sequence ?? 0) + 1,
              }));
            }}
          >
            <label htmlFor="research-query">Search sources</label>
            <input
              id="research-query"
              maxLength={100}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <button type="submit" disabled={busy}>
              Search research
            </button>
          </form>
        </>
      )}
      {busy && (
        <p role="status">
          {hasSources === null
            ? 'Checking research sources…'
            : 'Searching research…'}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {rows && rows.length === 0 && (
        <p>No unapproved sources are indexed in this environment.</p>
      )}
      {rows && rows.length > 0 && (
        <ul>
          {rows.map((row) => {
            const href = sourceLink(row);
            return (
              <li key={row.version_id}>
                {href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    {row.title}
                  </a>
                ) : (
                  row.title
                )}
                {' — '}
                {row.publisher} ·{' '}
                {row.origin === 'synthetic_test'
                  ? 'Synthetic test'
                  : 'Unapproved'}{' '}
                · {row.indexed ? 'Indexed' : 'Not indexed'}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

type Corpus = {
  status: 'unapproved_research_only';
  title: string;
  publisher: string;
  url: string;
  snapshot_date: string;
  sections: number;
  fingerprint_verified: boolean;
  raw_sha256: string;
  top_k: number;
};
type Ranked = { rank: number; section: string; title: string; score: string };
type TestResult = {
  terms: string[];
  total_sections: number;
  matched_sections: number;
  min_relative_score: string;
  strong_matches: number;
  results: Ranked[];
};

const SHA = /^[a-f0-9]{64}$/;
const SECTION = /^1020\.\d{3}$/;
const SCORE = /^\d{1,6}\.\d{6}$/;

function validCorpus(v: Corpus): boolean {
  return (
    v?.status === 'unapproved_research_only' &&
    Number.isSafeInteger(v.sections) &&
    /^\d{4}-\d{2}-\d{2}$/.test(v.snapshot_date) &&
    typeof v.fingerprint_verified === 'boolean' &&
    SHA.test(v.raw_sha256) &&
    Number.isSafeInteger(v.top_k)
  );
}

function validTest(v: TestResult): boolean {
  return (
    Array.isArray(v?.terms) &&
    Array.isArray(v.results) &&
    v.results.length <= 10 &&
    Number.isSafeInteger(v.matched_sections) &&
    v.min_relative_score === '0.25' &&
    v.strong_matches === v.results.length &&
    v.results.every(
      (r, n) =>
        r.rank === n + 1 &&
        SECTION.test(r.section) &&
        typeof r.title === 'string' &&
        SCORE.test(r.score),
    )
  );
}

function officialLink(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' && parsed.hostname === 'www.ecfr.gov'
      ? parsed.href
      : null;
  } catch {
    return null;
  }
}

/** The real retrieval corpus used for per-case regulatory context. Read-only; no AI call. */
export function RetrievalCorpus({
  token,
  onDenied,
  signal,
}: {
  token: string;
  onDenied: (status: number) => void;
  signal?: AbortSignal;
}) {
  const [corpus, setCorpus] = useState<Corpus | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [asked, setAsked] = useState<{ q: string; n: number } | null>(null);
  const [found, setFound] = useState<TestResult | null>(null);
  const [testError, setTestError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    request<Corpus>(
      '/api/v1/internal/regulatory-research/corpus',
      {
        headers: { Authorization: `Bearer ${token}` },
        signal: signal
          ? AbortSignal.any([signal, controller.signal])
          : controller.signal,
      },
      onDenied,
    )
      .then((value) => {
        if (controller.signal.aborted) return;
        if (!validCorpus(value)) throw new Error('invalid_corpus_view');
        setCorpus(value);
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(message(failure));
      });
    return () => controller.abort();
  }, [token, onDenied, signal]);
  useEffect(() => {
    if (!asked) return;
    const controller = new AbortController();
    request<TestResult>(
      `/api/v1/internal/regulatory-research/corpus/search?q=${encodeURIComponent(asked.q)}`,
      {
        headers: { Authorization: `Bearer ${token}` },
        signal: signal
          ? AbortSignal.any([signal, controller.signal])
          : controller.signal,
      },
      onDenied,
    )
      .then((value) => {
        if (controller.signal.aborted) return;
        if (!validTest(value)) throw new Error('invalid_retrieval_result');
        setTestError('');
        setFound(value);
      })
      .catch((failure) => {
        if (!controller.signal.aborted) {
          setFound(null);
          setTestError(message(failure));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [asked, token, onDenied, signal]);
  const href = corpus ? officialLink(corpus.url) : null;
  return (
    <section className="panel corpus-panel" aria-labelledby="corpus-title">
      <div className="card-head">
        <h2 id="corpus-title">Regulatory retrieval corpus</h2>
        <span className="tag">
          Unapproved research · Not production regulatory guidance
        </span>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!corpus && !error && <p role="status">Checking the corpus…</p>}
      {corpus && (
        <p className="corpus-line">
          {href ? (
            <a href={href} target="_blank" rel="noopener noreferrer">
              eCFR 31 CFR Part 1020
            </a>
          ) : (
            'eCFR 31 CFR Part 1020'
          )}{' '}
          · {corpus.sections} sections · snapshot{' '}
          {formatDate(corpus.snapshot_date)} ·{' '}
          <span
            className="has-tip"
            title={`Raw and extracted text hashes match the recorded snapshot (SHA-256 ${corpus.raw_sha256.slice(0, 12)}…)`}
          >
            fingerprint {corpus.fingerprint_verified ? '✓' : '✗'}
          </span>{' '}
          · retrieval: text-match (PostgreSQL ts_rank_cd), top {corpus.top_k}{' '}
          per case, results below 25% of the top score dropped
        </p>
      )}
      {corpus && (
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            const q = query.trim();
            if (!q) return;
            setBusy(true);
            setAsked((previous) => ({ q, n: (previous?.n ?? 0) + 1 }));
          }}
        >
          <label htmlFor="retrieval-query">Test retrieval</label>
          <input
            id="retrieval-query"
            maxLength={200}
            placeholder="e.g. cash currency transaction"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="submit" disabled={busy || !query.trim()}>
            Test retrieval
          </button>
        </form>
      )}
      {busy && <p role="status">Ranking sections…</p>}
      {testError && (
        <p role="alert" className="error">
          {testError}
        </p>
      )}
      {found && !busy && (
        <>
          <p className="muted" role="status">
            {found.terms.length === 0
              ? 'No searchable words in the query (words of 3 or more letters).'
              : `${found.strong_matches} strong match${found.strong_matches === 1 ? '' : 'es'} · ${found.matched_sections} of ${found.total_sections} sections matched any term · terms: ${found.terms.join(' | ')}`}
          </p>
          {found.results.length > 0 && (
            <table className="compact-table retrieval-table">
              <caption className="sr-only">Ranked sections</caption>
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Section</th>
                  <th>Title</th>
                  <th className="num">Score</th>
                </tr>
              </thead>
              <tbody>
                {found.results.map((row) => (
                  <tr key={row.section}>
                    <td>{row.rank}</td>
                    <td>§ {row.section}</td>
                    <td className="source-title" title={row.title}>
                      {row.title}
                    </td>
                    <td className="num" title={`ts_rank_cd ${row.score}`}>
                      {Number(row.score).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}

/** Retrieval corpus first; the separate unapproved metadata index stays collapsed. */
export function ResearchSources(props: {
  token: string;
  onDenied: (status: number) => void;
  signal?: AbortSignal;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <RetrievalCorpus {...props} />
      <details
        className="disclosure other-sources"
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary>Other research sources</summary>
        {open && <RegulatoryResearch {...props} embedded />}
      </details>
    </>
  );
}
