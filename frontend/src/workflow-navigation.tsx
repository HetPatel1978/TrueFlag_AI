import type { WorkflowCase } from './workflow-api';

export type CaseStage =
  'assessment' | 'evidence' | 'investigation' | 'decision' | 'activity';

export function WorkflowNavigation({
  record,
  current,
  evidenceAvailable,
  decisionsAvailable,
}: {
  record: WorkflowCase;
  current: CaseStage;
  evidenceAvailable: boolean;
  decisionsAvailable: boolean;
}) {
  const base = `#/cases/${record.id}`;
  const stages = [
    {
      title: 'Assess Alert',
      href: base,
      state:
        record.assessment_status === 'succeeded'
          ? 'Assessment saved'
          : record.assessment_status === 'failed'
            ? 'Review required'
            : ['pending', 'running'].includes(record.assessment_status)
              ? 'Processing'
              : 'Not assessed',
      key: 'assessment',
      available: true,
    },
    {
      title: 'Review Evidence',
      href: `${base}/evidence`,
      state: 'Check available sources',
      key: 'evidence',
      available: evidenceAvailable,
    },
    {
      title: 'AI Investigation',
      href: `${base}/investigation`,
      state: 'Evidence and provider checked on entry',
      key: 'investigation',
      available: evidenceAvailable,
    },
    {
      title: 'Human Decision',
      href: `${base}/casework`,
      state: record.disposition
        ? 'Decision recorded'
        : record.status === 'awaiting_approval'
          ? 'Awaiting supervisor'
          : 'Decision pending',
      key: 'decision',
      available: decisionsAvailable,
    },
  ];
  return (
    <nav className="workflow-navigation" aria-label="Case workflow">
      <ol>
        {stages.map((stage, index) => (
          <li key={stage.key}>
            {stage.available ? (
              <a
                href={stage.href}
                aria-current={current === stage.key ? 'step' : undefined}
              >
                <span className="workflow-number" aria-hidden="true">
                  {index + 1}
                </span>
                <span>
                  <strong>{stage.title}</strong>
                  <small>{stage.state}</small>
                </span>
              </a>
            ) : (
              <span className="workflow-unavailable">
                <span className="workflow-number">{index + 1}</span>
                <span>
                  {stage.title}
                  <small>Unavailable in this environment</small>
                </span>
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
