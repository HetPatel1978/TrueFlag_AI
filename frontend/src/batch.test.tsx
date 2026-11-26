// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { StrictMode } from 'react';
import { ApiError } from './api';
import {
  batchClient,
  type BatchFactory,
  type Batch,
  type Import,
  type Validation,
} from './batch-api';
import { BatchProcessing } from './batch';

const uid = '11111111-1111-4111-8111-111111111111',
  vid = '22222222-2222-4222-8222-222222222222',
  iid = '33333333-3333-4333-8333-333333333333',
  bid = '44444444-4444-4444-8444-444444444444';
const fields = [
  'source_id',
  'data_classification',
  'feature_contract_version',
  'income',
  'state',
  ...Array.from({ length: 25 }, (_, n) => `syntheticPredictor${n}`),
];
const mapping = Object.fromEntries(fields.map((n) => [n, n]));
const user = {
  id: 'unit-admin',
  username: 'unitadmin',
  role: 'admin' as const,
};
const validation: Validation = {
  validation_id: vid,
  upload_id: uid,
  version: 1,
  mapping,
  mapping_sha256: 'a'.repeat(64),
  upload_sha256: 'b'.repeat(64),
  mapping_version: 'trueflag.csv-mapping.v1',
  validator_version: 'trueflag.csv-validation.v1',
  units: 'baseline_source_units',
  total_rows: 2,
  valid_rows: 1,
  invalid_rows: 1,
  warning_rows: 0,
};
const imported: Import = {
  import_id: iid,
  upload_id: uid,
  validation_id: vid,
  validation_sha256: 'c'.repeat(64),
  status: 'partially_completed',
  total_rows: 2,
  valid_rows: 1,
  invalid_rows: 1,
  processed_rows: 2,
  created_rows: 1,
  reused_rows: 0,
  conflict_rows: 0,
  excluded_rows: 1,
  unprocessed_rows: 0,
  failure_code: null,
};
const batch: Batch = {
  batch_id: bid,
  import_id: iid,
  status: 'completed',
  total_cases: 1,
  total_eligible_cases: 1,
  pending_dispatch: 0,
  queued: 0,
  running: 0,
  succeeded: 0,
  failed_manual_review: 1,
  skipped: 0,
  already_assessed: 0,
  retrying: 0,
  policy: 'Balanced',
  model_version: 'synthetic-component-model',
  model_sha256: 'd'.repeat(64),
  policy_version: 'synthetic-component-policy',
  reason_code: null,
};
function mockApi() {
  return {
    contract: vi.fn(async () => ({
      metadata: fields.slice(0, 3).map((name) => ({ name })),
      predictors: fields.slice(3).map((name) => ({ name })),
      limits: {
        max_bytes: 1048576,
        max_rows: 2000,
        max_columns: 64,
        max_field_bytes: 4096,
      },
    })),
    template: vi.fn(async () => new Blob(['header'])),
    upload: vi.fn(async () => ({
      upload_id: uid,
      status: 'staged',
      sha256: 'b'.repeat(64),
      row_count: 2,
      column_count: 30,
      expires_at: '2026-12-01',
    })),
    metadata: vi.fn(async () => ({
      upload_id: uid,
      status: 'staged',
      sha256: 'b'.repeat(64),
      row_count: 2,
      column_count: 30,
      expires_at: '2026-12-01',
    })),
    columns: vi.fn(async () => ({
      columns: fields,
      required_columns: fields,
      exact_matches: mapping,
    })),
    validate: vi.fn(async () => validation),
    validation: vi.fn(async () => validation),
    issues: vi.fn(async () => ({
      total: 1,
      offset: 0,
      limit: 20,
      items: [
        {
          row_number: 3,
          errors: [{ field: 'income', code: 'number_format' }],
          warnings: [],
        },
      ],
    })),
    approve: vi.fn(async () => imported),
    imported: vi.fn(async () => imported),
    importRows: vi.fn(async () => ({
      total: 0,
      offset: 0,
      limit: 10,
      items: [],
    })),
    start: vi.fn(async () => batch),
    status: vi.fn(async () => batch),
    results: vi.fn(async () => ({
      total: 1,
      offset: 0,
      limit: 10,
      items: [
        {
          case_id: uid,
          source_row_number: 2,
          outcome: 'failed_manual_review',
          reason_code: 'child_failed',
          retrying: false,
          attempts: 3,
          assessment: null,
        },
      ],
    })),
    export: vi.fn(async () => new Blob(['"case_id"\r\n'])),
  };
}
function setup(route = '#/batch', memory = new Map<string, unknown>()) {
  const methods = mockApi();
  const api: BatchFactory = () => methods;
  const view = render(
    <StrictMode>
      <BatchProcessing api={api} user={user} route={route} memory={memory} />
    </StrictMode>,
  );
  return { methods, api, memory, ...view };
}
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('preserves a selected file across a same-session component remount', async () => {
  const memory = new Map<string, unknown>();
  const first = setup('#/batch/new', memory);
  await waitFor(() => expect(first.methods.contract).toHaveBeenCalled());
  const file = new File(['synthetic'], 'selected-synthetic.csv', {
    type: 'text/csv',
  });
  fireEvent.change(screen.getByLabelText('Choose a CSV file'), {
    target: { files: [file] },
  });
  first.unmount();
  setup('#/batch/new', memory);
  await screen.findByText('selected-synthetic.csv');
  await waitFor(() =>
    expect(
      screen
        .getByRole('button', { name: 'Upload CSV' })
        .hasAttribute('disabled'),
    ).toBe(false),
  );
});

describe('batch workflow components (synthetic UI fixtures, no scientific success substitution)', () => {
  it('explains row and size limits and clears progress after a rejected upload', async () => {
    const { methods, memory } = setup();
    expect(
      (await screen.findAllByText(/2,000 data rows/)).length,
    ).toBeGreaterThan(0);
    methods.upload.mockImplementation(async () => {
      throw new ApiError(413);
    });
    fireEvent.change(screen.getByLabelText('Choose a CSV file'), {
      target: {
        files: [
          new File(['source_id\nsynthetic\n'], 'synthetic.csv', {
            type: 'text/csv',
          }),
        ],
      },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Upload CSV' }));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('CSV exceeds an upload limit.');
    expect(alert.textContent).toContain(
      '2,000 data rows (excluding the header)',
    );
    expect(screen.queryByRole('progressbar')).toBeNull();
    expect(memory.has('pending-upload')).toBe(false);
    expect(methods.approve).not.toHaveBeenCalled();
    expect(methods.start).not.toHaveBeenCalled();
  });
  it('requires all 30 distinct source mappings and explicit units', async () => {
    const { methods } = setup(`#/batch/upload/${uid}`);
    await screen.findByRole('heading', { name: 'Column mapping' });
    expect(screen.getAllByRole('combobox')).toHaveLength(30);
    const validate = screen.getByRole('button', {
      name: 'Validate mapped file',
    });
    expect((validate as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(
      screen.getByLabelText(/Values use the required source units/),
    );
    fireEvent.change(screen.getByLabelText('Map income'), {
      target: { value: 'state' },
    });
    expect((validate as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Map income'), {
      target: { value: 'income' },
    });
    fireEvent.click(validate);
    await waitFor(() =>
      expect(methods.validate).toHaveBeenCalledWith(uid, {
        mapping,
        units: 'baseline_source_units',
      }),
    );
    expect(window.location.hash).toContain(`/validation/${vid}`);
  });
  it('shows safe diagnostics and never imports without confirmation', async () => {
    const { methods } = setup(`#/batch/upload/${uid}/validation/${vid}`);
    await screen.findByRole('heading', { name: 'Validation preview' });
    expect(screen.getByText('income: Number format')).toBeTruthy();
    const button = screen.getByRole('button', { name: 'Import valid records' });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(methods.approve).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText(/I approve importing only/));
    fireEvent.click(button);
    await waitFor(() => expect(methods.approve).toHaveBeenCalledTimes(1));
    expect(methods.approve.mock.calls[0]).toHaveLength(4);
  });
  it('retries an uncertain import with the exact original key and body', async () => {
    const memory = new Map<string, unknown>();
    const methods = mockApi();
    methods.approve.mockRejectedValueOnce(new ApiError(0));
    const api: BatchFactory = () => methods;
    render(
      <BatchProcessing
        api={api}
        user={user}
        route={`#/batch/upload/${uid}/validation/${vid}`}
        memory={memory}
      />,
    );
    await screen.findByRole('heading', { name: 'Validation preview' });
    fireEvent.click(screen.getByLabelText(/I approve importing only/));
    fireEvent.click(
      screen.getByRole('button', { name: 'Import valid records' }),
    );
    await screen.findByRole('alert');
    fireEvent.click(
      screen.getByRole('button', { name: 'Retry import request' }),
    );
    await waitFor(() => expect(methods.approve).toHaveBeenCalledTimes(2));
    expect(methods.approve.mock.calls[0]).toEqual(
      methods.approve.mock.calls[1],
    );
  });
  it('does not start inference on import completion', async () => {
    const { methods } = setup(`#/batch/import/${iid}`);
    await screen.findByRole('heading', { name: 'Assess imported alerts' });
    expect(methods.start).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Start assessments' }));
    await waitFor(() => expect(methods.start).toHaveBeenCalledTimes(1));
    expect(window.location.hash).toContain(`/assessment/${bid}`);
  });
  it('shows already-assessed imports with re-assessment as a secondary action', async () => {
    const methods = mockApi();
    methods.imported = vi.fn(async () => ({
      ...imported,
      created_rows: 2,
      assessed_cases: 2,
    }));
    const api: BatchFactory = () => methods;
    render(
      <BatchProcessing
        api={api}
        user={user}
        route={`#/batch/import/${iid}`}
        memory={new Map()}
      />,
    );
    await screen.findByText('Already assessed (2 of 2)');
    expect(screen.getByRole('button', { name: 'View cases' })).toBeTruthy();
    expect(
      screen.queryByRole('button', { name: 'Start assessments' }),
    ).toBeNull();
    // Counts are one line, not tiles.
    expect(screen.queryByText('Rejected')).toBeNull();
    expect(screen.getAllByText(/rejected/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Assess again' }));
    expect(screen.getByLabelText('Review policy')).toBeTruthy();
    const again = screen.getByRole('button', { name: 'Assess again' });
    expect(again.className).not.toContain('primary');
    fireEvent.click(again);
    await waitFor(() => expect(methods.start).toHaveBeenCalledTimes(1));
  });
  it('keeps Start assessments primary while some imported cases are unassessed', async () => {
    const methods = mockApi();
    methods.imported = vi.fn(async () => ({
      ...imported,
      created_rows: 3,
      assessed_cases: 1,
    }));
    const api: BatchFactory = () => methods;
    render(
      <BatchProcessing
        api={api}
        user={user}
        route={`#/batch/import/${iid}`}
        memory={new Map()}
      />,
    );
    await screen.findByText('Already assessed (1 of 3)');
    const start = screen.getByRole('button', { name: 'Start assessments' });
    expect(start.className).toContain('primary');
    expect(screen.queryByRole('button', { name: 'Assess again' })).toBeNull();
  });
  it('resumes by ID without storing credentials or predictor values', async () => {
    setup();
    fireEvent.click(await screen.findByText('Resume an existing import'));
    fireEvent.change(screen.getByLabelText('Import ID'), {
      target: { value: iid },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Resume import' }));
    expect(window.location.hash).toBe(`#/batch/import/${iid}`);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
  it('distinguishes terminal manual review from missing/fabricated scores', async () => {
    setup(`#/batch/import/${iid}/assessment/${bid}`);
    await screen.findByRole('heading', { name: 'Batch results' });
    expect(
      await screen.findByText('Manual review required · Child failed'),
    ).toBeTruthy();
    expect(screen.queryByText(/25.00%/)).toBeNull();
  });
  it('has admin-only entry even with a direct batch URL', () => {
    const api = vi.fn() as unknown as BatchFactory;
    render(
      <BatchProcessing
        api={api}
        user={{ ...user, role: 'analyst' }}
        route={`#/batch/import/${iid}`}
        memory={new Map()}
      />,
    );
    expect(
      screen.getByRole('heading', { name: 'Batch processing unavailable' }),
    ).toBeTruthy();
    expect(api).not.toHaveBeenCalled();
  });
  it('downloads only the explicit server export range', async () => {
    const create = vi.fn(() => 'blob:unit-test');
    vi.stubGlobal(
      'URL',
      Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() }),
    );
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {});
    const { methods } = setup(`#/batch/import/${iid}/assessment/${bid}`);
    fireEvent.click(await screen.findByText('Export results'));
    fireEvent.change(screen.getByLabelText('Maximum rows'), {
      target: { value: '10' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Download results CSV' }),
    );
    await waitFor(() =>
      expect(methods.export).toHaveBeenCalledWith(bid, 0, 10),
    );
    expect(create).toHaveBeenCalledTimes(1);
    click.mockRestore();
  });
  it('aborts polling and ignores late responses after navigation', async () => {
    const methods = mockApi();
    let resolve: ((value: Import) => void) | undefined;
    methods.imported.mockImplementation(
      () =>
        new Promise<Import>((done) => {
          resolve = done;
        }),
    );
    let signal: AbortSignal | undefined;
    const api: BatchFactory = (given) => {
      signal = given;
      return methods;
    };
    const view = render(
      <BatchProcessing
        api={api}
        user={user}
        route={`#/batch/import/${iid}`}
        memory={new Map()}
      />,
    );
    await waitFor(() => expect(methods.imported).toHaveBeenCalled());
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => resolve?.(imported));
    expect(methods.importRows).not.toHaveBeenCalled();
  });
  it('bounds active polling and stops timers on unmount', async () => {
    vi.useFakeTimers();
    const methods = mockApi();
    methods.imported.mockResolvedValue({ ...imported, status: 'running' });
    const api: BatchFactory = () => methods;
    const view = render(
      <BatchProcessing
        api={api}
        user={user}
        route={`#/batch/import/${iid}`}
        memory={new Map()}
      />,
    );
    await act(async () => {
      await Promise.resolve();
    });
    for (let n = 0; n < 60; n++)
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });
    expect(methods.imported).toHaveBeenCalledTimes(60);
    expect(screen.getByText(/Automatic refresh paused/)).toBeTruthy();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(methods.imported).toHaveBeenCalledTimes(60);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe('batch API boundary', () => {
  it('sends raw CSV with progress and cancels upload on navigation', async () => {
    class UploadXHR {
      static instance: UploadXHR;
      upload: {
        onprogress?: (e: {
          lengthComputable: boolean;
          loaded: number;
          total: number;
        }) => void;
      } = {};
      headers: Record<string, string> = {};
      timeout = 0;
      withCredentials = true;
      onabort?: () => void;
      open = vi.fn();
      send = vi.fn();
      abort = vi.fn(() => this.onabort?.());
      setRequestHeader(name: string, value: string) {
        this.headers[name] = value;
      }
      constructor() {
        UploadXHR.instance = this;
      }
    }
    vi.stubGlobal('XMLHttpRequest', UploadXHR);
    const controller = new AbortController(),
      progress = vi.fn();
    const file = new File(['synthetic-csv-only'], 'untrusted-name.csv', {
      type: 'text/csv',
    });
    const result = batchClient('unit', controller.signal, vi.fn()).upload(
      file,
      'stable-upload-key',
      progress,
    );
    const rejected = expect(result).rejects.toMatchObject({
      name: 'AbortError',
    });
    const xhr = UploadXHR.instance;
    expect(xhr.open).toHaveBeenCalledWith('POST', '/api/v1/batch-uploads');
    expect(xhr.headers).toEqual({
      Authorization: 'Bearer unit',
      'Content-Type': 'text/csv',
      'Idempotency-Key': 'stable-upload-key',
    });
    expect(xhr.send).toHaveBeenCalledWith(file);
    expect(xhr.withCredentials).toBe(false);
    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 1, total: 2 });
    expect(progress).toHaveBeenCalledWith(50);
    controller.abort();
    await rejected;
    expect(xhr.abort).toHaveBeenCalledTimes(1);
  });
  it('rejects empty and oversized uploads before creating a request', async () => {
    const xhr = vi.fn();
    vi.stubGlobal('XMLHttpRequest', xhr);
    const api = batchClient('unit', new AbortController().signal, vi.fn());
    await expect(
      api.upload(new File([], 'empty.csv'), 'key', vi.fn()),
    ).rejects.toMatchObject({ status: 422 });
    await expect(
      api.upload(
        new File([new Uint8Array(1048577)], 'large.csv'),
        'key',
        vi.fn(),
      ),
    ).rejects.toMatchObject({ status: 413 });
    expect(xhr).not.toHaveBeenCalled();
  });
  it.each([401, 403, 404])(
    'clears protected access on %s and never reflects server text',
    async (status) => {
      vi.stubGlobal(
        'fetch',
        vi
          .fn()
          .mockResolvedValue(
            new Response('private-server-predictor', { status }),
          ),
      );
      const deny = vi.fn();
      const api = batchClient(
        'synthetic-ui-token',
        new AbortController().signal,
        deny,
      );
      await expect(api.status(bid)).rejects.toBeInstanceOf(ApiError);
      expect(deny).toHaveBeenCalledWith(status);
    },
  );
  it.each([409, 413, 429])(
    'handles bounded/conflicting request %s',
    async (status) => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          new Response('private-values', {
            status,
            headers: { 'Retry-After': '3' },
          }),
        ),
      );
      const deny = vi.fn();
      await expect(
        batchClient('unit', new AbortController().signal, deny).export(
          bid,
          0,
          500,
        ),
      ).rejects.toMatchObject({ status, retryAfter: 3 });
      expect(deny).not.toHaveBeenCalled();
    },
  );
  it('uses bearer-protected blob export with no cookie or client-provided fields', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response('"case_id"\r\n', {
        headers: { 'Content-Type': 'text/csv' },
      }),
    );
    vi.stubGlobal('fetch', fetcher);
    const blob = await batchClient(
      'unit',
      new AbortController().signal,
      vi.fn(),
    ).export(bid, 10, 100);
    expect(await blob.text()).toContain('case_id');
    expect(fetcher.mock.calls[0][0]).toBe(
      `/api/v1/batch-assessments/${bid}/export?offset=10&limit=100`,
    );
    expect(fetcher.mock.calls[0][1]).toMatchObject({
      credentials: 'omit',
      cache: 'no-store',
      headers: { Authorization: 'Bearer unit' },
    });
  });
});
