// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { WorkflowNavigation } from './workflow-navigation';
import type { WorkflowCase } from './workflow-api';

afterEach(cleanup);
const record = {
  id: 'case',
  assessment_status: 'succeeded',
  status: 'open',
  disposition: null,
} as WorkflowCase;
it('uses four stages without inferring evidence or AI completion from navigation', () => {
  render(
    <WorkflowNavigation
      record={record}
      current="investigation"
      evidenceAvailable
      decisionsAvailable
    />,
  );
  const links = within(
    screen.getByRole('navigation', { name: 'Case workflow' }),
  ).getAllByRole('link');
  expect(links).toHaveLength(4);
  expect(links[2].getAttribute('aria-current')).toBe('step');
  expect(screen.getByText('Assessment saved')).toBeTruthy();
  expect(screen.getByText('Check available sources')).toBeTruthy();
  expect(screen.queryByText('Investigation completed')).toBeNull();
  expect(links.map((link) => link.getAttribute('href'))).toEqual([
    '#/cases/case',
    '#/cases/case/evidence',
    '#/cases/case/investigation',
    '#/cases/case/casework',
  ]);
});
it('does not expose unavailable workflow controls as clickable actions', () => {
  render(
    <WorkflowNavigation
      record={{ ...record, assessment_status: 'failed' }}
      current="assessment"
      evidenceAvailable={false}
      decisionsAvailable={false}
    />,
  );
  expect(screen.getAllByRole('link')).toHaveLength(1);
  expect(screen.getByText('Review required')).toBeTruthy();
  expect(screen.getAllByText('Unavailable in this environment')).toHaveLength(
    3,
  );
});
