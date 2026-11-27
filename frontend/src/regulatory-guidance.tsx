import { useEffect, useRef, useState, type FormEvent } from 'react';
import { message } from './api';
import type {
  InvestigationFactory,
  RegulatoryPassage,
  RegulatoryResult,
} from './investigation-api';

export function RegulatoryGuidance(props: {
  id: string;
  api: InvestigationFactory;
  run?: string;
  citations?: RegulatoryPassage[];
}) {
  return (
    <RegulatoryGuidanceContent
      key={`${props.id}:${props.run ?? ''}`}
      {...props}
    />
  );
}

function RegulatoryGuidanceContent({
  id,
  api,
  run,
  citations,
}: {
  id: string;
  api: InvestigationFactory;
  run?: string;
  citations?: RegulatoryPassage[];
}) {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<RegulatoryResult | null>(null);
  const [selected, setSelected] = useState<RegulatoryPassage | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  async function search(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || busy) return;
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setResult(null);
    setSelected(null);
    setError('');
    try {
      const service = api(controller.signal);
      if (!service.referenceSearch)
        throw new Error('Regulatory guidance unavailable.');
      const value =
        run && service.referenceInvestigation
          ? await service.referenceInvestigation(id, run, query.trim())
          : await service.referenceSearch(id, query.trim());
      if (!controller.signal.aborted) setResult(value);
    } catch (e) {
      if (!controller.signal.aborted) setError(message(e));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  async function open(reference: string) {
    if (busy) return;
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setSelected(null);
    setError('');
    try {
      const service = api(controller.signal);
      if (!service.referenceResolve)
        throw new Error('Regulatory guidance unavailable.');
      const value = await service.referenceResolve(id, reference);
      const item = value.passages.find(
        (p) => p.reference_id === reference && p.origin === 'official_curated',
      );
      if (!item || value.status !== 'available')
        throw new Error('This reference is no longer available.');
      if (!controller.signal.aborted) setSelected(item);
    } catch (e) {
      if (!controller.signal.aborted) {
        setResult(null);
        setError(message(e));
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  const passages =
    result?.status === 'available'
      ? result.passages.filter((p) => p.origin === 'official_curated')
      : (citations?.filter((p) => p.origin === 'official_curated') ?? []);
  let source: string | null = null;
  try {
    if (selected && new URL(selected.source_url).protocol === 'https:')
      source = selected.source_url;
  } catch {
    source = null;
  }
  return (
    <details className="panel disclosure">
      <summary>Regulatory Guidance</summary>
      <p>
        Search approved historical U.S. banking sources. Guidance is context for
        human review and is not included in simulated findings.
      </p>
      <form onSubmit={(e) => void search(e)}>
        <label htmlFor="regulatory-search">Search guidance</label>
        <input
          id="regulatory-search"
          value={query}
          maxLength={256}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button disabled={busy || !query.trim()}>
          {busy ? 'Checking…' : 'Search approved guidance'}
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {result && !passages.length && (
        <p role="status">
          Approved guidance is unavailable for this search and scope.
        </p>
      )}
      {passages.map((p) => (
        <p key={p.reference_id}>
          <button disabled={busy} onClick={() => void open(p.reference_id)}>
            {p.title} · {p.section}
          </button>
        </p>
      ))}
      {selected && (
        <section aria-label="Verified regulatory passage">
          <h4>
            {selected.title} · {selected.section}
          </h4>
          <p>{selected.text}</p>
          <p>
            {selected.authority.replaceAll('_', ' ')} · Historical as of{' '}
            {selected.as_of} · Human review required
          </p>
          {source && (
            <a href={source} target="_blank" rel="noopener noreferrer">
              Open official source
            </a>
          )}
          <details>
            <summary>Source version and limitations</summary>
            <p>{selected.version_id}</p>
            <p>{selected.limitations.join(', ')}</p>
          </details>
        </section>
      )}
    </details>
  );
}
