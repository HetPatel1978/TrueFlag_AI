import { WorkflowNavigation } from './workflow-navigation';
import {
  useContext,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
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
import { InvestigationView } from './investigation';
import type { InvestigationFactory } from './investigation-api';
import { TERMS, featureLabel } from './terminology';
import { PageHeader, StatusBadge } from './ui';
import type { WorkflowCase, WorkflowFactory } from './workflow-api';
import { AssignmentControl, ActivityHistory } from './case-workflows';
import { HumanCasework } from './human-casework';
import type { HumanFactory } from './human-casework-api';
import {
  AuditDetails,
  AuditList,
  CopyValue,
  InfoTip,
  PageAudit,
  Timestamp,
  VerifiedBadge,
} from './display';
import { CaseAudit, CaseHeader, CaseRail } from './case-file';
import { formatDateTime, pp1, scorePercent, shortId } from './format';

export const Badge = StatusBadge;
function ErrorState({
  error,
  retry,
  retryAt = 0,
}: {
  error: string;
  retry: () => void;
  retryAt?: number;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!retryAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [retryAt]);
  const wait = Math.max(0, Math.ceil((retryAt - now) / 1000));
  return (
    <div className="panel state" role="alert">
      <h2>{wait ? 'Updates paused' : 'Unable to load'}</h2>
      <p>
        {wait
          ? 'The request limit was reached. Your saved work is preserved; updates will retry after the wait.'
          : error}
      </p>
      <button onClick={retry} disabled={wait > 0}>
        {wait ? `Retry in ${wait}s` : 'Retry'}
      </button>
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
          Previous
        </button>
        <button
          aria-label="Next page"
          disabled={
            page.offset + page.limit >= page.total ||
            page.offset + page.limit > 10000
          }
          onClick={() => change(page.offset + page.limit)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

export function Dashboard({
  api,
  user,
  workflowApi,
  uploadSessionId,
}: {
  api: ApiFactory;
  user: User;
  workflowApi?: WorkflowFactory;
  uploadSessionId?: string;
}) {
  const [page, setPage] = useState<Page<WorkflowCase> | null>(null);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState('');
  const [filters, setFilters] = useState({
    queue: user.role === 'analyst' ? 'my' : 'all',
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
      if (uploadSessionId) {
        params.set('upload_session_id', uploadSessionId);
        params.set('origin', 'uploaded');
      }
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== '') params.set(key, String(value));
      });
      try {
        const result = workflowApi
          ? await workflowApi(controller.signal).queue(params)
          : await api(controller.signal).cases(params);
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
  }, [api, workflowApi, filters, revision, uploadSessionId]);
  function filter(key: keyof typeof filters, value: string) {
    setFilters((f) => ({ ...f, [key]: value, offset: 0 }));
  }
  return (
    <>
      <PageHeader
        title="Cases"
        actions={
          user.role === 'admin' && !uploadSessionId ? (
            <a className="button primary" href="#/batch">
              Import alerts
            </a>
          ) : undefined
        }
      />
      <section className="panel">
        <form
          className="filters"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            filter('search', draft);
          }}
        >
          {workflowApi && (
            <div className="queue-selector">
              <label htmlFor="case-queue">Case Queue</label>
              <select
                id="case-queue"
                value={filters.queue}
                onChange={(e) =>
                  setFilters((f) => ({
                    ...f,
                    queue: e.target.value,
                    assignment: 'all',
                    offset: 0,
                  }))
                }
              >
                <option value="my">My Assigned Cases</option>
                <option value="all">All Accessible Cases</option>
                {user.role !== 'analyst' && (
                  <option value="unassigned">Unassigned Cases</option>
                )}
                <option value="review">In review / awaiting approval</option>
                <option value="processing">Assessment processing</option>
              </select>
            </div>
          )}
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
          <details className="filter-disclosure">
            <summary>
              More filters
              {[
                filters.status,
                filters.priority,
                filters.assessment_status,
                filters.assignment !== 'all' ? filters.assignment : '',
              ].filter(Boolean).length > 0
                ? ' · active'
                : ''}
            </summary>
            <div className="filter-grid">
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
                    setFilters((f) => ({
                      ...f,
                      sort_by,
                      sort_order,
                      offset: 0,
                    }));
                  }}
                >
                  <option value="created_at:desc">Newest first</option>
                  <option value="created_at:asc">Oldest first</option>
                  <option value="status:asc">Case state</option>
                  <option value="version:desc">Case version</option>
                </select>
              </div>
            </div>
          </details>
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
              <div
                className="table-wrap"
                role="region"
                aria-label="Case results"
                tabIndex={0}
              >
                <table className="case-table">
                  <caption className="sr-only">
                    Authorized alerts and cases
                  </caption>
                  <colgroup>
                    <col className="col-case" />
                    <col className="col-priority" />
                    {workflowApi && <col className="col-score" />}
                    {workflowApi && <col className="col-recommendation" />}
                    <col className="col-assignee" />
                    <col className="col-updated" />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>Case</th>
                      <th>
                        Priority{' '}
                        <InfoTip text="Priority reflects the customer risk rating (KYC 3–6 is High)." />
                      </th>
                      {workflowApi && <th className="num">Score</th>}
                      {workflowApi && <th>Recommendation</th>}
                      <th>Assignee</th>
                      <th>Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((item) => (
                      <tr
                        key={item.id}
                        className="row-link"
                        onClick={() => {
                          window.location.hash = `/cases/${item.id}`;
                        }}
                      >
                        <td className="case-id">
                          <a
                            className="case-link"
                            href={`#/cases/${item.id}`}
                            aria-label={`Case ${shortId(item.id)}`}
                          >
                            {shortId(item.id)}
                          </a>
                          {item.status !== 'open' && (
                            <>
                              {' '}
                              <Badge value={item.status} />
                            </>
                          )}
                        </td>
                        <td>
                          <Badge value={item.priority} />
                        </td>
                        {workflowApi && (
                          <td className="num">
                            {item.assessment_status === 'succeeded' ? (
                              scorePercent(item.assessment_score)
                            ) : item.assessment_status === 'not_requested' ? (
                              <span className="muted">–</span>
                            ) : (
                              <Badge value={item.assessment_status} />
                            )}
                          </td>
                        )}
                        {workflowApi && (
                          <td
                            className="truncate"
                            title={
                              item.review_recommendation
                                ? label(item.review_recommendation)
                                : undefined
                            }
                          >
                            {item.review_recommendation ? (
                              <>{label(item.review_recommendation)}</>
                            ) : (
                              <span className="muted">Not assessed</span>
                            )}
                          </td>
                        )}
                        <td>
                          {item.assigned_investigator ??
                            (item.assigned_to === user.id
                              ? 'You'
                              : item.assigned_to
                                ? 'Assigned'
                                : 'Unassigned')}
                        </td>
                        <td>
                          <Timestamp
                            value={item.last_activity_at ?? item.created_at}
                            relative
                          />
                        </td>
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
    </>
  );
}

export function CaseView({
  id,
  workflow,
  api,
  user,
  investigation = false,
  evidence = false,
  investigationApi,
  workflowApi,
  activity = false,
  casework = false,
  decide = false,
  humanApi,
}: {
  id: string;
  workflow: boolean;
  api: ApiFactory;
  user: User;
  investigation?: boolean;
  evidence?: boolean;
  investigationApi?: InvestigationFactory;
  workflowApi?: WorkflowFactory;
  activity?: boolean;
  casework?: boolean;
  decide?: boolean;
  humanApi?: HumanFactory;
}) {
  const [record, setRecord] = useState<WorkflowCase | null>(null);
  const [missing, setMissing] = useState<string[] | null>(null);
  const stepLoadsEvidence = Boolean(
    investigationApi && (evidence || investigation || (casework && humanApi)),
  );
  // Steps that already read the evidence context report its missing categories; the
  // others read it once here, so the rail never adds a second concurrent evidence read.
  const caseVersion = record?.version;
  useEffect(() => {
    if (!investigationApi || stepLoadsEvidence || caseVersion === undefined)
      return;
    const controller = new AbortController();
    investigationApi(controller.signal)
      .context(id)
      .then((c) => {
        if (!controller.signal.aborted) setMissing(c.data.missing_categories);
      })
      .catch(() => {
        if (!controller.signal.aborted) setMissing([]);
      });
    return () => controller.abort();
  }, [id, investigationApi, stepLoadsEvidence, caseVersion]);
  const [error, setError] = useState('');
  const [retryAt, setRetryAt] = useState(0);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    async function load() {
      let delay = 10000;
      try {
        const value = workflowApi
          ? await workflowApi(controller.signal).overview(id)
          : await api(controller.signal).overview(id);
        if (!controller.signal.aborted) {
          setRecord(value);
          setError('');
          setRetryAt(0);
        }
      } catch (e) {
        if (!controller.signal.aborted) {
          setRecord(null);
          setError(message(e));
          if (e instanceof ApiError && e.status === 429) {
            delay = Math.max(delay, (e.retryAfter || 10) * 1000);
            setRetryAt(Date.now() + delay);
          }
        }
      } finally {
        if (!controller.signal.aborted)
          timer = window.setTimeout(() => void load(), delay);
      }
    }
    void load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [id, api, workflowApi, revision]);
  function refreshCase() {
    setRecord(null);
    setError('');
    setRevision((n) => n + 1);
  }
  const current = activity
    ? 'activity'
    : casework
      ? 'decision'
      : investigation
        ? 'investigation'
        : evidence
          ? 'evidence'
          : 'assessment';
  return (
    <>
      {error ? (
        <ErrorState
          error={error}
          retryAt={retryAt}
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
        <PageAudit.Provider value={<CaseAudit record={record} />}>
          <CaseHeader
            record={record}
            tabs={
              <>
                <WorkflowNavigation
                  record={record}
                  current={current}
                  evidenceAvailable={Boolean(investigationApi)}
                  decisionsAvailable={Boolean(humanApi && investigationApi)}
                />
                {workflowApi && (
                  <a
                    className="activity-link"
                    href={`#/cases/${id}/activity`}
                    aria-current={activity ? 'page' : undefined}
                  >
                    Activity History
                  </a>
                )}
              </>
            }
          />
          <div className="case-file">
            <div className="case-main">
              {casework && humanApi && investigationApi ? (
                <HumanCasework
                  id={id}
                  user={user}
                  api={humanApi}
                  evidenceApi={investigationApi}
                  changed={refreshCase}
                  decide={decide}
                  onMissing={setMissing}
                />
              ) : activity && workflowApi ? (
                <ActivityHistory
                  key={record.version}
                  record={record}
                  api={workflowApi}
                />
              ) : (investigation || evidence) && investigationApi ? (
                <InvestigationView
                  key={record.version}
                  record={record}
                  api={investigationApi}
                  modelApi={api}
                  view={evidence ? 'evidence' : 'investigation'}
                  onMissing={setMissing}
                />
              ) : workflow ? (
                <Workflow key={record.version} api={api} record={record} />
              ) : (
                <Results
                  key={record.version}
                  api={api}
                  record={record}
                  user={user}
                />
              )}
            </div>
            <CaseRail
              record={record}
              user={user}
              missing={investigationApi ? missing : []}
              decisionsAvailable={
                Boolean(humanApi && investigationApi) && !casework
              }
              showScore={current === 'evidence' || current === 'decision'}
              reassign={
                workflowApi && user.role !== 'analyst' ? (
                  <AssignmentControl
                    key={record.version}
                    record={record}
                    api={workflowApi}
                    changed={refreshCase}
                  />
                ) : undefined
              }
            />
          </div>
        </PageAudit.Provider>
      )}
    </>
  );
}

function Results({
  api,
  record,
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
  const versionLine =
    history && history.items.length > 0 ? (
      <div
        className="version-line"
        data-testid="assessment-history"
        data-total={history.total}
      >
        {history.items.length > 1 && (
          <select
            aria-label="Assessment version"
            value={selected?.assessment_id ?? ''}
            onChange={(e) => void choose(e.target.value)}
          >
            {!selected && <option value="">Loading version…</option>}
            {history.items.map((item) => (
              <option key={item.assessment_id} value={item.assessment_id}>
                v{item.version} · {item.selected_policy} ·{' '}
                {scorePercent(item.score)}
              </option>
            ))}
          </select>
        )}
        {history.total > history.items.length && (
          <Pager page={history} change={setOffset} />
        )}
      </div>
    ) : null;
  return (
    <>
      {loading && (
        <p className="state" role="status">
          Loading verified results…
        </p>
      )}
      {loading && !selected && versionLine}
      {!loading && !selected && (
        <section className="panel state">
          <h2>No assessment yet</h2>
          <p>
            Request an assessment to review the alert risk signal and
            contributing factors.
          </p>
          <a
            className="button primary"
            href={`#/cases/${record.id}/assessment`}
          >
            Assess risk
          </a>
        </section>
      )}
      {selected && (
        <Explanation
          value={selected}
          versionLine={versionLine}
          actions={
            <div className="next-actions">
              <a
                className="button primary"
                href={`#/cases/${record.id}/evidence`}
              >
                Review evidence
              </a>
              <a className="button" href={`#/cases/${record.id}/assessment`}>
                Request another assessment
              </a>
            </div>
          }
        />
      )}
    </>
  );
}

export function Explanation({
  value,
  versionLine,
  actions,
}: {
  value: AssessmentDetail;
  versionLine?: ReactNode;
  actions?: ReactNode;
}) {
  const [showAll, setShowAll] = useState(false);
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
      <section className="panel assessment-card" aria-label={TERMS.assessment}>
        <div className="assessment-head">
          <div>
            <span className="rail-label">{TERMS.assessment}</span>
            <div className="score" data-testid="rf-score">
              {scorePercent(value.score)}
            </div>
          </div>
          <div className="assessment-route">
            <span className="rail-label">{TERMS.recommendation}</span>
            <h2>{label(value.recommended_route)}</h2>
            <VerifiedBadge title="Model, policy and explanation checks passed" />
          </div>
        </div>
        <p className="muted">
          Model signal for analyst review, not proof.
          {value.policy_trace.override_reason
            ? ' High-priority coverage protection applied.'
            : ''}
        </p>
        {versionLine}
      </section>
      <section className="panel explanation" aria-labelledby="drivers-title">
        <div className="section-heading">
          <h2 id="drivers-title">{TERMS.drivers}</h2>
          <span className="legend">
            <span className="raise">↑ Raises score</span>
            <span className="lower">↓ Lowers score</span>
          </span>
        </div>
        <ol className="contributions" tabIndex={0} aria-label={TERMS.factors}>
          {(showAll ? ranked : ranked.slice(0, 3)).map((f) => (
            <li key={f.name}>
              <span className="feature-name">
                <span
                  className={`direction ${f.contribution >= 0 ? 'raise' : 'lower'}`}
                  aria-hidden="true"
                >
                  {f.contribution >= 0 ? '↑' : '↓'}
                </span>
                <span>{featureLabel(f.name)}</span>
                {f.missing && <em>missing</em>}
              </span>
              <svg
                className="contribution-bar"
                viewBox="0 0 200 12"
                aria-hidden="true"
              >
                <line x1="100" y1="0" x2="100" y2="12" />
                <rect
                  className={f.contribution >= 0 ? 'raise' : 'lower'}
                  x={
                    f.contribution >= 0
                      ? 100
                      : 100 - (Math.abs(f.contribution) / maximum) * 98
                  }
                  y="2"
                  width={(Math.abs(f.contribution) / maximum) * 98}
                  height="8"
                  rx="2"
                />
              </svg>
              <span className="contribution-number">
                {pp1(f.contribution * 100)}
              </span>
              <span className="sr-only">{label(f.direction)}</span>
            </li>
          ))}
        </ol>
        {ranked.length > 3 && (
          <button
            className="quiet"
            onClick={() => setShowAll((v) => !v)}
            aria-expanded={showAll}
          >
            {showAll ? 'Show top 3' : `Show all ${ranked.length}`}
          </button>
        )}
      </section>
      {actions}
      <AuditDetails>
        <AuditList>
          <CopyValue label="Model identity" value={value.model_version} />
          <CopyValue label="Model SHA-256" value={value.model_sha256} />
          <dt>Policy</dt>
          <dd>
            {value.selected_policy} / {value.policy_version} · threshold{' '}
            {value.policy_trace.threshold}
          </dd>
          <CopyValue
            label="Policy fingerprint"
            value={value.policy_trace.policy_sha256}
          />
          <CopyValue label="Input fingerprint" value={value.input_sha256} />
          <CopyValue label="Content fingerprint" value={value.content_sha256} />
          <dt>Feature contract</dt>
          <dd>{value.input_provenance.feature_contract_version}</dd>
          <CopyValue label="Run" value={value.run_id} />
          <CopyValue label="Assessment ID" value={value.assessment_id} />
          <dt>Explanation method</dt>
          <dd>
            {e.method.algorithm} / SHAP {e.method.library_version} ·{' '}
            {e.method.output_space}
          </dd>
          <dt>
            Exact contributions (pp, base {(e.base_value * 100).toFixed(4)}%)
          </dt>
          <dd>
            {ranked
              .map((f) => `${f.name} ${(f.contribution * 100).toFixed(4)}`)
              .join(' · ')}
          </dd>
          <dt>Verification</dt>
          <dd>
            {e.verification.verifier} · reconstruction residual{' '}
            {e.reconstruction_residual.toExponential(3)}
          </dd>
          <dt>Processed</dt>
          <dd>{formatDateTime(value.processed_at)}</dd>
        </AuditList>
      </AuditDetails>
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
        <h2>Request an assessment</h2>
        <p className="muted">
          Assess the saved alert information and identify contributing factors.
          Processing continues securely in the background; your review remains
          required.
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
          saved version. No dismissal or closure is performed.
        </p>
      </section>
      <section className="panel job-status" aria-live="polite">
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
                Request received. Waiting for the processing service. Results
                will appear when processing completes.
              </p>
            )}
            {job.status === 'running' && (
              <p className="muted">
                Assessment and contributing factors are being checked.
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
                  Assessment and key risk drivers saved.
                </p>
                <a className="button primary" href={`#/cases/${record.id}`}>
                  View verified results →
                </a>
              </>
            )}
            {paused && (
              <p className="notice">
                Automatic status checks are paused. Background processing
                continues.
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
                ? 'Checking latest assessment…'
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
