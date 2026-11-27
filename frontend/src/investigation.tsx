import {
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
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
  type Page,
} from './api';
import type { ApiFactory } from './App';
import {
  InvestigationReceipts,
  type Activity,
  type CaseContext,
  type Currency,
  type Customer,
  type CursorPage,
  type Evidence,
  type InvestigationFactory,
  type PacketDetail,
  type PacketHistory,
  type PacketRequest,
  type Related,
  type Transaction,
  type Window,
} from './investigation-api';
import { TERMS, decimalMoney } from './terminology';
import { StatusBadge } from './ui';
import { Fragment } from 'react';
import {
  AuditDetails,
  AuditList,
  CopyValue,
  CoverageBadge,
  MissingLine,
} from './display';
import {
  formatDate,
  money as formatMoney,
  percent1,
  periodLabel,
  shortId,
  subtractDecimal,
  utcText,
} from './format';
import './investigation.css';
import { DraftWorkspace } from './drafts';
import { directionShort } from './investigation-result';

const failure = (e: unknown) =>
  e instanceof ApiError && e.reason === 'clock_uncertainty'
    ? 'Service temporarily unavailable: time verification could not be completed. Supporting evidence has been hidden. Try again when service is restored.'
    : e instanceof ApiError && [409, 422].includes(e.status)
      ? 'The evidence changed, its access window expired, or the selected period is invalid. Refresh supporting evidence before continuing.'
      : e instanceof ApiError && e.status === 503
        ? 'Evidence service unavailable. Protected observations have been cleared. Retry safely.'
        : e instanceof ApiError && e.status === 413
          ? 'Evidence exceeds supported bounds. Choose a narrower window or contact an authorized administrator.'
          : message(e);
const utc = (value: string | null) =>
  value
    ? new Date(value).toISOString().replace('T', ' ').replace('.000Z', ' UTC')
    : 'Time not recorded';
const money = decimalMoney;
const codes = (values: string[]) =>
  values.length ? (
    <ul>
      {values.map((v) => (
        <li key={v}>{label(v)}</li>
      ))}
    </ul>
  ) : (
    <p className="muted">None reported for this selection.</p>
  );
function Cover({ value }: { value: Evidence<unknown> }) {
  return (
    <div className="coverage-strip" role="note">
      <b>{label(value.coverage.status)}</b>
      {value.coverage.unknown_time_excluded > 0 && (
        <span>
          {value.coverage.unknown_time_excluded} unresolved-time observations
          excluded
        </span>
      )}
      {value.coverage.limitations.length > 0 && (
        <details>
          <summary>Coverage limitations</summary>
          {codes(value.coverage.limitations)}
        </details>
      )}
    </div>
  );
}

export function InvestigationView({
  record,
  api,
  modelApi,
  renderModel,
  view = 'all',
  onMissing,
}: {
  record: Case;
  api: InvestigationFactory;
  modelApi: ApiFactory;
  renderModel?: (a: AssessmentDetail) => ReactNode;
  view?: 'all' | 'evidence' | 'investigation';
  /** Reports the case's missing evidence categories to the case rail. */
  onMissing?: (missing: string[]) => void;
}) {
  const [context, setContext] = useState<Evidence<CaseContext> | null>(null);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selection, setSelection] = useState('latest');
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [showEmptyDetails, setShowEmptyDetails] = useState(false);
  const [tab, setTab] = useState(
    view === 'investigation' ? 'findings' : 'evidence',
  );
  const scope = useRef<AbortController | null>(null);
  const invalidate = useCallback((e: unknown) => {
    scope.current?.abort();
    setContext(null);
    setAssessments([]);
    setError(failure(e));
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    scope.current = controller;
    let timer: number | undefined;
    let checks = 0;
    async function load() {
      setContext(null);
      setError('');
      setAssessments([]);
      try {
        const history = await modelApi(controller.signal).history(record.id);
        if (controller.signal.aborted) return;
        const assessment =
          selection === 'latest'
            ? history.items[0]?.assessment_id
            : selection === 'none'
              ? undefined
              : selection;
        const initial = await api(controller.signal).context(
          record.id,
          assessment,
        );
        if (controller.signal.aborted) return;
        setAssessments(history.items);
        setContext(initial);
        async function recheck() {
          if (controller.signal.aborted) return;
          if (++checks > 30) {
            setContext(null);
            setError(
              'Refresh supporting evidence to renew access to the current records.',
            );
            return;
          }
          try {
            const current = await api(controller.signal).context(
              record.id,
              assessment,
            );
            if (controller.signal.aborted) return;
            if (current.snapshot.sha256 !== initial.snapshot.sha256) {
              setContext(null);
              setRevision((n) => n + 1);
              return;
            }
            timer = window.setTimeout(() => {
              void recheck();
            }, 15000);
          } catch (e) {
            if (!controller.signal.aborted) invalidate(e);
          }
        }
        timer = window.setTimeout(() => {
          void recheck();
        }, 15000);
      } catch (e) {
        if (!controller.signal.aborted) invalidate(e);
      }
    }
    void load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [
    record.id,
    record.version,
    api,
    modelApi,
    revision,
    selection,
    invalidate,
  ]);
  const missingCategories = context?.data.missing_categories;
  useEffect(() => {
    if (missingCategories) onMissing?.(missingCategories);
  }, [missingCategories, onMissing]);
  if (error)
    return (
      <section className="panel state" role="alert">
        <h2>Investigation unavailable</h2>
        <p>{error}</p>
        <button onClick={() => setRevision((n) => n + 1)}>
          Refresh evidence
        </button>
      </section>
    );
  if (!context || context.snapshot.case_version !== record.version)
    return (
      <div className="state" role="status">
        Verifying authorized evidence…
      </div>
    );
  const data = context.data;
  const needsEvidence = !context.sources.length;
  const caseFile = view !== 'all';
  // Assessment selection and exact revisions live in the page's Audit details.
  const versionControls = (
    <div className="version-controls">
      <label htmlFor="investigation-assessment">Assessment to include</label>
      <select
        id="investigation-assessment"
        value={selection}
        onChange={(e) => {
          setContext(null);
          setSelection(e.target.value);
        }}
      >
        <option value="latest">Latest completed assessment</option>
        <option value="none">Evidence only — no assessment selected</option>
        {assessments.map((a) => (
          <option key={a.assessment_id} value={a.assessment_id}>
            Assessment v{a.version} · {a.selected_policy}
          </option>
        ))}
      </select>
      <p className="hint">
        Case v{context.snapshot.case_version} · Evidence revision{' '}
        {context.snapshot.evidence_revision} · Access revision{' '}
        {context.snapshot.access_revision}
        {data.model_signal
          ? ''
          : ` · No completed assessment selected (processing status: ${label(record.assessment_status)}); no score is inferred.`}
      </p>
    </div>
  );
  if (caseFile && !needsEvidence && view === 'evidence')
    return (
      <EvidenceStep
        key={context.snapshot.sha256}
        id={record.id}
        api={api}
        context={context}
        invalidate={invalidate}
        versionControls={versionControls}
      />
    );
  if (caseFile && !needsEvidence)
    return (
      <div className="investigation-workspace" key={context.snapshot.sha256}>
        <PacketWorkspace
          id={record.id}
          api={api}
          context={context}
          invalidate={invalidate}
          omissionReason={selection === 'none' ? 'not_selected' : 'unavailable'}
          draftFocus
          auditPrefix={versionControls}
        />
      </div>
    );
  return (
    <div className="investigation-workspace" key={context.snapshot.sha256}>
      <div className="investigation-toolbar">
        <div>
          <h2>
            {view === 'evidence'
              ? 'Supporting evidence'
              : view === 'investigation'
                ? 'Investigation'
                : 'Investigation workspace'}
          </h2>
          <p className="muted">
            {view === 'evidence'
              ? 'Review the records behind this case.'
              : 'Review verified summaries and record your conclusions.'}
          </p>
        </div>
        <button onClick={() => setRevision((n) => n + 1)}>
          Refresh evidence
        </button>
      </div>
      {needsEvidence && (
        <section
          className="panel evidence-empty-state"
          aria-label="Investigation readiness"
        >
          <h3>Supporting records needed</h3>
          <p>
            {data.model_signal ? 'Your risk assessment is available. ' : ''}
            No accessible supporting records are linked to this case. Customer,
            account and transaction records are needed for an evidence-based
            investigation.
          </p>
          <div className="actions">
            <a className="button primary" href={`#/cases/${record.id}`}>
              View risk assessment
            </a>
            <button
              aria-expanded={showEmptyDetails}
              onClick={() => setShowEmptyDetails((v) => !v)}
            >
              {showEmptyDetails
                ? 'Hide details and history'
                : 'Show details and history'}
            </button>
          </div>
          <p className="hint">
            Missing or revoked records do not indicate zero activity. AI and
            regulatory references cannot replace case evidence.
          </p>
        </section>
      )}
      {(!needsEvidence || showEmptyDetails) && (
        <>
          {view === 'all' && (
            <dl
              className="investigation-overview"
              aria-label="Investigation overview"
            >
              <div>
                <dt>{TERMS.assessment}</dt>
                <dd>
                  {data.model_signal
                    ? `${(data.model_signal.score * 100).toFixed(2)}%`
                    : 'Not assessed'}
                  <small>
                    Model signal, not a likelihood of money laundering
                  </small>
                </dd>
              </div>
              <div>
                <dt>{TERMS.recommendation}</dt>
                <dd>
                  {data.model_signal
                    ? label(data.model_signal.recommended_route)
                    : 'Awaiting assessment'}
                  <small>Final review remains with an analyst</small>
                </dd>
              </div>
              <div>
                <dt>Evidence availability</dt>
                <dd>
                  {label(context.coverage.status)}
                  <small>
                    {data.missing_categories.length
                      ? `${data.missing_categories.length} evidence categories missing`
                      : 'Available categories linked to this case'}
                  </small>
                </dd>
              </div>
            </dl>
          )}
          {view === 'all' && (
            <>
              <nav className="tabs" aria-label="Investigation sections">
                {[
                  ['evidence', TERMS.customer],
                  ['activity', TERMS.activity],
                  ['sources', TERMS.evidence],
                  ['packets', TERMS.summary],
                  ['findings', TERMS.findings],
                ]
                  .filter(
                    ([key]) =>
                      view === 'all' ||
                      (view === 'evidence'
                        ? ['evidence', 'activity', 'sources'].includes(key)
                        : ['packets', 'findings'].includes(key)),
                  )
                  .map(([key, title]) => (
                    <button
                      key={key}
                      className={tab === key ? 'selected' : ''}
                      aria-pressed={tab === key}
                      onClick={() => setTab(key)}
                    >
                      {title}
                    </button>
                  ))}
              </nav>
            </>
          )}
          <Cover value={context} />
          {data.missing_categories.length > 0 && tab !== 'findings' && (
            <details className="notice">
              <summary>
                Missing evidence · {data.missing_categories.length} categories
              </summary>
              <p>{data.missing_categories.map(label).join(', ')}.</p>
            </details>
          )}
          {(tab === 'evidence' || view === 'evidence') && (
            <>
              {context.sources.length > 0 ? (
                <CustomerAccounts
                  id={record.id}
                  api={api}
                  context={context}
                  invalidate={invalidate}
                />
              ) : (
                <section className="panel">
                  <h3>Customer and account evidence unavailable</h3>
                  <p>
                    No authorized source records are available for this review.
                  </p>
                </section>
              )}
            </>
          )}
          {view === 'evidence' && (
            <details className="panel disclosure">
              <summary>Source records & revisions</summary>
              <Sources context={context} />
            </details>
          )}
          {tab === 'sources' && view !== 'evidence' && (
            <Sources context={context} />
          )}
          {(tab === 'activity' || view === 'evidence') && (
            <ActivityWorkspace
              id={record.id}
              api={api}
              context={context}
              invalidate={invalidate}
            />
          )}
          {view !== 'evidence' && (tab === 'packets' || tab === 'findings') && (
            <PacketWorkspace
              id={record.id}
              api={api}
              context={context}
              invalidate={invalidate}
              omissionReason={
                selection === 'none' ? 'not_selected' : 'unavailable'
              }
              draftFocus={tab === 'findings'}
            />
          )}
          <details className="panel investigation-selection disclosure">
            <summary>Assessment and evidence version</summary>
            <label htmlFor="investigation-assessment">
              Assessment to include
            </label>
            <select
              id="investigation-assessment"
              value={selection}
              onChange={(e) => {
                setContext(null);
                setSelection(e.target.value);
              }}
            >
              <option value="latest">Latest completed assessment</option>
              <option value="none">
                Evidence only — no assessment selected
              </option>
              {assessments.map((a) => (
                <option key={a.assessment_id} value={a.assessment_id}>
                  Assessment v{a.version} · {a.selected_policy}
                </option>
              ))}
            </select>
            <details className="technical-details">
              <summary>Evidence version details</summary>{' '}
              <p className="hint">
                Case v{context.snapshot.case_version} · Evidence revision{' '}
                {context.snapshot.evidence_revision} · Access revision{' '}
                {context.snapshot.access_revision}
              </p>
            </details>
            {data.model_signal ? (
              renderModel && (
                <details>
                  <summary>{TERMS.drivers}</summary>
                  {renderModel(data.model_signal)}
                </details>
              )
            ) : (
              <p className="notice">
                No completed assessment selected. Processing status:{' '}
                {label(record.assessment_status)}. No score is inferred.
              </p>
            )}
          </details>
          {view === 'evidence' && (
            <p className="next-actions">
              <a
                className="button primary"
                href={`#/cases/${record.id}/investigation`}
              >
                Continue to AI Investigation
              </a>
            </p>
          )}
        </>
      )}
    </div>
  );
}

function Sources({ context }: { context: Evidence<CaseContext> }) {
  return (
    <section className="panel">
      <h3>Evidence Source Details</h3>
      {context.sources.length ? (
        context.sources.map((s) => (
          <details key={s.source_version_id}>
            <summary>
              Source v{s.version} · {label(s.coverage)}
            </summary>
            <dl className="provenance-list">
              <dt>Source identity</dt>
              <dd className="mono">{s.source_id}</dd>
              <dt>Version identity</dt>
              <dd className="mono">{s.source_version_id}</dd>
              <dt>SHA-256</dt>
              <dd className="mono">{s.sha256}</dd>
              <dt>Declared coverage window</dt>
              <dd>
                {utc(s.window.start)} – {utc(s.window.end)}
              </dd>
              <dt>Membership complete</dt>
              <dd>{s.membership_complete ? 'Yes' : 'No'}</dd>
              <dt>Model-input reconciliation</dt>
              <dd>{label(s.case_input_reconciliation)}</dd>
            </dl>
          </details>
        ))
      ) : (
        <p>No source versions available.</p>
      )}
    </section>
  );
}

function CustomerAccounts({
  id,
  api,
  context,
  invalidate,
}: {
  id: string;
  api: InvestigationFactory;
  context: Evidence<CaseContext>;
  invalidate: (e: unknown) => void;
}) {
  const [customers, setCustomers] = useState<CursorPage<Customer> | null>(null);
  const [related, setRelated] = useState<CursorPage<Related> | null>(null);
  const [customerCursor, setCustomerCursor] = useState<string>();
  const [relatedCursor, setRelatedCursor] = useState<string>();
  const [showAllRecords, setShowAllRecords] = useState(false);
  useEffect(() => {
    const c = new AbortController();
    async function load() {
      setCustomers(null);
      setRelated(null);
      await Promise.all([
        api(c.signal).customers(
          id,
          context.data.snapshot_token,
          customerCursor,
        ),
        api(c.signal).related(id, context.data.snapshot_token, relatedCursor),
      ])
        .then(([a, b]) => {
          if (!c.signal.aborted) {
            setCustomers(a.data);
            setRelated(b.data);
          }
        })
        .catch((e) => {
          if (!c.signal.aborted) invalidate(e);
        });
    }
    void load();
    return () => c.abort();
  }, [id, api, context, customerCursor, relatedCursor, invalidate]);
  return (
    <div className="evidence-columns evidence-customer-context">
      <section className="panel">
        <h3>Customer Profile</h3>
        {customers?.items.some(
          (customer) => customer.contradictory_observations,
        ) && (
          <p className="notice">
            Conflicting customer evidence is present. Review all source
            observations before deciding.
          </p>
        )}
        {!customers ? (
          <p role="status">Loading customer evidence…</p>
        ) : !customers.items.length ? (
          <p>No customer observations available.</p>
        ) : (
          (showAllRecords ? customers.items : customers.items.slice(0, 1)).map(
            (c) => (
              <article
                className="evidence-record"
                key={c.reference.record_version_id}
              >
                <h4>{c.alias}</h4>
                <dl>
                  <dt>Declared annual income</dt>
                  <dd>
                    {c.annual_income === null
                      ? 'Not recorded (missing, not zero)'
                      : money(c.annual_income, c.currency)}
                  </dd>
                  <dt>Declared KYC score</dt>
                  <dd>{c.declared_kyc_score}</dd>
                  <dt>Observed</dt>
                  <dd>
                    {utc(c.observed_at)} · {c.age_days_at_source_as_of} days
                    before source as-of
                  </dd>
                  <dt>Expected activity</dt>
                  <dd>{label(c.expected_activity_status)}</dd>
                </dl>
                <details>
                  <summary>Source details</summary>
                  <dl>
                    <dt>Evidence reference</dt>
                    <dd className="mono">{c.reference.record_version_id}</dd>
                    <dt>Source version</dt>
                    <dd>{c.reference.version}</dd>
                  </dl>
                </details>
                {c.contradictory_observations && (
                  <p className="notice">
                    Conflicting customer observations — review source records.
                  </p>
                )}
              </article>
            ),
          )
        )}
        {customers &&
          related &&
          (customers.items.length > 1 || related.items.length > 2) && (
            <button
              aria-expanded={showAllRecords}
              onClick={() => setShowAllRecords((value) => !value)}
            >
              {showAllRecords
                ? 'Show context preview'
                : 'View all customer and account records'}
            </button>
          )}
        {customers?.next_cursor && (
          <button onClick={() => setCustomerCursor(customers.next_cursor!)}>
            Next customer observations
          </button>
        )}
        {customerCursor && (
          <button onClick={() => setCustomerCursor(undefined)}>
            First customer page
          </button>
        )}
      </section>
      <section className="panel">
        <h3>Accounts & Relationships</h3>
        {!related ? (
          <p role="status">Loading account evidence…</p>
        ) : !related.items.length ? (
          <p>No linked account records available.</p>
        ) : (
          (showAllRecords ? related.items : related.items.slice(0, 2)).map(
            (r) => (
              <article
                className="evidence-record"
                key={r.reference.record_version_id}
              >
                <h4>{r.alias ?? label(r.relation ?? r.kind)}</h4>
                <p>{r.currency ?? 'Currency not recorded'}</p>
                <p>
                  {r.relation ? label(r.relation) : 'Relationship not recorded'}
                </p>
                <details>
                  <summary>Source and account references</summary>
                  <dl>
                    <dt>Account handle</dt>
                    <dd className="mono">{r.account_handle}</dd>
                    {r.customer_handle && (
                      <>
                        <dt>Customer handle</dt>
                        <dd className="mono">{r.customer_handle}</dd>
                      </>
                    )}
                    <dt>Relationship</dt>
                    <dd>
                      {r.relation
                        ? label(r.relation)
                        : 'Not recorded on this account observation'}
                    </dd>
                    <dt>Evidence reference</dt>
                    <dd className="mono">{r.reference.record_version_id}</dd>
                  </dl>
                </details>
              </article>
            ),
          )
        )}
        {related?.next_cursor && (
          <button onClick={() => setRelatedCursor(related.next_cursor!)}>
            Next account observations
          </button>
        )}
        {relatedCursor && (
          <button onClick={() => setRelatedCursor(undefined)}>
            First account page
          </button>
        )}
      </section>
    </div>
  );
}

function QueryForm({
  context,
  submit,
  busy,
}: {
  context: Evidence<CaseContext>;
  submit: (window: Window, currency: Currency) => void;
  busy: boolean;
}) {
  const initial = context.sources[0]?.window;
  const [start, setStart] = useState(
    initial ? new Date(initial.start).toISOString().slice(0, -1) : '',
  );
  const [end, setEnd] = useState(
    initial ? new Date(initial.end).toISOString().slice(0, -1) : '',
  );
  const [currency, setCurrency] = useState<Currency>('USD');
  const [error, setError] = useState('');
  return (
    <form
      className="panel investigation-query"
      onSubmit={(e) => {
        e.preventDefault();
        const from = new Date(start + 'Z'),
          to = new Date(end + 'Z');
        const span = to.getTime() - from.getTime();
        if (!Number.isFinite(span) || span <= 0 || span > 366 * 86400000) {
          setError('Choose a valid UTC window between 0 and 366 days.');
          return;
        }
        setError('');
        submit(
          {
            start: from.toISOString(),
            end: to.toISOString(),
          },
          currency,
        );
      }}
    >
      <div>
        <label htmlFor="evidence-start">Window start (UTC)</label>
        <input
          id="evidence-start"
          type="datetime-local"
          step="0.001"
          required
          value={start}
          onChange={(e) => setStart(e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="evidence-end">Window end, exclusive (UTC)</label>
        <input
          id="evidence-end"
          type="datetime-local"
          step="0.001"
          required
          value={end}
          onChange={(e) => setEnd(e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="evidence-currency">Currency</label>
        <select
          id="evidence-currency"
          value={currency}
          onChange={(e) => setCurrency(e.target.value as Currency)}
        >
          {['USD', 'CAD', 'EUR', 'GBP'].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </div>
      <button disabled={busy} className="primary">
        {busy ? 'Loading…' : 'Apply evidence window'}
      </button>
      <p className="hint">
        Explicit UTC window and one currency. No FX conversion or inferred
        settlement.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

function ActivityWorkspace({
  id,
  api,
  context,
  invalidate,
}: {
  id: string;
  api: InvestigationFactory;
  context: Evidence<CaseContext>;
  invalidate: (e: unknown) => void;
}) {
  const [query, setQuery] = useState<{
    window: Window;
    currency: Currency;
  } | null>(() =>
    context.sources[0]
      ? { window: context.sources[0].window, currency: 'USD' }
      : null,
  );
  const [page, setPage] = useState<Evidence<CursorPage<Transaction>> | null>(
    null,
  );
  const [activity, setActivity] = useState<Evidence<Activity>[]>([]);
  const [cursor, setCursor] = useState<string>();
  const [showAllTransactions, setShowAllTransactions] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!query) return;
    const c = new AbortController();
    async function load() {
      setBusy(true);
      setPage(null);
      setActivity([]);
      const input = { snapshot: context.data.snapshot_token, ...query };
      // Evidence reads serialize on the actor/case in PostgreSQL. Bound this
      // view to one active read; an aborted StrictMode mount must not fan out.
      try {
        const tx = await api(c.signal).transactions(id, {
          ...input,
          limit: 25,
          ...(cursor ? { cursor } : {}),
        });
        const facts: Evidence<Activity>[] = [];
        for (const calculation of [
          'incoming_outgoing',
          'velocity',
          'concentration',
        ]) {
          if (c.signal.aborted) return;
          facts.push(
            await api(c.signal).activity(id, { ...input, calculation }),
          );
        }
        if (!c.signal.aborted) {
          setPage(tx);
          setActivity(facts);
          setBusy(false);
        }
      } catch (e) {
        if (!c.signal.aborted) {
          setBusy(false);
          invalidate(e);
        }
      }
    }
    void load();
    return () => c.abort();
  }, [query, cursor, id, api, context, invalidate]);
  return (
    <>
      <details className="panel disclosure">
        <summary>
          Time period & currency{query ? ` · ${query.currency}` : ''}
        </summary>
        {query && (
          <p className="query-period">
            {utc(query.window.start)} to {utc(query.window.end)}
          </p>
        )}
        <QueryForm
          context={context}
          busy={busy}
          submit={(window, currency) => {
            setCursor(undefined);
            setQuery({ window, currency });
          }}
        />
      </details>
      {!query && (
        <p className="notice">
          Select an explicit investigation window; none is inferred for missing
          source evidence.
        </p>
      )}
      {activity.length > 0 && (
        <>
          <Facts value={activity[0].data} />
          <Cover value={activity[0]} />
          <details className="panel disclosure financial-advanced">
            <summary>Advanced activity calculations</summary>
            <section className="panel">
              <h3>Transaction frequency · daily observations</h3>
              <div className="velocity-grid">
                {activity[1].data.buckets
                  .filter((b) => b.observed_count > 0)
                  .map((b) => (
                    <div key={b.window.start}>
                      <span>{b.window.start.slice(0, 10)}</span>
                      <b>{b.observed_count}</b>
                      <span>
                        {money(b.observed_total, activity[1].data.currency)}
                      </span>
                    </div>
                  ))}
              </div>
              {!activity[1].data.buckets.some((b) => b.observed_count > 0) && (
                <p>
                  No observed events in the selected buckets; review coverage
                  before inferring inactivity.
                </p>
              )}
            </section>
            <section className="panel">
              <h3>Counterparty concentration</h3>
              {activity[2].data.concentration.map((p) => (
                <div className="concentration-row" key={p.counterparty_handle}>
                  <span className="mono">{p.counterparty_handle}</span>
                  <meter
                    min={0}
                    max={1}
                    value={Number(p.share_of_observed_amount ?? 0)}
                    aria-label={`Observed share for ${p.counterparty_handle}`}
                  />
                  <span>
                    {money(p.observed_total, query!.currency)} ·{' '}
                    {p.observed_count} observations
                  </span>
                </div>
              ))}
            </section>
          </details>
        </>
      )}
      <section className="panel">
        <h3>Transaction observations</h3>
        {busy ? (
          <p role="status">Loading transactions and calculations…</p>
        ) : !page ? (
          <p>No transaction query performed.</p>
        ) : (
          <>
            <p className="muted">
              {page.data.total} matching observations · amounts shown exactly as
              returned by the server.
            </p>
            <div
              className="table-wrap"
              role="region"
              aria-label="Transaction records"
              tabIndex={0}
            >
              <table>
                <caption className="sr-only">
                  Authorized transaction observations
                </caption>
                <thead>
                  <tr>
                    <th>Time (UTC)</th>
                    <th>Direction / event</th>
                    <th>Amount</th>
                    <th>Supporting evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {(showAllTransactions
                    ? page.data.items
                    : page.data.items.slice(0, 5)
                  ).map((t) => (
                    <tr key={t.reference.record_version_id}>
                      <td>
                        {t.event_at
                          ? utc(t.event_at)
                          : `Unresolved time: ${t.original_time}`}
                      </td>
                      <td>
                        {label(t.direction)} · {label(t.event_kind)}
                        {t.reverses_handle && (
                          <small>Reverses {t.reverses_handle}</small>
                        )}
                      </td>
                      <td>{money(t.amount, t.currency)}</td>
                      <td>
                        <details>
                          <summary>Source & counterparty</summary>
                          <p className="mono">
                            {t.counterparty_handle ??
                              'Counterparty unavailable'}
                          </p>
                          <p className="mono">
                            {t.reference.record_version_id}
                          </p>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {page.data.items.length > 5 && (
              <button
                aria-expanded={showAllTransactions}
                onClick={() => setShowAllTransactions((value) => !value)}
              >
                {showAllTransactions
                  ? 'Show transaction preview'
                  : 'View full transaction page'}
              </button>
            )}
            {!page.data.items.length && (
              <p>
                No matching observations; this is not proof of zero activity.
              </p>
            )}
            <div className="pagination">
              {cursor && (
                <button onClick={() => setCursor(undefined)}>
                  First transaction page
                </button>
              )}
              <button
                disabled={!page.data.next_cursor}
                onClick={() => setCursor(page.data.next_cursor!)}
              >
                Next transaction page
              </button>
            </div>
            <Cover value={page} />
          </>
        )}
      </section>
    </>
  );
}

function Facts({ value }: { value: Activity }) {
  return (
    <section className="panel">
      <h3>
        Server-verified {label(value.calculation)} · {value.currency}
      </h3>
      <div className="financial-facts">
        <div>
          <small>Observed count</small>
          <b>{value.observed_count}</b>
        </div>
        <div>
          <small>Incoming</small>
          <b>{money(value.incoming_total, value.currency)}</b>
        </div>
        <div>
          <small>Outgoing</small>
          <b>{money(value.outgoing_total, value.currency)}</b>
        </div>
        <div>
          <small>Gross observed total</small>
          <b>{money(value.observed_total, value.currency)}</b>
        </div>
      </div>
      <p className="hint">
        {label(value.status)} · {label(value.treatment)}. Reversals observed:{' '}
        {value.reversal_observations}; verified pairs excluded:{' '}
        {value.verified_reversal_pairs_excluded}; unmatched:{' '}
        {value.unmatched_reversals}. Gross observations are not settled cash
        flow.
      </p>
      {value.calculation === 'concentration' &&
        value.concentration.length > 0 && (
          <details>
            <summary>Observed counterparty concentration</summary>
            <ul>
              {value.concentration.map((p) => (
                <li key={p.counterparty_handle}>
                  <span className="mono">{p.counterparty_handle}</span> ·{' '}
                  {money(p.observed_total, value.currency)} · {p.observed_count}{' '}
                  observations · observed share{' '}
                  {p.share_of_observed_amount ?? 'Not available'}
                </li>
              ))}
            </ul>
          </details>
        )}
    </section>
  );
}

function PacketWorkspace({
  id,
  api,
  context,
  invalidate,
  omissionReason,
  draftFocus = false,
  auditPrefix,
}: {
  id: string;
  api: InvestigationFactory;
  context: Evidence<CaseContext>;
  invalidate: (e: unknown) => void;
  omissionReason: 'not_selected' | 'unavailable';
  draftFocus?: boolean;
  /** Version controls shown first inside Audit details on the case-file layout. */
  auditPrefix?: ReactNode;
}) {
  const receipts = useContext(InvestigationReceipts);
  const [query, setQuery] = useState<{
    window: Window;
    currency: Currency;
  } | null>(() =>
    context.sources[0]
      ? { window: context.sources[0].window, currency: 'USD' }
      : null,
  );
  const [history, setHistory] = useState<Page<PacketHistory> | null>(null);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [run, setRun] = useState<string>();
  const [detail, setDetail] = useState<PacketDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [paused, setPaused] = useState(false);
  const [autoDraftRun, setAutoDraftRun] = useState<string>();
  const [startedDraft, setStartedDraft] = useState<string>();
  const submission = useRef<AbortController | null>(null);
  const lock = useRef(false);
  useEffect(() => {
    const c = new AbortController();
    async function load() {
      setHistory(null);
      await api(c.signal)
        .history(id, offset)
        .then((p) => {
          if (!c.signal.aborted) setHistory(p);
        })
        .catch((e) => {
          if (!c.signal.aborted) invalidate(e);
        });
    }
    void load();
    return () => c.abort();
  }, [api, id, offset, revision, detail?.status, invalidate]);
  useEffect(() => () => submission.current?.abort(), []);
  useEffect(() => {
    if (!run) return;
    const c = new AbortController();
    let timer: number | undefined;
    let polls = 0;
    async function start() {
      setDetail(null);
      setPaused(false);
      await poll();
    }
    async function poll() {
      if (c.signal.aborted) return;
      try {
        const value = await api(c.signal).detail(id, run!);
        if (c.signal.aborted) return;
        setDetail(value);
        setError('');
        if (['pending', 'running'].includes(value.status)) {
          if (++polls >= 40) {
            setPaused(true);
            return;
          }
          timer = window.setTimeout(() => {
            void poll();
          }, 2000);
        }
      } catch (e) {
        if (c.signal.aborted) return;
        setDetail(null);
        if (
          e instanceof ApiError &&
          [401, 403, 404, 409, 422, 503].includes(e.status)
        ) {
          invalidate(e);
          return;
        }
        setError(failure(e));
        const delay = pollDelay(e instanceof ApiError ? e.retryAfter : 2);
        if (++polls < 40 && delay !== null)
          timer = window.setTimeout(() => {
            void poll();
          }, delay);
        else setPaused(true);
      }
    }
    void start();
    return () => {
      c.abort();
      window.clearTimeout(timer);
    };
  }, [run, api, id, revision, invalidate]);
  async function requestPacket(startDraft = false, packetOnly = false) {
    if (!query || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError('');
    setDetail(null);
    setAutoDraftRun(undefined);
    setStartedDraft(undefined);
    const c = new AbortController();
    submission.current = c;
    const body: PacketRequest = {
      expected_case_version: context.snapshot.case_version,
      expected_evidence_revision: context.snapshot.evidence_revision,
      expected_access_revision: context.snapshot.access_revision,
      ...(context.data.selected_assessment_id
        ? { assessment_id: context.data.selected_assessment_id }
        : { without_assessment_reason: omissionReason }),
      window: query.window,
      currencies: [query.currency],
    };
    const intent =
      id + '|' + (startDraft ? 'draft|' : 'packet|') + JSON.stringify(body);
    try {
      if (!receipts) throw new Error();
      let receipt = receipts.get(intent);
      if (!receipt) {
        if (receipts.size >= 100) throw new Error();
        receipt = { key: crypto.randomUUID(), body };
        receipts.set(intent, receipt);
      }
      const client = api(c.signal);
      if (startDraft && client.draftStart && !packetOnly) {
        const result = await client.draftStart(id, receipt.body, receipt.key);
        if (c.signal.aborted) return;
        receipt.run_id = result.investigation_run_id;
        setRun(result.investigation_run_id);
        setStartedDraft(result.draft_run_id);
        setRevision((n) => n + 1);
        return;
      }
      const result = await client.submit(id, receipt.body, receipt.key);
      if (c.signal.aborted) return;
      receipt.run_id = result.run_id;
      setRun(result.run_id);
      if (startDraft) setAutoDraftRun(result.run_id);
      setRevision((n) => n + 1);
    } catch (e) {
      if (!c.signal.aborted) {
        if (
          e instanceof ApiError &&
          [401, 403, 404, 409, 422, 503].includes(e.status)
        )
          invalidate(e);
        else setError(failure(e));
      }
    } finally {
      lock.current = false;
      if (!c.signal.aborted) setBusy(false);
    }
  }
  const packet = detail?.packet;
  const verified =
    packet &&
    ['succeeded', 'abstained'].includes(detail!.status) &&
    packet.mode === 'deterministic_evidence_only' &&
    packet.provider_used === false &&
    detail!.verification?.status === 'source_numeric_reference_checks_passed';
  // On the AI Investigation step these evidence controls live inside Audit details.
  const extras = (
    <>
      {auditPrefix && (
        <>
          <h5>Assessment and evidence version</h5>
          {auditPrefix}
          <h5>Coverage</h5>
          <p>
            {label(context.coverage.status)}
            {context.coverage.limitations.length
              ? ` · ${context.coverage.limitations.map((l) => label(l)).join(', ')}`
              : ''}
          </p>
        </>
      )}
      <details className="panel disclosure">
        <summary>
          Time period & currency{query ? ` · ${query.currency}` : ''}
        </summary>
        {query && (
          <p className="query-period">
            {utc(query.window.start)} to {utc(query.window.end)}
          </p>
        )}
        <QueryForm
          context={context}
          busy={busy}
          submit={(window, currency) => setQuery({ window, currency })}
        />
      </details>
      {verified && (
        <details
          className="panel verified-packet disclosure"
          open={!draftFocus}
        >
          <summary>Verified evidence summary</summary>
          <p className="muted">Evidence and financial checks passed</p>
          <h3>Investigation Summary · {label(packet.outcome)}</h3>
          <p>
            A structured review of supporting evidence. This is not an
            AI-generated conclusion or a determination of criminal conduct.
          </p>
          <details className="technical-details">
            <summary>Summary verification details</summary>
            <div className="mono">
              Run {detail!.run_id}
              <br />
              Manifest {packet.manifest_sha256}
              <br />
              Packet SHA-256 {detail!.verification!.packet_sha256}
            </div>
          </details>
          {packet.facts.map((f) => (
            <div className="packet-fact" key={f.reference_id}>
              <Facts value={f.result} />
              <p className="hint">
                Calculation reference{' '}
                <span className="mono">{f.reference_id}</span> ·{' '}
                {f.input_record_ids.length} source records
              </p>
              {codes(f.coverage.limitations)}
            </div>
          ))}
          <div className="evidence-columns">
            <div>
              <h4>Questions for review</h4>
              {codes(packet.questions)}
              <h4>Missing evidence</h4>
              {codes(packet.missing_evidence)}
            </div>
            <div>
              <h4>Conflicting observations</h4>
              {codes(packet.conflicts)}
              <h4>Limitations & unresolved questions</h4>
              {codes([...packet.limitations, ...packet.abstentions])}
            </div>
          </div>
          <details>
            <summary>Supporting records ({packet.evidence.length})</summary>
            {packet.evidence.map((r) => (
              <p className="mono evidence-reference" key={r.record_version_id}>
                {r.kind} v{r.version} · {r.record_version_id}
                <br />
                Source version {r.source_version_id}
                <br />
                SHA-256 {r.sha256}
              </p>
            ))}
          </details>
          <p className="notice">
            Regulatory guidance has not been applied. Supporting records are not
            legal conclusions. An analyst must review these observations.
          </p>
        </details>
      )}
      <details className="panel disclosure">
        <summary>
          Previous evidence summaries · {history?.total ?? 0} requests
        </summary>
        <p className="hint">
          Your requests for this case. Evidence and access are checked again
          whenever you open a summary.
        </p>
        {!history ? (
          <p role="status">Loading investigation history…</p>
        ) : !history.items.length ? (
          <p>No investigation summaries in your history.</p>
        ) : (
          <>
            <div
              className="table-wrap"
              role="region"
              aria-label="Investigation request history"
              tabIndex={0}
            >
              <table>
                <caption className="sr-only">Investigation history</caption>
                <thead>
                  <tr>
                    <th>Requested (UTC)</th>
                    <th>Stored state</th>
                    <th>Bound revisions</th>
                    <th>View</th>
                  </tr>
                </thead>
                <tbody>
                  {history.items.map((h) => (
                    <tr key={h.run_id}>
                      <td>
                        {utc(h.created_at)}
                        <small className="mono">{h.run_id}</small>
                      </td>
                      <td>{label(h.status)}</td>
                      <td>
                        Case {h.case_version} / evidence {h.evidence_revision} /
                        access {h.access_revision}
                      </td>
                      <td>
                        <button
                          onClick={() => {
                            setDetail(null);
                            setRun(h.run_id);
                            setRevision((n) => n + 1);
                          }}
                        >
                          Open summary
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <button
                disabled={offset === 0}
                onClick={() => setOffset((n) => Math.max(0, n - 10))}
              >
                Previous summary page
              </button>
              <span>{history.total} stored requests</span>
              <button
                disabled={offset + 10 >= history.total || offset >= 1000}
                onClick={() => setOffset((n) => n + 10)}
              >
                Next summary page
              </button>
            </div>
          </>
        )}
      </details>
    </>
  );
  return (
    <>
      {!draftFocus && (
        <>
          <section className="panel">
            <div className="section-heading">
              <h3>Investigation Summary</h3>
              <button
                className="primary"
                disabled={!query || busy}
                onClick={() => {
                  void requestPacket(draftFocus);
                }}
              >
                {busy
                  ? 'Requesting…'
                  : draftFocus
                    ? 'Generate investigation'
                    : TERMS.requestSummary}
              </button>
            </div>
            <p className="muted">
              {draftFocus
                ? 'Prepare verified evidence and request findings using the authorized provider. Provider status is shown with the result.'
                : 'Generate a structured summary from the selected records and assessment. Repeating the same request safely retrieves the same investigation.'}
            </p>
            {query && (
              <p className="hint">
                Summary currency: {query.currency}. Other currencies remain
                excluded and will be reported as a limitation.
              </p>
            )}
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            {detail && (
              <p role="status">
                <b>Processing status: </b>
                <StatusBadge value={detail.status} /> · Attempt{' '}
                {detail.attempts}
                {detail.error_code && ` · ${label(detail.error_code)}`}
              </p>
            )}
            {run && !detail && !error && (
              <p role="status">Checking summary progress…</p>
            )}
            {paused && (
              <p className="notice">
                Automatic status checks paused after the bounded polling period.
                The request remains available in your history.
              </p>
            )}
            {run && (
              <button onClick={() => setRevision((n) => n + 1)}>
                Check progress
              </button>
            )}
            {detail?.status === 'failed' && (
              <p className="notice">
                Processing failed. Analyst review is required; no case was
                closed. Repeating the same request does not force a
                reassessment.
              </p>
            )}
            {detail?.status === 'invalidated' && (
              <p className="notice">
                This summary is no longer current or its access changed. Its
                evidence has been withheld. Refresh the case context.
              </p>
            )}
            {!run && (
              <p>
                No summary selected. Generate one or open an earlier request.
              </p>
            )}
          </section>
        </>
      )}
      {draftFocus && (
        <DraftWorkspace
          key={id + context.snapshot.sha256}
          id={id}
          api={api}
          context={context}
          packet={detail}
          autoStartRunId={autoDraftRun}
          initialDraftRunId={startedDraft}
          orchestrate={() => void requestPacket(true)}
          prepareEvidence={() => void requestPacket(true, true)}
          orchestrating={busy}
          orchestrationStatus={detail?.status}
          orchestrationError={error}
          invalidate={invalidate}
          auditExtras={extras}
        />
      )}
      {!draftFocus && extras}
    </>
  );
}

/* ---------- Step 2 · Review Evidence (case-file layout) ---------- */

const KYC_HIGH_AT = 3;

export const KYC_SCALE = `0–6 scale, High at ${KYC_HIGH_AT}+`;

/** "KYC 1 (0–6 scale, High at 3+)" for detail lists; the card shows the number with a tooltip. */
export function kycText(score: number) {
  return `KYC ${score} (${KYC_SCALE})`;
}

/** Plain relationship wording for account tags: "declared_holder" → "Holder". */
export function relationTag(relation: string) {
  const text = label(relation).replace(/^Declared\s+/i, '');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Fields the customer record does not carry, as one "Missing" line. */
export function customerMissing(c: Customer): string[] {
  const out: string[] = [];
  if (c.annual_income === null) out.push('Annual income');
  if (c.expected_activity_status === 'not_recorded')
    out.push('Expected activity');
  return out;
}

export function EvidenceStep({
  id,
  api,
  context,
  invalidate,
  versionControls,
}: {
  id: string;
  api: InvestigationFactory;
  context: Evidence<CaseContext>;
  invalidate: (e: unknown) => void;
  versionControls: ReactNode;
}) {
  const [customers, setCustomers] = useState<CursorPage<Customer> | null>(null);
  const [related, setRelated] = useState<CursorPage<Related> | null>(null);
  const [query, setQuery] = useState<{
    window: Window;
    currency: Currency;
  } | null>(() =>
    context.sources[0]
      ? { window: context.sources[0].window, currency: 'USD' }
      : null,
  );
  const [page, setPage] = useState<Evidence<CursorPage<Transaction>> | null>(
    null,
  );
  const [activity, setActivity] = useState<Evidence<Activity>[]>([]);
  const [cursor, setCursor] = useState<string>();
  const [showAll, setShowAll] = useState(false);
  const [changing, setChanging] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const c = new AbortController();
    Promise.all([
      api(c.signal).customers(id, context.data.snapshot_token),
      api(c.signal).related(id, context.data.snapshot_token),
    ])
      .then(([a, b]) => {
        if (!c.signal.aborted) {
          setCustomers(a.data);
          setRelated(b.data);
        }
      })
      .catch((e) => {
        if (!c.signal.aborted) invalidate(e);
      });
    return () => c.abort();
  }, [id, api, context, invalidate]);
  useEffect(() => {
    if (!query) return;
    const c = new AbortController();
    async function load() {
      setBusy(true);
      setPage(null);
      setActivity([]);
      const input = { snapshot: context.data.snapshot_token, ...query };
      // One active evidence read at a time (reads serialize per actor and case).
      try {
        const tx = await api(c.signal).transactions(id, {
          ...input,
          limit: 25,
          ...(cursor ? { cursor } : {}),
        });
        const facts: Evidence<Activity>[] = [];
        for (const calculation of [
          'incoming_outgoing',
          'velocity',
          'concentration',
        ]) {
          if (c.signal.aborted) return;
          facts.push(
            await api(c.signal).activity(id, { ...input, calculation }),
          );
        }
        if (!c.signal.aborted) {
          setPage(tx);
          setActivity(facts);
          setBusy(false);
        }
      } catch (e) {
        if (!c.signal.aborted) {
          setBusy(false);
          invalidate(e);
        }
      }
    }
    void load();
    return () => c.abort();
  }, [query, cursor, id, api, context, invalidate]);

  const customer = customers?.items[0];
  const totals = activity[0]?.data;
  const coverageLimitations = [
    ...context.coverage.limitations,
    ...(activity[0]?.coverage.limitations ?? []),
  ];
  const complete =
    context.coverage.status === 'complete_declared_window' &&
    (!activity[0] ||
      activity[0].coverage.status === 'complete_declared_window');
  const rows = page
    ? showAll
      ? page.data.items
      : page.data.items.slice(0, 10)
    : [];
  // Accounts are listed once; relationship records become a tag on the matching account.
  const accounts = related?.items.filter((r) => !r.relation) ?? [];
  const relations = related?.items.filter((r) => r.relation) ?? [];
  const tagsFor = (handle: string) =>
    relations
      .filter((r) => r.account_handle === handle)
      .map((r) => relationTag(r.relation!));
  const unmatched = relations.filter(
    (r) => !accounts.some((a) => a.account_handle === r.account_handle),
  );
  const relationRecorded = accounts.some(
    (a) => tagsFor(a.account_handle).length > 0,
  );
  return (
    <div className="evidence-step">
      <div className="evidence-top">
        <section
          className="panel customer-card"
          aria-labelledby="customer-title"
        >
          <div className="card-head">
            <h2 id="customer-title">
              {customer ? customer.alias : 'Customer'}
            </h2>
            <CoverageBadge
              complete={complete}
              limitations={[...new Set(coverageLimitations)].map((l) =>
                label(l),
              )}
            />
          </div>
          {!customers ? (
            <p role="status">Loading customer evidence…</p>
          ) : !customer ? (
            <p>No customer observations available.</p>
          ) : (
            <>
              <dl className="fact-row">
                <div>
                  <dt>Annual income</dt>
                  <dd>
                    {customer.annual_income === null
                      ? 'Not recorded'
                      : formatMoney(customer.annual_income, customer.currency, {
                          whole: true,
                        })}
                  </dd>
                </div>
                <div>
                  <dt>Customer risk rating</dt>
                  <dd>
                    <span className="has-tip" title={KYC_SCALE}>
                      {customer.declared_kyc_score}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>Profile updated</dt>
                  <dd title={utcText(customer.observed_at)}>
                    {formatDate(customer.observed_at)}
                  </dd>
                </div>
              </dl>
              <MissingLine items={customerMissing(customer)} />
              {customers.items.some((x) => x.contradictory_observations) && (
                <p className="notice">
                  Conflicting customer observations — review all records before
                  deciding.
                </p>
              )}
            </>
          )}
        </section>

        <section
          className="panel accounts-card"
          aria-labelledby="accounts-title"
        >
          <h2 id="accounts-title">
            Accounts ({related ? accounts.length : '…'})
          </h2>
          {!related ? (
            <p role="status">Loading account evidence…</p>
          ) : !accounts.length ? (
            <p>No linked account records available.</p>
          ) : (
            <>
              <ul className="account-rows">
                {accounts.map((r) => (
                  <li key={r.reference.record_version_id}>
                    <span>{r.alias ?? shortId(r.account_handle)}</span>
                    {r.currency && <span className="muted">{r.currency}</span>}
                    {tagsFor(r.account_handle).map((tag) => (
                      <span key={tag} className="tag">
                        {tag}
                      </span>
                    ))}
                  </li>
                ))}
              </ul>
              {!relationRecorded && (
                <p className="muted">
                  Relationship not recorded for any account
                </p>
              )}
            </>
          )}
        </section>
      </div>

      <section className="panel activity-card" aria-labelledby="activity-title">
        <div className="card-head">
          <h2 id="activity-title">
            Activity
            {query && (
              <>
                {' '}
                · {periodLabel(query.window.start, query.window.end)} ·{' '}
                {query.currency}
              </>
            )}
          </h2>
          <button
            className="small"
            aria-expanded={changing}
            onClick={() => setChanging((v) => !v)}
          >
            Change period
          </button>
        </div>
        {changing && (
          <QueryForm
            context={context}
            busy={busy}
            submit={(window, currency) => {
              setCursor(undefined);
              setShowAll(false);
              setQuery({ window, currency });
              setChanging(false);
            }}
          />
        )}
        {!query ? (
          <p className="notice">
            Select an explicit period; none is inferred for missing source
            evidence.
          </p>
        ) : busy || !totals ? (
          <p role="status">Loading activity…</p>
        ) : (
          <dl className="fact-row activity-totals">
            <div>
              <dt>Transactions</dt>
              <dd>{totals.observed_count}</dd>
            </div>
            <div>
              <dt>In</dt>
              <dd>{formatMoney(totals.incoming_total, totals.currency)}</dd>
            </div>
            <div>
              <dt>Out</dt>
              <dd>{formatMoney(totals.outgoing_total, totals.currency)}</dd>
            </div>
            <div>
              <dt>Net</dt>
              <dd>
                {totals.incoming_total !== null &&
                totals.outgoing_total !== null
                  ? formatMoney(
                      subtractDecimal(
                        totals.incoming_total,
                        totals.outgoing_total,
                      ),
                      totals.currency,
                      {
                        signed: true,
                      },
                    )
                  : 'Not available'}
              </dd>
            </div>
            <div>
              <dt>Total</dt>
              <dd>{formatMoney(totals.observed_total, totals.currency)}</dd>
            </div>
          </dl>
        )}
        {page && (
          <div className="transactions-block" aria-label="Transactions">
            {page.data.items.length ? (
              <table className="compact-table transactions-table">
                <caption className="sr-only">
                  Transactions in the selected period
                </caption>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Direction / type</th>
                    <th className="num">Amount</th>
                    <th>Counterparty</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((t) => (
                    <tr key={t.reference.record_version_id}>
                      <td
                        title={
                          t.event_at ? utcText(t.event_at) : t.original_time
                        }
                      >
                        {t.event_at
                          ? formatDate(t.event_at)
                          : 'Time unresolved'}
                      </td>
                      <td>
                        {directionShort(t.direction, t.event_kind)}
                        {t.reverses_handle && ' · reversal'}
                      </td>
                      <td className="num">
                        {formatMoney(t.amount, t.currency)}
                      </td>
                      <td title={t.counterparty_handle ?? undefined}>
                        {t.counterparty_handle
                          ? shortId(t.counterparty_handle)
                          : 'Not recorded'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p>
                No matching transactions; this is not proof of zero activity.
              </p>
            )}
            <div className="table-foot">
              {page.data.items.length > 10 && (
                <button
                  className="small"
                  aria-expanded={showAll}
                  onClick={() => setShowAll((v) => !v)}
                >
                  {showAll
                    ? 'Show first 10'
                    : `Show all ${page.data.items.length}`}
                </button>
              )}
              {cursor && (
                <button className="small" onClick={() => setCursor(undefined)}>
                  First page
                </button>
              )}
              {page.data.next_cursor && (
                <button
                  className="small"
                  onClick={() => setCursor(page.data.next_cursor!)}
                >
                  Next page
                </button>
              )}
              <span className="muted">{page.data.total} in period</span>
              <a
                className="button primary"
                href={`#/cases/${id}/investigation`}
              >
                Continue to AI Investigation
              </a>
            </div>
          </div>
        )}
      </section>

      <div className="disclosure-bar">
        {customers && related && (
          <details className="panel disclosure">
            <summary>All customer and account records</summary>
            {customers.items.map((c) => (
              <article
                className="evidence-record"
                key={c.reference.record_version_id}
              >
                <h4>{c.alias}</h4>
                <p>
                  {c.annual_income === null
                    ? 'Annual income not recorded'
                    : `Annual income ${formatMoney(c.annual_income, c.currency, { whole: true })}`}{' '}
                  · {kycText(c.declared_kyc_score)} · Profile updated{' '}
                  {formatDate(c.observed_at)} ({c.age_days_at_source_as_of} days
                  before the source date)
                </p>
              </article>
            ))}
            {related.items.map((r) => (
              <article
                className="evidence-record"
                key={r.reference.record_version_id}
              >
                <h4>{r.alias ?? shortId(r.account_handle)}</h4>
                <p>
                  {r.currency ?? 'Currency not recorded'} ·{' '}
                  {r.relation ? label(r.relation) : 'Relationship not recorded'}
                  {r.opened_at && ` · Opened ${formatDate(r.opened_at)}`}
                </p>
              </article>
            ))}
          </details>
        )}

        <AuditDetails>
          <h5>Source records & revisions</h5>
          <AuditList>
            {context.sources.map((s) => (
              <Fragment key={s.source_version_id}>
                <dt>Source v{s.version}</dt>
                <dd>
                  {label(s.coverage)} · {utcText(s.window.start)} to{' '}
                  {utcText(s.window.end)} (end exclusive) · membership{' '}
                  {s.membership_complete ? 'complete' : 'incomplete'} ·
                  model-input reconciliation{' '}
                  {label(s.case_input_reconciliation)}
                </dd>
                <CopyValue label="Source identity" value={s.source_id} />
                <CopyValue label="Source version" value={s.source_version_id} />
                <CopyValue label="Source SHA-256" value={s.sha256} />
              </Fragment>
            ))}
          </AuditList>
          <h5>Time period & currency</h5>
          <p>
            {query
              ? `${utcText(query.window.start)} to ${utcText(query.window.end)} (end exclusive) · ${query.currency}. One currency per view; no FX conversion or inferred settlement.`
              : 'No period selected.'}
          </p>
          {totals && (
            <p>
              {label(totals.status)} · {label(totals.treatment)}. Reversals
              observed: {totals.reversal_observations}; verified pairs excluded:{' '}
              {totals.verified_reversal_pairs_excluded}; unmatched:{' '}
              {totals.unmatched_reversals}. Gross observations are not settled
              cash flow. Exact totals: in {totals.incoming_total}, out{' '}
              {totals.outgoing_total}, total {totals.observed_total}.
            </p>
          )}
          {activity.length === 3 && (
            <>
              <h5>Advanced activity calculations</h5>
              <ul>
                {activity[1].data.buckets
                  .filter((b) => b.observed_count > 0)
                  .map((b) => (
                    <li key={b.window.start}>
                      {formatDate(b.window.start)} · {b.observed_count} ·{' '}
                      {formatMoney(b.observed_total, activity[1].data.currency)}
                    </li>
                  ))}
              </ul>
              <ul>
                {activity[2].data.concentration.map((p) => (
                  <li key={p.counterparty_handle}>
                    {p.counterparty_handle} ·{' '}
                    {formatMoney(p.observed_total, activity[2].data.currency)} ·{' '}
                    {p.observed_count} transactions · share{' '}
                    {p.share_of_observed_amount === null
                      ? 'not available'
                      : percent1(Number(p.share_of_observed_amount) * 100)}
                  </li>
                ))}
              </ul>
            </>
          )}
          <h5>Assessment and evidence version</h5>
          {versionControls}
          {unmatched.length > 0 && (
            <>
              <h5>Relationships without a listed account</h5>
              <ul>
                {unmatched.map((r) => (
                  <li key={r.reference.record_version_id}>
                    {relationTag(r.relation!)} · account {r.account_handle}
                    {r.customer_handle
                      ? ` · customer ${r.customer_handle}`
                      : ''}
                  </li>
                ))}
              </ul>
            </>
          )}
          <h5>Customer, account and transaction references</h5>
          <AuditList>
            {customers?.items.map((c) => (
              <CopyValue
                key={c.reference.record_version_id}
                label={`Customer ${c.alias} (v${c.reference.version})`}
                value={c.reference.record_version_id}
              />
            ))}
            {related?.items.map((r) => (
              <Fragment key={r.reference.record_version_id}>
                <CopyValue
                  label={`Account ${r.alias ?? r.account_handle}`}
                  value={r.account_handle}
                />
                {r.customer_handle && (
                  <CopyValue
                    label="Customer handle"
                    value={r.customer_handle}
                  />
                )}
                <CopyValue
                  label="Account evidence reference"
                  value={r.reference.record_version_id}
                />
              </Fragment>
            ))}
            {rows.map((t) => (
              <CopyValue
                key={t.reference.record_version_id}
                label={`Transaction ${t.event_at ? formatDate(t.event_at) : t.original_time} ${t.amount}`}
                value={t.reference.record_version_id}
              />
            ))}
          </AuditList>
        </AuditDetails>
      </div>
    </div>
  );
}
