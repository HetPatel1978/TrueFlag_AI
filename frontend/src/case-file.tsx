/** Case-file layout: compact header with step tabs, main story column and a sticky right rail. */
import type { ReactNode } from 'react';
import { label, type User } from './api';
import type { WorkflowCase } from './workflow-api';
import { AuditList, CopyValue, MissingLine, Timestamp } from './display';
import { scorePercent, shortId } from './format';
import { displayLabel } from './terminology';
import { StatusBadge } from './ui';

export function assigneeName(record: WorkflowCase, user: User): string {
  if (record.assigned_investigator) return record.assigned_investigator;
  if (record.assigned_to === user.id) return user.username;
  return record.assigned_to ? 'Assigned' : 'Unassigned';
}

export function CaseHeader({
  record,
  tabs,
}: {
  record: WorkflowCase;
  tabs: ReactNode;
}) {
  return (
    <header className="case-header">
      <div className="case-title-row">
        <h1>Case {shortId(record.id)}</h1>
        <StatusBadge value={record.priority} />
        <StatusBadge value={record.status} />
      </div>
      <div className="case-step-tabs">{tabs}</div>
    </header>
  );
}

/**
 * Read-only case summary. Score and recommendation appear only on tabs whose main column
 * does not already show them; the "not proof" caveat travels with the score.
 * Below 1400px the rail is a one-row summary bar above the main column.
 */
export function CaseRail({
  record,
  user,
  missing,
  decisionsAvailable,
  reassign,
  showScore,
}: {
  record: WorkflowCase;
  user: User;
  missing: string[] | null;
  decisionsAvailable: boolean;
  reassign?: ReactNode;
  showScore: boolean;
}) {
  const scored =
    record.assessment_score !== null && record.assessment_score !== undefined;
  return (
    <aside className="case-rail sticky-rail" aria-label="Case summary">
      {showScore && (
        <div className="rail-score">
          <span className="rail-label">Risk score</span>
          <strong
            title={
              scored ? 'Model signal for analyst review, not proof' : undefined
            }
          >
            {scored ? scorePercent(record.assessment_score) : '–'}
          </strong>
          <span className="muted rail-caveat">
            {scored
              ? 'Model signal for analyst review, not proof'
              : 'Not assessed yet'}
          </span>
        </div>
      )}
      <dl className="rail-facts">
        {showScore && (
          <div className="rail-rec">
            <dt>Recommendation</dt>
            <dd
              title={
                record.review_recommendation
                  ? displayLabel(record.review_recommendation)
                  : undefined
              }
            >
              {record.review_recommendation
                ? displayLabel(record.review_recommendation)
                : 'Not assessed'}
            </dd>
          </div>
        )}
        <div className="rail-priority">
          <dt>Priority</dt>
          <dd>
            <StatusBadge value={record.priority} />
          </dd>
        </div>
        <div className="rail-assignee-row">
          <dt>Assignee</dt>
          <dd className="rail-assignee">
            <span>{assigneeName(record, user)}</span>
            {reassign}
          </dd>
        </div>
        <div>
          <dt>Decision</dt>
          <dd>
            {record.disposition ? label(record.disposition) : 'Not recorded'}
          </dd>
        </div>
      </dl>
      {missing === null ? (
        <p className="muted rail-missing">Checking evidence…</p>
      ) : (
        <MissingLine items={missing.map((m) => label(m))} />
      )}
      {decisionsAvailable && (
        <a
          className="button primary rail-action"
          href={`#/cases/${record.id}/casework/decide`}
        >
          Record decision
        </a>
      )}
    </aside>
  );
}

/** Case references shown at the top of the page's single Audit details section. */
export function CaseAudit({ record }: { record: WorkflowCase }) {
  return (
    <AuditList>
      <CopyValue label="Case ID" value={record.id} />
      <CopyValue label="Alert reference" value={record.source_id} />
      <CopyValue label="Alert ID" value={record.alert_id} />
      <dt>Received</dt>
      <dd>
        <Timestamp value={record.created_at} />
      </dd>
      <dt>Case version</dt>
      <dd>{record.version}</dd>
    </AuditList>
  );
}
