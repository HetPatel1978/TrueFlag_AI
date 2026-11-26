import { request, type Case, type Page } from './api';

export type WorkflowCase = Case & {
  assigned_investigator?: string | null;
  review_recommendation?:
    'retain_human_review' | 'review_reduction_candidate' | null;
  assessment_version?: number | null;
  /** Verified latest model score (0..1), read-only display field. */
  assessment_score?: number | null;
  /** Time of the newest Activity History event. */
  last_activity_at?: string | null;
};
export type Directory = Page<{ id: string; username: string }> & {
  case_version: number;
};
export type Activity = {
  id: string;
  case_id: string;
  recorded_at: string;
  event_type: string;
  actor: 'you' | 'redacted' | 'system';
  outcome: string;
  case_version: number | null;
  assessment_version: number | null;
  evidence_revision: number | null;
  access_revision: number | null;
  assignment_change: 'assigned' | 'reassigned' | 'unassigned' | null;
  /** Identical legacy failure records folded into this line (kept as audit data). */
  duplicate_records?: number | null;
  historical: true;
};
export type ActivityPage = Page<Activity> & {
  case_version: number;
  historical: true;
};
export function workflowClient(
  token: string,
  signal?: AbortSignal,
  onDenied?: (status: number) => void,
) {
  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
  const get = <T>(path: string) =>
    request<T>(`/api/v1/${path}`, { headers, signal }, onDenied);
  return {
    queue: (query: URLSearchParams) =>
      get<Page<WorkflowCase>>(`case-queue?${query}`),
    overview: (id: string) => get<WorkflowCase>(`cases/${id}/workflow`),
    directory: (id: string, search: string, offset: number) =>
      get<Directory>(
        `cases/${id}/assignment-options?${new URLSearchParams({ search, offset: String(offset), limit: '20' })}`,
      ),
    assign: (id: string, version: number, assigned: string | null) =>
      request<Case>(
        `/api/v1/cases/${id}/assignment`,
        {
          method: 'PUT',
          headers,
          signal,
          body: JSON.stringify({
            expected_version: version,
            assigned_to: assigned,
          }),
        },
        onDenied,
      ),
    activity: (id: string, category: string, offset: number) =>
      get<ActivityPage>(
        `cases/${id}/activity?${new URLSearchParams({ category, offset: String(offset), limit: '20' })}`,
      ),
  };
}
export type WorkflowFactory = (
  signal?: AbortSignal,
) => ReturnType<typeof workflowClient>;
