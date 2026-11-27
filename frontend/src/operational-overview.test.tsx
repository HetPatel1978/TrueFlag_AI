// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { OperationalOverview, needsAttention } from './operational-overview';
import type { WorkflowCase, WorkflowFactory } from './workflow-api';
import { findViolations, mainViewText } from './ui-rules';

afterEach(() => cleanup());

const item = (
  id: string,
  priority: 'High' | 'Standard',
  score: number | null,
): WorkflowCase =>
  ({
    id: `${id}-0000-4000-8000-000000000000`,
    status: 'open',
    priority,
    assessment_score: score,
    review_recommendation: 'retain_human_review',
  }) as WorkflowCase;

it('uses authorized session-scoped counts for 4 tiles and lists cases needing attention', async () => {
  const items = [
    item('aaaaaaaa', 'Standard', 0.9),
    item('bbbbbbbb', 'High', 0.0089),
    item('cccccccc', 'High', 0.2),
  ];
  const queue = vi.fn().mockResolvedValue({ total: 4, items });
  const api = (() => ({ queue })) as unknown as WorkflowFactory;
  const { container } = render(
    <OperationalOverview api={api} sessionId="session-1" />,
  );
  const summary = await screen.findByRole('region', { name: 'Case summary' });
  expect(within(summary).getAllByText('4')).toHaveLength(4);
  expect(within(summary).getByText('Assigned to me')).toBeTruthy();
  expect(queue).toHaveBeenCalledTimes(5);
  for (const [params] of queue.mock.calls) {
    expect(params.get('upload_session_id')).toBe('session-1');
    expect(params.get('origin')).toBe('uploaded');
  }
  const rows = screen.getAllByRole('row').slice(1);
  expect(
    rows.map((r) => r.querySelector('a')?.getAttribute('aria-label')),
  ).toEqual(['Case cccccccc', 'Case bbbbbbbb', 'Case aaaaaaaa']);
  expect(rows.every((r) => r.classList.contains('row-link'))).toBe(true);
  expect(screen.queryByText(/→/)).toBeNull();
  expect(screen.getByText('0.9%')).toBeTruthy();
  expect(screen.queryByText(/Counts reflect/)).toBeNull(); // tooltip only
  expect(findViolations(mainViewText(container))).toEqual([]);
});

it('ranks open cases by priority then score and caps the list at 5', () => {
  const many = Array.from({ length: 8 }, (_, i) =>
    item(`${i}`.padStart(8, '0'), 'Standard', i / 10),
  );
  expect(needsAttention(many).map((c) => c.assessment_score)).toEqual([
    0.7, 0.6, 0.5, 0.4, 0.3,
  ]);
  expect(
    needsAttention([{ ...item('x', 'High', null), status: 'closed' }]),
  ).toEqual([]);
});
