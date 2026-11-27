import { describe, expect, it } from 'vitest';
import { groupActivity } from './case-workflows';
import type { Activity } from './workflow-api';

const event = (id: string, event_type: string, minute: number): Activity => ({
  id,
  case_id: 'case',
  recorded_at: `2026-11-24T10:${String(minute).padStart(2, '0')}:00Z`,
  event_type,
  actor: 'you',
  outcome: 'recorded',
  case_version: null,
  assessment_version: null,
  evidence_revision: null,
  access_revision: null,
  assignment_change: null,
  historical: true,
});

describe('Activity History grouping', () => {
  it('folds the sub-events of one request into one line, newest first', () => {
    const groups = groupActivity([
      event('5', 'assignment_changed', 9),
      event('4', 'ai_investigation_completed', 8),
      event('3', 'ai_investigation_processing', 7),
      event('2', 'ai_investigation_approved', 6),
      event('1', 'ai_investigation_requested', 5),
    ]);
    expect(groups.map((g) => g.last.event_type)).toEqual([
      'assignment_changed',
      'ai_investigation_completed',
    ]);
    expect(groups[1].steps.map((s) => s.id)).toEqual(['1', '2', '3', '4']);
  });
  it('starts a new line for each new request and keeps unrelated events separate', () => {
    const groups = groupActivity([
      event('1', 'ai_investigation_requested', 1),
      event('2', 'ai_investigation_failed', 2),
      event('3', 'ai_investigation_requested', 3),
      event('4', 'casework_note', 4),
      event('5', 'assessment_requested', 5),
      event('6', 'assessment_completed', 6),
    ]);
    expect(groups.map((g) => [g.last.event_type, g.steps.length])).toEqual([
      ['assessment_completed', 2],
      ['casework_note', 1],
      ['ai_investigation_requested', 1],
      ['ai_investigation_failed', 2],
    ]);
  });
  it('keeps out-of-order assessment sub-events on one line titled by the outcome', () => {
    const groups = groupActivity([
      event('1', 'assessment_enqueued', 1),
      event('2', 'assessment_requested', 2),
      event('3', 'assessment_processing', 3),
      event('4', 'assessment_completed', 4),
      event('5', 'assessment_processing_completed', 5),
    ]);
    expect(groups.map((g) => [g.last.event_type, g.steps.length])).toEqual([
      ['assessment_completed', 5],
    ]);
  });
});
