import type { ReactNode } from 'react';
import { displayLabel } from './terminology';

type IconName =
  | 'cases'
  | 'investigation'
  | 'batch'
  | 'assessment'
  | 'refresh'
  | 'logout'
  | 'chevron'
  | 'shield'
  | 'overview'
  | 'inbox';
const paths: Record<IconName, ReactNode> = {
  cases: (
    <>
      <rect x="3" y="5" width="18" height="15" rx="2" />
      <path d="M8 5V3h8v2M3 11h18M10 11v3h4v-3" />
    </>
  ),
  investigation: (
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m16 16 5 5M8 11l2 2 4-4" />
    </>
  ),
  batch: (
    <>
      <path d="M7 3h10l4 4v14H7zM17 3v5h4M3 7v14h14M10 12h8M10 16h8" />
    </>
  ),
  assessment: (
    <>
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 7v5h-5M4 17v-5h5" />
      <path d="M6.1 6.1A8 8 0 0 1 20 12M17.9 17.9A8 8 0 0 1 4 12" />
    </>
  ),
  logout: (
    <>
      <path d="M9 4H4v16h5M13 8l4 4-4 4M8 12h13" />
    </>
  ),
  chevron: <path d="m9 5 7 7-7 7" />,
  overview: (
    <>
      <rect x="3" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5" />
    </>
  ),
  inbox: (
    <>
      <path d="M3 13h5l1.5 3h5L16 13h5" />
      <path d="M5.5 5h13L21 13v6H3v-6z" />
    </>
  ),
  shield: (
    <>
      <path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6" />
    </>
  ),
};
/** Original line icons, no external font, asset service or icon package. */
export function Icon({ name }: { name: IconName }) {
  return (
    <svg
      className="ui-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {paths[name]}
    </svg>
  );
}
type Tone =
  'open' | 'info' | 'warning' | 'muted' | 'success' | 'danger' | 'processing';
/** One status vocabulary and colour set across the app. */
export const STATUS_VOCABULARY: Readonly<Record<string, [string, Tone]>> =
  Object.freeze({
    open: ['Open', 'open'],
    in_review: ['In review', 'info'],
    awaiting_approval: ['Awaiting approval', 'warning'],
    closed: ['Closed', 'muted'],
    succeeded: ['Completed', 'success'],
    completed: ['Completed', 'success'],
    pending: ['Processing', 'processing'],
    running: ['Processing', 'processing'],
    queued: ['Processing', 'processing'],
    failed: ['Failed', 'danger'],
    high: ['High', 'warning'],
    standard: ['Standard', 'muted'],
  });
export function StatusBadge({ value }: { value: string }) {
  const [text, tone] = STATUS_VOCABULARY[value.toLowerCase()] ?? [
    displayLabel(value),
    'muted',
  ];
  return (
    <span className={`badge ${value.toLowerCase()} tone-${tone}`}>
      <span className="status-dot" aria-hidden="true" />
      {text}
    </span>
  );
}
/** Page title row. `eyebrow` is accepted for compatibility but not shown (no caps labels). */
export function PageHeader({
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        {description && <p className="muted">{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}
