import { ApiError, request, type AssessmentDetail, type Policy } from './api';

export type CSVContract = {
  metadata: { name: string }[];
  predictors: { name: string }[];
  limits?: {
    max_bytes: number;
    max_rows: number;
    max_columns: number;
    max_field_bytes: number;
  };
};
export type Upload = {
  upload_id: string;
  status: string;
  sha256: string;
  row_count: number;
  column_count: number;
  expires_at: string;
};
export type Columns = {
  columns: string[];
  required_columns: string[];
  exact_matches: Record<string, string>;
};
export type Validation = {
  validation_id: string;
  upload_id: string;
  version: number;
  mapping: Record<string, string>;
  mapping_sha256: string;
  upload_sha256: string;
  mapping_version: string;
  validator_version: string;
  units: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  warning_rows: number;
};
export type Issues = {
  row_number: number;
  errors: { field: string; code: string }[];
  warnings: { field: string; code: string }[];
};
export type BatchPage<T> = {
  total: number;
  offset: number;
  limit: number;
  items: T[];
};
export type Import = {
  import_id: string;
  upload_id: string;
  validation_id: string;
  validation_sha256: string;
  status: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  processed_rows: number;
  created_rows: number;
  reused_rows: number;
  conflict_rows: number;
  excluded_rows: number;
  unprocessed_rows: number;
  failure_code: string | null;
  /** Imported cases with an assessment of their current version (read-only count). */
  assessed_cases?: number;
};
export type ImportRow = {
  row_number: number;
  status: string;
  reason_code: string | null;
  case_id: string | null;
  errors: { field: string; code: string }[];
  warnings: { field: string; code: string }[];
};
export type Batch = {
  batch_id: string;
  import_id: string;
  status: string;
  total_cases: number;
  total_eligible_cases: number;
  pending_dispatch: number;
  queued: number;
  running: number;
  succeeded: number;
  failed_manual_review: number;
  skipped: number;
  already_assessed: number;
  retrying: number;
  policy: Policy;
  model_version: string;
  model_sha256: string;
  policy_version: string;
  reason_code: string | null;
};
export type BatchRow = {
  case_id: string;
  source_row_number: number;
  outcome: string;
  reason_code: string | null;
  retrying: boolean;
  attempts: number;
  assessment: AssessmentDetail | null;
};
export type MappingBody = {
  units: 'baseline_source_units';
  mapping: Record<string, string>;
};
export type Approval = Pick<
  Validation,
  | 'upload_sha256'
  | 'mapping_sha256'
  | 'mapping_version'
  | 'validator_version'
  | 'units'
> & { approve_valid_rows: true; validation_version: number };
export type StartBody = {
  start_assessment: true;
  import_validation_sha256: string;
  policy: Policy;
};
export const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/i;

export function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function batchClient(
  token: string,
  signal: AbortSignal,
  onDenied: (status: number) => void,
) {
  const get = <T>(
    path: string,
    init: RequestInit = {},
    kind: 'json' | 'blob' = 'json',
  ) =>
    request<T>(
      path,
      {
        ...init,
        signal,
        headers: { Authorization: `Bearer ${token}`, ...init.headers },
      },
      onDenied,
      kind,
    );
  const post = <T>(path: string, body: unknown, key?: string) =>
    get<T>(path, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(key ? { 'Idempotency-Key': key } : {}),
      },
      body: JSON.stringify(body),
    });
  return {
    contract: () => get<CSVContract>('/api/v1/batch-uploads/contract'),
    template: () => get<Blob>('/api/v1/batch-uploads/template', {}, 'blob'),
    upload: (
      file: File,
      key: string,
      progress: (percent: number) => void,
      sessionId?: string,
    ) =>
      new Promise<Upload>((resolve, reject) => {
        if (file.size > 1048576 || !file.size) {
          reject(new ApiError(file.size ? 413 : 422));
          return;
        }
        if (signal.aborted) {
          reject(new DOMException('Aborted', 'AbortError'));
          return;
        }
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/v1/batch-uploads');
        xhr.timeout = 65000;
        xhr.withCredentials = false;
        xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        xhr.setRequestHeader('Content-Type', 'text/csv');
        xhr.setRequestHeader('Idempotency-Key', key);
        if (sessionId) xhr.setRequestHeader('X-Upload-Session-ID', sessionId);
        const abort = () => xhr.abort();
        signal.addEventListener('abort', abort, { once: true });
        const cleanup = () => signal.removeEventListener('abort', abort);
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable && !signal.aborted)
            progress(
              Math.min(100, Math.round((event.loaded / event.total) * 100)),
            );
        };
        xhr.onload = () => {
          cleanup();
          if (signal.aborted)
            return reject(new DOMException('Aborted', 'AbortError'));
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              resolve(JSON.parse(xhr.responseText) as Upload);
            } catch {
              reject(new ApiError(503));
            }
          } else {
            if ([401, 403, 404].includes(xhr.status)) onDenied(xhr.status);
            const retry = Number(xhr.getResponseHeader('Retry-After'));
            reject(
              new ApiError(
                xhr.status,
                Number.isFinite(retry) && retry > 0 ? Math.min(3600, retry) : 0,
              ),
            );
          }
        };
        xhr.onerror = () => {
          cleanup();
          reject(new ApiError(0));
        };
        xhr.ontimeout = () => {
          cleanup();
          reject(new ApiError(408));
        };
        xhr.onabort = () => {
          cleanup();
          reject(new DOMException('Aborted', 'AbortError'));
        };
        xhr.send(file);
      }),
    metadata: (id: string) =>
      get<Upload>(`/api/v1/batch-uploads/${encodeURIComponent(id)}`),
    columns: (id: string) =>
      get<Columns>(`/api/v1/batch-uploads/${encodeURIComponent(id)}/columns`),
    validate: (id: string, body: MappingBody) =>
      post<Validation>(
        `/api/v1/batch-uploads/${encodeURIComponent(id)}/validations`,
        body,
      ),
    validation: (uid: string, vid: string) =>
      get<Validation>(
        `/api/v1/batch-uploads/${encodeURIComponent(uid)}/validations/${encodeURIComponent(vid)}`,
      ),
    issues: (uid: string, vid: string, offset = 0) =>
      get<BatchPage<Issues>>(
        `/api/v1/batch-uploads/${encodeURIComponent(uid)}/validations/${encodeURIComponent(vid)}/errors?limit=20&offset=${offset}`,
      ),
    approve: (uid: string, vid: string, body: Approval, key: string) =>
      post<Import>(
        `/api/v1/batch-uploads/${encodeURIComponent(uid)}/validations/${encodeURIComponent(vid)}/imports`,
        body,
        key,
      ),
    imported: (id: string) =>
      get<Import>(`/api/v1/batch-imports/${encodeURIComponent(id)}`),
    importRows: (id: string, offset = 0) =>
      get<BatchPage<ImportRow>>(
        `/api/v1/batch-imports/${encodeURIComponent(id)}/rows?limit=10&offset=${offset}`,
      ),
    start: (id: string, body: StartBody, key: string) =>
      post<Batch>(
        `/api/v1/batch-imports/${encodeURIComponent(id)}/assessments`,
        body,
        key,
      ),
    status: (id: string) =>
      get<Batch>(`/api/v1/batch-assessments/${encodeURIComponent(id)}`),
    results: (id: string, offset = 0) =>
      get<BatchPage<BatchRow>>(
        `/api/v1/batch-assessments/${encodeURIComponent(id)}/results?limit=10&offset=${offset}`,
      ),
    export: (id: string, offset: number, limit: number) =>
      get<Blob>(
        `/api/v1/batch-assessments/${encodeURIComponent(id)}/export?offset=${offset}&limit=${limit}`,
        {},
        'blob',
      ),
  };
}
export type BatchClient = ReturnType<typeof batchClient>;
export type BatchFactory = (signal?: AbortSignal) => BatchClient;
