import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
  ApiError,
  label,
  message,
  type AssessmentDetail,
  type Policy,
  type User,
} from './api';
import { Badge, Explanation } from './workbench';
import { TERMS, featureLabel } from './terminology';
import { PageHeader } from './ui';
import {
  download,
  uuid,
  type Approval,
  type Batch,
  type BatchFactory,
  type BatchPage,
  type BatchRow,
  type Columns,
  type CSVContract,
  type Import,
  type ImportRow,
  type Issues,
  type StartBody,
  type Upload,
  type Validation,
} from './batch-api';
import './batch.css';
import { AuditDetails, AuditList, CopyValue } from './display';
import { scorePercent } from './format';

export type BatchMemory = Map<string, unknown>;
type PendingUpload = { file: File; key: string; attempted?: boolean };
type PendingRequest<T> = { key: string; body: T };
const activeImport = (value: Import) =>
  ['pending', 'running'].includes(value.status);
const activeBatch = (value: Batch) =>
  ['dispatching', 'processing'].includes(value.status);
const terminalError = (e: unknown) =>
  e instanceof ApiError && [401, 403, 404, 410].includes(e.status);
function uploadLimits(contract: CSVContract | null) {
  const limits = contract?.limits;
  return limits
    ? `Limits: ${limits.max_bytes.toLocaleString()} bytes per file; ${limits.max_rows.toLocaleString()} data rows (excluding the header); ${limits.max_columns.toLocaleString()} columns; ${limits.max_field_bytes.toLocaleString()} bytes per cell.`
    : 'File-size, row-count, column-count and cell-size limits apply.';
}
function routeParts(route: string) {
  if (['#/batch', '#/batch/', '#/batch/new'].includes(route)) return {};
  const match =
    /^#\/batch\/(upload|import)\/([a-f0-9-]{36})(?:\/(validation|assessment)\/([a-f0-9-]{36}))?$/i.exec(
      route,
    );
  if (
    !match ||
    !uuid.test(match[2]) ||
    (match[4] && !uuid.test(match[4])) ||
    (match[3] &&
      match[3] !== (match[1] === 'upload' ? 'validation' : 'assessment'))
  )
    return null;
  return { kind: match[1], id: match[2], child: match[4] };
}
function Pager({
  page,
  change,
}: {
  page: BatchPage<unknown>;
  change: (offset: number) => void;
}) {
  return (
    <div className="pager">
      <span>
        {page.total
          ? `${page.offset + 1}–${Math.min(page.offset + page.limit, page.total)} of ${page.total}`
          : '0 results'}
      </span>
      <div>
        <button
          aria-label="Previous batch page"
          disabled={!page.offset}
          onClick={() => change(Math.max(0, page.offset - page.limit))}
        >
          Previous
        </button>
        <button
          aria-label="Next batch page"
          disabled={
            page.offset + page.limit >= page.total ||
            page.offset + page.limit > 10000
          }
          onClick={() => change(page.offset + page.limit)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
/** Counts as one line ("3 imported · 0 rejected · 0 remaining"); no nested boxes. */
function StatLine({ values }: { values: Record<string, number> }) {
  return (
    <p className="stat-line">
      {Object.entries(values).map(([name, count], n) => (
        <span key={name}>
          {n > 0 && ' · '}
          <strong>{count.toLocaleString()}</strong> {name}
        </span>
      ))}
    </p>
  );
}

function Stats({ values }: { values: Record<string, number> }) {
  return (
    <dl className="batch-stats">
      {Object.entries(values).map(([name, count]) => (
        <div key={name}>
          <dt>{name}</dt>
          <dd>{count.toLocaleString()}</dd>
        </div>
      ))}
    </dl>
  );
}

export function BatchProcessing({
  api,
  user,
  route,
  memory,
  uploadSessionId,
}: {
  api: BatchFactory;
  user: User;
  route: string;
  memory: BatchMemory;
  uploadSessionId?: string;
}) {
  const parts = routeParts(route);
  const [contract, setContract] = useState<CSVContract | null>(null);
  const [upload, setUpload] = useState<Upload | null>(null);
  const [columns, setColumns] = useState<Columns | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [validation, setValidation] = useState<Validation | null>(null);
  const [issues, setIssues] = useState<BatchPage<Issues> | null>(null);
  const [imported, setImported] = useState<Import | null>(null);
  const [importRows, setImportRows] = useState<BatchPage<ImportRow> | null>(
    null,
  );
  const [batch, setBatch] = useState<Batch | null>(null);
  const [results, setResults] = useState<BatchPage<BatchRow> | null>(null);
  const [selected, setSelected] = useState<AssessmentDetail | null>(null);
  const [file, setFile] = useState<File | null>(
    () =>
      (memory.get('pending-upload') as PendingUpload | undefined)?.file ?? null,
  );
  const [units, setUnits] = useState(false);
  const [approval, setApproval] = useState(false);
  const [policy, setPolicy] = useState<Policy>('Balanced');
  const [resume, setResume] = useState('');
  const [showSteps, setShowSteps] = useState(false);
  const [showRows, setShowRows] = useState(false);
  const [reassess, setReassess] = useState(false);
  const [showSkipped, setShowSkipped] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [paused, setPaused] = useState('');
  const [loading, setLoading] = useState(true);
  const [percent, setPercent] = useState<number | null>(null);
  const [revision, setRevision] = useState(0);
  const [offset, setOffset] = useState(0);
  const [exportOffset, setExportOffset] = useState(0);
  const [exportLimit, setExportLimit] = useState(500);
  const controller = useRef<AbortController | null>(null);
  const executing = useRef(false);
  const partKind = parts?.kind,
    partId = parts?.id,
    partChild = parts?.child;

  function navigate(target: string) {
    memory.set('resume-route', target);
    window.location.hash = target;
  }
  useEffect(() => {
    if (user.role !== 'admin' || !parts) return;
    const scope = new AbortController();
    controller.current = scope;
    let timer: number | undefined;
    let calls = 0;
    let contractLoaded = !!contract;
    const started = Date.now();
    async function refresh() {
      calls++;
      try {
        const client = api(scope.signal);
        if (!contractLoaded) {
          const value = await client.contract();
          if (scope.signal.aborted) return;
          setContract(value);
          contractLoaded = true;
        }
        let pending = false;
        if (partKind === 'upload' && partId) {
          const [meta, headers] = await Promise.all([
            client.metadata(partId),
            client.columns(partId),
          ]);
          if (scope.signal.aborted) return;
          setUpload(meta);
          setColumns(headers);
          setMapping(headers.exact_matches);
          if (meta.status === 'expired') throw new ApiError(410);
          if (partChild) {
            const value = await client.validation(partId, partChild);
            if (scope.signal.aborted) return;
            setValidation(value);
            setMapping(value.mapping);
            const page = await client.issues(partId, partChild, offset);
            if (scope.signal.aborted) return;
            setIssues(page);
          }
        }
        if (partKind === 'import' && partId) {
          const value = await client.imported(partId);
          if (scope.signal.aborted) return;
          setImported(value);
          if (partChild) {
            const status = await client.status(partChild);
            if (scope.signal.aborted) return;
            if (status.import_id !== partId) throw new ApiError(404);
            setBatch(status);
            pending = activeBatch(status);
            const page = await client.results(partChild, offset);
            if (scope.signal.aborted) return;
            setResults(page);
          } else {
            pending = activeImport(value);
            const page = await client.importRows(partId, offset);
            if (scope.signal.aborted) return;
            setImportRows(page);
          }
        }
        setError('');
        setPaused('');
        setLoading(false);
        if (pending) {
          if (calls >= 60 || Date.now() - started >= 300000)
            setPaused(
              'Automatic refresh paused after five minutes. Processing continues on the server. Save this link or refresh later.',
            );
          else timer = window.setTimeout(() => void refresh(), 5000);
        }
      } catch (failure) {
        if (scope.signal.aborted) return;
        setLoading(false);
        setError(message(failure));
        if (terminalError(failure)) {
          setUpload(null);
          setValidation(null);
          setImported(null);
          setBatch(null);
          setResults(null);
          setSelected(null);
          return;
        }
        if (
          partKind === 'import' &&
          calls < 60 &&
          Date.now() - started < 300000
        ) {
          const retry = failure instanceof ApiError ? failure.retryAfter : 0;
          if (retry > 60)
            setPaused(
              'Refresh is rate-limited. Wait before refreshing manually.',
            );
          else
            timer = window.setTimeout(
              () => void refresh(),
              Math.max(5000, retry * 1000),
            );
        }
      }
    }
    void refresh();
    return () => {
      scope.abort();
      if (timer) window.clearTimeout(timer);
      controller.current = null;
    };
    // A new route/page/revision owns an independent request and polling generation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, user.role, partKind, partId, partChild, revision, offset]);

  async function run(
    name: string,
    operation: (signal: AbortSignal) => Promise<void>,
  ) {
    const scope = controller.current;
    if (!scope || scope.signal.aborted || executing.current) return;
    executing.current = true;
    setBusy(name);
    setError('');
    try {
      await operation(scope.signal);
    } catch (failure) {
      if (!scope.signal.aborted) {
        if (name === 'upload') setPercent(null);
        if (
          name === 'upload' &&
          failure instanceof ApiError &&
          failure.status === 413
        ) {
          memory.delete('pending-upload');
          setError(
            `CSV exceeds an upload limit. ${uploadLimits(contract)} Split the file into smaller batches or reduce oversized columns or cells before uploading again.`,
          );
        } else setError(message(failure));
      }
    } finally {
      executing.current = false;
      if (!scope.signal.aborted) setBusy('');
    }
  }
  function requestReceipt<T>(key: string, body: T): PendingRequest<T> {
    let saved = memory.get(key) as PendingRequest<T> | undefined;
    if (!saved) {
      saved = { key: crypto.randomUUID(), body };
      memory.set(key, saved);
    }
    return saved;
  }
  async function submitFile(signal: AbortSignal) {
    if (!file) return;
    let saved = memory.get('pending-upload') as PendingUpload | undefined;
    if (!saved || saved.file !== file) {
      saved = { file, key: crypto.randomUUID() };
      memory.set('pending-upload', saved);
    }
    setPercent(0);
    saved.attempted = true;
    const value = await api(signal).upload(
      saved.file,
      saved.key,
      setPercent,
      uploadSessionId,
    );
    if (signal.aborted) return;
    memory.delete('pending-upload');
    setFile(null);
    navigate(`#/batch/upload/${value.upload_id}`);
  }
  function resumeImport(event: FormEvent) {
    event.preventDefault();
    if (!uuid.test(resume)) {
      setError('Enter a valid import ID from your saved receipt.');
      return;
    }
    navigate(`#/batch/import/${resume}`);
  }

  if (user.role !== 'admin')
    return (
      <section className="state" role="alert">
        <h1>Batch processing unavailable</h1>
        <p>
          Administrator access is required. Case permissions remain enforced by
          the server.
        </p>
      </section>
    );
  if (!parts)
    return (
      <section className="state">
        <h1>Invalid batch link</h1>
        <a href="#/batch">Open Batch Processing</a>
      </section>
    );
  const fields = contract
    ? [
        ...contract.metadata.map((f) => f.name),
        ...contract.predictors.map((f) => f.name),
      ]
    : [];
  const mapped =
    fields.length === 30 &&
    fields.every((f) => mapping[f]) &&
    new Set(fields.map((f) => mapping[f])).size === 30;
  const step = batch ? 4 : imported ? 3 : validation ? 2 : upload ? 1 : 0;
  const alreadyAssessed = imported?.assessed_cases ?? 0;
  const importedCases = imported
    ? imported.created_rows + imported.reused_rows
    : 0;
  // Re-assessment becomes secondary only when every imported case is already assessed.
  const allAssessed = alreadyAssessed > 0 && alreadyAssessed >= importedCases;
  const finished =
    !!batch &&
    ['completed', 'partially_completed', 'failed', 'stopped'].includes(
      batch.status,
    );
  const skippedRows =
    results?.items.filter((row) => row.outcome === 'skipped') ?? [];
  const shownRows = (results?.items ?? []).filter(
    (row) => showSkipped || row.outcome !== 'skipped',
  );
  return (
    <div className="batch-workspace">
      <PageHeader
        title="Imports"
        description="Upload alerts, assess risk, then review the cases."
        actions={
          partId && (
            <a className="button" href="#/batch/new">
              Add another CSV
            </a>
          )
        }
      />
      {finished && !showSteps ? (
        <p className="import-complete" role="status">
          <strong>Import complete</strong> ·{' '}
          {batch.total_cases.toLocaleString()} case
          {batch.total_cases === 1 ? '' : 's'}
          <button
            className="small"
            aria-expanded={false}
            onClick={() => setShowSteps(true)}
          >
            View details
          </button>
        </p>
      ) : (
        <ol className="batch-steps" aria-label="Batch workflow">
          {[
            'Upload',
            'Map columns',
            'Validate',
            'Import',
            'Assess & results',
          ].map((name, n) => (
            <li
              key={name}
              aria-current={step === n ? 'step' : undefined}
              className={step >= n ? 'reached' : ''}
            >
              <span>{n + 1}</span>
              {name}
            </li>
          ))}
        </ol>
      )}
      {error && (
        <div className="error batch-alert" role="alert">
          {error}{' '}
          <button
            disabled={!!busy}
            onClick={() => {
              setError('');
              setRevision((n) => n + 1);
            }}
          >
            Refresh
          </button>
        </div>
      )}
      {paused && (
        <p className="notice" role="status">
          {paused}{' '}
          <button onClick={() => setRevision((n) => n + 1)}>
            Resume refresh
          </button>
        </p>
      )}
      {loading && <p role="status">Loading authorized batch data…</p>}
      {!partId && (
        <>
          <section className="panel batch-panel">
            <div className="section-heading">
              <h2>Upload CSV</h2>
              <button
                disabled={!!busy || !contract}
                onClick={() =>
                  void run('template', async (signal) => {
                    const blob = await api(signal).template();
                    if (!signal.aborted)
                      download(blob, 'trueflag-alerts-v1.csv');
                  })
                }
              >
                Download CSV template
              </button>
            </div>
            <p className="muted">
              UTF-8 CSV ·{' '}
              {contract?.limits?.max_rows.toLocaleString() ?? 'Limited'} data
              rows per file · synthetic records only.
            </p>
            <details className="file-requirements">
              <summary>File requirements</summary>
              <p>{uploadLimits(contract)}</p>
              <p>
                Use the template's required columns. Files are not
                malware-scanned.
              </p>
            </details>
            <label className="batch-drop" htmlFor="batch-file">
              Choose a CSV file
              <input
                id="batch-file"
                type="file"
                accept=".csv,text/csv"
                disabled={!!busy}
                onChange={(event) => {
                  const chosen = event.target.files?.[0] ?? null;
                  setFile(chosen);
                  if (chosen)
                    memory.set('pending-upload', {
                      file: chosen,
                      key: crypto.randomUUID(),
                    });
                  else memory.delete('pending-upload');
                  setError('');
                  setPercent(null);
                }}
              />
            </label>
            {file && (
              <p>
                {file.name}{' '}
                <span className="muted">
                  ({Math.ceil(file.size / 1024)} KiB)
                </span>
              </p>
            )}
            {percent !== null && (
              <div className="batch-upload-progress">
                <label htmlFor="upload-progress">
                  {percent === 100
                    ? 'Upload transferred; checking file…'
                    : `Uploading ${percent}%`}
                </label>
                <progress id="upload-progress" value={percent} max={100} />
              </div>
            )}
            <button
              className="primary"
              disabled={!file || !!busy || !contract}
              onClick={() => void run('upload', submitFile)}
            >
              {busy === 'upload'
                ? 'Uploading…'
                : (memory.get('pending-upload') as PendingUpload | undefined)
                      ?.attempted
                  ? 'Retry same upload'
                  : 'Upload CSV'}
            </button>
          </section>
          <details className="panel batch-panel disclosure">
            <summary>Resume an existing import</summary>
            <p className="muted">
              Use a saved import link or the ID on your import receipt. Sign-in
              and current permissions are required.
            </p>
            <form className="batch-resume" onSubmit={resumeImport}>
              <label htmlFor="resume-import">Import ID</label>
              <input
                id="resume-import"
                value={resume}
                onChange={(e) => setResume(e.target.value)}
                maxLength={36}
                autoComplete="off"
                required
              />
              <button>Resume import</button>
            </form>
            {typeof memory.get('resume-route') === 'string' && (
              <a className="button" href={memory.get('resume-route') as string}>
                Resume latest batch
              </a>
            )}
          </details>
        </>
      )}
      {upload && !validation && columns && (
        <section className="panel batch-panel">
          <div className="section-heading">
            <h2>Column mapping</h2>
            <Badge value="staged" />
          </div>
          <p>
            {upload.row_count.toLocaleString()} rows · {upload.column_count}{' '}
            source columns · 30 required targets
          </p>
          <p className="muted">
            {mapped
              ? 'All required columns matched. Confirm the source units to continue.'
              : 'Match the missing columns before continuing.'}
          </p>
          <details className="disclosure mapping-disclosure" open={!mapped}>
            <summary>
              Review column mapping · {fields.filter((n) => mapping[n]).length}{' '}
              of {fields.length} matched
            </summary>
            <div className="batch-mapping">
              {fields.map((name, index) => (
                <label key={name} htmlFor={`map-${index}`}>
                  <span>
                    {featureLabel(name)}
                    <small>
                      {index < (contract?.metadata.length ?? 0)
                        ? 'Alert metadata'
                        : name === 'state'
                          ? 'Recorded category'
                          : 'Assessment field'}{' '}
                      · {name}
                    </small>
                  </span>
                  <select
                    id={`map-${index}`}
                    aria-label={`Map ${name}`}
                    value={mapping[name] ?? ''}
                    disabled={!!busy}
                    onChange={(e) =>
                      setMapping((previous) => ({
                        ...previous,
                        [name]: e.target.value,
                      }))
                    }
                  >
                    <option value="">Select column</option>
                    {columns.columns.map((header) => (
                      <option key={header} value={header}>
                        {header}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </details>
          {!mapped && (
            <p className="hint">
              All 30 targets require different source columns.
            </p>
          )}
          <label className="batch-confirm">
            <input
              type="checkbox"
              checked={units}
              onChange={(e) => setUnits(e.target.checked)}
              disabled={!!busy}
            />{' '}
            Values use the required source units. Missing values and zero remain
            distinct; no conversion or substitution is applied.
          </label>
          <button
            className="primary"
            disabled={!mapped || !units || !!busy}
            onClick={() =>
              void run('validate', async (signal) => {
                const value = await api(signal).validate(upload.upload_id, {
                  mapping,
                  units: 'baseline_source_units',
                });
                if (!signal.aborted)
                  navigate(
                    `#/batch/upload/${upload.upload_id}/validation/${value.validation_id}`,
                  );
              })
            }
          >
            {busy === 'validate' ? 'Validating…' : 'Validate mapped file'}
          </button>
        </section>
      )}
      {validation && (
        <>
          <section className="panel batch-panel">
            <div className="section-heading">
              <h2>Validation preview</h2>
              <span className="muted">Mapping v{validation.version}</span>
            </div>
            <Stats
              values={{
                'Total rows': validation.total_rows,
                'Valid rows': validation.valid_rows,
                'Invalid rows': validation.invalid_rows,
                'Warning rows': validation.warning_rows,
              }}
            />
            {issues && (
              <>
                <IssueTable rows={issues.items} />
                <Pager page={issues} change={setOffset} />
              </>
            )}
          </section>
          <section className="panel batch-panel">
            <h2>Approve valid-row import</h2>
            <p>
              Only valid records become alerts and cases. Invalid records remain
              excluded. Import does not start risk assessment.
            </p>
            <label className="batch-confirm">
              <input
                type="checkbox"
                checked={approval}
                disabled={!validation.valid_rows || !!busy}
                onChange={(e) => setApproval(e.target.checked)}
              />{' '}
              I approve importing only the{' '}
              {validation.valid_rows.toLocaleString()} valid records.
            </label>
            <button
              className="primary"
              disabled={
                (!approval &&
                  !memory.has(`approve:${validation.validation_id}`)) ||
                !validation.valid_rows ||
                !!busy
              }
              onClick={() =>
                void run('approve', async (signal) => {
                  const saved = requestReceipt<Approval>(
                    `approve:${validation.validation_id}`,
                    {
                      approve_valid_rows: true,
                      upload_sha256: validation.upload_sha256,
                      mapping_sha256: validation.mapping_sha256,
                      mapping_version: validation.mapping_version,
                      validator_version: validation.validator_version,
                      validation_version: validation.version,
                      units: validation.units,
                    },
                  );
                  const value = await api(signal).approve(
                    validation.upload_id,
                    validation.validation_id,
                    saved.body,
                    saved.key,
                  );
                  if (!signal.aborted)
                    navigate(`#/batch/import/${value.import_id}`);
                })
              }
            >
              {busy === 'approve'
                ? 'Submitting…'
                : memory.has(`approve:${validation.validation_id}`)
                  ? 'Retry import request'
                  : 'Import valid records'}
            </button>
          </section>
        </>
      )}
      {imported && !batch && (
        <>
          <section className="panel batch-panel">
            <div className="section-heading">
              <h2>Import progress</h2>
              <Badge value={imported.status} />
            </div>
            <p className="import-next-step">
              {activeImport(imported)
                ? 'Importing your records. You can leave this page and return using the saved link.'
                : imported.status === 'failed'
                  ? 'Import needs attention. Review the details below.'
                  : allAssessed
                    ? 'Import finished. These cases already have assessments.'
                    : 'Import finished. Start an assessment when you are ready.'}
            </p>
            <StatLine
              values={{
                imported: imported.created_rows + imported.reused_rows,
                rejected: imported.invalid_rows + imported.conflict_rows,
                remaining: imported.unprocessed_rows,
              }}
            />
            <details
              className="disclosure"
              id="import-rows"
              open={showRows}
              onToggle={(event) => setShowRows(event.currentTarget.open)}
            >
              <summary>Import details and row results</summary>
              <StatLine
                values={{
                  processed: imported.processed_rows,
                  'new cases': imported.created_rows,
                  'reused / skipped': imported.reused_rows,
                  'invalid rows': imported.invalid_rows,
                  conflicts: imported.conflict_rows,
                  unprocessed: imported.unprocessed_rows,
                  'failed / not imported':
                    imported.status === 'failed'
                      ? imported.unprocessed_rows
                      : 0,
                }}
              />
              <progress
                aria-label="Import progress"
                value={imported.processed_rows}
                max={imported.total_rows}
              />
              {activeImport(imported) && (
                <p role="status">
                  Import queued or processing. You can leave and resume using
                  this link.
                </p>
              )}
              {imported.failure_code && (
                <p role="status">
                  {label(imported.failure_code)}. Committed records remain
                  available; unprocessed records are not silently imported.
                </p>
              )}
              {importRows && (
                <>
                  <div
                    className="table-wrap"
                    role="region"
                    aria-label="Imported row results"
                    tabIndex={0}
                  >
                    <table>
                      <caption className="sr-only">
                        Committed import row results
                      </caption>
                      <thead>
                        <tr>
                          <th>Row</th>
                          <th>Outcome</th>
                          <th>Details</th>
                          <th>Case</th>
                        </tr>
                      </thead>
                      <tbody>
                        {importRows.items.map((row) => (
                          <tr key={row.row_number}>
                            <td>{row.row_number}</td>
                            <td>
                              <Badge value={row.status} />
                            </td>
                            <td>
                              {row.errors
                                .map((e) => `${e.field}: ${label(e.code)}`)
                                .join('; ') ||
                                (row.reason_code
                                  ? label(row.reason_code)
                                  : 'Committed')}
                            </td>
                            <td>
                              {row.case_id ? (
                                <a href={`#/cases/${row.case_id}`}>Open case</a>
                              ) : (
                                '—'
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <Pager page={importRows} change={setOffset} />
                </>
              )}
            </details>
          </section>
          {['completed', 'partially_completed'].includes(imported.status) && (
            <section className="panel batch-panel">
              <h2>Assess imported alerts</h2>
              {alreadyAssessed > 0 && (
                <p className="already-assessed" role="status">
                  <strong>
                    Already assessed ({alreadyAssessed} of {importedCases})
                  </strong>{' '}
                  ·{' '}
                  <button
                    className="link-button"
                    onClick={() => {
                      setShowRows(true);
                      document
                        .getElementById('import-rows')
                        ?.scrollIntoView?.({ block: 'start' });
                    }}
                  >
                    View cases
                  </button>
                </p>
              )}
              {allAssessed && !reassess ? (
                <button className="small" onClick={() => setReassess(true)}>
                  Assess again
                </button>
              ) : (
                <>
                  <p>
                    Score the imported alerts and prepare review
                    recommendations. Cases stay open for human review.
                  </p>
                  <div className="assess-row">
                    <label htmlFor="batch-policy">Review policy</label>
                    <select
                      id="batch-policy"
                      value={policy}
                      disabled={
                        !!busy || memory.has(`start:${imported.import_id}`)
                      }
                      onChange={(e) => setPolicy(e.target.value as Policy)}
                    >
                      {(['Efficiency', 'Balanced', 'Coverage'] as Policy[]).map(
                        (p) => (
                          <option key={p}>{p}</option>
                        ),
                      )}
                    </select>
                    <button
                      className={allAssessed ? undefined : 'primary'}
                      disabled={
                        !!busy ||
                        !(imported.created_rows + imported.reused_rows)
                      }
                      onClick={() =>
                        void run('start', async (signal) => {
                          const saved = requestReceipt<StartBody>(
                            `start:${imported.import_id}`,
                            {
                              start_assessment: true,
                              import_validation_sha256:
                                imported.validation_sha256,
                              policy,
                            },
                          );
                          const value = await api(signal).start(
                            imported.import_id,
                            saved.body,
                            saved.key,
                          );
                          if (!signal.aborted)
                            navigate(
                              `#/batch/import/${imported.import_id}/assessment/${value.batch_id}`,
                            );
                        })
                      }
                    >
                      {busy === 'start'
                        ? 'Submitting…'
                        : memory.has(`start:${imported.import_id}`)
                          ? 'Retry assessment request'
                          : allAssessed
                            ? 'Assess again'
                            : 'Start assessments'}
                    </button>
                  </div>
                </>
              )}
            </section>
          )}
        </>
      )}
      {batch && (
        <>
          <section className="panel batch-panel">
            <div className="section-heading">
              <h2>Assessment progress</h2>
              <Badge value={batch.status} />
            </div>
            <p className="muted">
              {batch.total_eligible_cases.toLocaleString()} eligible cases ·{' '}
              {batch.policy} policy
            </p>
            <Stats
              values={{
                Completed: batch.succeeded,
                'In progress': batch.running,
                Waiting: batch.pending_dispatch + batch.queued,
                'Needs review': batch.failed_manual_review,
              }}
            />
            <progress
              aria-label="Assessment progress"
              value={
                batch.succeeded + batch.failed_manual_review + batch.skipped
              }
              max={Math.max(1, batch.total_cases)}
            />
            {batch.reason_code && (
              <p className="notice" role="status">
                {batch.reason_code === 'queue_capacity'
                  ? 'Waiting for worker capacity. Other batches may be ahead of this one.'
                  : batch.reason_code === 'rate_limit'
                    ? 'Dispatch is temporarily paused by the request limit.'
                    : label(batch.reason_code)}{' '}
                Processing continues on the server; you can leave this page.
              </p>
            )}
          </section>
          <section className="panel batch-panel">
            <div className="section-heading">
              <h2>Batch results</h2>
              {skippedRows.length > 0 && (
                <button
                  className="small"
                  aria-expanded={showSkipped}
                  onClick={() => setShowSkipped((v) => !v)}
                >
                  {showSkipped
                    ? 'Hide skipped'
                    : `Show skipped (${skippedRows.length})`}
                </button>
              )}
            </div>
            <p className="batch-disclaimer">
              Model scores are not proof of money laundering. Recommendations
              require human review; cases are never automatically dismissed.
            </p>
            {results && (
              <>
                <div
                  className="table-wrap"
                  role="region"
                  aria-label="Batch assessment results"
                  tabIndex={0}
                >
                  <table>
                    <caption className="sr-only">
                      Authorized batch assessment results
                    </caption>
                    <thead>
                      <tr>
                        <th>Case</th>
                        <th>Score</th>
                        <th>{TERMS.recommendation}</th>
                        <th>
                          <span className="sr-only">Links</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {shownRows.map((row) => (
                        <tr key={row.case_id}>
                          <td className="case-id">
                            <a
                              href={`#/cases/${row.case_id}`}
                              aria-label={`Case ${row.case_id.slice(0, 8)}, row ${row.source_row_number}`}
                            >
                              {row.case_id.slice(0, 8)}
                            </a>
                          </td>
                          <td className="num">
                            {row.assessment
                              ? scorePercent(row.assessment.score)
                              : '–'}
                          </td>
                          <td>
                            {row.assessment
                              ? label(row.assessment.recommended_route)
                              : row.outcome === 'failed_manual_review'
                                ? `Manual review required${row.reason_code ? ` · ${label(row.reason_code)}` : ''}`
                                : row.outcome === 'skipped'
                                  ? `Skipped${row.reason_code ? ` · ${label(row.reason_code)}` : ''}`
                                  : row.retrying
                                    ? `Retrying · attempt ${row.attempts}`
                                    : 'Processing'}
                          </td>
                          <td>
                            {row.assessment && (
                              <button
                                className="quiet"
                                onClick={() => setSelected(row.assessment)}
                              >
                                View explanation
                              </button>
                            )}
                            <a href={`#/cases/${row.case_id}`}>Open case</a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!results.total && <p>No case results available.</p>}
                <Pager
                  page={results}
                  change={(value) => {
                    setSelected(null);
                    setResults(null);
                    setOffset(value);
                  }}
                />
              </>
            )}
            {!results && <p role="status">Loading authorized results…</p>}
          </section>
          {selected && (
            <>
              <button onClick={() => setSelected(null)}>
                Hide explanation
              </button>
              <Explanation value={selected} />
            </>
          )}
          <details className="panel batch-panel disclosure">
            <summary>Export results</summary>
            <p className="muted">
              Exports contain authorized result fields only, without predictor
              values or source identifiers. Spreadsheet formulas are neutralized
              by the server.
            </p>
            <div className="batch-export">
              <label htmlFor="export-offset">
                Rows to skip before export
                <input
                  id="export-offset"
                  type="number"
                  min={0}
                  max={Math.max(0, batch.total_cases - 1)}
                  value={exportOffset}
                  onChange={(e) => setExportOffset(Number(e.target.value))}
                />
              </label>
              <label htmlFor="export-limit">
                Maximum rows
                <select
                  id="export-limit"
                  value={exportLimit}
                  onChange={(e) => setExportLimit(Number(e.target.value))}
                >
                  <option value={10}>10</option>
                  <option value={100}>100</option>
                  <option value={500}>500</option>
                </select>
              </label>
              <button
                disabled={
                  !!busy ||
                  !Number.isInteger(exportOffset) ||
                  exportOffset < 0 ||
                  exportOffset >= batch.total_cases
                }
                onClick={() =>
                  void run('export', async (signal) => {
                    const blob = await api(signal).export(
                      batch.batch_id,
                      exportOffset,
                      exportLimit,
                    );
                    if (!signal.aborted)
                      download(
                        blob,
                        `trueflag-results-${batch.batch_id}-${exportOffset + 1}.csv`,
                      );
                  })
                }
              >
                {busy === 'export'
                  ? 'Preparing export…'
                  : 'Download results CSV'}
              </button>
            </div>
            <p className="hint">
              Only the requested bounded range is downloaded; exports are
              audited. Save downloaded data according to your organization’s
              retention rules.
            </p>
          </details>
        </>
      )}
      {(imported || batch) && (
        <AuditDetails>
          <AuditList>
            {imported && (
              <CopyValue label="Import ID" value={imported.import_id} />
            )}
            {imported && (
              <>
                <dt>Saved resume link</dt>
                <dd>
                  <a href={`#/batch/import/${imported.import_id}`}>
                    Open this import
                  </a>
                </dd>
              </>
            )}
            {batch && <CopyValue label="Batch ID" value={batch.batch_id} />}
            {batch && <CopyValue label="Model" value={batch.model_version} />}
            {batch && (
              <CopyValue label="Model SHA-256" value={batch.model_sha256} />
            )}
            {batch && (
              <>
                <dt>Policy</dt>
                <dd>
                  {batch.policy} / {batch.policy_version}
                </dd>
              </>
            )}
          </AuditList>
          {batch && (
            <div>
              <h5>Processing breakdown</h5>

              <Stats
                values={{
                  Eligible: batch.total_eligible_cases,
                  'Awaiting dispatch': batch.pending_dispatch,
                  Queued: batch.queued,
                  'In progress': batch.running,
                  Completed: batch.succeeded,
                  'Failed / manual review': batch.failed_manual_review,
                  Skipped: batch.skipped,
                  Retrying: batch.retrying,
                }}
              />
              <p className="hint">
                Already assessed: {batch.already_assessed}. Retrying is a subset
                of queued; it is not a terminal failure.
              </p>
            </div>
          )}
        </AuditDetails>
      )}
    </div>
  );
}

function IssueTable({ rows }: { rows: Issues[] }) {
  if (!rows.length)
    return (
      <p className="notice">
        No row errors or warnings. All records passed validation.
      </p>
    );
  return (
    <div
      className="table-wrap"
      role="region"
      aria-label="Validation issues"
      tabIndex={0}
    >
      <table>
        <caption className="sr-only">Validation row diagnostics</caption>
        <thead>
          <tr>
            <th>Logical row</th>
            <th>Errors</th>
            <th>Warnings</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.row_number}>
              <td>{row.row_number}</td>
              <td>
                {row.errors
                  .map((e) => `${e.field}: ${label(e.code)}`)
                  .join('; ') || '—'}
              </td>
              <td>
                {row.warnings
                  .map((e) => `${e.field}: ${label(e.code)}`)
                  .join('; ') || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
