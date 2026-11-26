/** Shared display pieces for the analyst-first layout. Display only; no data is changed. */
import { createContext, useContext, useState, type ReactNode } from 'react';
import {
  exactLocalTime,
  formatDateTime,
  relativeTime,
  utcText,
} from './format';

export const FOOTER_TEXT =
  'Synthetic data · Academic demo · Not regulatory guidance · Human review required · No automatic case actions';

/** The single app-wide disclaimer line. */
export function AppFooter() {
  return (
    <footer className="app-footer" data-ui-guard-skip>
      {FOOTER_TEXT}
    </footer>
  );
}

/** Page-level references (e.g. the case IDs) prepended to the page's Audit details. */
export const PageAudit = createContext<ReactNode>(null);

/** The one collapsed technical section per page. Its text is exempt from the main-view rules. */
export function AuditDetails({
  children,
  summary = 'Audit details',
}: {
  children: ReactNode;
  summary?: string;
}) {
  const page = useContext(PageAudit);
  return (
    <details className="panel disclosure audit-details" data-ui-guard-skip>
      <summary>{summary}</summary>
      <div className="audit-body">
        {page}
        {children}
      </div>
    </details>
  );
}

/** A labelled exact value with a copy button (IDs, hashes, policy strings). */
export function CopyValue({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  const [copied, setCopied] = useState(false);
  if (value === null || value === undefined || value === '') return null;
  return (
    <>
      <dt>{label}</dt>
      <dd className="copy-value">
        <code>{value}</code>
        <button
          type="button"
          className="link-button"
          aria-label={`Copy ${label}`}
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1500);
            } catch {
              /* clipboard unavailable: the value stays selectable */
            }
          }}
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </dd>
    </>
  );
}

export function AuditList({ children }: { children: ReactNode }) {
  return <dl className="audit-list">{children}</dl>;
}

export function VerifiedBadge({
  title = 'Source, reference and numeric checks passed',
}) {
  return (
    <span className="badge tone-success" title={title}>
      ✓ Verified
    </span>
  );
}

/** One coverage badge per page, with the limitation list in a single expandable. */
export function CoverageBadge({
  complete,
  limitations = [],
  verified = false,
}: {
  complete: boolean;
  limitations?: ReactNode[];
  verified?: boolean;
}) {
  const text = `${verified ? '✓ Verified · ' : ''}${complete ? 'Complete for period' : 'Partial coverage'}`;
  return (
    <span className="coverage-badge">
      <span className={`badge ${complete ? 'tone-success' : 'tone-warning'}`}>
        {text}
      </span>
      {limitations.length > 0 && (
        <details className="inline-disclosure">
          <summary>
            {limitations.length} note{limitations.length === 1 ? '' : 's'}
          </summary>
          <ul>
            {limitations.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </details>
      )}
    </span>
  );
}

/** One "⚠ Missing: …" line per card instead of a "Not recorded" row per field. */
export function MissingLine({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <p className="missing-line">
      <span aria-hidden="true">⚠ </span>Missing: {items.join(', ')}
    </p>
  );
}

/** Local date/time with the exact UTC value in a tooltip. `relative` for lists and history. */
export function Timestamp({
  value,
  relative = false,
}: {
  value: string | null | undefined;
  relative?: boolean;
}) {
  if (!value) return <span className="muted">Not available</span>;
  return (
    <time
      dateTime={value}
      className={relative ? 'has-tip' : undefined}
      title={
        relative
          ? `${exactLocalTime(value)} · ${utcText(value)}`
          : `${formatDateTime(value)} · ${utcText(value)}`
      }
    >
      {relative ? relativeTime(value) : formatDateTime(value)}
    </time>
  );
}

export function KpiTile({
  label,
  value,
  href,
}: {
  label: string;
  value: number | null;
  href?: string;
}) {
  const body = (
    <>
      <span className="kpi-label">{label}</span>
      <strong className="kpi-value">
        {value === null ? '–' : value.toLocaleString()}
      </strong>
    </>
  );
  return href ? (
    <a className="kpi-tile" href={href}>
      {body}
    </a>
  ) : (
    <div className="kpi-tile">{body}</div>
  );
}

/** Small "?" affordance whose explanation lives in a tooltip. */
export function InfoTip({ text }: { text: string }) {
  return (
    <span className="info-tip" title={text} aria-label={text} role="img">
      ⓘ
    </span>
  );
}
