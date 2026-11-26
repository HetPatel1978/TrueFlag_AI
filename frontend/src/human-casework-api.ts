import { request, type Page } from './api';
import type { Reference } from './investigation-api';

export type Resolution =
  | 'additional_review_required'
  | 'no_further_action_recommended'
  | 'escalated_for_compliance_review'
  | 'investigation_completed';
export type HumanEntry = {
  id: string;
  case_id: string;
  actor_id: string;
  author: string;
  recorded_at: string;
  revision: number;
  kind: string;
  parent_id: string | null;
  content_sha256: string;
  payload:
    | ({
        rationale: string;
        supporting_records: Reference[];
        status?: string;
        category?: string;
        due_date?: string;
        responsible_party?: string;
        decision?: string;
        proposed_outcome?: Resolution;
        outcome?: Resolution;
        reference_id?: string;
        draft_run_id?: string;
      } & Record<string, unknown>)
    | null;
  binding: {
    case_version: number;
    evidence_revision: number;
    access_revision: number;
    finding?: {
      mode: 'offline_simulation';
      draft_sha256: string;
      claim_type: string;
    };
  } | null;
  content_status: 'available' | 'withheld_source_changed';
  immutable: true;
};
export type HumanPage = Page<HumanEntry> & {
  revision: number;
  open_information_requests: number;
  pending_escalations: number;
  resolution: Resolution | null;
  policy_version: string;
  allowed_resolutions: Resolution[];
};
export function humanCaseworkClient(
  token: string,
  signal?: AbortSignal,
  onDenied?: (status: number) => void,
) {
  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
  return {
    history: (id: string, offset = 0) =>
      request<HumanPage>(
        `/api/v1/cases/${id}/casework?limit=20&offset=${offset}`,
        { headers, signal },
        onDenied,
      ),
    submit: (id: string, key: string, body: Record<string, unknown>) =>
      request<HumanEntry>(
        `/api/v1/cases/${id}/casework`,
        {
          method: 'POST',
          headers: { ...headers, 'Idempotency-Key': key },
          body: JSON.stringify(body),
          signal,
        },
        onDenied,
      ),
    queue: (offset = 0) =>
      request<
        Page<{
          case_id: string;
          escalation_id: string;
          author: string;
          recorded_at: string;
        }>
      >(
        `/api/v1/supervisor-review-queue?limit=20&offset=${offset}`,
        { headers, signal },
        onDenied,
      ),
  };
}
export type HumanFactory = (
  signal?: AbortSignal,
) => ReturnType<typeof humanCaseworkClient>;
