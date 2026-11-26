/** Admin status card for the Anthropic provider (read-only aggregate; no credential is read). */
import { useEffect, useState } from 'react';
import { message, request } from './api';
import { money } from './format';

export type AnthropicUsage = {
  provider: 'anthropic';
  status: 'available' | 'approval_policy_missing' | 'disabled';
  model: string | null;
  runs_investigations: boolean;
  requests_this_month: number;
  requests_total?: number;
  spent_this_month_usd: string;
  spent_total_usd: string;
  cumulative_cap_usd: string | null;
  reservation_usd: string | null;
  approval_rule: string;
};

const STATUS: Record<AnthropicUsage['status'], [string, string]> = {
  available: ['Available', 'tone-success'],
  approval_policy_missing: ['Approval policy missing', 'tone-warning'],
  disabled: ['Disabled', 'tone-muted'],
};

const decimal = /^\d{1,12}(?:\.\d{1,28})?$/;
function valid(v: AnthropicUsage): boolean {
  return (
    v?.provider === 'anthropic' &&
    v.status in STATUS &&
    typeof v.runs_investigations === 'boolean' &&
    Number.isSafeInteger(v.requests_this_month) &&
    (v.requests_total === undefined ||
      Number.isSafeInteger(v.requests_total)) &&
    decimal.test(v.spent_this_month_usd) &&
    decimal.test(v.spent_total_usd) &&
    (v.cumulative_cap_usd === null || decimal.test(v.cumulative_cap_usd)) &&
    typeof v.approval_rule === 'string'
  );
}

export function AnthropicCard({
  token,
  onDenied,
  signal,
}: {
  token: string;
  onDenied: (status: number) => void;
  signal?: AbortSignal;
}) {
  const [usage, setUsage] = useState<AnthropicUsage | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    request<AnthropicUsage>(
      '/api/v1/internal/provider-usage/anthropic',
      {
        headers: { Authorization: `Bearer ${token}` },
        signal: signal
          ? AbortSignal.any([signal, controller.signal])
          : controller.signal,
      },
      onDenied,
    )
      .then((value) => {
        if (controller.signal.aborted) return;
        if (!valid(value)) throw new Error('invalid_provider_view');
        setUsage(value);
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(message(failure));
      });
    return () => controller.abort();
  }, [token, onDenied, signal]);
  const [status, tone] = usage
    ? STATUS[usage.status]
    : ['Loading', 'tone-muted'];
  return (
    <section className="panel provider-card" aria-labelledby="anthropic-title">
      <div className="card-head">
        <h2 id="anthropic-title">Anthropic</h2>
        <span className={`badge ${tone}`}>{status}</span>
        {usage?.runs_investigations && (
          <span className="tag">Runs AI investigations</span>
        )}
      </div>
      {error ? (
        <p role="alert" className="error">
          {error}
        </p>
      ) : !usage ? (
        <p role="status">Loading provider status…</p>
      ) : (
        <>
          <dl className="fact-row">
            <div>
              <dt>Model</dt>
              <dd>{usage.model ?? 'Not configured'}</dd>
            </div>
            <div>
              <dt>Requests</dt>
              <dd>
                {usage.requests_this_month} this month
                {usage.requests_total !== undefined &&
                  ` · ${usage.requests_total} all time`}
              </dd>
            </div>
          </dl>
          <ul className="provider-lines">
            <li>
              <strong>Spend:</strong> {money(usage.spent_this_month_usd, 'USD')}{' '}
              this month · {money(usage.spent_total_usd, 'USD')}
              {usage.cumulative_cap_usd
                ? ` of ${money(usage.cumulative_cap_usd, 'USD')} cap`
                : ''}{' '}
              (all time)
            </li>
            <li title={usage.approval_rule}>
              <strong>Approval:</strong> one named approver per request · No
              automatic retries
            </li>
          </ul>
        </>
      )}
    </section>
  );
}
