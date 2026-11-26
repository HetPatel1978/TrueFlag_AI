import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError, label, message, type User } from './api';
import type { HumanFactory, HumanPage } from './human-casework-api';
import type {
  CaseContext,
  Evidence,
  InvestigationFactory,
} from './investigation-api';
import type { SimulationDraft } from './draft-api';
import { PageHeader, StatusBadge } from './ui';
import { AuditDetails, AuditList, CopyValue, Timestamp } from './display';
import { utcText } from './format';
import './human-casework.css';

type Command = { kind: string } & Record<string, unknown>;
const deny = (e: unknown) =>
  e instanceof ApiError && [401, 403, 404, 409, 422, 503].includes(e.status);

function Form({
  title,
  action,
  children,
  submit,
  disabled,
  note = false,
}: {
  title: string;
  action: string;
  children?: ReactNode;
  submit: (data: FormData) => Promise<void>;
  disabled: boolean;
  note?: boolean;
}) {
  return (
    <div className="case-action">
      <form
        className="human-form"
        aria-label={title}
        onSubmit={(e) => {
          e.preventDefault();
          const element = e.currentTarget;
          void submit(new FormData(element))
            .then(() => element.reset())
            .catch(() => {});
        }}
      >
        {children}
        <label>
          {note ? 'Investigation note' : 'Decision rationale'}
          <textarea
            name="rationale"
            required
            minLength={10}
            maxLength={4000}
            rows={3}
            disabled={disabled}
          />
        </label>
        <button className="primary" disabled={disabled}>
          {action}
        </button>
      </form>
    </div>
  );
}

export function HumanCasework({
  id,
  user,
  api,
  evidenceApi,
  changed,
  decide = false,
  onMissing,
}: {
  id: string;
  user: User;
  api: HumanFactory;
  evidenceApi: InvestigationFactory;
  changed: () => void;
  /** Opened from "Record decision": preselect the decision action valid for this user. */
  decide?: boolean;
  onMissing?: (missing: string[]) => void;
}) {
  const [action, setAction] = useState<string | null>(null);
  const [page, setPage] = useState<HumanPage | null>(null);
  const [context, setContext] = useState<Evidence<CaseContext> | null>(null);
  const [draft, setDraft] = useState<SimulationDraft | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [offset, setOffset] = useState(0);
  const [tick, setTick] = useState(0);
  const [confirmation, setConfirmation] = useState<Command | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!confirmation) return;
    const previous = document.activeElement;
    dialogRef.current?.querySelector('button')?.focus();
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus();
    };
  }, [confirmation]);
  const [selectedRecord, setSelectedRecord] = useState('');
  const [recordDetail, setRecordDetail] = useState<ReactNode>(null);
  const requests = useRef(new AbortController());
  const pending = useRef(false);
  const retry = useRef<{ signature: string; key: string } | null>(null);
  const manager = user.role !== 'analyst';
  const lastSnapshot = useRef('');
  function clear() {
    setPage(null);
    setContext(null);
    setDraft(null);
    setConfirmation(null);
    setSelectedRecord('');
    setRecordDetail(null);
  }
  useEffect(() => {
    const controller = new AbortController();
    requests.current = controller;
    let timer = 0,
      checks = 0;
    async function load() {
      if (checks === 0) clear();
      try {
        const [p, c] = await Promise.all([
          api(controller.signal).history(id, offset),
          evidenceApi(controller.signal).context(id),
        ]);
        if (!controller.signal.aborted) {
          if (
            lastSnapshot.current &&
            lastSnapshot.current !== c.snapshot.sha256
          )
            clear();
          lastSnapshot.current = c.snapshot.sha256;
          setPage(p);
          setContext(c);
          setError('');
        }
        // Finite refresh budget. No consequential action is ever repeated by polling.
        if (!controller.signal.aborted && ++checks < 20)
          timer = window.setTimeout(() => void load(), 15000);
      } catch (e) {
        if (!controller.signal.aborted) {
          clear();
          setError(message(e));
        }
      }
    }
    void load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [id, api, evidenceApi, offset, tick]);
  const missingCategories = context?.data.missing_categories;
  useEffect(() => {
    if (missingCategories) onMissing?.(missingCategories);
  }, [missingCategories, onMissing]);
  async function send(command: Command) {
    if (!page || !context || pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    const signature = JSON.stringify(command);
    if (retry.current?.signature !== signature)
      retry.current = { signature, key: crypto.randomUUID() };
    const signal = requests.current.signal;
    try {
      await api(signal).submit(id, retry.current.key, {
        ...command,
        snapshot: context.data.snapshot_token,
        expected_revision: page.revision,
      });
      if (signal.aborted) return;
      retry.current = null;
      setConfirmation(null);
      setNotice('Human casework recorded. Submitted history is immutable.');
      setTick((n) => n + 1);
      if (command.kind === 'resolution') changed();
    } catch (e) {
      if (!signal.aborted) {
        if (deny(e)) clear();
        setError(message(e));
      }
      throw e;
    } finally {
      pending.current = false;
      if (!signal.aborted) setBusy(false);
    }
  }
  async function prepare(
    kind: string,
    data: FormData,
    extra: Record<string, unknown> = {},
  ) {
    const refs =
      selectedRecord && context
        ? context.evidence.filter((r) => r.record_version_id === selectedRecord)
        : [];
    const command = {
      kind,
      rationale: String(data.get('rationale') ?? ''),
      supporting_records: refs,
      ...extra,
    };
    if (
      [
        'supervisor_response',
        'resolution',
        'escalation',
        'finding_review',
      ].includes(kind)
    )
      setConfirmation(command);
    else await send(command);
  }
  async function loadFindings() {
    const signal = requests.current.signal;
    setBusy(true);
    setDraft(null);
    try {
      const history = await evidenceApi(signal).draftHistory(id, 0);
      const candidate = history.items.find((r) =>
        ['succeeded', 'abstained'].includes(r.status),
      );
      if (!candidate) {
        setNotice(
          'No completed simulated draft is available in your latest history. Generate one in Investigation first.',
        );
        return;
      }
      const detail = await evidenceApi(signal).draftDetail(
        id,
        candidate.draft_run_id,
      );
      if (
        !detail.draft ||
        !detail.draft.simulation ||
        detail.draft.live_provider_used ||
        !detail.draft.content_sha256
      )
        throw new ApiError(409);
      if (!signal.aborted) setDraft(detail.draft);
    } catch (e) {
      if (!signal.aborted) {
        if (deny(e)) clear();
        setError(message(e));
      }
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }
  async function inspect() {
    if (!context || !selectedRecord) return;
    const signal = requests.current.signal;
    setRecordDetail(null);
    const reference = context.evidence.find(
      (r) => r.record_version_id === selectedRecord,
    );
    if (!reference) return;
    try {
      // Existing authorized paged evidence APIs, no invented citations or raw predictor data.
      let cursor: string | undefined;
      for (let i = 0; i < 10; i++) {
        const query = {
          snapshot: context.data.snapshot_token,
          limit: 20,
          ...(cursor ? { cursor } : {}),
        };
        const value =
          reference.kind === 'transaction'
            ? await evidenceApi(signal).transactions(id, query)
            : reference.kind === 'customer'
              ? await evidenceApi(signal).customers(
                  id,
                  context.data.snapshot_token,
                  cursor,
                )
              : await evidenceApi(signal).related(
                  id,
                  context.data.snapshot_token,
                  cursor,
                );
        const row = value.data.items.find(
          (r) => r.reference.record_version_id === selectedRecord,
        );
        if (row) {
          if (
            row.reference.sha256 !== reference.sha256 ||
            row.reference.source_version_id !== reference.source_version_id
          )
            throw new ApiError(409);
          if (!signal.aborted)
            setRecordDetail(
              <dl className="human-record">
                {Object.entries(row)
                  .filter(([k]) => !['reference'].includes(k))
                  .map(([k, v]) => (
                    <div key={k}>
                      <dt>{label(k)}</dt>
                      <dd>{v === null ? 'Not recorded' : String(v)}</dd>
                    </div>
                  ))}
              </dl>,
            );
          return;
        }
        cursor = value.data.next_cursor ?? undefined;
        if (!cursor) break;
      }
      throw new ApiError(404);
    } catch (e) {
      if (!signal.aborted) {
        if (deny(e)) clear();
        setError(message(e));
      }
    }
  }
  const entries = page?.items ?? [];
  const visible = entries.filter((r) => r.payload);
  const answered = new Set(
    entries
      .filter((r) =>
        ['information_response', 'supervisor_response'].includes(r.kind),
      )
      .map((r) => r.parent_id),
  );
  const open = entries.filter(
    (r) => r.kind === 'information_request' && !answered.has(r.id),
  );
  const escalations = entries.filter(
    (r) => r.kind === 'escalation' && !answered.has(r.id),
  );
  const approved = visible.find(
    (r) =>
      r.kind === 'supervisor_response' &&
      r.payload?.decision === 'approve_resolution' &&
      r.revision === page?.revision &&
      r.actor_id === user.id,
  );
  const disabled =
    busy ||
    !page ||
    !context ||
    ['investigation_completed', 'no_further_action_recommended'].includes(
      page.resolution ?? '',
    );
  // One action picker. Only actions valid for this case state and the user's role are listed;
  // every capability that was available before remains available here.
  const actionList = page
    ? (
        [
          ['note', 'Write note', true],
          ['information_request', 'Request information', true],
          [
            'information_response',
            'Respond to information request',
            open.length > 0,
          ],
          ['finding_review', 'Review simulated findings', true],
          [
            'escalation',
            'Escalate to supervisor',
            page.pending_escalations === 0,
          ],
          [
            'supervisor_response',
            'Supervisor review',
            manager && escalations.length > 0,
          ],
          ['resolution', 'Record resolution', manager && Boolean(approved)],
          ['link', 'Link supporting evidence', true],
        ] as const
      ).filter(([, , valid]) => valid)
    : [];
  const validKeys = actionList.map(([key]) => key as string);
  const preferred = decide
    ? validKeys.includes('resolution')
      ? 'resolution'
      : validKeys.includes('escalation')
        ? 'escalation'
        : 'note'
    : 'note';
  const chosen = action && validKeys.includes(action) ? action : preferred;
  const linked = context?.evidence.find(
    (r) => r.record_version_id === selectedRecord,
  );
  return (
    <section
      className="human-casework"
      aria-label="Human investigation casework"
    >
      {error && (
        <div className="notice" role="alert">
          {error} Refresh casework before continuing.
        </div>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {!page || !context ? (
        <p className="state">
          {error
            ? 'Casework is withheld until current access and evidence can be verified.'
            : 'Loading authorized casework…'}
        </p>
      ) : (
        <>
          <section
            className="panel decision-card"
            aria-labelledby="decision-title"
          >
            <h2 id="decision-title">Human decision</h2>
            <p className="status-line" role="status">
              Resolution:{' '}
              {page.resolution ? label(page.resolution) : 'Not recorded'} ·{' '}
              {page.open_information_requests} open information request
              {page.open_information_requests === 1 ? '' : 's'} ·{' '}
              {page.pending_escalations} pending supervisor review
              {page.pending_escalations === 1 ? '' : 's'}
            </p>
            <div className="action-row">
              <label>
                Action
                <select
                  value={chosen}
                  onChange={(e) => setAction(e.target.value)}
                  disabled={busy}
                >
                  {actionList.map(([key, text]) => (
                    <option key={key} value={key}>
                      {text}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Supporting record
                <select
                  value={selectedRecord}
                  onChange={(e) => {
                    setSelectedRecord(e.target.value);
                    setRecordDetail(null);
                  }}
                >
                  <option value="">None linked</option>
                  {context.evidence.map((r) => (
                    <option
                      key={r.record_version_id}
                      value={r.record_version_id}
                    >
                      {label(r.kind)} · {r.record_version_id.slice(0, 8)} · v
                      {r.version}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {chosen === 'link' && (
              <div className="case-action">
                <p className="muted">
                  The selected record is linked to your next submission.
                  Free-text rationale is analyst-authored and is not
                  independently verified fact.
                </p>
                <button
                  onClick={() => void inspect()}
                  disabled={!selectedRecord || busy}
                >
                  Inspect supporting record
                </button>
                {recordDetail && (
                  <div className="human-inspector">
                    <h4>Current supporting record</h4>
                    {recordDetail}
                    <button onClick={() => setRecordDetail(null)}>
                      Close supporting record
                    </button>
                  </div>
                )}
              </div>
            )}
            {chosen === 'note' && (
              <Form
                title="Investigation Notes"
                action="Submit investigation note"
                note
                disabled={disabled}
                submit={(d) =>
                  prepare('note', d, {
                    ...(d.get('parent_id')
                      ? { parent_id: d.get('parent_id') }
                      : {}),
                  })
                }
              >
                {visible.some(
                  (r) => r.kind === 'note' && r.actor_id === user.id,
                ) && (
                  <label>
                    Note version
                    <select name="parent_id">
                      <option value="">New submitted note</option>
                      {visible
                        .filter(
                          (r) => r.kind === 'note' && r.actor_id === user.id,
                        )
                        .map((r) => (
                          <option key={r.id} value={r.id}>
                            Addendum to revision {r.revision}
                          </option>
                        ))}
                    </select>
                  </label>
                )}
                <p className="hint">
                  Submitted notes are immutable; corrections create an addendum.
                </p>
              </Form>
            )}
            {chosen === 'information_request' && (
              <Form
                title="Additional Information Requested"
                action="Record information request"
                disabled={disabled}
                submit={(d) =>
                  prepare('information_request', d, {
                    category: d.get('category'),
                    responsible_party: d.get('responsible_party'),
                    ...(d.get('due_date')
                      ? { due_date: d.get('due_date') }
                      : {}),
                  })
                }
              >
                <div className="form-row">
                  <label>
                    Information category
                    <select name="category">
                      {[
                        'customer_documentation',
                        'account_information',
                        'transaction_clarification',
                        'relationship_verification',
                        'activity_history',
                      ].map((v) => (
                        <option key={v} value={v}>
                          {label(v)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Responsible party
                    <select name="responsible_party">
                      <option value="assigned_analyst">Assigned analyst</option>
                      <option value="supervisor">Supervisor</option>
                    </select>
                  </label>
                  <label>
                    Due date (optional)
                    <input name="due_date" type="date" />
                  </label>
                </div>
                <p className="hint">
                  Internal tracking only. No email or external delivery.
                </p>
              </Form>
            )}
            {chosen === 'information_response' && (
              <Form
                title="Information Request Response"
                action="Record request response"
                disabled={disabled || !open.length}
                submit={(d) =>
                  prepare('information_response', d, {
                    parent_id: d.get('parent_id'),
                    status: d.get('status'),
                  })
                }
              >
                <div className="form-row">
                  <label>
                    Open request
                    <select name="parent_id" required>
                      {open.map((r) => (
                        <option key={r.id} value={r.id}>
                          Revision {r.revision} ·{' '}
                          {r.payload?.category
                            ? label(r.payload.category)
                            : 'Source changed — content withheld'}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Request status
                    <select name="status">
                      <option value="resolved">
                        Resolved with supporting record
                      </option>
                      <option value="cancelled">
                        Cancelled with rationale
                      </option>
                    </select>
                  </label>
                </div>
                <p className="hint">
                  Resolving requires a linked supporting record.
                </p>
              </Form>
            )}
            {chosen === 'finding_review' && (
              <div className="case-action" aria-label="Review Findings">
                <p className="muted">
                  Offline simulation · Accepting a finding for consideration
                  does not establish criminal activity, approve a SAR or resolve
                  the case.
                </p>
                <div className="actions">
                  <button
                    onClick={() => void loadFindings()}
                    disabled={disabled}
                  >
                    Load my verified simulated findings
                  </button>
                  <a href={`#/cases/${id}/investigation`}>
                    Open AI Investigation
                  </a>
                </div>
                {draft && (
                  <Form
                    title="Finding Review Decision"
                    action="Record finding review"
                    disabled={disabled}
                    submit={(d) =>
                      prepare('finding_review', d, {
                        draft_run_id: draft.draft_run_id,
                        reference_id: d.get('reference_id'),
                        expected_draft_sha256: draft.content_sha256,
                        decision: d.get('decision'),
                      })
                    }
                  >
                    <div className="form-row">
                      <label>
                        Simulated finding
                        <select name="reference_id">
                          {draft.findings.map((r, i) => (
                            <option key={r.reference_id} value={r.reference_id}>
                              {i + 1}. {label(r.claim_type)} ·{' '}
                              {r.reference_id.slice(0, 8)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Review decision
                        <select name="decision">
                          {[
                            'accept_for_consideration',
                            'reject',
                            'defer',
                            'further_investigation',
                          ].map((v) => (
                            <option key={v} value={v}>
                              {label(v)}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                  </Form>
                )}
              </div>
            )}
            {chosen === 'escalation' && (
              <Form
                title="Supervisor Escalation"
                action="Request supervisor review"
                disabled={disabled || page.pending_escalations > 0}
                submit={(d) => prepare('escalation', d)}
              >
                <p className="hint">
                  Record why independent supervisory review is required.
                </p>
              </Form>
            )}
            {chosen === 'supervisor_response' && (
              <Form
                title="Supervisor Review"
                action="Review supervisor response"
                disabled={disabled || !escalations.length}
                submit={(d) =>
                  prepare('supervisor_response', d, {
                    parent_id: d.get('parent_id'),
                    decision: d.get('decision'),
                    proposed_outcome: d.get('proposed_outcome'),
                  })
                }
              >
                <div className="form-row">
                  <label>
                    Pending escalation
                    <select name="parent_id" required>
                      {escalations.map((r) => (
                        <option key={r.id} value={r.id}>
                          Revision {r.revision} · {r.author}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Supervisor decision
                    <select name="decision">
                      <option value="return_for_investigation">
                        Return for additional investigation
                      </option>
                      <option value="approve_resolution">
                        Approve proposed internal outcome
                      </option>
                    </select>
                  </label>
                  <label>
                    Proposed outcome
                    <select name="proposed_outcome">
                      {page.allowed_resolutions.map((v) => (
                        <option key={v} value={v}>
                          {label(v)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <p className="hint">
                  Self-approval is prohibited. Approval requires completed
                  casework and current verified findings.
                </p>
              </Form>
            )}
            {chosen === 'resolution' && approved && (
              <Form
                title="Case Resolution"
                action="Review final case resolution"
                disabled={disabled}
                submit={(d) =>
                  prepare('resolution', d, {
                    parent_id: approved.id,
                    outcome: approved.payload!.proposed_outcome,
                    confirmed: true,
                  })
                }
              >
                <p>
                  Approved internal outcome:{' '}
                  {label(approved.payload!.proposed_outcome!)}.
                </p>
                <p className="hint">
                  Final outcomes are internal synthetic-workflow decisions. They
                  provide no regulatory filing approval.
                </p>
              </Form>
            )}
            {linked && chosen !== 'link' && (
              <p className="hint">
                Linked record: {label(linked.kind)}{' '}
                {linked.record_version_id.slice(0, 8)}
              </p>
            )}
          </section>
          <details
            className="panel disclosure casework-history"
            open={entries.length > 0}
            aria-label="Casework Activity History"
          >
            <summary>Casework history · {page.total} entries</summary>
            {entries.length ? (
              <ol className="human-history compact-timeline">
                {entries.map((r) => (
                  <li key={r.id}>
                    <div className="timeline-head">
                      <strong>{label(r.kind)}</strong>
                      <StatusBadge
                        value={
                          r.payload?.status ??
                          r.payload?.decision ??
                          'submitted'
                        }
                      />
                      <span className="muted">
                        {r.author} ·{' '}
                        <Timestamp value={r.recorded_at} relative />
                      </span>
                    </div>
                    {r.payload ? (
                      <>
                        {/* Analyst-authored text is shown verbatim and is exempt from display rules. */}
                        <p className="human-rationale" data-ui-guard-skip>
                          {r.payload.rationale}
                        </p>
                        {(r.payload.outcome ||
                          r.payload.category ||
                          r.binding?.finding) && (
                          <p className="hint">
                            {r.payload.outcome &&
                              `Internal outcome: ${label(r.payload.outcome)}`}
                            {r.payload.category &&
                              `${label(r.payload.category)} · ${label(
                                r.payload.responsible_party ?? 'not_recorded',
                              )} · Due ${r.payload.due_date ?? 'not set'}`}
                            {r.binding?.finding &&
                              `Offline simulation · ${label(r.binding.finding.claim_type)} · original finding preserved`}
                          </p>
                        )}
                        {r.payload.supporting_records.length > 0 && (
                          <div className="actions">
                            {r.payload.supporting_records.map((ref) => (
                              <button
                                key={ref.record_version_id}
                                className="small"
                                onClick={() => {
                                  setSelectedRecord(ref.record_version_id);
                                  setRecordDetail(null);
                                  setAction('link');
                                }}
                              >
                                Select supporting {label(ref.kind)}{' '}
                                {ref.record_version_id.slice(0, 8)}
                              </button>
                            ))}
                          </div>
                        )}
                      </>
                    ) : (
                      <p className="notice">
                        Content withheld because source evidence or access
                        changed.
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            ) : (
              <p>No submitted human casework yet.</p>
            )}
            {page.total > 20 && (
              <div className="pagination">
                <button
                  disabled={!offset || busy}
                  onClick={() => setOffset(Math.max(0, offset - 20))}
                >
                  Previous casework
                </button>
                <button
                  disabled={offset + 20 >= page.total || busy}
                  onClick={() => setOffset(offset + 20)}
                >
                  Next casework
                </button>
              </div>
            )}
          </details>
          <AuditDetails>
            <AuditList>
              <dt>Casework revision</dt>
              <dd>{page.revision}</dd>
              <CopyValue
                label="Evidence snapshot"
                value={context.snapshot.sha256}
              />
            </AuditList>
            {entries.length > 0 && (
              <ul className="audit-events">
                {entries.map((r) => (
                  <li key={r.id}>
                    {label(r.kind)} · revision {r.revision} ·{' '}
                    {utcText(r.recorded_at)} · case{' '}
                    {r.binding?.case_version ?? '–'} · evidence{' '}
                    {r.binding?.evidence_revision ?? '–'} · access{' '}
                    {r.binding?.access_revision ?? '–'} · {r.content_sha256}
                  </li>
                ))}
              </ul>
            )}
          </AuditDetails>
        </>
      )}
      {confirmation && (
        <div
          ref={dialogRef}
          className="human-confirm panel"
          role="dialog"
          aria-modal="true"
          aria-label="Confirm human decision"
          onKeyDown={(e) => {
            if (e.key === 'Escape' && !busy) {
              e.preventDefault();
              setConfirmation(null);
            }
            if (e.key === 'Tab') {
              const buttons = [
                ...e.currentTarget.querySelectorAll<HTMLButtonElement>(
                  'button:not(:disabled)',
                ),
              ];
              const first = buttons[0],
                last = buttons[buttons.length - 1];
              if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last?.focus();
              } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first?.focus();
              }
            }
          }}
        >
          <h3>Confirm human decision</h3>
          <p>
            {label(confirmation.kind)} ·{' '}
            {label(String(confirmation.outcome ?? confirmation.decision))}
          </p>
          <p className="human-rationale">{String(confirmation.rationale)}</p>
          <p>
            This creates an immutable human decision. No SAR or external filing
            is performed.
          </p>
          <button onClick={() => setConfirmation(null)} disabled={busy}>
            Cancel decision
          </button>
          <button
            className="primary"
            disabled={busy}
            onClick={() => void send(confirmation).catch(() => {})}
          >
            Confirm and record decision
          </button>
        </div>
      )}
    </section>
  );
}

export function SupervisorQueue({ api }: { api: HumanFactory }) {
  const [queue, setQueue] = useState<Awaited<
    ReturnType<ReturnType<HumanFactory>['queue']>
  > | null>(null);
  const [error, setError] = useState(''),
    [offset, setOffset] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    async function load() {
      setQueue(null);
      setError('');
      await api(c.signal)
        .queue(offset)
        .then((v) => {
          if (!c.signal.aborted) setQueue(v);
        })
        .catch((e) => {
          if (!c.signal.aborted) setError(message(e));
        });
    }
    void load();
    return () => c.abort();
  }, [api, offset]);
  return (
    <>
      <PageHeader title="Review Queue" />
      <section className="panel review-queue">
        {error ? (
          <p role="alert">{error}</p>
        ) : !queue ? (
          <p role="status">Loading review queue…</p>
        ) : !queue.items.length ? (
          <div className="state">
            <h2>No escalations waiting</h2>
            <p className="muted">
              Cases escalated for supervisor review will appear here.
            </p>
          </div>
        ) : (
          <>
            <table className="compact-table queue-table">
              <caption className="sr-only">
                Escalations waiting for supervisor review
              </caption>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Escalated by</th>
                  <th>Waiting</th>
                </tr>
              </thead>
              <tbody>
                {queue.items.map((r) => (
                  <tr
                    key={r.escalation_id}
                    className="row-link"
                    onClick={() => {
                      window.location.hash = `/cases/${r.case_id}/casework`;
                    }}
                  >
                    <td className="case-id">
                      <a
                        href={`#/cases/${r.case_id}/casework`}
                        aria-label={`Review case ${r.case_id.slice(0, 8)}`}
                      >
                        {r.case_id.slice(0, 8)}
                      </a>
                    </td>
                    <td>{r.author}</td>
                    <td>
                      <Timestamp value={r.recorded_at} relative />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {queue.total > 20 && (
              <div className="pager">
                <span>{queue.total} escalations</span>
                <div>
                  <button
                    disabled={!offset}
                    onClick={() => setOffset(Math.max(0, offset - 20))}
                  >
                    Previous
                  </button>
                  <button
                    disabled={offset + 20 >= queue.total}
                    onClick={() => setOffset(offset + 20)}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </>
  );
}
