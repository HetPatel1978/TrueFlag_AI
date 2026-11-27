import { RegulatoryGuidance } from './regulatory-guidance';
import { ResearchGuidance } from './research-guidance';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError, label, message, pollDelay, type Page } from './api';
import type { DraftDetail, DraftHistoryItem } from './draft-api';
import type {
  CaseContext,
  Customer,
  Evidence,
  InvestigationFactory,
  PacketDetail,
  Reference,
  Related,
  ResearchStatus,
  Transaction,
} from './investigation-api';
import { ResearchReviewPanel } from './research-review';
import {
  InvestigationResult,
  directionShort,
  money,
  sectionTitle,
} from './investigation-result';
import { decimalMoney } from './terminology';
import { Icon, StatusBadge } from './ui';
import './drafts.css';
import { AuditDetails, AuditList, CopyValue, Timestamp } from './display';
import { formatDate, shortId } from './format';

const critical = (e: unknown) =>
  e instanceof ApiError &&
  e.reason !== 'simulation_unavailable' &&
  [401, 403, 404, 409, 422, 503].includes(e.status);
const time = (v: string | null) =>
  v
    ? new Date(v)
        .toISOString()
        .replace('T', ' ')
        .replace(/\.\d+Z$/, ' UTC')
    : 'Not recorded';
function Codes({ values }: { values: string[] }) {
  return values.length ? (
    <ul className="draft-codes">
      {[...new Set(values)].map((v) => (
        <li key={v}>{label(v)}</li>
      ))}
    </ul>
  ) : (
    <p className="muted">None identified in the supplied evidence.</p>
  );
}

export function DraftWorkspace({
  id,
  api,
  context,
  packet,
  invalidate,
  autoStartRunId,
  initialDraftRunId,
  orchestrate,
  prepareEvidence,
  orchestrating = false,
  orchestrationStatus,
  orchestrationError,
  auditExtras,
}: {
  id: string;
  api: InvestigationFactory;
  context: Evidence<CaseContext>;
  packet: PacketDetail | null;
  invalidate: (e: unknown) => void;
  autoStartRunId?: string;
  initialDraftRunId?: string;
  orchestrate?: () => void;
  // Builds a fresh verified evidence summary only (no AI draft); the page then continues.
  prepareEvidence?: () => void;
  orchestrating?: boolean;
  orchestrationStatus?: string;
  orchestrationError?: string;
  /** Evidence-summary controls and history shown inside Audit details. */
  auditExtras?: ReactNode;
}) {
  const [history, setHistory] = useState<Page<DraftHistoryItem> | null>(null);
  const [offset, setOffset] = useState(0);
  const [chosenRun, setChosenRun] = useState<{
    initial?: string;
    value: string;
  }>();
  const run =
    chosenRun && chosenRun.initial === initialDraftRunId
      ? chosenRun.value
      : initialDraftRunId;
  function setRun(value: string) {
    setChosenRun({ initial: initialDraftRunId, value });
  }
  const [detail, setDetail] = useState<DraftDetail | null>(null);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [historyError, setHistoryError] = useState('');
  const [busy, setBusy] = useState(false);
  const [paused, setPaused] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [selected, setSelected] = useState<Reference | null>(null);
  const [providerChoice, setProviderChoice] = useState<
    'loading' | 'simulation' | 'claude' | 'unavailable'
  >(() => (api().draftCapabilities ? 'loading' : 'simulation'));
  const [groundingAvailable, setGroundingAvailable] = useState(false);
  const [researchStatus, setResearchStatus] = useState<
    ResearchStatus | undefined
  >();
  const [researchRun, setResearchRun] = useState<string | null>(null);
  const [reviewRun, setReviewRun] = useState<string | null>(null);
  const [capabilityRevision, setCapabilityRevision] = useState(0);
  const researchApproved =
    researchStatus === 'approved' && !!researchRun && !!api().researchExecute;
  // In-app exact-request approval: Generate prepares the request for an approver's review.
  const inappReady =
    (researchStatus === 'generate_ready' ||
      researchStatus === 'request_expired') &&
    !!api().researchStart &&
    !!api().researchReview;
  const researchReady = researchApproved || inappReady;
  const [includeGrounding, setIncludeGrounding] = useState(false);
  const [regulatoryQuery, setRegulatoryQuery] = useState('');
  const lock = useRef(false);
  const recordTrigger = useRef<HTMLElement | null>(null);
  const transactionsRef = useRef<HTMLDetailsElement | null>(null);
  const [loadedTransactions, setLoadedTransactions] = useState<Transaction[]>(
    [],
  );
  const submission = useRef<AbortController | null>(null);
  const autoStarted = useRef<string | null>(null);
  const verifiedParent =
    packet?.packet &&
    ['succeeded', 'abstained'].includes(packet.status) &&
    packet.verification?.status === 'source_numeric_reference_checks_passed'
      ? packet
      : null;
  useEffect(
    () => () => {
      submission.current?.abort();
    },
    [],
  );
  useEffect(() => {
    const c = new AbortController();
    const client = api(c.signal);
    const result = client.draftCapabilities
      ? client.draftCapabilities(id)
      : Promise.resolve({
          provider: 'simulation' as const,
          regulatory_grounding_enabled: false,
        });
    void result
      .then((value) => {
        if (!c.signal.aborted) {
          setProviderChoice(value.provider);
          setGroundingAvailable(value.regulatory_grounding_enabled);
          setResearchStatus(
            'research_status' in value ? value.research_status : undefined,
          );
          if ('research_run_id' in value && value.research_run_id) {
            setResearchRun(value.research_run_id);
            if (
              value.research_status === 'awaiting_approval' ||
              (value.research_status === 'request_expired' &&
                'research_run_phase' in value &&
                value.research_run_phase === 'request_expired')
            )
              setReviewRun(value.research_run_id); // review (or its expiry notice) survives refresh
            else if (
              value.research_status === 'approved' ||
              value.research_status === 'approved_queued' ||
              value.research_status === 'running' ||
              value.research_status === 'generate_ready' ||
              value.research_status === 'budget_exhausted'
            )
              // the latest stored result survives refresh
              setChosenRun({
                initial: initialDraftRunId,
                value: value.research_run_id,
              });
          }
        }
      })
      .catch((e) => {
        if (!c.signal.aborted) {
          setProviderChoice('unavailable');
          if (critical(e)) invalidate(e);
        }
      });
    return () => c.abort();
  }, [api, id, invalidate, capabilityRevision, initialDraftRunId]);
  useEffect(() => {
    const c = new AbortController();
    async function load() {
      setHistory(null);
      await api(c.signal)
        .draftHistory(id, offset)
        .then((value) => {
          if (!c.signal.aborted) {
            setHistory(value);
            setUnavailable(false);
            setHistoryError('');
          }
        })
        .catch((e) => {
          if (c.signal.aborted) return;
          if (e instanceof ApiError && e.reason === 'simulation_unavailable') {
            setUnavailable(true);
            setHistoryError(
              'Offline simulation is unavailable in this environment. The verified evidence summary remains available.',
            );
            return;
          }
          if (critical(e)) invalidate(e);
          else setHistoryError(message(e));
        });
    }
    void load();
    return () => c.abort();
  }, [api, id, offset, revision, detail?.status, invalidate]);
  useEffect(() => {
    if (!run) return;
    const c = new AbortController();
    let timer: number | undefined;
    let attempts = 0;
    async function start() {
      setDetail(null);
      setSelected(null);
      setPaused(false);
      setError('');
      await poll();
    }
    async function poll() {
      if (c.signal.aborted) return;
      let delay: number | null = 2000;
      try {
        const value = await api(c.signal).draftDetail(id, run!);
        if (c.signal.aborted) return;
        setDetail(value);
        setError('');
        if (!['pending', 'running'].includes(value.status)) return;
      } catch (e) {
        if (c.signal.aborted) return;
        setDetail(null);
        setSelected(null);
        if (critical(e)) {
          invalidate(e);
          return;
        }
        setError(message(e));
        delay = pollDelay(e instanceof ApiError ? e.retryAfter : 2);
      }
      if (++attempts >= 40 || delay === null) {
        setPaused(true);
        return;
      }
      timer = window.setTimeout(() => {
        void poll();
      }, delay);
    }
    void start();
    return () => {
      c.abort();
      window.clearTimeout(timer);
    };
  }, [api, id, run, revision, invalidate]);
  const terminal = detail && !['pending', 'running'].includes(detail.status);
  const finishedRun = useRef<string | null>(null);
  useEffect(() => {
    if (
      terminal &&
      detail &&
      (researchStatus === 'approved_queued' || researchStatus === 'running') &&
      finishedRun.current !== detail.draft_run_id
    ) {
      finishedRun.current = detail.draft_run_id;
      setCapabilityRevision((v) => v + 1);
    }
  }, [terminal, detail, researchStatus]);
  async function prepareResearch() {
    // Generate / Refresh Request: the server takes a fresh snapshot and prepares the exact
    // request for review (an open, still-valid request is reused). Nothing is sent here.
    if (!verifiedParent?.verification || lock.current || !api().researchStart)
      return;
    lock.current = true;
    setBusy(true);
    setError('');
    const c = new AbortController();
    submission.current = c;
    try {
      const value = await api(c.signal).researchStart!(
        id,
        {
          investigation_run_id: verifiedParent.run_id,
          expected_packet_sha256: verifiedParent.verification.packet_sha256,
        },
        `research-${crypto.randomUUID()}`,
      );
      if (!c.signal.aborted) {
        setReviewRun(value.draft_run_id);
        setCapabilityRevision((v) => v + 1);
      }
    } catch (e) {
      if (!c.signal.aborted) {
        if (e instanceof ApiError && e.status === 401) invalidate(e);
        else setError(message(e));
      }
    } finally {
      lock.current = false;
      if (!c.signal.aborted) setBusy(false);
    }
  }
  async function generate() {
    if (inappReady) return prepareResearch();
    if (
      (!researchReady && !verifiedParent?.verification) ||
      (inappReady && !verifiedParent?.verification) ||
      lock.current ||
      providerChoice === 'loading' ||
      (providerChoice === 'unavailable' && !researchReady)
    )
      return;
    lock.current = true;
    setBusy(true);
    setDetail(null);
    setSelected(null);
    setError('');
    const c = new AbortController();
    submission.current = c;
    try {
      if (researchApproved && researchRun) {
        const value = await api(c.signal).researchExecute!(
          id,
          researchRun,
          `research-execute-${researchRun}`,
        );
        if (!c.signal.aborted) {
          setRun(value.draft_run_id);
          setRevision((v) => v + 1);
        }
        return;
      }
      const parent = verifiedParent!.run_id;
      const key = `${providerChoice === 'claude' ? 'claude' : 'offline'}-${parent}${includeGrounding ? '-regulatory' : ''}`;
      const value = await api(c.signal).draftSubmit(
        id,
        {
          investigation_run_id: parent,
          expected_packet_sha256: verifiedParent!.verification!.packet_sha256,
          ...(providerChoice === 'claude'
            ? { provider: 'claude' as const }
            : {}),
          ...(includeGrounding
            ? { regulatory_query: { query: regulatoryQuery.trim(), limit: 5 } }
            : {}),
        },
        key,
      );
      if (c.signal.aborted) return;
      setRun(value.draft_run_id);
      setRevision((v) => v + 1);
    } catch (e) {
      if (!c.signal.aborted) {
        if (critical(e)) invalidate(e);
        else setError(message(e));
      }
    } finally {
      lock.current = false;
      if (!c.signal.aborted) setBusy(false);
    }
  }
  useEffect(() => {
    if (
      !autoStartRunId ||
      // Research mode continues only to the review step; preparing never sends anything.
      (!!researchStatus && !inappReady) ||
      providerChoice === 'loading' ||
      (providerChoice === 'unavailable' && !inappReady) ||
      !history ||
      unavailable ||
      !verifiedParent ||
      verifiedParent.packet?.mode !== 'deterministic_evidence_only' ||
      verifiedParent.packet?.provider_used !== false ||
      verifiedParent.run_id !== autoStartRunId ||
      autoStarted.current === autoStartRunId
    )
      return;
    autoStarted.current = autoStartRunId;
    void generate();
    // A user-authorized run is dispatched once after its verified parent is available.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    autoStartRunId,
    history,
    unavailable,
    verifiedParent?.run_id,
    providerChoice,
    researchStatus,
  ]);
  const shownDraft = detail?.draft?.draft_run_id;
  const needsTransactions =
    !!shownDraft && !packet?.packet?.transactions?.length;
  useEffect(() => {
    if (!needsTransactions) return;
    const c = new AbortController();
    async function load() {
      const rows: Transaction[] = [];
      let cursor: string | undefined;
      try {
        for (let n = 0; n < 10; n++) {
          const page = await api(c.signal).transactions(id, {
            snapshot: context.data.snapshot_token,
            limit: 20,
            ...(cursor ? { cursor } : {}),
          });
          if (c.signal.aborted) return;
          rows.push(...page.data.items);
          if (!page.data.next_cursor) break;
          cursor = page.data.next_cursor;
        }
        setLoadedTransactions(rows);
      } catch {
        // Records stay reachable from the card; access errors surface through other reads.
      }
    }
    void load();
    return () => c.abort();
  }, [api, id, context.data.snapshot_token, shownDraft, needsTransactions]);
  function inspect(reference: string) {
    const value = context.evidence.find(
      (r) => r.record_version_id === reference,
    );
    if (!value) {
      invalidate(new ApiError(409));
      return;
    }
    recordTrigger.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    setSelected(value);
  }
  const draft = detail?.draft;
  const safe =
    draft &&
    ['succeeded', 'abstained'].includes(detail.status) &&
    ((draft.simulation === true &&
      draft.live_provider_used === false &&
      detail.mode === 'offline_simulation' &&
      draft.provenance.provider === 'deterministic_fake') ||
      (draft.simulation === false &&
        draft.live_provider_used === true &&
        detail.mode === 'claude_live' &&
        draft.provenance.provider === 'anthropic' &&
        draft.provenance.model === 'claude-sonnet-5-5')) &&
    draft.verification === 'source_reference_numeric_checks_passed';
  const live = Boolean(safe && draft?.live_provider_used);
  const requested = history?.items.find(
    (item) => item.draft_run_id === run,
  )?.created_at;
  const cited = new Set(
    safe
      ? [
          ...draft.findings.flatMap((f) => f.supporting_evidence),
          ...draft.hypotheses.flatMap((h) => h.supporting_evidence),
        ]
      : [],
  );
  const transactions: Transaction[] = (
    packet?.packet?.transactions?.length
      ? packet.packet.transactions
      : loadedTransactions.length
        ? loadedTransactions
        : (draft?.findings ?? [])
            .filter((f) => f.claim_type === 'observed_fact')
            .map((f) => f.summary as Transaction)
  )
    .filter((t) => !cited.size || cited.has(t.reference.record_version_id))
    .sort((a, b) => (a.event_at ?? '').localeCompare(b.event_at ?? ''));
  const research = !!safe && draft.regulatory_context === 'research_unapproved';
  const passages = (safe ? (draft.regulatory_citations ?? []) : []).filter(
    (p): p is import('./investigation-api').ResearchPassage =>
      'origin' in p && p.origin === 'official_public_research',
  );
  const fullSources = fullSourceTexts(safe ? draft : null, passages);
  const openTransactions = () => {
    const panel = transactionsRef.current;
    if (!panel) return;
    panel.open = true;
    panel.scrollIntoView({ block: 'start', behavior: 'smooth' });
    panel.querySelector('summary')?.focus();
  };
  const spendText: string = researchStatus
    ? inappReady
      ? 'Prepares the exact request for review — nothing is sent to Claude until an authorized spending approver approves it.'
      : researchStatus === 'awaiting_approval'
        ? 'The exact request is awaiting review by an authorized spending approver.'
        : researchStatus === 'approved_queued' || researchStatus === 'running'
          ? 'Approved — one Claude request is running; refreshing does not repeat it.'
          : researchStatus === 'budget_exhausted'
            ? "The owner's AI spending cap has been reached."
            : researchReady
              ? 'Runs the exact owner-approved request once.'
              : 'A fresh request needs approval by an authorized spending approver.'
    : providerChoice === 'claude'
      ? 'Requests Claude findings from verified synthetic evidence; claims are checked before display.'
      : providerChoice === 'unavailable'
        ? 'No authorized provider is available.'
        : 'Offline simulation, not a live LLM result.';
  const headerContent = (
    <div className="draft-action">
      <div className="section-heading">
        <div>
          {!live && (
            <p className="muted provider-line">
              {researchStatus
                ? 'Claude — Controlled research request'
                : providerChoice === 'claude'
                  ? 'Claude — Ready'
                  : providerChoice === 'unavailable'
                    ? 'Unavailable'
                    : providerChoice === 'loading'
                      ? 'Checking provider availability'
                      : 'Offline simulation'}
            </p>
          )}
          <h3 id="ai-result-title">AI investigation</h3>
        </div>
        <div className="header-actions">
          <button
            className="primary"
            title={spendText}
            aria-describedby="spend-note"
            disabled={
              busy ||
              orchestrating ||
              (!researchReady && !verifiedParent && !orchestrate) ||
              (inappReady && !verifiedParent && !prepareEvidence) ||
              !!reviewRun ||
              unavailable ||
              providerChoice === 'loading' ||
              (providerChoice === 'unavailable' && !researchReady) ||
              (includeGrounding && !regulatoryQuery.trim())
            }
            onClick={() => {
              if (inappReady && !verifiedParent && prepareEvidence)
                prepareEvidence();
              else if (researchReady) void generate();
              else if (orchestrate && !includeGrounding) orchestrate();
              else void generate();
            }}
          >
            <Icon name="investigation" />
            {busy || orchestrating
              ? 'Requesting investigation…'
              : researchStatus
                ? inappReady
                  ? researchStatus === 'request_expired' && !detail
                    ? 'Refresh Request'
                    : terminal
                      ? 'Generate new investigation'
                      : 'Generate investigation'
                  : researchReady
                    ? 'Generate investigation'
                    : researchStatus === 'budget_exhausted'
                      ? 'AI spending cap reached'
                      : researchStatus === 'awaiting_approval'
                        ? 'Awaiting owner approval'
                        : (researchStatus === 'approved_queued' ||
                              researchStatus === 'running') &&
                            !terminal
                          ? 'Investigation in progress'
                          : researchStatus === 'request_expired' ||
                              researchStatus === 'request_required'
                            ? 'New approval request required'
                            : 'Owner approval required'
                : orchestrate || providerChoice === 'claude'
                  ? 'Generate investigation'
                  : 'Generate Simulated Investigation Draft'}
          </button>
          <div className="draft-state-line">
            {detail && !safe && (
              <>
                <StatusBadge
                  value={
                    detail.status === 'running'
                      ? 'processing'
                      : detail.status === 'succeeded'
                        ? 'completed'
                        : detail.status
                  }
                />
              </>
            )}
            {run && (
              <button
                className="icon-button"
                aria-label="Check draft status"
                title="Check draft status"
                onClick={() => setRevision((v) => v + 1)}
              >
                <Icon name="refresh" />
              </button>
            )}
          </div>
        </div>
      </div>
      <p id="spend-note" className="sr-only">
        {spendText}
      </p>
      {groundingAvailable && (
        <div>
          <label>
            <input
              type="checkbox"
              checked={includeGrounding}
              onChange={(e) => setIncludeGrounding(e.target.checked)}
            />{' '}
            Include approved regulatory guidance
          </label>
          {includeGrounding && (
            <label>
              Regulatory topic
              <input
                maxLength={256}
                value={regulatoryQuery}
                onChange={(e) => setRegulatoryQuery(e.target.value)}
              />
            </label>
          )}
        </div>
      )}
      {!verifiedParent && !orchestrate && (
        <p className="hint">
          Generate or open a verified Investigation Summary before requesting a
          draft.
        </p>
      )}
      {orchestrationError && (
        <p className="error" role="alert">
          {orchestrationError}
        </p>
      )}
      {orchestrationStatus && !detail && (
        <p role="status">Evidence preparation: {label(orchestrationStatus)}.</p>
      )}
      {reviewRun && api().researchReview && (
        <ResearchReviewPanel
          id={id}
          run={reviewRun}
          api={api}
          invalidate={invalidate}
          onApproved={(approved) => {
            setReviewRun(null);
            setRun(approved);
            setRevision((v) => v + 1);
            setCapabilityRevision((v) => v + 1);
          }}
          onClosed={() => {
            setReviewRun(null);
            setCapabilityRevision((v) => v + 1);
          }}
          onRefresh={() => {
            setReviewRun(null);
            void prepareResearch();
          }}
        />
      )}
      {detail && researchStatus && detail.mode === 'claude_live' && (
        <p role="status" className="research-progress">
          {detail.status === 'pending'
            ? 'Approved — queued for one Claude request.'
            : detail.status === 'running'
              ? 'Generating with Claude, then independently verifying financial figures, evidence references and citations…'
              : null}
        </p>
      )}
      {run && !detail && !error && (
        <p role="status">Checking investigation progress…</p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {historyError && (
        <p role="alert" className="error">
          {historyError}
        </p>
      )}
      {paused && (
        <p className="notice">
          Automatic checks paused after the bounded polling period. Use Check
          draft status or reopen this request from history.
        </p>
      )}
      {detail?.status === 'failed' && (
        <p role="alert" className="notice">
          No verified findings are available.{' '}
          {label(detail.error_code ?? 'processing_unavailable')}. Analyst review
          remains required. Repeating this request does not restart a terminal
          failure.
        </p>
      )}
      {detail?.status === 'invalidated' && (
        <p role="alert" className="notice">
          The source evidence or access has changed. Draft content has been
          withheld. Refresh supporting evidence before continuing.
        </p>
      )}
      {draft && !safe && (
        <p role="alert" className="notice">
          This result is outside the verified provider contract and has been
          withheld.
        </p>
      )}
    </div>
  );
  return (
    <section className="drafts-workspace" aria-label="AI-Assisted Findings">
      {safe ? (
        <InvestigationResult
          draft={draft}
          status={detail.status}
          requestedAt={requested ?? undefined}
          transactions={transactions}
          inspect={inspect}
          openTransactions={openTransactions}
          header={headerContent}
        />
      ) : (
        <section className="panel ai-result" aria-labelledby="ai-result-title">
          {headerContent}
        </section>
      )}
      {selected && (
        <RecordInspection
          key={selected.record_version_id}
          id={id}
          api={api}
          context={context}
          reference={selected}
          close={() => {
            setSelected(null);
            recordTrigger.current?.focus();
          }}
          invalidate={invalidate}
        />
      )}
      <div className="disclosure-bar">
        {safe && transactions.length > 0 && (
          <details className="panel disclosure" ref={transactionsRef}>
            <summary>Transactions · {transactions.length}</summary>
            <div
              className="table-wrap"
              role="region"
              aria-label="Transactions"
              tabIndex={0}
            >
              <table className="compact-table">
                <caption className="sr-only">
                  Transactions used by this investigation
                </caption>
                <thead>
                  <tr>
                    <th>Ref</th>
                    <th>Date</th>
                    <th>Direction / type</th>
                    <th className="num">Amount</th>
                    <th>Counterparty</th>
                    <th>Record</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((t, i) => (
                    <tr key={t.reference.record_version_id}>
                      <td>T{i + 1}</td>
                      <td>
                        {t.event_at ? formatDate(t.event_at) : 'Not recorded'}
                      </td>
                      <td>{directionShort(t.direction, t.event_kind)}</td>
                      <td className="num">{money(t.amount, t.currency)}</td>
                      <td title={t.counterparty_handle ?? undefined}>
                        {t.counterparty_handle
                          ? shortId(t.counterparty_handle)
                          : 'Not recorded'}
                      </td>
                      <td>
                        <button
                          className="link-button"
                          onClick={() => inspect(t.reference.record_version_id)}
                        >
                          Open T{i + 1}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
        {safe && fullSources.length > 0 && (
          <details className="panel disclosure">
            <summary>Full source text · {fullSources.length}</summary>
            {fullSources.map((source) => (
              <article key={source.reference_id} className="source-text">
                <h5>
                  {source.rId && <>{source.rId} · </>}31 CFR § {source.section}
                  {sectionTitle(source.text) && (
                    <> — {sectionTitle(source.text)}</>
                  )}
                  {source.cited && <span className="tag">Cited by the AI</span>}
                </h5>
                <p className="hint">
                  {source.publisher} · historical eCFR as of{' '}
                  {source.historicalAsOf} · Unapproved research · historical
                  U.S. bank research only, not legally adjudicated
                  {source.sentNote && <> · {source.sentNote}</>}
                  {source.url && (
                    <>
                      {' '}
                      ·{' '}
                      <a href={source.url} target="_blank" rel="noreferrer">
                        Open historical eCFR source
                      </a>
                    </>
                  )}
                </p>
                {/* Verbatim regulation text is exempt from display rules. */}
                <p className="source-body" data-ui-guard-skip>
                  {source.text}
                </p>
                {source.excerpt && (
                  <details className="excerpt-sent">
                    <summary>Excerpt sent to the AI</summary>
                    <p className="source-body" data-ui-guard-skip>
                      {source.excerpt}
                    </p>
                  </details>
                )}
              </article>
            ))}
          </details>
        )}
        <AuditDetails>
          {safe && (
            <>
              <AuditList>
                <CopyValue label="Draft run" value={draft.draft_run_id} />
                <CopyValue
                  label="Investigation run"
                  value={draft.investigation_run_id}
                />
                <dt>Provider / model</dt>
                <dd>
                  {draft.provenance.provider} / {draft.provenance.model}
                </dd>
                <CopyValue
                  label="Input manifest"
                  value={draft.manifest_sha256}
                />
                <CopyValue
                  label="Verified packet"
                  value={draft.packet_sha256}
                />
                <dt>Prompt version</dt>
                <dd>{draft.provenance.prompt_version}</dd>
                <dt>Verification result</dt>
                <dd>
                  Source, reference and numeric checks passed
                  {research && '; citations verified against the retrieved set'}
                  . Semantic and legal review remain incomplete.
                </dd>
                {draft.retrieval && (
                  <>
                    <dt>Retrieval</dt>
                    <dd>
                      {draft.retrieval.method} · passage budget{' '}
                      {draft.retrieval.passage_budget_bytes} bytes
                    </dd>
                  </>
                )}
                {detail && (
                  <>
                    <dt>Evidence revision</dt>
                    <dd>
                      {(() => {
                        const item = history?.items.find(
                          (h) => h.draft_run_id === run,
                        );
                        return item
                          ? `Case ${item.case_version} · evidence ${item.evidence_revision} · access ${item.access_revision}`
                          : 'Not available';
                      })()}
                    </dd>
                  </>
                )}
              </AuditList>
              <h5>All limitations ({draft.limitations.length})</h5>
              <Codes values={draft.limitations} />
              {[...draft.missing_evidence, ...draft.conflicts].length > 3 && (
                <>
                  <h5>All missing evidence</h5>
                  <Codes
                    values={[...draft.missing_evidence, ...draft.conflicts]}
                  />
                </>
              )}
            </>
          )}
          {auditExtras}
          <div className="audit-history">
            <div className="section-heading">
              <h5>
                Activity History ·{' '}
                {history?.items.some((item) => item.mode === 'claude_live')
                  ? 'Investigation Drafts'
                  : 'Simulated Drafts'}
              </h5>
              <button onClick={() => setRevision((v) => v + 1)}>
                Refresh draft history
              </button>
            </div>
            <p className="hint">
              Your requests only. Opening a draft rechecks current evidence and
              access. Historical statuses are not freshly verified results.
            </p>
            {!history && historyError ? (
              <p>
                Draft history is unavailable. Refresh when service is restored.
              </p>
            ) : !history ? (
              <p role="status">Loading draft history…</p>
            ) : !history.items.length ? (
              <p>No simulated investigation drafts have been requested.</p>
            ) : (
              <>
                <div
                  className="table-wrap"
                  role="region"
                  aria-label="Simulated draft history"
                  tabIndex={0}
                >
                  <table>
                    <caption className="sr-only">
                      Simulated draft history
                    </caption>
                    <thead>
                      <tr>
                        <th>Requested</th>
                        <th>Status</th>
                        <th>Source revisions</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.items.map((item) => (
                        <tr key={item.draft_run_id}>
                          <td>
                            <Timestamp value={item.created_at} />
                          </td>
                          <td>
                            <StatusBadge value={item.status} />
                          </td>
                          <td>
                            Case {item.case_version} · Evidence{' '}
                            {item.evidence_revision} · Access{' '}
                            {item.access_revision}
                          </td>
                          <td>
                            <button
                              onClick={() => {
                                setDetail(null);
                                setSelected(null);
                                setRun(item.draft_run_id);
                                setRevision((v) => v + 1);
                              }}
                            >
                              {item.mode === 'claude_live'
                                ? 'Open Claude investigation'
                                : 'Open simulated draft'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="pager">
                  <span>{history.total} requests</span>
                  <div>
                    <button
                      disabled={!offset}
                      onClick={() => setOffset((v) => Math.max(0, v - 10))}
                    >
                      Previous drafts
                    </button>
                    <button
                      disabled={
                        offset + 10 >= history.total || offset + 10 > 1000
                      }
                      onClick={() => setOffset((v) => v + 10)}
                    >
                      Next drafts
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </AuditDetails>
        {!research && (
          <ResearchGuidance id={id} api={api} invalidate={invalidate} />
        )}
        {!research && (
          <RegulatoryGuidance
            id={id}
            api={api}
            run={safe ? draft.investigation_run_id : verifiedParent?.run_id}
            citations={
              safe
                ? draft.regulatory_citations?.filter(
                    (p): p is import('./investigation-api').RegulatoryPassage =>
                      p.origin !== 'official_public_research',
                  )
                : undefined
            }
          />
        )}
      </div>
      {research && !safe && (
        <p className="ai-footer" role="note">
          <strong>
            Unapproved research · Not production regulatory guidance
          </strong>{' '}
          · AI-assisted academic research demonstration
        </p>
      )}
    </section>
  );
}

function RecordInspection({
  id,
  api,
  context,
  reference,
  close,
  invalidate,
}: {
  id: string;
  api: InvestigationFactory;
  context: Evidence<CaseContext>;
  reference: Reference;
  close: () => void;
  invalidate: (e: unknown) => void;
}) {
  const [row, setRow] = useState<Transaction | Customer | Related | null>(null);
  const [error, setError] = useState('');
  const focus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const c = new AbortController();
    focus.current?.focus();
    async function load() {
      try {
        let cursor: string | undefined;
        for (let n = 0; n < 10; n++) {
          const client = api(c.signal);
          const page =
            reference.kind === 'transaction'
              ? await client.transactions(id, {
                  snapshot: context.data.snapshot_token,
                  limit: 20,
                  ...(cursor ? { cursor } : {}),
                })
              : reference.kind === 'customer'
                ? await client.customers(
                    id,
                    context.data.snapshot_token,
                    cursor,
                  )
                : await client.related(id, context.data.snapshot_token, cursor);
          if (c.signal.aborted) return;
          const found = page.data.items.find(
            (r) =>
              r.reference.record_version_id === reference.record_version_id,
          );
          if (found) {
            if (
              found.reference.sha256 !== reference.sha256 ||
              found.reference.source_version_id !== reference.source_version_id
            )
              throw new ApiError(409);
            setRow(found);
            return;
          }
          if (!page.data.next_cursor) break;
          cursor = page.data.next_cursor;
        }
        setError(
          'This supporting record is unavailable in the authorized evidence window. Refresh supporting evidence.',
        );
      } catch (e) {
        if (!c.signal.aborted) {
          setRow(null);
          if (critical(e)) invalidate(e);
          else setError(message(e));
        }
      }
    }
    void load();
    return () => c.abort();
  }, [id, api, context, reference, invalidate]);
  return (
    <section
      className="panel supporting-inspector"
      aria-label="Supporting record details"
      tabIndex={-1}
      ref={focus}
    >
      <div className="section-heading">
        <h4>Supporting Records · Source Details</h4>
        <button onClick={close}>Close record</button>
      </div>
      {error ? (
        <p role="alert">{error}</p>
      ) : !row ? (
        <p role="status">Verifying authorized supporting record…</p>
      ) : (
        <>
          <p className="muted">
            {label(reference.kind)} · Record version {reference.version}
          </p>
          <dl className="draft-values">
            {'amount' in row ? (
              <>
                <div>
                  <dt>Amount</dt>
                  <dd>{decimalMoney(row.amount, row.currency)}</dd>
                </div>
                <div>
                  <dt>Direction</dt>
                  <dd>{label(row.direction)}</dd>
                </div>
                <div>
                  <dt>Event</dt>
                  <dd>{label(row.event_kind)}</dd>
                </div>
                <div>
                  <dt>Recorded time</dt>
                  <dd>{time(row.event_at)}</dd>
                </div>
              </>
            ) : 'annual_income' in row ? (
              <>
                <div>
                  <dt>Customer alias</dt>
                  <dd>{row.alias}</dd>
                </div>
                <div>
                  <dt>Recorded income</dt>
                  <dd>{decimalMoney(row.annual_income, row.currency)}</dd>
                </div>
              </>
            ) : (
              <>
                <div>
                  <dt>Account / relationship</dt>
                  <dd>{row.alias ?? label(row.kind)}</dd>
                </div>
                <div>
                  <dt>Currency</dt>
                  <dd>{row.currency ?? 'Not recorded'}</dd>
                </div>
              </>
            )}
          </dl>
          <details className="technical-details">
            <summary>Record provenance</summary>
            <dl className="draft-provenance">
              <dt>Record version</dt>
              <dd>{reference.record_version_id}</dd>
              <dt>Source version</dt>
              <dd>{reference.source_version_id}</dd>
              <dt>Integrity hash</dt>
              <dd>{reference.sha256}</dd>
            </dl>
          </details>
        </>
      )}
    </section>
  );
}

/** The exact excerpt sent, rebuilt from its stored UTF-8 byte ranges in the section text. */
export function excerptText(
  text: string,
  spans: { start: number; end: number }[] = [],
) {
  const bytes = new TextEncoder().encode(text);
  const decoder = new TextDecoder();
  return spans
    .map((s) => decoder.decode(bytes.slice(s.start, s.end)))
    .join('\n[…]\n');
}

type FullSource = {
  reference_id: string;
  rank?: number;
  section: string;
  text: string;
  rId?: string;
  cited: boolean;
  publisher: string;
  historicalAsOf: string;
  url?: string;
  sentNote?: string;
  excerpt?: string;
};

/** Every retrieved section (full hash-verified text), cited ones first, then by rank. Earlier
 * runs without stored section texts list the cited passages, as before. */
export function fullSourceTexts(
  draft: import('./draft-api').SimulationDraft | null,
  cited: import('./investigation-api').ResearchPassage[],
): FullSource[] {
  if (!draft) return [];
  const byId = new Map(cited.map((p) => [p.reference_id, p]));
  const first = cited[0];
  const url = (value?: string) =>
    value?.startsWith('https://www.ecfr.gov/api/versioner/')
      ? value
      : undefined;
  const results = draft.retrieval?.results ?? [];
  if (!draft.source_texts?.length || !results.length)
    return cited.map((p) => ({
      reference_id: p.reference_id,
      section: p.section,
      text: p.text,
      cited: true,
      publisher: p.publisher,
      historicalAsOf: p.historical_as_of,
      url: url(p.source_url),
    }));
  const rows = draft.source_texts.map((t) => {
    const r = results.find((x) => x.reference_id === t.reference_id);
    const passage = byId.get(t.reference_id);
    const excerpted =
      r?.excerpt_bytes !== undefined && r.excerpt_bytes < r.text_bytes;
    return {
      reference_id: t.reference_id,
      section: t.section,
      text: t.text,
      rId: r ? `R${r.rank}` : undefined,
      rank: r?.rank ?? 99,
      cited: !!passage,
      publisher: passage?.publisher ?? first?.publisher ?? 'eCFR',
      historicalAsOf:
        passage?.historical_as_of ?? first?.historical_as_of ?? '2026-11-02',
      url: url(passage?.source_url ?? first?.source_url),
      sentNote: !r
        ? undefined
        : !r.sent
          ? 'Not sent to the AI (request size limit)'
          : excerpted
            ? `Sent to the AI as an excerpt (${r.excerpt_bytes!.toLocaleString('en-US')} of ${r.text_bytes.toLocaleString('en-US')} bytes)`
            : 'Sent to the AI in full',
      excerpt: excerpted ? excerptText(t.text, r!.excerpt_spans) : undefined,
    };
  });
  return rows.sort(
    (a, b) => Number(b.cited) - Number(a.cited) || a.rank - b.rank,
  );
}
