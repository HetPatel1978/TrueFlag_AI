import { useEffect, useRef, useState } from 'react';
import { ApiError, message } from './api';
import { AuditDetails, Timestamp } from './display';
import { formatDate, utcText } from './format';
import type {
  Activity,
  ActivityPage,
  Directory,
  WorkflowCase,
  WorkflowFactory,
} from './workflow-api';
import './case-workflows.css';

export function AssignmentControl({
  record,
  api,
  changed,
}: {
  record: WorkflowCase;
  api: WorkflowFactory;
  changed: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        className="small"
        aria-label={
          record.assigned_to ? 'Reassign investigator' : 'Assign investigator'
        }
        onClick={() => setOpen(true)}
        disabled={record.status === 'closed'}
      >
        {record.assigned_to ? 'Reassign' : 'Assign'}
      </button>
      {open && (
        <AssignmentDialog
          record={record}
          api={api}
          close={() => setOpen(false)}
          changed={changed}
        />
      )}
    </>
  );
}
function AssignmentDialog({
  record,
  api,
  close,
  changed,
}: {
  record: WorkflowCase;
  api: WorkflowFactory;
  close: () => void;
  changed: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const control = useRef<AbortController | null>(null);
  const submitting = useRef(false);
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [directory, setDirectory] = useState<Directory | null>(null);
  const [selected, setSelected] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    control.current = controller;
    const focused = document.activeElement;
    const modal = dialog.current;
    modal?.showModal();
    return () => {
      controller.abort();
      modal?.close();
      if (focused instanceof HTMLElement) focused.focus();
    };
  }, []);
  function dismiss() {
    dialog.current?.close();
    close();
  }
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void api(controller.signal)
        .directory(record.id, search, offset)
        .then((value) => {
          if (controller.signal.aborted) return;
          if (value.case_version !== record.version) {
            setBlocked(true);
            setError('Assignment changed. Refresh the case before continuing.');
            return;
          }
          setDirectory(value);
        })
        .catch((failure) => {
          if (!controller.signal.aborted) setError(message(failure));
        });
    }, 300);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [api, record.id, record.version, search, offset, revision]);
  function reload(searchValue: string, page: number) {
    setDirectory(null);
    setSelected('');
    setError('');
    setSearch(searchValue);
    setOffset(page);
  }
  async function save() {
    const signal = control.current?.signal;
    if (!signal || submitting.current || blocked || !directory || !selected)
      return;
    submitting.current = true;
    setBusy(true);
    setError('');
    try {
      await api(signal).assign(
        record.id,
        record.version,
        selected === '__unassigned' ? null : selected,
      );
      if (!signal.aborted) changed();
    } catch (failure) {
      if (!signal.aborted) {
        setError(message(failure));
        // A lost response may have committed. Require a fresh server version before another mutation.
        setBlocked(true);
        setSelected('');
      }
    } finally {
      submitting.current = false;
      if (!signal.aborted) setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="assignment-dialog"
      aria-labelledby="assignment-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) dismiss();
      }}
    >
      <h2 id="assignment-title">
        {record.assigned_to ? 'Reassign investigator' : 'Assign investigator'}
      </h2>
      <p className="muted">
        Current: {record.assigned_investigator ?? 'Unassigned'}. Changes are
        recorded in Activity History.
      </p>
      <label htmlFor="investigator-search">Find active analyst</label>
      <input
        id="investigator-search"
        maxLength={100}
        value={search}
        disabled={busy || blocked}
        onChange={(e) => reload(e.target.value, 0)}
      />
      {!directory && !error && (
        <p role="status">Loading eligible investigators…</p>
      )}
      {directory && (
        <>
          <label htmlFor="investigator">Assigned Investigator</label>
          <select
            id="investigator"
            value={selected}
            disabled={busy || blocked}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">Choose an investigator</option>
            <option value="__unassigned">Leave unassigned</option>
            {directory.items.map((person) => (
              <option value={person.id} key={person.id}>
                {person.username}
              </option>
            ))}
          </select>
          <p className="hint">
            {directory.total} matching active analysts. Only authorized accounts
            are listed.
          </p>
          <div className="pager">
            <button
              disabled={busy || blocked || !offset}
              onClick={() => reload(search, offset - 20)}
            >
              Previous investigators
            </button>
            <button
              disabled={
                busy ||
                blocked ||
                offset + 20 >= directory.total ||
                offset + 20 > 1000
              }
              onClick={() => reload(search, offset + 20)}
            >
              More investigators
            </button>
          </div>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {error && !blocked && (
        <button
          onClick={() => {
            setError('');
            setRevision((n) => n + 1);
          }}
        >
          Retry lookup
        </button>
      )}
      <div className="dialog-actions">
        <button disabled={busy} onClick={dismiss}>
          Cancel
        </button>
        {blocked ? (
          <button className="primary" onClick={changed}>
            Refresh case
          </button>
        ) : (
          <button
            className="primary"
            disabled={busy || !directory || !selected}
            onClick={() => {
              void save();
            }}
          >
            {busy ? 'Saving assignment…' : 'Confirm assignment'}
          </button>
        )}
      </div>
    </dialog>
  );
}

const EVENTS: Record<string, string> = {
  casework_note: 'Investigation note submitted',
  casework_information_request: 'Additional information requested',
  casework_information_response: 'Information request response recorded',
  casework_finding_review: 'Human finding review recorded',
  casework_escalation: 'Supervisor review requested',
  casework_supervisor_response: 'Supervisor response recorded',
  casework_resolution: 'Human case resolution recorded',
  alert_ingested: 'Alert ingested',
  assignment_changed: 'Assignment changed',
  assessment_completed: 'Assessment and review recommendation saved',
  evidence_linked: 'Supporting evidence linked',
  evidence_revised: 'Evidence revision recorded',
  evidence_access_granted: 'Evidence access granted',
  evidence_access_revoked: 'Evidence access revoked',
  evidence_records_revoked: 'Evidence records revoked',
  assessment_enqueued: 'Assessment registered',
  assessment_requested: 'Assessment requested',
  assessment_processing: 'Assessment processing',
  assessment_retry_scheduled: 'Assessment retry scheduled',
  assessment_failed: 'Assessment failed',
  assessment_processing_completed: 'Assessment processing completed',
  summary_requested: 'Evidence summary requested',
  summary_processing: 'Evidence summary processing',
  summary_published: 'Evidence summary saved',
  summary_attempt_failed: 'Evidence summary processing attempt failed',
  summary_invalidated: 'Evidence summary invalidated',
  ai_investigation_requested: 'AI investigation requested',
  ai_investigation_approved: 'AI request approved',
  ai_investigation_processing: 'AI investigation processing',
  ai_investigation_completed: 'AI investigation completed',
  ai_investigation_failed: 'AI investigation not completed',
};
/** Past events describe what happened, not a current processing state. */
const HISTORICAL_OUTCOME: Record<string, string> = {
  pending: 'requested',
  running: 'started',
};
export function ActivityHistory({
  record,
  api,
}: {
  record: WorkflowCase;
  api: WorkflowFactory;
}) {
  const [page, setPage] = useState<ActivityPage | null>(null);
  const [category, setCategory] = useState('all');
  // Number of 20-event pages shown; "Show older" adds one. Updates reload all shown pages.
  const [pages, setPages] = useState(1);
  const [older, setOlder] = useState(false);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    let attempts = 0;
    async function load() {
      setError('');
      setPaused(false);
      try {
        const client = api(controller.signal);
        const loaded: ActivityPage[] = [];
        for (let n = 0; n < pages; n++) {
          const value = await client.activity(record.id, category, n * 20);
          if (controller.signal.aborted) return;
          if (value.case_version !== record.version) {
            setPage(null);
            setError('Case changed. Refresh the case before viewing history.');
            return;
          }
          loaded.push(value);
          if ((n + 1) * 20 >= value.total) break;
        }
        const seen = new Set<string>();
        const items = loaded
          .flatMap((value) => value.items)
          .filter((item) => !seen.has(item.id) && !!seen.add(item.id));
        setPage({ ...loaded[loaded.length - 1], offset: 0, items });
        setOlder(false);
      } catch (failure) {
        if (controller.signal.aborted) return;
        setPage(null);
        setOlder(false);
        setError(message(failure));
        if (
          failure instanceof ApiError &&
          [401, 403, 404, 429].includes(failure.status)
        )
          return;
      }
      if (++attempts < 30)
        timer = window.setTimeout(() => {
          void load();
        }, 15000);
      else setPaused(true);
    }
    void load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [api, record.id, record.version, category, pages, revision]);
  const groups = page ? groupActivity(page.items) : [];
  const days = groupByDay(groups);
  return (
    <section className="panel activity-panel">
      <div className="section-heading">
        <h2>Activity History</h2>
        <label className="compact-filter">
          <span className="sr-only">Event category</span>
          <select
            id="activity-category"
            aria-label="Event category"
            value={category}
            onChange={(e) => {
              setPage(null);
              setCategory(e.target.value);
              setPages(1);
            }}
          >
            <option value="all">All activity</option>
            <option value="assignment">Assignments only</option>
          </select>
        </label>
      </div>
      {error ? (
        <div role="alert" className="state">
          <p>{error}</p>
          <button onClick={() => setRevision((n) => n + 1)}>
            Retry activity
          </button>
        </div>
      ) : !page ? (
        <p className="state" role="status">
          Loading activity…
        </p>
      ) : !page.items.length ? (
        <div className="state">
          <h3>No recorded activity</h3>
          <p>Missing entries do not establish that no activity occurred.</p>
        </div>
      ) : (
        days.map(([day, entries]) => (
          <section key={day} className="activity-day" aria-label={day}>
            <h3>{day}</h3>
            <ol className="activity-list timeline">
              {entries.map((group) => {
                const item = group.last;
                return (
                  <li key={item.id}>
                    <span
                      className={`activity-icon ${group.family}`}
                      aria-hidden="true"
                    >
                      {FAMILY_ICON[group.family]}
                    </span>
                    <strong>
                      {EVENTS[item.event_type] ?? 'Recorded event'}
                    </strong>
                    {item.assignment_change && (
                      <span className="muted">
                        {item.assignment_change === 'reassigned'
                          ? 'Investigator reassigned'
                          : item.assignment_change === 'assigned'
                            ? 'Investigator assigned'
                            : 'Case left unassigned'}
                      </span>
                    )}
                    <span className="muted">
                      {actorName(item.actor)} ·{' '}
                      <Timestamp value={item.recorded_at} relative />
                    </span>
                    {group.steps.length > 1 && (
                      <details className="inline-disclosure activity-steps">
                        <summary>{group.steps.length} steps</summary>
                        <ol>
                          {group.steps.map((step) => (
                            <li key={step.id}>
                              {EVENTS[step.event_type] ?? 'Recorded event'} ·{' '}
                              {actorName(step.actor)} ·{' '}
                              <Timestamp value={step.recorded_at} />
                            </li>
                          ))}
                        </ol>
                      </details>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>
        ))
      )}
      {page && page.items.length < page.total && pages * 20 <= 1000 && (
        <div className="show-older">
          <button
            disabled={older}
            onClick={() => {
              setOlder(true);
              setPages((n) => n + 1);
            }}
          >
            {older ? 'Loading older activity…' : 'Show older'}
          </button>
          <span className="muted">
            {page.items.length} of {page.total} events
          </span>
        </div>
      )}
      {paused && (
        <p role="status">
          Automatic activity updates paused. Use the refresh button in the top
          bar to resume.
        </p>
      )}
      <AuditDetails>
        <p>
          Recorded timestamps can reflect clock corrections; they do not
          guarantee causal ordering. Only supported, authorized event categories
          are shown.
          {page ? ` ${page.total} recorded events.` : ''}
        </p>
        {page && page.items.length > 0 && (
          <ul className="audit-events">
            {page.items.map((item) => {
              const versions = [
                ['Case version', item.case_version],
                ['Assessment version', item.assessment_version],
                ['Evidence revision', item.evidence_revision],
                ['Access revision', item.access_revision],
              ]
                .filter(([, v]) => v !== null && v !== undefined)
                .map(([name, v]) => `${name} ${v}`);
              return (
                <li key={item.id}>
                  {EVENTS[item.event_type] ?? 'Recorded event'} ·{' '}
                  {HISTORICAL_OUTCOME[item.outcome] ?? item.outcome} ·{' '}
                  {utcText(item.recorded_at)}
                  {versions.length > 0 && ` · ${versions.join(' · ')}`}
                  {item.duplicate_records
                    ? ` (${item.duplicate_records} duplicate record${item.duplicate_records === 1 ? '' : 's'})`
                    : ''}
                </li>
              );
            })}
          </ul>
        )}
      </AuditDetails>
    </section>
  );
}

type Family = 'ai' | 'summary' | 'assessment' | 'casework' | 'case';
const FAMILY_ICON: Record<Family, string> = {
  ai: '◆',
  summary: '▤',
  assessment: '◔',
  casework: '✎',
  case: '•',
};
const START_EVENTS = new Set([
  'ai_investigation_requested',
  'summary_requested',
  'assessment_requested',
  'assessment_enqueued',
]);
const END_EVENTS = new Set([
  'ai_investigation_completed',
  'ai_investigation_failed',
  'summary_published',
  'summary_invalidated',
  'assessment_completed',
  'assessment_failed',
]);
function familyOf(type: string): Family {
  if (type.startsWith('ai_investigation_')) return 'ai';
  if (type.startsWith('summary_')) return 'summary';
  if (type.startsWith('assessment_')) return 'assessment';
  if (type.startsWith('casework_')) return 'casework';
  return 'case';
}
export type ActivityGroup = {
  family: Family;
  steps: Activity[];
  last: Activity;
};

/**
 * Folds the internal sub-events of one request (requested → processing → saved) into one
 * line, newest first. Grouping is display only; every event stays listed in Audit details.
 */
export function groupActivity(items: Activity[]): ActivityGroup[] {
  const chronological = [...items].sort(
    (a, b) =>
      a.recorded_at.localeCompare(b.recorded_at) || a.id.localeCompare(b.id),
  );
  const groups: ActivityGroup[] = [];
  const open = new Map<Family, ActivityGroup>();
  for (const item of chronological) {
    const family = familyOf(item.event_type);
    if (family === 'case' || family === 'casework') {
      groups.push({ family, steps: [item], last: item });
      continue;
    }
    let group = open.get(family);
    // A request starts a new line unless the open line is still unfinished and has not
    // seen this same step (sub-events can be recorded slightly out of order).
    const startsNew =
      !group ||
      (START_EVENTS.has(item.event_type) &&
        group.steps.some(
          (step) =>
            END_EVENTS.has(step.event_type) ||
            step.event_type === item.event_type,
        ));
    if (startsNew || !group) {
      group = { family, steps: [], last: item };
      groups.push(group);
      open.set(family, group);
    }
    group.steps.push(item);
    // The line is titled by its outcome event when it has one; otherwise by the newest step.
    if (
      END_EVENTS.has(item.event_type) ||
      !END_EVENTS.has(group.last.event_type)
    )
      group.last = item;
  }
  return groups.reverse();
}

function dayLabel(value: string, now = new Date()) {
  const date = new Date(value);
  const key = (d: Date) => d.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (key(date) === key(now)) return 'Today';
  if (key(date) === key(yesterday)) return 'Yesterday';
  return formatDate(date);
}
function groupByDay(groups: ActivityGroup[]): [string, ActivityGroup[]][] {
  const days = new Map<string, ActivityGroup[]>();
  for (const group of groups) {
    const day = dayLabel(group.last.recorded_at);
    days.set(day, [...(days.get(day) ?? []), group]);
  }
  return [...days.entries()];
}
const actorName = (actor: Activity['actor']) =>
  actor === 'you' ? 'You' : actor === 'system' ? 'System' : 'Another user';
