import { useContext, useEffect, useRef, useState, type FormEvent } from 'react';
import {
  ApiError,
  label,
  message,
  pollDelay,
  type Assessment,
  type AssessmentDetail,
  type Case,
  type Job,
  type Page,
  type Policy,
  type User,
} from './api';
import type { ApiFactory } from './App';
import { Receipts, type Receipt } from './receipts';

export function Badge({ value }: { value: string }) {
  return <span className={`badge ${value.toLowerCase()}`}>{label(value)}</span>;
}
const date = (value: string) =>
  new Date(value).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
function ErrorState({ error, retry }: { error: string; retry: () => void }) {
  return (
    <div className="state" role="alert">
      <h2>Unable to load</h2>
      <p>{error}</p>
      <button onClick={retry}>Retry</button>
    </div>
  );
}
function Pager({
  page,
  change,
}: {
  page: Page<unknown>;
  change: (offset: number) => void;
}) {
  return (
    <div className="pager">
      <span>
        {page.total
          ? `${page.offset + 1}–${Math.min(page.offset + page.limit, page.total)} of ${page.total}`
          : '0 results'}
      </span>
      <div>
        <button
          aria-label="Previous page"
          disabled={!page.offset}
          onClick={() => change(Math.max(0, page.offset - page.limit))}
        >
          ← Previous
        </button>
        <button
          aria-label="Next page"
          disabled={
            page.offset + page.limit >= page.total ||
            page.offset + page.limit > 10000
          }
          onClick={() => change(page.offset + page.limit)}
        >
          Next →
        </button>
      </div>
    </div>
  );
}

export function Dashboard({ api, user }: { api: ApiFactory; user: User }) {
  const [page, setPage] = useState<Page<Case> | null>(null);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState('');
  const [filters, setFilters] = useState({
    search: '',
    status: '',
    priority: '',
    assessment_status: '',
    assignment: 'all',
    sort_by: 'created_at',
    sort_order: 'desc',
    offset: 0,
  });
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setPage(null);
      setError('');
      const params = new URLSearchParams({ limit: '20' });
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== '') params.set(key, String(value));
      });
      try {
        const result = await api(controller.signal).cases(params);
        if (!controller.signal.aborted) setPage(result);
      } catch (e) {
        if (!controller.signal.aborted) setError(message(e));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    // Clear old authorized rows before each refresh, including after assignment changes.
    const timer = window.setInterval(() => {
      void load();
    }, 10000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [api, filters, revision]);
  function filter(key: keyof typeof filters, value: string) {
    setFilters((f) => ({ ...f, [key]: value, offset: 0 }));
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ALERT INTELLIGENCE</p>
          <h1>Alert dashboard</h1>
          <p className="muted">
            {user.role === 'analyst'
              ? 'Your assigned cases, ready for review.'
              : 'Authorized cases across the current workspace.'}
          </p>
        </div>
        <button className="quiet" onClick={() => setRevision((n) => n + 1)}>
          ↻ Refresh
        </button>
      </div>
      <section className="panel">
        <form
          className="filters"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            filter('search', draft);
          }}
        >
          <div className="search">
            <label htmlFor="search">Search cases</label>
            <div>
              <input
                id="search"
                placeholder="Alert reference or case ID"
                maxLength={128}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
              <button className="quiet" type="submit">
                Search
              </button>
            </div>
          </div>
          {(
            [
              [
                'status',
                'Case state',
                [
                  ['', 'All states'],
                  ['open', 'Open'],
                  ['in_review', 'In review'],
                  ['awaiting_approval', 'Awaiting approval'],
                  ['closed', 'Closed'],
                ],
              ],
              [
                'priority',
                'Priority',
                [
                  ['', 'All priorities'],
                  ['High', 'High'],
                  ['Standard', 'Standard'],
                ],
              ],
              [
                'assessment_status',
                'Assessment',
                [
                  ['', 'All assessments'],
                  ['not_requested', 'Not requested'],
                  ['pending', 'Pending'],
                  ['running', 'Running'],
                  ['succeeded', 'Succeeded'],
                  ['failed', 'Failed'],
                ],
              ],
            ] as const
          ).map(([key, title, options]) => (
            <div key={key}>
              <label htmlFor={key}>{title}</label>
              <select
                id={key}
                value={filters[key]}
                onChange={(e) => filter(key, e.target.value)}
              >
                {options.map(([value, text]) => (
                  <option key={value} value={value}>
                    {text}
                  </option>
                ))}
              </select>
            </div>
          ))}
          {user.role !== 'analyst' && (
            <div>
              <label htmlFor="assignment">Assignment</label>
              <select
                id="assignment"
                value={filters.assignment}
                onChange={(e) => filter('assignment', e.target.value)}
              >
                <option value="all">All assignments</option>
                <option value="assigned">Assigned</option>
                <option value="unassigned">Unassigned</option>
              </select>
            </div>
          )}
          <div>
            <label htmlFor="sort">Sort by</label>
            <select
              id="sort"
              value={`${filters.sort_by}:${filters.sort_order}`}
              onChange={(e) => {
                const [sort_by, sort_order] = e.target.value.split(':');
                setFilters((f) => ({ ...f, sort_by, sort_order, offset: 0 }));
              }}
            >
              <option value="created_at:desc">Newest first</option>
              <option value="created_at:asc">Oldest first</option>
              <option value="status:asc">Case state</option>
              <option value="version:desc">Case version</option>
            </select>
          </div>
        </form>
        {loading ? (
          <div className="state" role="status">
            Loading authorized cases…
          </div>
        ) : error ? (
          <ErrorState error={error} retry={() => setRevision((n) => n + 1)} />
        ) : (
          page && (
            <>
              <div className="table-wrap">
                <table>
                  <caption className="sr-only">
                    Authorized alerts and cases
                  </caption>
                  <thead>
                    <tr>
                      <th>Alert / case</th>
                      <th>Priority</th>
                      <th>Case state</th>
                      <th>Assessment</th>
                      <th>Assignment</th>
                      <th>Received</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <a className="case-link" href={`#/cases/${item.id}`}>
                            {item.source_id}
                          </a>
                          <small className="mono">{item.id.slice(0, 8)}</small>
                        </td>
                        <td>
                          <Badge value={item.priority} />
                        </td>
                        <td>
                          <Badge value={item.status} />
                        </td>
                        <td>
                          <Badge value={item.assessment_status} />
                        </td>
                        <td>
                          {item.assigned_to === user.id
                            ? 'Assigned to you'
                            : item.assigned_to
                              ? 'Assigned'
                              : 'Unassigned'}
                        </td>
                        <td className="muted">{date(item.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!page.items.length && (
                <div className="state">
                  <h2>No matching cases</h2>
                  <p>
                    Try different filters or ask a supervisor about assignment.
                  </p>
                </div>
              )}
              <Pager
                page={page}
                change={(offset) => setFilters((f) => ({ ...f, offset }))}
              />
            </>
          )
        )}
      </section>
      <p className="hint">
        Priority follows the frozen KYC grouping. Assessment status describes
        processing, not a human decision.
      </p>
    </>
  );
}

export function CaseView({
  id,
  workflow,
  api,
  user,
}: {
  id: string;
  workflow: boolean;
  api: ApiFactory;
  user: User;
}) {
  const [record, setRecord] = useState<Case | null>(null);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const value = await api(controller.signal).overview(id);
        if (!controller.signal.aborted) setRecord(value);
      } catch (e) {
        if (!controller.signal.aborted) {
          setRecord(null);
          setError(message(e));
        }
      }
    }
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 10000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [id, api, revision]);
  return (
    <>
      <a className="back" href="#/">
        ← Alert dashboard
      </a>
      {error ? (
        <ErrorState
          error={error}
          retry={() => {
            setError('');
            setRevision((n) => n + 1);
          }}
        />
      ) : !record ? (
        <div className="state" role="status">
          Loading case…
        </div>
      ) : (
        <>
          <div className="page-heading">
            <div>
              <p className="eyebrow">
                CASE REVIEW /{' '}
                <span className="mono">{record.id.slice(0, 8)}</span>
              </p>
              <h1>{record.source_id}</h1>
              <p className="muted">
                Received {date(record.created_at)} · Case version{' '}
                {record.version}
              </p>
            </div>
            <div className="heading-badges">
              <Badge value={record.priority} />
              <Badge value={record.status} />
            </div>
          </div>
          <nav className="tabs" aria-label="Case views">
            <a
              className={!workflow ? 'selected' : ''}
              aria-current={!workflow ? 'page' : undefined}
              href={`#/cases/${id}`}
            >
              Case details
            </a>
            <a
              className={workflow ? 'selected' : ''}
              aria-current={workflow ? 'page' : undefined}
              href={`#/cases/${id}/assessment`}
            >
              Assessment workflow
            </a>
          </nav>
          <div className="notice compact">
            <b>Human decision:</b>{' '}
            {record.disposition ? label(record.disposition) : 'Not recorded'}.
            Model recommendations do not change case state.
          </div>
          {workflow ? (
            <Workflow api={api} record={record} />
          ) : (
            <Results api={api} record={record} user={user} />
          )}
        </>
      )}
    </>
  );
}

function Results({
  api,
  record,
  user,
}: {
  api: ApiFactory;
  record: Case;
  user: User;
}) {
  const [history, setHistory] = useState<Page<Assessment> | null>(null);
  const [selected, setSelected] = useState<AssessmentDetail | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const active = useRef<AbortController | null>(null);
  const selection = useRef(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    active.current = controller;
    async function load() {
      const sequence = ++selection.current;
      setLoading(true);
      setSelected(null);
      setHistory(null);
      setError('');
      try {
        const response = await api(controller.signal).history(
          record.id,
          offset,
        );
        if (controller.signal.aborted) return;
        setHistory(response);
        if (response.items[0]) {
          const detail = await api(controller.signal).detail(
            record.id,
            response.items[0].assessment_id,
          );
          if (!controller.signal.aborted && sequence === selection.current)
            setSelected(detail);
        }
      } catch (e) {
        if (!controller.signal.aborted && sequence === selection.current) {
          setSelected(null);
          setHistory(null);
          setError(message(e));
        }
      } finally {
        if (!controller.signal.aborted && sequence === selection.current)
          setLoading(false);
      }
    }
    void load();
    return () => {
      controller.abort();
      active.current = null;
    };
  }, [api, record.id, offset, revision]);
  async function choose(id: string) {
    const signal = active.current?.signal;
    if (!signal || signal.aborted) return;
    const sequence = ++selection.current;
    setSelected(null);
    setLoading(true);
    try {
      const detail = await api(signal).detail(record.id, id);
      if (!signal.aborted && sequence === selection.current)
        setSelected(detail);
    } catch (e) {
      if (!signal.aborted && sequence === selection.current) {
        setError(message(e));
        setHistory(null);
      }
    } finally {
      if (!signal.aborted && sequence === selection.current) setLoading(false);
    }
  }
  if (error)
    return <ErrorState error={error} retry={() => setRevision((n) => n + 1)} />;
  return (
    <>
      {loading && (
        <p className="state" role="status">
          Loading verified results…
        </p>
      )}
      {!loading && !selected && (
        <section className="panel state">
          <h2>No assessment yet</h2>
          <p>
            Request a verified assessment to view RF scoring and feature
            attribution.
          </p>
          <a
            className="button primary"
            href={`#/cases/${record.id}/assessment`}
          >
            Open assessment workflow →
          </a>
        </section>
      )}
      {selected && <Explanation value={selected} />}
      {history && history.items.length > 0 && (
        <section className="panel history">
          <div className="section-heading">
            <h2>Assessment history</h2>
            <span className="muted">Immutable versions</span>
          </div>
          <div className="table-wrap">
            <table>
              <caption className="sr-only">Assessment versions</caption>
              <thead>
                <tr>
                  <th>Version</th>
                  <th>Processed</th>
                  <th>Policy</th>
                  <th>RF score</th>
                  <th>View</th>
                </tr>
              </thead>
              <tbody>
                {history.items.map((item) => (
                  <tr key={item.assessment_id}>
                    <td>v{item.version}</td>
                    <td>{date(item.processed_at)}</td>
                    <td>{item.selected_policy}</td>
                    <td>{(item.score * 100).toFixed(2)}%</td>
                    <td>
                      <button
                        className="quiet"
                        aria-label={`View assessment version ${item.version}`}
                        onClick={() => {
                          void choose(item.assessment_id);
                        }}
                      >
                        View →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={history} change={setOffset} />
        </section>
      )}
      <p className="hint">
        {record.assigned_to === user.id
          ? 'You are the assigned analyst.'
          : record.assigned_to
            ? 'This case is assigned to an analyst.'
            : 'This case is unassigned.'}{' '}
        Customer predictor values are not requested by this workbench.
      </p>
    </>
  );
}

export function Explanation({ value }: { value: AssessmentDetail }) {
  const e = value.explanation;
  if (
    e?.status !== 'verified' ||
    e.verification?.status !== 'verified' ||
    e.method?.positive_class_label !== 1 ||
    !Number.isFinite(e.base_value) ||
    !Number.isFinite(e.reconstruction_residual) ||
    Math.abs(e.reconstruction_residual) > 1e-6 ||
    !Number.isFinite(value.score) ||
    value.score < 0 ||
    value.score > 1 ||
    e.features.length !== 27 ||
    e.features.some((f) => !Number.isFinite(f.contribution))
  )
    return (
      <p role="alert" className="error">
        Verified explanation unavailable.
      </p>
    );
  const ranked = [...e.features].sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution),
  );
  const maximum = Math.max(
    ...ranked.map((f) => Math.abs(f.contribution)),
    1e-12,
  );
  return (
    <>
      <div className="result-summary">
        <section className="panel score-panel">
          <p className="eyebrow">RF SAR-POSITIVE SCORE</p>
          <div className="score" data-testid="rf-score">
            {(value.score * 100).toFixed(2)}
            <span>%</span>
          </div>
          <p className="muted">
            Frozen Random Forest · v{value.version} assessment
          </p>
        </section>
        <section className="panel recommendation">
          <p className="eyebrow">
            MODEL RECOMMENDATION / {value.selected_policy.toUpperCase()}
          </p>
          <h2>
            {value.recommended_route === 'retain_human_review'
              ? 'Retain for human review'
              : 'Review reduction candidate'}
          </h2>
          <p className="muted">
            {value.policy_trace.override_reason
              ? 'High-priority coverage protection applied.'
              : 'Frozen policy threshold applied.'}{' '}
            Human decision required.
          </p>
          <Badge value="verified" />
        </section>
      </div>
      <p className="disclaimer">
        Model scores are not proof of money laundering or calibrated
        probabilities of criminal conduct. SHAP describes model attribution, not
        causality.
      </p>
      <section className="panel explanation">
        <div className="section-heading">
          <div>
            <p className="eyebrow">VERIFIED EXPLAINABILITY</p>
            <h2>What influenced this score</h2>
          </div>
          <span className="legend">
            <i className="raise" />
            Raises <i className="lower" />
            Lowers
          </span>
        </div>
        <p className="muted">
          Contributions in score percentage points · base{' '}
          {(e.base_value * 100).toFixed(2)}%
        </p>
        <ol
          className="contributions"
          tabIndex={0}
          aria-label="SHAP feature contributions"
        >
          {ranked.map((f, index) => (
            <li key={f.name}>
              <span className="feature-name">
                <small>{String(index + 1).padStart(2, '0')}</small>
                {f.name.replace(/([a-z])([A-Z])/g, '$1 $2')}
                {f.missing && <em>missing</em>}
              </span>
              <svg
                className="contribution-bar"
                viewBox="0 0 200 16"
                aria-hidden="true"
              >
                <line x1="100" y1="0" x2="100" y2="16" />
                <rect
                  className={f.contribution >= 0 ? 'raise' : 'lower'}
                  x={
                    f.contribution >= 0
                      ? 100
                      : 100 - (Math.abs(f.contribution) / maximum) * 98
                  }
                  y="3"
                  width={(Math.abs(f.contribution) / maximum) * 98}
                  height="10"
                  rx="2"
                />
              </svg>
              <span className="contribution-number">
                {f.contribution >= 0 ? '+' : ''}
                {(f.contribution * 100).toFixed(4)} pp
              </span>
              <span className="sr-only">{label(f.direction)}</span>
            </li>
          ))}
        </ol>
      </section>
      <section className="panel provenance">
        <details>
          <summary>Model provenance & verification</summary>
          <dl>
            <dt>Model identity</dt>
            <dd>{value.model_version}</dd>
            <dt>Model SHA-256</dt>
            <dd className="mono">{value.model_sha256}</dd>
            <dt>Policy</dt>
            <dd>
              {value.selected_policy} / {value.policy_version} · threshold{' '}
              {value.policy_trace.threshold}
            </dd>
            <dt>Input fingerprint</dt>
            <dd className="mono">{value.input_sha256}</dd>
            <dt>Content fingerprint</dt>
            <dd className="mono">{value.content_sha256}</dd>
            <dt>Feature contract</dt>
            <dd>{value.input_provenance.feature_contract_version}</dd>
            <dt>Run</dt>
            <dd className="mono">{value.run_id}</dd>
            <dt>Explanation</dt>
            <dd>
              {e.method.algorithm} / SHAP {e.method.library_version} ·{' '}
              {e.method.output_space}
            </dd>
            <dt>Verification</dt>
            <dd>
              {e.verification.verifier} · reconstruction residual{' '}
              {e.reconstruction_residual.toExponential(3)}
            </dd>
            <dt>Processed</dt>
            <dd>{date(value.processed_at)}</dd>
          </dl>
        </details>
      </section>
    </>
  );
}

export function Workflow({ api, record }: { api: ApiFactory; record: Case }) {
  const [policy, setPolicy] = useState<Policy>('Balanced');
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [paused, setPaused] = useState(false);
  const [revision, setRevision] = useState(0);
  const [cooldown, setCooldown] = useState(0);
  const [conflict, setConflict] = useState(false);
  const [newRequest, setNewRequest] = useState(false);
  const receipts = useContext(Receipts);
  const [receipt, setReceipt] = useState<Receipt | null>(
    () => receipts?.get(record.id) ?? null,
  );
  const controller = useRef<AbortController | null>(null);
  const submitting = useRef(false);
  useEffect(() => {
    const local = new AbortController();
    controller.current = local;
    return () => {
      local.abort();
      controller.current = null;
    };
  }, []);
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setInterval(
      () => setCooldown((n) => Math.max(0, n - 1)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [cooldown]);
  const jobId = job?.job_id ?? (newRequest ? null : record.latest_job_id);
  const terminal = job?.status === 'succeeded' || job?.status === 'failed';
  useEffect(() => {
    if (!jobId || terminal) return;
    const local = new AbortController();
    let timer: number | undefined;
    let attempts = 0;
    const started = Date.now();
    async function poll() {
      if (local.signal.aborted) return;
      if (++attempts > 60 || Date.now() - started >= 300000) {
        setPaused(true);
        return;
      }
      let delay: number | null = 2000;
      try {
        const result = await api(local.signal).job(jobId!);
        if (local.signal.aborted) return;
        setJob(result);
        setError('');
        setPaused(false);
        if (['succeeded', 'failed'].includes(result.status)) return;
      } catch (failure) {
        if (local.signal.aborted) return;
        setError(message(failure));
        if (
          failure instanceof ApiError &&
          [401, 403, 404].includes(failure.status)
        )
          return;
        if (failure instanceof ApiError && failure.retryAfter)
          setCooldown(Math.ceil(failure.retryAfter));
        delay = pollDelay(
          failure instanceof ApiError ? failure.retryAfter || 5 : 5,
        );
      }
      if (delay === null) {
        setPaused(true);
        return;
      }
      timer = window.setTimeout(() => {
        void poll();
      }, delay);
    }
    void poll();
    return () => {
      local.abort();
      window.clearTimeout(timer);
    };
  }, [api, jobId, terminal, revision]);
  async function submit() {
    const signal = controller.current?.signal;
    if (!signal || signal.aborted || submitting.current || cooldown || conflict)
      return;
    submitting.current = true;
    setBusy(true);
    setError('');
    setJob(null);
    setNewRequest(true);
    const run = crypto.randomUUID();
    const request = receipt ?? {
      body: { expected_version: record.version, run_id: run, policy },
      key: `assessment:${run}`,
    };
    setReceipt(request);
    receipts?.set(record.id, request);
    try {
      const result = await api(signal).submit(
        record.id,
        request.body,
        request.key,
      );
      if (!signal.aborted) {
        receipts?.delete(record.id);
        setJob(result);
        setPaused(false);
        setRevision((n) => n + 1);
      }
    } catch (failure) {
      if (!signal.aborted) {
        setError(message(failure));
        if (failure instanceof ApiError) {
          setCooldown(Math.ceil(failure.retryAfter));
          if (failure.status === 409) {
            receipts?.delete(record.id);
            setConflict(true);
          }
        }
      }
    } finally {
      submitting.current = false;
      if (!signal.aborted) setBusy(false);
    }
  }
  function newRun() {
    receipts?.delete(record.id);
    setReceipt(null);
    setNewRequest(true);
    setJob(null);
    setError('');
    setRevision((n) => n + 1);
  }
  const active = !!job && !terminal;
  return (
    <div className="workflow-grid">
      <section className="panel workflow">
        <p className="eyebrow">CONTROLLED MODEL EXECUTION</p>
        <h2>Request an assessment</h2>
        <p className="muted">
          Uses the immutable alert snapshot. RF scoring, policy routing and
          verified SHAP run in the isolated worker.
        </p>
        <label htmlFor="policy">Review policy</label>
        <select
          id="policy"
          value={receipt?.body.policy ?? policy}
          disabled={busy || !!receipt || active}
          onChange={(e) => setPolicy(e.target.value as Policy)}
        >
          <option>Efficiency</option>
          <option>Balanced</option>
          <option>Coverage</option>
        </select>
        <p className="hint">
          Efficiency reduces review volume; Balanced retains more positive
          cases; Coverage also protects High-priority cases.
        </p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {cooldown > 0 && <p role="status">Retry available in {cooldown}s.</p>}
        {conflict ? (
          <a className="button" href={`#/cases/${record.id}`}>
            Reload case details
          </a>
        ) : terminal && receipt ? (
          <button onClick={newRun}>Prepare new assessment</button>
        ) : (
          <button
            className="primary"
            disabled={
              busy ||
              active ||
              record.status === 'closed' ||
              cooldown > 0 ||
              (!newRequest && !!record.latest_job_id && !job)
            }
            onClick={() => {
              void submit();
            }}
          >
            {busy
              ? 'Submitting…'
              : active
                ? 'Assessment in progress'
                : receipt
                  ? 'Retry same request'
                  : 'Request assessment'}
          </button>
        )}
        <p className="hint">
          A retry reuses the original run and key. Reassessment creates a new
          immutable version. No dismissal or closure is performed.
        </p>
      </section>
      <section className="panel job-status" aria-live="polite">
        <p className="eyebrow">PROCESSING STATUS</p>
        {job ? (
          <>
            <h2>
              <Badge value={job.status} />
            </h2>
            <ol className="steps">
              {['pending', 'running', 'succeeded'].map((state) => (
                <li
                  key={state}
                  className={job.status === state ? 'current' : ''}
                >
                  {label(state)}
                </li>
              ))}
            </ol>
            <dl>
              <dt>Attempts</dt>
              <dd>{job.attempts} / 3</dd>
              <dt>Policy</dt>
              <dd>{job.policy}</dd>
            </dl>
            {job.status === 'pending' && (
              <p className="muted">
                Durably queued. A stopped worker leaves this job pending; no
                result is fabricated.
              </p>
            )}
            {job.status === 'running' && (
              <p className="muted">
                The isolated worker is scoring and verifying the explanation.
              </p>
            )}
            {job.status === 'failed' && (
              <div className="error">
                <b>Manual review required.</b>
                <p>
                  {label(job.failure_code ?? 'processing_unavailable')}. No case
                  decision was changed.
                </p>
              </div>
            )}
            {job.status === 'succeeded' && (
              <>
                <p className="success">
                  Assessment and verified explanation saved.
                </p>
                <a className="button primary" href={`#/cases/${record.id}`}>
                  View verified results →
                </a>
              </>
            )}
            {paused && (
              <p className="notice">
                Polling paused after the bounded observation window. The durable
                job continues independently.
              </p>
            )}
            {paused && (
              <button
                disabled={cooldown > 0}
                onClick={() => {
                  setPaused(false);
                  setRevision((n) => n + 1);
                }}
              >
                Resume status checks
              </button>
            )}
          </>
        ) : (
          <>
            <h2>
              {record.latest_job_id
                ? 'Checking latest job…'
                : 'Ready when you are'}
            </h2>
            <p className="muted">
              {record.latest_job_id
                ? 'Retrieving authorized processing status.'
                : 'Request an assessment to start the asynchronous workflow.'}
            </p>
          </>
        )}
      </section>
    </div>
  );
}
