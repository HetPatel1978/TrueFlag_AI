import { createContext } from 'react';
import {
  request,
  protectedRead,
  type AssessmentDetail,
  type Page,
} from './api';
import type {
  DraftDetail,
  DraftHistoryItem,
  DraftRequest,
  DraftStatus,
} from './draft-api';

export type Currency = 'USD' | 'CAD' | 'EUR' | 'GBP';
export type RegulatoryPassage = {
  reference_id: string;
  title: string;
  section: string;
  text: string;
  origin: 'official_curated' | 'synthetic_test';
  source_url: string;
  authority: string;
  as_of: string;
  version_id: string;
  limitations: string[];
};
export type RegulatoryResult = {
  status: string;
  as_of: string;
  passages: RegulatoryPassage[];
};
export type ResearchPassage = {
  reference_id: string;
  section: string;
  text: string;
  source_url: string;
  publisher: string;
  historical_as_of: string;
  raw_sha256: string;
  text_sha256: string;
  approval_status: 'unapproved_research';
  origin: 'official_public_research';
  /** Present when ``text`` is a bounded excerpt of the section (newer research runs). */
  excerpt_sha256?: string;
  section_text_bytes?: number;
};
export type ResearchStatus =
  | 'approval_required'
  | 'request_expired'
  | 'request_required'
  | 'approved'
  | 'generate_ready'
  | 'awaiting_approval'
  | 'approved_queued'
  | 'running'
  | 'budget_exhausted';
export type ResearchReview = {
  draft_run_id: string;
  case_id: string;
  phase: string;
  can_approve: boolean;
  is_approver: boolean;
  model: string;
  data_scope: 'synthetic_only';
  max_input_tokens: number;
  max_output_tokens: number;
  timeout_seconds: number;
  maximum_requests: 1;
  automatic_retries: false;
  reservation_usd: string;
  cumulative_cap_usd: string | null;
  spent_usd: string;
  expires_at: string;
  approve_before: string;
  financial_facts: {
    reference_id: string;
    observed_total: string;
    observed_count: number;
    currency: string;
    window: { start: string; end: string } | null;
  }[];
  transactions: number;
  model_signal: { score: number; model_version: string } | null;
  missing_evidence: string[];
  limitations: string[];
  regulatory_status: string;
  regulatory_sources: {
    reference_id: string;
    section: string;
    approval_status: string;
    historical_as_of: string;
    text_sha256: string;
    source_url: string;
  }[];
  request_sha256: string;
  request_bytes: number;
  request: unknown;
};
export type ResearchContext = {
  status: 'research_unapproved';
  notice: string;
  passages: ResearchPassage[];
  draft_run_id: string;
  publication_approved: false;
  dispatch_binding_status?: 'current' | 'expired';
  authorizes_dispatch?: false;
};
export type Window = { start: string; end: string };
export type Reference = {
  record_version_id: string;
  identity_id: string;
  source_version_id: string;
  kind: string;
  version: number;
  sha256: string;
};
export type Coverage = {
  status: string;
  unknown_time_excluded: number;
  outside_window_excluded: number;
  limitations: string[];
};
export type Source = {
  source_id: string;
  source_version_id: string;
  version: number;
  sha256: string;
  coverage: string;
  window: Window;
  membership_complete: boolean;
  case_input_reconciliation: string;
};
export type Evidence<T> = {
  data: T;
  snapshot: {
    id: string;
    sha256: string;
    case_version: number;
    evidence_revision: number;
    access_revision: number;
  };
  sources: Source[];
  evidence: Reference[];
  coverage: Coverage;
};
export type CaseContext = {
  case_id: string;
  snapshot_token: string;
  selected_assessment_id: string | null;
  model_signal: AssessmentDetail | null;
  available_categories: string[];
  missing_categories: string[];
  account_handles: string[];
};
export type CursorPage<T> = {
  items: T[];
  total: number;
  next_cursor: string | null;
};
export type Customer = {
  reference: Reference;
  customer_handle: string;
  alias: string;
  observed_at: string;
  annual_income: string | null;
  currency: Currency;
  declared_kyc_score: number;
  contradictory_observations: boolean;
  expected_activity_status: string;
  age_days_at_source_as_of: number;
};
export type Related = {
  reference: Reference;
  kind: string;
  account_handle: string;
  customer_handle: string | null;
  alias: string | null;
  currency: Currency | null;
  relation: string | null;
  observed_at: string | null;
  opened_at: string | null;
};
export type Transaction = {
  reference: Reference;
  account_handle: string | null;
  counterparty_handle: string | null;
  amount: string;
  currency: Currency;
  event_at: string | null;
  original_time: string;
  event_kind: string;
  direction: string;
  channel: string;
  reverses_handle: string | null;
  settlement_status: string;
};
export type Activity = {
  calculation: string;
  status: string;
  currency: Currency;
  window: Window;
  treatment: string;
  observed_count: number;
  observed_total: string | null;
  incoming_total: string | null;
  outgoing_total: string | null;
  reversal_observations: number;
  unmatched_reversals: number;
  verified_reversal_pairs_excluded: number;
  buckets: {
    window: Window;
    observed_count: number;
    observed_total: string | null;
  }[];
  concentration: {
    counterparty_handle: string;
    observed_count: number;
    observed_total: string;
    share_of_observed_amount: string | null;
  }[];
};
export type PacketRequest = {
  expected_case_version: number;
  expected_evidence_revision: number;
  expected_access_revision: number;
  assessment_id?: string;
  without_assessment_reason?: 'not_selected' | 'unavailable';
  window: Window;
  currencies: Currency[];
};
export type PacketJob = {
  run_id: string;
  status:
    | 'pending'
    | 'running'
    | 'succeeded'
    | 'abstained'
    | 'failed'
    | 'invalidated';
  attempts: number;
  error_code: string | null;
  human_review_required: true;
  mode: 'deterministic_evidence_only';
};
export type PacketHistory = PacketJob & {
  created_at: string;
  manifest_sha256: string;
  assessment_id: string | null;
  case_version: number;
  evidence_revision: number;
  access_revision: number;
  validation_status: 'stored_not_revalidated';
};
export type Packet = {
  run_id: string;
  manifest_sha256: string;
  mode: 'deterministic_evidence_only';
  outcome: string;
  transactions: Transaction[];
  facts: {
    reference_id: string;
    input_record_ids: string[];
    result: Activity;
    coverage: Coverage;
  }[];
  model_signal: AssessmentDetail | null;
  evidence: Reference[];
  questions: string[];
  missing_evidence: string[];
  conflicts: string[];
  limitations: string[];
  abstentions: string[];
  provider_used: false;
  regulatory_citations: [];
  human_review_required: true;
};
export type PacketDetail = PacketJob & {
  packet: Packet | null;
  verification: {
    status: string;
    verifier: string;
    manifest_sha256: string;
    packet_sha256: string;
    human_semantic_review_required: true;
  } | null;
};
export type PacketReceipt = {
  key: string;
  body: PacketRequest;
  run_id?: string;
};
export const InvestigationReceipts = createContext<Map<
  string,
  PacketReceipt
> | null>(null);

export function investigationClient(
  token: string,
  signal: AbortSignal,
  onDenied: (status: number) => void,
) {
  const call = <T>(
    path: string,
    body?: unknown,
    key?: string,
    denied: (status: number) => void = onDenied,
  ) => {
    const operation = () =>
      request<T>(
        path,
        {
          signal,
          method: body === undefined ? 'GET' : 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            ...(body === undefined
              ? {}
              : { 'Content-Type': 'application/json' }),
            ...(key ? { 'Idempotency-Key': key } : {}),
          },
          ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        },
        denied,
      );
    return body === undefined || path.includes('/evidence/')
      ? protectedRead(operation, signal)
      : operation();
  };
  const path = (id: string) => `/api/v1/cases/${encodeURIComponent(id)}`;
  const sessionOnly = (status: number) => {
    if (status === 401) onDenied(status);
  };
  const referenceCall = <T>(url: string, body?: object) =>
    request<T>(
      url,
      {
        signal,
        method: body ? 'POST' : 'GET',
        headers: {
          Authorization: `Bearer ${token}`,
          ...(body ? { 'Content-Type': 'application/json' } : {}),
        },
        ...(body ? { body: JSON.stringify(body) } : {}),
      },
      (status) => {
        if (status === 401 || status === 403) onDenied(status);
      },
    );
  return {
    referenceInvestigation: (id: string, run: string, query: string) =>
      referenceCall<RegulatoryResult>(
        `${path(id)}/investigations/${encodeURIComponent(run)}/regulatory-context`,
        { query, limit: 5 },
      ),
    referenceSearch: (id: string, query: string) =>
      referenceCall<RegulatoryResult>(`${path(id)}/references/search`, {
        query,
        limit: 5,
      }),
    referenceResolve: (id: string, reference: string) =>
      referenceCall<RegulatoryResult>(
        `${path(id)}/references/${encodeURIComponent(reference)}`,
      ),
    context: (id: string, assessment?: string) =>
      call<Evidence<CaseContext>>(
        `${path(id)}/evidence${assessment ? `?assessment_id=${encodeURIComponent(assessment)}` : ''}`,
      ),
    customers: (id: string, snapshot: string, cursor?: string) =>
      call<Evidence<CursorPage<Customer>>>(`${path(id)}/evidence/customers`, {
        snapshot,
        limit: 20,
        ...(cursor ? { cursor } : {}),
      }),
    related: (id: string, snapshot: string, cursor?: string) =>
      call<Evidence<CursorPage<Related>>>(`${path(id)}/evidence/related`, {
        snapshot,
        limit: 20,
        ...(cursor ? { cursor } : {}),
      }),
    transactions: (id: string, body: object) =>
      call<Evidence<CursorPage<Transaction>>>(
        `${path(id)}/evidence/transactions`,
        body,
      ),
    activity: (id: string, body: object) =>
      call<Evidence<Activity>>(`${path(id)}/evidence/activity`, body),
    history: (id: string, offset = 0) =>
      call<Page<PacketHistory>>(
        `${path(id)}/investigations?limit=10&offset=${offset}`,
      ),
    submit: (id: string, body: PacketRequest, key: string) =>
      call<PacketJob>(`${path(id)}/investigations`, body, key),
    detail: (id: string, run: string) =>
      call<PacketDetail>(
        `${path(id)}/investigations/${encodeURIComponent(run)}`,
      ),
    draftHistory: (id: string, offset = 0) =>
      call<Page<DraftHistoryItem>>(
        `${path(id)}/investigation-drafts?limit=10&offset=${offset}`,
      ),
    draftSubmit: (id: string, body: DraftRequest, key: string) =>
      call<DraftStatus>(`${path(id)}/investigation-drafts`, body, key),
    draftStart: (id: string, body: PacketRequest, key: string) =>
      call<DraftStatus & { investigation_run_id: string }>(
        `${path(id)}/investigation-drafts/start`,
        { investigation_request: body, provider: 'auto' },
        key,
      ),
    draftCapabilities: (id: string) =>
      call<{
        provider: 'claude' | 'simulation' | 'unavailable';
        regulatory_grounding_enabled: boolean;
        research_status?: ResearchStatus;
        research_run_id?: string | null;
        research_can_approve?: boolean;
        research_run_phase?: string | null;
        general_generation_enabled?: false;
      }>(`${path(id)}/investigation-drafts/capabilities`),
    // Generate AI Investigation: the server takes a fresh snapshot, builds and records the
    // exact request for review. Nothing is queued or sent until an approver approves it.
    researchStart: (
      id: string,
      body: { investigation_run_id: string; expected_packet_sha256: string },
      key: string,
    ) =>
      call<DraftStatus>(
        `${path(id)}/investigation-drafts/research-start`,
        body,
        key,
        sessionOnly,
      ),
    researchReview: (id: string, run: string) =>
      call<ResearchReview>(
        `${path(id)}/investigation-drafts/${encodeURIComponent(run)}/research-review`,
        undefined,
        undefined,
        sessionOnly,
      ),
    // The browser sends only the hash it displayed; the server rebuilds and re-verifies.
    researchApprove: (id: string, run: string, sha: string, key: string) =>
      call<DraftStatus>(
        `${path(id)}/investigation-drafts/${encodeURIComponent(run)}/research-approve`,
        { request_sha256: sha },
        key,
        sessionOnly,
      ),
    researchCancel: (id: string, run: string, key: string) =>
      call<DraftStatus>(
        `${path(id)}/investigation-drafts/${encodeURIComponent(run)}/research-cancel`,
        {},
        key,
        sessionOnly,
      ),
    researchExecute: (id: string, run: string, key: string) =>
      call<DraftStatus>(
        `${path(id)}/investigation-drafts/${encodeURIComponent(run)}/execute-research`,
        {},
        key,
      ),
    draftDetail: (id: string, run: string) =>
      call<DraftDetail>(
        `${path(id)}/investigation-drafts/${encodeURIComponent(run)}`,
      ),
    // 404 here means "no research context for this case", not lost case access; the
    // panel simply stays hidden. 401/403 still clear the session's protected data.
    researchContext: (id: string) =>
      call<ResearchContext>(
        `${path(id)}/investigation-drafts/research-context/latest`,
        undefined,
        undefined,
        (status) => {
          if (status !== 404) onDenied(status);
        },
      ),
  };
}
type FullInvestigationClient = ReturnType<typeof investigationClient>;
export type InvestigationClient = Omit<
  FullInvestigationClient,
  | 'referenceSearch'
  | 'referenceResolve'
  | 'referenceInvestigation'
  | 'draftCapabilities'
  | 'draftStart'
  | 'researchContext'
  | 'researchExecute'
  | 'researchStart'
  | 'researchReview'
  | 'researchApprove'
  | 'researchCancel'
> &
  Partial<
    Pick<
      FullInvestigationClient,
      | 'referenceSearch'
      | 'referenceResolve'
      | 'referenceInvestigation'
      | 'draftCapabilities'
      | 'draftStart'
      | 'researchContext'
      | 'researchExecute'
      | 'researchStart'
      | 'researchReview'
      | 'researchApprove'
      | 'researchCancel'
    >
  >;
export type InvestigationFactory = (
  signal?: AbortSignal,
) => InvestigationClient;
