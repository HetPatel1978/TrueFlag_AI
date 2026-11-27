import { useEffect, useState, type ReactNode } from 'react';
import { message, request } from './api';
import { PageHeader } from './ui';
import { ResearchSources } from './regulatory-research';

type Usage = {
  schema_version: 'trueflag.provider-usage.v2';
  state: 'blocked';
  dispatch_allowed: false;
  floor_guaranteed: false;
  financial_policy?: 'prepaid_floor_v2' | 'bounded_probe_v3';
  minimum_balance_usd: string | null;
  safety_buffer_usd: string | null;
  indicative_spending_ceiling_usd: string;
  reported_balance_usd: string | null;
  balance_observed_at: string | null;
  projected_headroom_usd: string | null;
  retained_reservations_usd: string;
  estimated_usage_cost_usd: string;
  inference_attempts: number;
  inference_attempts_this_month?: number;
  estimated_usage_cost_this_month_usd?: string;
  unreconciled_attempts: number;
  refresh_enabled: boolean;
  blocked_reasons: string[];
  last_refresh_status?: string;
};
const reasons: Record<string, string> = {
  financial_authorization_unavailable:
    'Financial authorization could not be verified.',
  current_balance_unverified: 'Current USD balance is unverified.',
  balance_stale_or_invalid: 'The balance observation is stale or invalid.',
  balance_floor_reached:
    'The balance has reached the protected floor and buffer.',
  request_charge_bound_unverified: 'Maximum request charges are unverified.',
  billing_settlement_unverified: 'Provider billing settlement is unverified.',
  outside_account_usage_unbounded: 'Usage outside TrueFlag cannot be reserved.',
  provider_atomic_floor_unverified:
    'An account-wide provider spending floor is unverified.',
  clock_health_unavailable: 'Trusted time verification is unavailable.',
  provider_disabled: 'Live provider execution is disabled.',
  provider_contract_unverified: 'Live response compatibility is unverified.',
  probe_bootstrap_unverified:
    'The exact-payload compatibility probe is not ready.',
};
const amount = (value: string | null) =>
  value === null ? 'Unverified' : `$${value}`;
function valid(value: Usage): boolean {
  return (
    value.schema_version === 'trueflag.provider-usage.v2' &&
    value.state === 'blocked' &&
    value.dispatch_allowed === false &&
    value.floor_guaranteed === false &&
    [
      'indicative_spending_ceiling_usd',
      'retained_reservations_usd',
      'estimated_usage_cost_usd',
    ].every(
      (key) =>
        typeof value[key as keyof Usage] === 'string' &&
        /^\d{1,12}(?:\.\d{1,28})?$/.test(String(value[key as keyof Usage])),
    ) &&
    [
      value.minimum_balance_usd,
      value.safety_buffer_usd,
      value.reported_balance_usd,
      value.projected_headroom_usd,
    ].every(
      (v) =>
        v === null ||
        (typeof v === 'string' && /^\d{1,12}(?:\.\d{1,28})?$/.test(v)),
    ) &&
    Number.isSafeInteger(value.inference_attempts) &&
    (value.inference_attempts_this_month === undefined ||
      Number.isSafeInteger(value.inference_attempts_this_month)) &&
    (value.estimated_usage_cost_this_month_usd === undefined ||
      /^\d{1,12}(?:\.\d{1,28})?$/.test(
        value.estimated_usage_cost_this_month_usd,
      )) &&
    value.inference_attempts >= 0 &&
    Number.isSafeInteger(value.unreconciled_attempts) &&
    value.unreconciled_attempts >= 0 &&
    typeof value.refresh_enabled === 'boolean' &&
    Array.isArray(value.blocked_reasons) &&
    value.blocked_reasons.length <= 20 &&
    value.blocked_reasons.every((v) => typeof v === 'string')
  );
}

export function ProviderUsage({
  token,
  onDenied,
  signal,
  before,
}: {
  token: string;
  onDenied: (status: number) => void;
  signal?: AbortSignal;
  /** Other provider cards shown in the same row (the Anthropic card). */
  before?: ReactNode;
}) {
  const [view, setView] = useState<Usage | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  const [command, setCommand] = useState({ refresh: false, generation: 0 });
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const result = await request<Usage>(
          `/api/v1/internal/provider-usage${command.refresh ? '/balance-refresh' : ''}`,
          {
            method: command.refresh ? 'POST' : 'GET',
            headers: { Authorization: `Bearer ${token}` },
            signal: signal
              ? AbortSignal.any([signal, controller.signal])
              : controller.signal,
          },
          onDenied,
        );
        if (controller.signal.aborted || signal?.aborted) return;
        if (!valid(result)) throw new Error('invalid_provider_view');
        setView(result);
      } catch (failure) {
        if (controller.signal.aborted || signal?.aborted) return;
        setView(null);
        setError(message(failure));
      } finally {
        if (!controller.signal.aborted && !signal?.aborted) setBusy(false);
      }
    })();
    return () => controller.abort();
  }, [token, onDenied, signal, command]);
  function load(refresh: boolean) {
    setView(null);
    setError('');
    setBusy(true);
    setCommand((previous) => ({
      refresh,
      generation: previous.generation + 1,
    }));
  }
  return (
    <section className="admin-workspace" aria-label="Provider usage">
      <PageHeader title="Provider usage" />
      <div className="provider-cards">
        {before}
        <details
          className="panel provider-card provider-collapsed"
          aria-labelledby="luminal-title"
        >
          <summary>
            <h2 id="luminal-title">Luminal</h2> ·{' '}
            <span className="badge tone-warning">Blocked</span> ·{' '}
            <span className="muted">Not used for AI investigations</span>
          </summary>
          {busy && <p role="status">Loading provider usage…</p>}
          {view && (
            <>
              <dl className="fact-row">
                <div>
                  <dt>Model</dt>
                  <dd>Not reported</dd>
                </div>
                <div>
                  <dt>Requests</dt>
                  <dd>
                    {view.inference_attempts_this_month !== undefined &&
                      `${view.inference_attempts_this_month} this month · `}
                    {view.inference_attempts} all time
                  </dd>
                </div>
              </dl>
              <ul className="provider-lines">
                <li>
                  <strong>Spend:</strong>{' '}
                  {view.estimated_usage_cost_this_month_usd !== undefined &&
                    `${amount(view.estimated_usage_cost_this_month_usd)} this month · `}
                  {amount(view.estimated_usage_cost_usd)} of{' '}
                  {amount(view.indicative_spending_ceiling_usd)} cap (all time)
                </li>
                <li role="status">
                  <strong>Status:</strong> paid requests blocked until a
                  compatibility probe and bounded billing are verified
                </li>
              </ul>
              <table className="compact-table">
                <caption className="sr-only">
                  Provider financial controls
                </caption>
                <tbody>
                  {[
                    ...(view.financial_policy === 'bounded_probe_v3'
                      ? []
                      : [
                          [
                            'Minimum preserved balance',
                            amount(view.minimum_balance_usd),
                          ],
                          ['Safety buffer', amount(view.safety_buffer_usd)],
                        ]),
                    [
                      'Indicative spending ceiling',
                      amount(view.indicative_spending_ceiling_usd),
                    ],
                    [
                      'Provider-reported USD balance',
                      amount(view.reported_balance_usd),
                    ],
                    [
                      'Projected headroom (not spend authorization)',
                      amount(view.projected_headroom_usd),
                    ],
                    [
                      'Retained cost reservations',
                      amount(view.retained_reservations_usd),
                    ],
                    [
                      'Estimated usage cost (not settled charges)',
                      amount(view.estimated_usage_cost_usd),
                    ],
                    ['Inference attempts', String(view.inference_attempts)],
                    [
                      'Attempts without usage estimates',
                      String(view.unreconciled_attempts),
                    ],
                  ].map(([name, value]) => (
                    <tr key={name}>
                      <th scope="row">{name}</th>
                      <td>{value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h3>Why live requests are blocked</h3>
              <ul>
                {view.blocked_reasons.map((reason) => (
                  <li key={reason}>
                    {reasons[reason] ??
                      'Additional financial verification is required.'}
                  </li>
                ))}
              </ul>
              <button
                disabled={!view.refresh_enabled || busy}
                onClick={() => load(true)}
              >
                Refresh provider balance
              </button>
              <p className="muted">
                Balance refresh is an explicit read-only provider request.
                Outside usage and delayed billing are not treated as known
                available funds. This screen cannot enable paid inference.
              </p>
            </>
          )}
        </details>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {view?.last_refresh_status &&
          !['not_observed', 'provider_reported_balance_observed'].includes(
            view.last_refresh_status,
          ) && (
            <p role="alert" className="error">
              The latest provider balance could not be verified. Paid requests
              remain blocked.
            </p>
          )}
      </div>
      {view && (
        <ResearchSources token={token} onDenied={onDenied} signal={signal} />
      )}
    </section>
  );
}
