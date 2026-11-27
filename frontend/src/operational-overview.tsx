import { useEffect, useState } from 'react';
import { message } from './api';
import type { WorkflowCase, WorkflowFactory } from './workflow-api';
import { PageHeader, StatusBadge } from './ui';
import { InfoTip, KpiTile } from './display';
import { scorePercent, shortId } from './format';
import { displayLabel } from './terminology';

const tiles = [
  ['Open', { status: 'open' }],
  ['Assigned to me', { queue: 'my' }],
  ['Awaiting approval', { status: 'awaiting_approval' }],
  ['In review', { status: 'in_review' }],
] as const;

/** Open cases first by priority (High before Standard), then by model score. */
export function needsAttention(
  items: WorkflowCase[],
  limit = 5,
): WorkflowCase[] {
  return items
    .filter((c) => c.status === 'open')
    .sort(
      (a, b) =>
        Number(b.priority === 'High') - Number(a.priority === 'High') ||
        (b.assessment_score ?? -1) - (a.assessment_score ?? -1),
    )
    .slice(0, limit);
}

export function OperationalOverview({
  api,
  sessionId,
}: {
  api: WorkflowFactory;
  sessionId: string;
}) {
  const [counts, setCounts] = useState<number[] | null>(null);
  const [attention, setAttention] = useState<WorkflowCase[] | null>(null);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const scope = { upload_session_id: sessionId, origin: 'uploaded' };
    async function load() {
      setCounts(null);
      setAttention(null);
      setError('');
      try {
        const values: number[] = [];
        for (const [, filter] of tiles) {
          const params = new URLSearchParams({
            limit: '1',
            ...scope,
            ...filter,
          });
          values.push((await api(controller.signal).queue(params)).total);
          if (controller.signal.aborted) return;
        }
        const open = await api(controller.signal).queue(
          new URLSearchParams({ limit: '50', status: 'open', ...scope }),
        );
        if (controller.signal.aborted) return;
        setCounts(values);
        setAttention(needsAttention(open.items ?? []));
      } catch (e) {
        if (!controller.signal.aborted) setError(message(e));
      }
    }
    void load();
    return () => controller.abort();
  }, [api, sessionId, revision]);
  return (
    <>
      <PageHeader
        title={
          <>
            Overview{' '}
            <InfoTip text="Counts reflect your current access and the selected upload session." />
          </>
        }
      />
      {error ? (
        <section className="panel state" role="alert">
          <p>{error}</p>
          <button onClick={() => setRevision((n) => n + 1)}>Retry</button>
        </section>
      ) : !counts ? (
        <p role="status">Loading case summary…</p>
      ) : (
        <>
          <section className="kpi-row" aria-label="Case summary">
            {tiles.map(([name], i) => (
              <KpiTile key={name} label={name} value={counts[i]} href="#/" />
            ))}
          </section>
          <section
            className="panel needs-attention"
            aria-labelledby="attention-title"
          >
            <div className="section-heading">
              <h2 id="attention-title">Needs attention</h2>
              <a href="#/">All cases</a>
            </div>
            {!attention?.length ? (
              <p className="muted">No open cases.</p>
            ) : (
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Priority</th>
                    <th>Score</th>
                    <th>Recommendation</th>
                  </tr>
                </thead>
                <tbody>
                  {attention.map((c) => (
                    <tr
                      key={c.id}
                      className="row-link"
                      onClick={() => {
                        window.location.hash = `/cases/${c.id}`;
                      }}
                    >
                      <td className="case-id">
                        <a
                          href={`#/cases/${c.id}`}
                          aria-label={`Case ${shortId(c.id)}`}
                        >
                          {shortId(c.id)}
                        </a>
                      </td>
                      <td>
                        <StatusBadge value={c.priority} />
                      </td>
                      <td className="num">
                        {scorePercent(c.assessment_score)}
                      </td>
                      <td>
                        {c.review_recommendation
                          ? displayLabel(c.review_recommendation)
                          : 'Not assessed'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </>
  );
}
