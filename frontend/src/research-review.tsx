import { useEffect, useRef, useState } from 'react';
import { ApiError, message } from './api';
import type { InvestigationFactory, ResearchReview } from './investigation-api';
import { money, scorePercent } from './format';

type Props = {
  id: string;
  run: string;
  api: InvestigationFactory;
  invalidate: (error: unknown) => void;
  onApproved: (run: string) => void;
  onClosed: () => void;
  onRefresh: () => void;
};

const time = (value: string) =>
  new Date(value).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

/** AI Request Review: the exact prepared Claude request. Viewing never approves it; only an
 * authorized spending approver's explicit click does, and the server re-verifies everything. */
export function ResearchReviewPanel({
  id,
  run,
  api,
  invalidate,
  onApproved,
  onClosed,
  onRefresh,
}: Props) {
  const [review, setReview] = useState<ResearchReview | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [reload, setReload] = useState(0);
  const lock = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    void api(controller.signal).researchReview!(id, run)
      .then((value) => {
        if (controller.signal.aborted) return;
        setError('');
        setReview(value);
      })
      .catch((failure) => {
        if (controller.signal.aborted) return;
        if (failure instanceof ApiError && failure.status === 401)
          invalidate(failure);
        else setError(message(failure));
      });
    return () => controller.abort();
  }, [api, id, run, reload, invalidate]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  if (!review)
    return (
      <section className="panel" aria-label="AI Request Review">
        <h3>AI Request Review</h3>
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : (
          <p role="status">Preparing the exact request…</p>
        )}
      </section>
    );
  const expired =
    review.phase === 'request_expired' ||
    new Date(review.approve_before).getTime() <= now;
  const changed = review.phase === 'request_changed';
  async function act(kind: 'approve' | 'cancel') {
    if (lock.current || !review) return;
    lock.current = true;
    setBusy(true);
    setError('');
    try {
      if (kind === 'approve') {
        const status = await api().researchApprove!(
          id,
          run,
          review.request_sha256,
          `approve-${run}`,
        );
        onApproved(status.draft_run_id);
      } else {
        await api().researchCancel!(id, run, `cancel-${run}`);
        onClosed();
      }
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401)
        invalidate(failure);
      else {
        setError(
          failure instanceof ApiError && failure.status === 409
            ? 'The evidence snapshot expired or the request changed. Nothing was sent. Refresh the request to review the current one.'
            : failure instanceof ApiError && failure.status === 403
              ? 'You are not authorized to approve AI spending. Nothing was sent.'
              : message(failure),
        );
        setReload((v) => v + 1);
      }
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  const seconds = Math.max(
    0,
    Math.floor((new Date(review.approve_before).getTime() - now) / 1000),
  );
  return (
    <section className="panel ai-request-review" aria-label="AI Request Review">
      <div className="section-heading">
        <div>
          <p className="muted">
            Paid external AI request · nothing has been sent
          </p>
          <h3>AI Request Review</h3>
        </div>
      </div>
      <p role="note" className="notice">
        <strong>{researchStatusText(review.regulatory_status)}</strong>
      </p>
      <dl className="facts">
        <dt>Case</dt>
        <dd>{review.case_id.slice(0, 8)}</dd>
        <dt>Model</dt>
        <dd>{review.model}</dd>
        <dt>Data scope</dt>
        <dd>Synthetic data only</dd>
        <dt>Limits</dt>
        <dd>
          {review.maximum_requests} request, no automatic retries ·{' '}
          {review.max_output_tokens} output tokens · {review.timeout_seconds}s
          timeout
        </dd>
        <dt>Spending reservation</dt>
        <dd>
          ${review.reservation_usd} (spent ${review.spent_usd} of $
          {review.cumulative_cap_usd} cap)
        </dd>
        <dt>Financial evidence</dt>
        <dd>
          {review.financial_facts
            .map(
              (f) =>
                `${money(f.observed_total, f.currency)} across ${f.observed_count} transactions`,
            )
            .join('; ')}{' '}
          · {review.transactions} synthetic transactions
          {review.model_signal
            ? ` · model score ${scorePercent(review.model_signal.score)}`
            : ''}
        </dd>
        <dt>Regulatory sources</dt>
        <dd>
          {review.regulatory_sources
            .map(
              (s) =>
                `31 CFR § ${s.section} (${s.historical_as_of}, research only)`,
            )
            .join('; ')}
        </dd>
        <dt>Missing evidence</dt>
        <dd>{review.missing_evidence.join(', ') || 'None reported'}</dd>
        <dt>Limitations</dt>
        <dd>{review.limitations.join(', ')}</dd>
      </dl>
      {/* Raw request and its hash are audit content: exact, collapsed, exempt from display rules. */}
      <details data-ui-guard-skip>
        <summary>
          Complete request ({review.request_bytes.toLocaleString()} bytes)
        </summary>
        <p className="hash">
          Request SHA-256: <code>{review.request_sha256}</code>
        </p>
        <pre className="request-preview">
          {JSON.stringify(review.request, null, 2)}
        </pre>
      </details>
      {expired || changed ? (
        <div role="status">
          <p className="notice">
            {changed
              ? 'The evidence changed after this request was prepared. It will not be sent.'
              : 'This request expired before approval (evidence is valid for 15 minutes). It will not be sent.'}
          </p>
          <button className="primary" disabled={busy} onClick={onRefresh}>
            Refresh Request
          </button>
        </div>
      ) : review.is_approver ? (
        <div className="review-actions">
          <p role="status">
            Approve before {time(review.approve_before)} ({seconds}s remaining).
          </p>
          <button
            className="primary"
            disabled={busy || !review.can_approve}
            onClick={() => void act('approve')}
          >
            {busy ? 'Submitting…' : 'Approve & Run Once'}
          </button>
          <button disabled={busy} onClick={() => void act('cancel')}>
            Cancel
          </button>
        </div>
      ) : (
        <div role="status">
          <p className="notice">
            <strong>Pending Owner Approval.</strong> Only an authorized spending
            approver can approve this exact request. Nothing has been sent.
          </p>
          <button disabled={busy} onClick={() => void act('cancel')}>
            Cancel
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}

/** Display only: the backend label in sentence case; any other value is shown verbatim. */
function researchStatusText(value: string) {
  return value === 'UNAPPROVED RESEARCH — NOT PRODUCTION REGULATORY GUIDANCE'
    ? 'Unapproved research · Not production regulatory guidance'
    : value;
}
