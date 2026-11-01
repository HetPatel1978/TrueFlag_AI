export type User = {
  id: string;
  username: string;
  role: 'analyst' | 'supervisor' | 'admin';
};
export type Policy = 'Efficiency' | 'Balanced' | 'Coverage';
export type JobState = 'pending' | 'running' | 'succeeded' | 'failed';
export type Case = {
  id: string;
  alert_id: string;
  source_id: string;
  assigned_to: string | null;
  status: 'open' | 'in_review' | 'awaiting_approval' | 'closed';
  disposition: 'close' | 'recommend' | null;
  version: number;
  created_at: string;
  priority: 'Standard' | 'High';
  assessment_status: JobState | 'not_requested';
  latest_job_id: string | null;
};
export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};
export type Job = {
  job_id: string;
  case_id: string;
  run_id: string;
  status: JobState;
  attempts: number;
  policy: Policy;
  assessment_id: string | null;
  failure_code: string | null;
  fallback_route: 'manual_review' | null;
  human_decision_required: true;
};
export type Assessment = {
  assessment_id: string;
  case_id: string;
  alert_id: string;
  run_id: string;
  version: number;
  case_version: number;
  processed_at: string;
  score: number;
  model_version: string;
  model_sha256: string;
  selected_policy: Policy;
  policy_version: string;
  recommended_route: 'retain_human_review' | 'review_reduction_candidate';
  input_sha256: string;
  content_sha256: string;
  human_decision_required: true;
};
export type Contribution = {
  name: string;
  contribution: number;
  direction: string;
  missing: boolean;
};
export type AssessmentDetail = Assessment & {
  input_provenance: {
    feature_contract_version: string;
    contract_sha256: string;
    ingestion_input_sha256: string;
    hash_schema: string;
  };
  policy_trace: {
    threshold: number;
    priority_group: string;
    override_reason: string | null;
    routing_reason: string;
    policy_sha256: string;
  };
  explanation: {
    status: 'verified';
    base_value: number;
    features: Contribution[];
    ranking: string[];
    reconstruction_residual: number;
    method: {
      algorithm: string;
      output_space: string;
      positive_class_label: number;
      library_version: string;
    };
    verification: {
      status: 'verified';
      verifier: string;
      reconstruction_atol: number;
      runtime_dependencies: Record<string, string>;
    };
  };
};
export type Submission = {
  expected_version: number;
  run_id: string;
  policy: Policy;
};

const messages: Record<number, string> = {
  0: 'Network unavailable or request timed out. Retry safely.',
  500: 'Service unavailable (500). Try again.',
  401: 'Sign-in failed or your session expired.',
  403: 'Access is no longer permitted. Protected information has been cleared.',
  404: 'Case or assessment unavailable. Access may have changed.',
  409: 'Case changed or request conflicts. Reload the case before creating a new request.',
  422: 'The request is invalid. Check your filters or reload the case.',
  429: 'Request limit reached. Wait before retrying.',
  503: 'Service unavailable (503). The worker or queue may be unavailable. Retry safely.',
};
export class ApiError extends Error {
  constructor(
    public status: number,
    public retryAfter = 0,
  ) {
    super(messages[status] ?? 'Service request failed. Try again.');
  }
}
async function request<T>(
  path: string,
  init: RequestInit = {},
  onDenied?: (status: number) => void,
): Promise<T> {
  const signal = init.signal
    ? AbortSignal.any([init.signal, AbortSignal.timeout(10000)])
    : AbortSignal.timeout(10000);
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      cache: 'no-store',
      credentials: 'omit',
      signal,
    });
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw new ApiError(0);
  }
  if (!response.ok) {
    if ([401, 403, 404].includes(response.status) && !init.signal?.aborted)
      onDenied?.(response.status);
    const hint = Number(response.headers?.get('Retry-After'));
    throw new ApiError(
      response.status,
      Number.isFinite(hint) && hint > 0 ? Math.min(3600, hint) : 0,
    );
  }
  return response.json() as Promise<T>;
}
export async function health(): Promise<boolean> {
  return (await request<{ status: string }>('/health')).status === 'ok';
}
export async function signIn(
  username: string,
  password: string,
  signal?: AbortSignal,
): Promise<string> {
  const result = await request<{ access_token?: unknown }>(
    '/api/v1/auth/token',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
      signal,
    },
  );
  if (typeof result.access_token !== 'string')
    throw new Error('Invalid authentication response.');
  return result.access_token;
}
export async function currentUser(
  token: string,
  signal?: AbortSignal,
): Promise<User> {
  const result = await request<User>('/api/v1/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  });
  if (
    !result ||
    typeof result.id !== 'string' ||
    typeof result.username !== 'string' ||
    !['analyst', 'supervisor', 'admin'].includes(result.role)
  ) {
    throw new Error('Invalid account response.');
  }
  return result;
}
export function client(
  token: string,
  signal: AbortSignal,
  onDenied: (status: number) => void,
) {
  function get<T>(path: string, init: RequestInit = {}) {
    return request<T>(
      path,
      {
        ...init,
        signal,
        headers: { Authorization: `Bearer ${token}`, ...init.headers },
      },
      onDenied,
    );
  }
  return {
    cases: (query: URLSearchParams) =>
      get<Page<Case>>(`/api/v1/cases?${query}`),
    overview: (id: string) =>
      get<Case>(`/api/v1/cases/${encodeURIComponent(id)}/overview`),
    history: (id: string, offset = 0) =>
      get<Page<Assessment>>(
        `/api/v1/cases/${encodeURIComponent(id)}/assessments?limit=10&offset=${offset}`,
      ),
    detail: (id: string, assessment: string) =>
      get<AssessmentDetail>(
        `/api/v1/cases/${encodeURIComponent(id)}/assessments/${encodeURIComponent(assessment)}`,
      ),
    job: (id: string) =>
      get<Job>(`/api/v1/assessment-jobs/${encodeURIComponent(id)}`),
    submit: (id: string, body: Submission, key: string) =>
      get<Job>(`/api/v1/cases/${encodeURIComponent(id)}/assessments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
        body: JSON.stringify(body),
      }),
  };
}
export type Client = ReturnType<typeof client>;
export const label = (value: string) =>
  value.replaceAll('_', ' ').replace(/^./, (s) => s.toUpperCase());
export const message = (error: unknown) =>
  error instanceof ApiError ? error.message : 'Service unavailable. Try again.';
export function pollDelay(retryAfter = 2): number | null {
  return retryAfter > 60 ? null : Math.max(2000, retryAfter * 1000);
}
