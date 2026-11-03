import {
  useCallback,
  useEffect,
  useState,
  useSyncExternalStore,
  type FormEvent,
} from 'react';
import {
  ApiError,
  client,
  currentUser,
  message,
  signIn,
  type Client,
  type User,
} from './api';
import { Dashboard, CaseView } from './workbench';
import { Receipts, type Receipt } from './receipts';
import { BatchProcessing, type BatchMemory } from './batch';
import { batchClient, type BatchFactory } from './batch-api';

export type ApiFactory = (signal?: AbortSignal) => Client;
type Session = { token: string; user: User; controller: AbortController };
const subscribe = (fn: () => void) => {
  window.addEventListener('hashchange', fn);
  return () => window.removeEventListener('hashchange', fn);
};

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [notice, setNotice] = useState('');
  const logout = useCallback((reason = '') => {
    setSession((previous) => {
      previous?.controller.abort();
      return null;
    });
    setNotice(reason);
    window.location.hash = '/';
  }, []);
  // No localStorage/sessionStorage/cookie token; refresh always requires sign-in.
  return session ? (
    <Workspace key={session.token} session={session} logout={logout} />
  ) : (
    <Login notice={notice} onLogin={setSession} />
  );
}

function Login({
  notice,
  onLogin,
}: {
  notice: string;
  onLogin: (s: Session) => void;
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function login(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    const controller = new AbortController();
    try {
      const token = await signIn(username, password, controller.signal);
      const user = await currentUser(token, controller.signal);
      setPassword('');
      onLogin({ token, user, controller });
    } catch (failure) {
      setPassword('');
      setError(message(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-shell">
      <section className="login-intro">
        <Brand />
        <p className="eyebrow">AML INTELLIGENCE WORKBENCH</p>
        <h1>
          Clarity for every
          <br />
          <em>investigation.</em>
        </h1>
        <p>
          Verified model intelligence.
          <br />
          Accountable human review.
        </p>
        <div className="login-rule" />
        <span className="environment">SYNTHETIC ENVIRONMENT</span>
      </section>
      <section className="login-form" aria-labelledby="sign-in-title">
        <p className="eyebrow">AUTHORIZED ACCESS</p>
        <h2 id="sign-in-title">Welcome back</h2>
        <p className="muted">Sign in to your assigned case workspace.</p>
        {notice && (
          <p role="status" className="notice">
            {notice}
          </p>
        )}
        <form
          onSubmit={(e) => {
            void login(e);
          }}
        >
          <label htmlFor="username">Username</label>
          <input
            id="username"
            autoComplete="username"
            required
            minLength={3}
            maxLength={100}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={1024}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in →'}
          </button>
        </form>
        <p className="hint">
          Accounts are provisioned by an administrator. Your session stays in
          memory and clears on sign-out or refresh.
        </p>
      </section>
    </main>
  );
}

function Brand() {
  return (
    <a className="brand" href="#/" aria-label="TrueFlag home">
      <span className="mark">TF</span>
      <span>
        TrueFlag <b>AI</b>
      </span>
    </a>
  );
}

function Workspace({
  session,
  logout,
}: {
  session: Session;
  logout: (reason?: string) => void;
}) {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  const [denied, setDenied] = useState<number | null>(null);
  const [guard, setGuard] = useState<'ready' | 'checking' | 'unavailable'>(
    'ready',
  );
  const [generation, setGeneration] = useState(0);
  const [receipts] = useState(() => new Map<string, Receipt>());
  const [batchMemory] = useState<BatchMemory>(() => new Map());
  const onDenied = useCallback(
    (status: number) => {
      if (status === 401) logout('Your session ended. Sign in again.');
      else {
        receipts.clear();
        batchMemory.clear();
        setDenied(status);
      }
    },
    [logout, receipts, batchMemory],
  );
  const api = useCallback<ApiFactory>(
    (signal) =>
      client(
        session.token,
        signal
          ? AbortSignal.any([session.controller.signal, signal])
          : session.controller.signal,
        onDenied,
      ),
    [session, onDenied],
  );
  const batchApi = useCallback<BatchFactory>(
    (signal) =>
      batchClient(
        session.token,
        signal
          ? AbortSignal.any([session.controller.signal, signal])
          : session.controller.signal,
        onDenied,
      ),
    [session, onDenied],
  );

  useEffect(() => {
    const controller = new AbortController();
    let busy = false;
    async function verify() {
      if (busy || document.hidden) return;
      busy = true;
      try {
        const user = await currentUser(session.token, controller.signal);
        if (controller.signal.aborted) return;
        if (user.role !== session.user.role || user.id !== session.user.id) {
          logout('Permissions changed. Sign in again.');
          return;
        }
        setGuard('ready');
      } catch (failure) {
        if (controller.signal.aborted) return;
        if (failure instanceof ApiError && [401, 403].includes(failure.status))
          logout('Your access changed. Sign in again.');
        else setGuard('unavailable');
      } finally {
        busy = false;
      }
    }
    function visibility() {
      if (document.hidden) setGuard('checking');
      else {
        setGuard('checking');
        setGeneration((n) => n + 1);
        void verify();
      }
    }
    void verify();
    const timer = window.setInterval(() => {
      void verify();
    }, 10000);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [session, logout, generation]);

  const match = /^#\/cases\/([a-f0-9-]{36})(\/assessment)?$/i.exec(hash);
  const isBatch = hash.startsWith('#/batch');
  return (
    <div className="workspace">
      <a
        className="skip"
        href="#main-content"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById('main-content')?.focus();
        }}
      >
        Skip to content
      </a>
      <aside className="sidebar">
        <Brand />
        <p className="nav-label">WORKSPACE</p>
        <a
          className={`nav-item ${!match && !isBatch ? 'active' : ''}`}
          href="#/"
        >
          ◫ <span>Alert dashboard</span>
        </a>
        {session.user.role === 'admin' && (
          <a className={`nav-item ${isBatch ? 'active' : ''}`} href="#/batch">
            <span aria-hidden="true">▤</span> <span>Batch Processing</span>
          </a>
        )}
        <div className="sidebar-bottom">
          <span className="environment">SYNTHETIC DATA</span>
          <p>
            Recommendations support
            <br />
            human decisions.
          </p>
        </div>
      </aside>
      <div className="work-area">
        <header className="topbar">
          <span className="breadcrumb">
            Workspace <span>/</span>{' '}
            {isBatch ? 'Batch Processing' : match ? 'Case review' : 'Alerts'}
          </span>
          <div className="account">
            <span>
              <b>{session.user.username}</b>
              <small>{session.user.role}</small>
            </span>
            <button className="quiet" onClick={() => logout()}>
              Sign out
            </button>
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          <Receipts.Provider value={receipts}>
            {guard !== 'ready' ? (
              <div className="state" role="status">
                <h2>
                  {guard === 'checking'
                    ? 'Verifying access…'
                    : 'Access verification unavailable'}
                </h2>
                <p>Protected information is hidden until access is verified.</p>
                {guard === 'unavailable' && (
                  <button onClick={() => setGeneration((n) => n + 1)}>
                    Retry verification
                  </button>
                )}
              </div>
            ) : denied ? (
              <div className="state" role="alert">
                <h1>Information unavailable</h1>
                <p>{new ApiError(denied).message}</p>
                <button
                  onClick={() => {
                    setDenied(null);
                    window.location.hash = '/';
                    setGeneration((n) => n + 1);
                  }}
                >
                  Return to authorized cases
                </button>
              </div>
            ) : isBatch ? (
              <BatchProcessing
                key={`${hash}:${generation}`}
                api={batchApi}
                user={session.user}
                route={hash}
                memory={batchMemory}
              />
            ) : match ? (
              <CaseView
                key={`${hash}:${generation}`}
                id={match[1]}
                workflow={!!match[2]}
                api={api}
                user={session.user}
              />
            ) : (
              <Dashboard key={generation} api={api} user={session.user} />
            )}
          </Receipts.Provider>
        </main>
        <footer>
          TrueFlag AI <span>·</span> Human review required. No automatic case
          actions.
        </footer>
      </div>
    </div>
  );
}
