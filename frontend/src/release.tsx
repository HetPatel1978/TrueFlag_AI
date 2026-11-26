import { useEffect, useState } from 'react';

declare const __TRUEFLAG_BUILD__: {
  build_id: string;
  frontend_version: string;
  source_state: string;
};

const validId = (value: unknown): value is string =>
  typeof value === 'string' && /^(unknown|[a-f0-9]{64})$/.test(value);
const short = (value: string) =>
  value === 'unknown' ? value : value.slice(0, 12);

// Rendered only inside the administrator's authenticated workspace.
export function ReleaseIdentity({
  token,
  onDenied,
}: {
  token: string;
  onDenied: (status: number) => void;
}) {
  const [backend, setBackend] = useState('unavailable');
  const [different, setDifferent] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await fetch('/api/v1/internal/release', {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        if ([401, 403].includes(response.status)) onDenied(response.status);
        if (!response.ok) throw new Error();
        const value = await response.json();
        if (controller.signal.aborted) return;
        if (
          !validId(value?.release?.build_id) ||
          !['ready', 'not_ready'].includes(value.status)
        )
          throw new Error();
        setBackend(
          `${short(value.release.build_id)} (${value.status === 'ready' ? 'ready' : 'not ready'})`,
        );
        setDifferent(
          value.release.build_id !== 'unknown' &&
            __TRUEFLAG_BUILD__.build_id !== 'unknown' &&
            value.release.build_id !== __TRUEFLAG_BUILD__.build_id,
        );
      } catch {
        if (!controller.signal.aborted) setBackend('unavailable');
      }
    })();
    return () => controller.abort();
  }, [token, onDenied]);
  const health = backend.endsWith('(ready)')
    ? 'Ready'
    : backend.endsWith('(not ready)')
      ? 'Not ready'
      : 'Unavailable';
  return (
    <table className="compact-table kv-table" aria-label="Release identity">
      <tbody>
        <tr>
          <th scope="row">Release</th>
          <td>
            Frontend v{__TRUEFLAG_BUILD__.frontend_version}{' '}
            {short(__TRUEFLAG_BUILD__.build_id)} (
            {__TRUEFLAG_BUILD__.source_state})
          </td>
        </tr>
        <tr>
          <th scope="row">API service</th>
          <td>API {backend}</td>
        </tr>
        <tr>
          <th scope="row">Health</th>
          <td>{health}</td>
        </tr>
        <tr>
          <th scope="row">Builds</th>
          <td>{different ? 'Builds differ' : 'Consistent or not reported'}</td>
        </tr>
      </tbody>
    </table>
  );
}
