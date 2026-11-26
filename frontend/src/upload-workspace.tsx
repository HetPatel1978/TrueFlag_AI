import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError, message, request, type User } from './api';

export type UploadSession = {
  id: string;
  created_at: string;
  case_count: number;
  upload_count: number;
  can_upload: boolean;
  uploads: {
    upload_id: string;
    created_at: string;
    status: string;
    resume_route: string;
  }[];
};
type Workspace = {
  version: number;
  active: UploadSession | null;
  items: { id: string; created_at: string }[];
  total: number;
  offset: number;
  limit: number;
};
const title = (value: { created_at: string; id: string }) =>
  `Session ${new Date(value.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })} · ${value.id.slice(0, 6)}`;
const shortTitle = (value: { created_at: string }) =>
  `Upload session ${new Date(value.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;

export function UploadWorkspace({
  token,
  user,
  onDenied,
  children,
  route,
}: {
  token: string;
  user: User;
  onDenied: (status: number) => void;
  children: (session: UploadSession) => ReactNode;
  route: string;
}) {
  const [state, setState] = useState<Workspace | null>(null);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const menu = useRef<HTMLDetailsElement | null>(null);
  const closeMenu = () => {
    if (menu.current) menu.current.open = false;
  };
  const [busy, setBusy] = useState(false);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const contextKey = JSON.stringify([token, route, offset, revision]);
  const [verifiedFor, setVerifiedFor] = useState('');
  const checking = verifiedFor !== contextKey;
  const pending = useRef<{ key: string; version: number } | null>(null);
  const controller = useRef<AbortController | null>(null);
  const mutateLock = useRef(false);
  useEffect(() => {
    const c = new AbortController();
    controller.current = c;
    async function load() {
      const signal = c.signal;
      let value = await request<Workspace>(
        `/api/v1/upload-sessions?limit=20&offset=${offset}`,
        { headers: { Authorization: `Bearer ${token}` }, signal },
        onDenied,
      );
      if (signal.aborted) return;
      const reference =
        /^#\/batch\/(upload|import)\/([a-f0-9-]{36})(?:\/|$)/i.exec(route);
      if (reference && user.role === 'admin') {
        const linked = await request<{ session_id: string }>(
          `/api/v1/upload-sessions/lookup/${reference[1]}/${reference[2]}`,
          { headers: { Authorization: `Bearer ${token}` }, signal },
          onDenied,
        );
        if (signal.aborted) return;
        if (linked.session_id !== value.active?.id) {
          value = await request<Workspace>(
            `/api/v1/upload-sessions/${encodeURIComponent(linked.session_id)}/selection`,
            {
              method: 'PUT',
              signal,
              headers: {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ version: value.version }),
            },
            onDenied,
          );
        }
      }
      if (signal.aborted) return;
      if (!Number.isInteger(value.version) || !Array.isArray(value.items))
        throw new Error('Invalid upload session response.');
      setState(value);
      setError('');
      setVerifiedFor(contextKey);
    }
    void load().catch((e) => {
      if (!c.signal.aborted) {
        setState(null);
        setError(message(e));
        setVerifiedFor(contextKey);
      }
    });
    return () => {
      c.abort();
      controller.current = null;
    };
  }, [token, onDenied, offset, route, user.role, contextKey]);
  useEffect(() => {
    const focus = () => setRevision((n) => n + 1);
    window.addEventListener('focus', focus);
    return () => window.removeEventListener('focus', focus);
  }, []);
  useEffect(() => {
    if (checking || !['#/batch', '#/batch/'].includes(route)) return;
    const resume = state?.active?.uploads.find((u) => u.status !== 'expired');
    if (resume) window.location.replace(resume.resume_route);
  }, [checking, route, state]);
  async function change(id?: string) {
    if (!state || checking || mutateLock.current || !controller.current) return;
    mutateLock.current = true;
    setBusy(true);
    const signal = controller.current.signal;
    const saved = id
      ? null
      : (pending.current ??= {
          key: crypto.randomUUID(),
          version: state.version,
        });
    try {
      const value = await request<Workspace>(
        id
          ? `/api/v1/upload-sessions/${encodeURIComponent(id)}/selection`
          : '/api/v1/upload-sessions',
        {
          method: id ? 'PUT' : 'POST',
          signal,
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
            ...(saved ? { 'Idempotency-Key': saved.key } : {}),
          },
          body: JSON.stringify({ version: saved?.version ?? state.version }),
        },
        onDenied,
      );
      if (signal.aborted) return;
      pending.current = null;
      setState(value);
      setError('');
      setConfirm(false);
      setOffset(0);
      window.location.hash = id ? '/' : '/batch/new';
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) pending.current = null;
      if (!signal.aborted) {
        setError(message(e));
        setState(null);
      }
    } finally {
      mutateLock.current = false;
      setBusy(false);
    }
  }
  return (
    <>
      <section
        className="upload-session-bar compact"
        aria-label="Upload session"
      >
        <p
          className="session-line"
          title={state?.active ? title(state.active) : undefined}
        >
          <strong>
            {state?.active ? shortTitle(state.active) : 'Upload session'}
          </strong>
          {state?.active && (
            <span className="muted">
              {' · '}
              {state.active.case_count.toLocaleString()} case
              {state.active.case_count === 1 ? '' : 's'}
            </span>
          )}
        </p>
        {state && (user.role === 'admin' || state.total > 0) && (
          <details className="session-menu" ref={menu}>
            <summary aria-label="Session options">⋯</summary>
            <div className="session-menu-items" role="menu">
              {user.role === 'admin' && (
                <>
                  <a role="menuitem" href="#/batch/new" onClick={closeMenu}>
                    Add CSV
                  </a>
                  <button
                    role="menuitem"
                    disabled={busy}
                    onClick={() => {
                      closeMenu();
                      setConfirm(true);
                    }}
                  >
                    New session
                  </button>
                </>
              )}
              {state.total > 0 && (
                <button
                  role="menuitem"
                  onClick={() => {
                    closeMenu();
                    setShowHistory((v) => !v);
                  }}
                >
                  Session history
                </button>
              )}
            </div>
          </details>
        )}
        {confirm && (
          <div
            className="session-confirm"
            role="group"
            aria-label="Confirm new upload session"
          >
            <p>
              Start an empty workspace? Previous cases, results and running jobs
              stay saved in session history.
            </p>
            <button
              className="primary"
              disabled={busy}
              onClick={() => void change()}
            >
              {busy ? 'Starting…' : 'Confirm new session'}
            </button>
            <button disabled={busy} onClick={() => setConfirm(false)}>
              Cancel
            </button>
          </div>
        )}
        {error && (
          <p role="alert">
            {error}{' '}
            <button onClick={() => setRevision((n) => n + 1)}>
              Reload session
            </button>
          </p>
        )}
        {checking && !error && (
          <p role="status">Restoring your upload session…</p>
        )}
        {state && state.total > 0 && showHistory && (
          <div className="session-history">
            <label htmlFor="upload-session-choice">Open a saved session</label>
            <select
              id="upload-session-choice"
              value={
                state.items.some((s) => s.id === state.active?.id)
                  ? state.active?.id
                  : ''
              }
              disabled={busy}
              onChange={(e) => {
                if (e.target.value) void change(e.target.value);
              }}
            >
              <option value="" disabled>
                Select a session
              </option>
              {state.items.map((s) => (
                <option key={s.id} value={s.id}>
                  {title(s)}
                </option>
              ))}
            </select>
            <div className="pager">
              <button
                disabled={!offset || busy}
                onClick={() => setOffset((n) => Math.max(0, n - 20))}
              >
                Previous sessions
              </button>
              <button
                disabled={offset + 20 >= state.total || busy}
                onClick={() => setOffset((n) => n + 20)}
              >
                More sessions
              </button>
            </div>
            {!!state.active?.uploads.length && (
              <ul>
                {state.active.uploads.map((u, i) => (
                  <li key={u.upload_id}>
                    <a href={u.resume_route}>
                      Resume upload {state.active!.upload_count - i}
                    </a>{' '}
                    · {u.status.replaceAll('_', ' ')}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
      {state?.active ? (
        <div hidden={checking || !!error}>{children(state.active)}</div>
      ) : (
        state && (
          <section className="state">
            <h1>Cases</h1>
            <h2>No uploaded cases available</h2>
            <p>Your authorized uploaded cases will appear here.</p>
          </section>
        )
      )}
    </>
  );
}
