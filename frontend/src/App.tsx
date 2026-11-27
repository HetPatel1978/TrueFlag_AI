import {
  useCallback,
  useEffect,
  useRef,
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
import { ReleaseIdentity } from './release';
import { ProviderUsage } from './provider-usage';
import { AnthropicCard } from './anthropic-card';
import {
  clearSignOutIntent,
  endBrowserSession,
  markSignOutIntent,
  restoreBrowserSession,
  rememberedRenewalDelay,
} from './session';
import { Icon, PageHeader } from './ui';
import { workflowClient, type WorkflowFactory } from './workflow-api';
import { humanCaseworkClient, type HumanFactory } from './human-casework-api';
import { SupervisorQueue } from './human-casework';
import { UploadWorkspace } from './upload-workspace';
import { OperationalOverview } from './operational-overview';
import { AppFooter } from './display';
import {
  investigationClient,
  InvestigationReceipts,
  type InvestigationFactory,
  type PacketReceipt,
} from './investigation-api';

export type ApiFactory = (signal?: AbortSignal) => Client;
type Session = { token: string; user: User; controller: AbortController };
const subscribe = (fn: () => void) => {
  window.addEventListener('hashchange', fn);
  return () => window.removeEventListener('hashchange', fn);
};

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [notice, setNotice] = useState('');
  const [restoring, setRestoring] = useState(true);
  const [restoreError, setRestoreError] = useState(false);
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const [signingOut, setSigningOut] = useState(false);
  const renewal = useRef<AbortController | null>(null);
  useEffect(() => () => renewal.current?.abort(), []);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const restored = await restoreBrowserSession(controller.signal);
        if (!controller.signal.aborted) {
          setSession((previous) => {
            previous?.controller.abort();
            return restored
              ? { ...restored, controller: new AbortController() }
              : null;
          });
        }
      } catch {
        if (!controller.signal.aborted) setRestoreError(true);
      } finally {
        if (!controller.signal.aborted) setRestoring(false);
      }
    })();
    return () => controller.abort();
  }, [restoreAttempt]);
  const logout = useCallback((reason = '') => {
    renewal.current?.abort();
    markSignOutIntent();
    setSession((previous) => {
      previous?.controller.abort();
      return null;
    });
    setNotice(reason);
    setRestoreError(false);
    setSigningOut(true);
    window.location.hash = '/';
    void endBrowserSession()
      .catch(() =>
        setNotice(
          'Sign-out could not be confirmed. Sign in again to start a new session.',
        ),
      )
      .finally(() => setSigningOut(false));
  }, []);
  const renewSession = useCallback(() => {
    if (!session || session.controller.signal.aborted || renewal.current)
      return;
    if (rememberedRenewalDelay(session.token) === null) {
      logout('Your session ended. Sign in again.');
      return;
    }
    const controller = new AbortController();
    renewal.current = controller;
    session.controller.abort();
    void restoreBrowserSession(controller.signal)
      .then((restored) => {
        if (controller.signal.aborted) return;
        if (
          !restored ||
          restored.user.id !== session.user.id ||
          restored.user.role !== session.user.role
        ) {
          logout('Your access changed. Sign in again.');
          return;
        }
        setSession({ ...restored, controller: new AbortController() });
      })
      .catch(() => {
        if (!controller.signal.aborted) setRestoreError(true);
      })
      .finally(() => {
        if (renewal.current === controller) renewal.current = null;
      });
  }, [session, logout]);
  useEffect(() => {
    if (!session) return;
    const delay = rememberedRenewalDelay(session.token);
    if (delay === null) return;
    // A client clock ahead of the server must not create an immediate renewal loop.
    const timer = window.setTimeout(renewSession, Math.max(60000, delay));
    const resumed = () => {
      if (!document.hidden && rememberedRenewalDelay(session.token) === 0)
        renewSession();
    };
    window.addEventListener('focus', resumed);
    document.addEventListener('visibilitychange', resumed);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('focus', resumed);
      document.removeEventListener('visibilitychange', resumed);
    };
  }, [session, renewSession]);
  if (restoring || signingOut)
    return (
      <main className="state">
        <p role="status">
          {signingOut ? 'Signing out…' : 'Restoring your session…'}
        </p>
      </main>
    );
  if (restoreError)
    return (
      <main className="state" role="alert">
        <h1>Session verification unavailable</h1>
        <p>Your workspace is hidden until your session can be verified.</p>
        <button
          onClick={() => {
            setRestoreError(false);
            setRestoring(true);
            setRestoreAttempt((n) => n + 1);
          }}
        >
          Retry
        </button>
        <button onClick={() => logout()}>Sign in again</button>
      </main>
    );
  return session ? (
    <Workspace
      key={session.user.id}
      session={session}
      logout={logout}
      renewSession={renewSession}
    />
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
      clearSignOutIntent();
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
        <p className="eyebrow">AML intelligence workbench</p>
        <h1>
          Clarity for every
          <br />
          investigation.
        </h1>
        <p>
          Verified model intelligence.
          <br />
          Accountable human review.
        </p>
        <div className="login-rule" />
        <span className="environment">Synthetic environment</span>
      </section>
      <section className="login-form" aria-labelledby="sign-in-title">
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
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="hint">
          Accounts are provisioned by an administrator. This browser can
          remember your sign-in when enabled. Sign out when you finish on a
          shared device.
        </p>
      </section>
    </main>
  );
}

function Brand() {
  return (
    <a className="brand" href="#/" aria-label="TrueFlag home">
      <img
        className="brand-logo"
        src="/trueflag-logo.png"
        alt=""
        width="42"
        height="42"
      />
      <span>
        TrueFlag <b>AI</b>
      </span>
    </a>
  );
}

function Workspace({
  session,
  logout,
  renewSession,
}: {
  session: Session;
  logout: (reason?: string) => void;
  renewSession: () => void;
}) {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  const [denied, setDenied] = useState<number | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [compact, setCompact] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const [guard, setGuard] = useState<'ready' | 'checking' | 'unavailable'>(
    'ready',
  );
  const [generation, setGeneration] = useState(0);
  const [receipts] = useState(() => new Map<string, Receipt>());
  const [batchMemory] = useState<BatchMemory>(() => new Map());
  function sessionMemory(id: string): BatchMemory {
    const key = `session:${id}`;
    let value = batchMemory.get(key) as BatchMemory | undefined;
    if (!value) {
      value = new Map();
      batchMemory.set(key, value);
    }
    return value;
  }
  const [investigationMemory] = useState(
    () => new Map<string, PacketReceipt>(),
  );
  const onDenied = useCallback(
    (status: number) => {
      if (status === 401) {
        if (rememberedRenewalDelay(session.token) !== null) {
          setGuard('checking');
          renewSession();
        } else logout('Your session ended. Sign in again.');
      } else {
        receipts.clear();
        batchMemory.clear();
        investigationMemory.clear();
        setDenied(status);
      }
    },
    [
      logout,
      renewSession,
      session.token,
      receipts,
      batchMemory,
      investigationMemory,
    ],
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
  const investigationApi = useCallback<InvestigationFactory>(
    (signal) =>
      investigationClient(
        session.token,
        signal
          ? AbortSignal.any([session.controller.signal, signal])
          : session.controller.signal,
        onDenied,
      ),
    [session, onDenied],
  );
  const humanApi = useCallback<HumanFactory>(
    (signal) =>
      humanCaseworkClient(
        session.token,
        signal
          ? AbortSignal.any([session.controller.signal, signal])
          : session.controller.signal,
        onDenied,
      ),
    [session, onDenied],
  );
  const workflowApi = useCallback<WorkflowFactory>(
    (signal) =>
      workflowClient(
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
        if (
          failure instanceof ApiError &&
          failure.status === 401 &&
          rememberedRenewalDelay(session.token) !== null
        ) {
          setGuard('checking');
          renewSession();
        } else if (
          failure instanceof ApiError &&
          [401, 403].includes(failure.status)
        )
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
  }, [session, logout, renewSession, generation]);

  const match =
    /^#\/cases\/([a-f0-9-]{36})(\/assessment|\/evidence|\/investigation|\/activity|\/casework(?:\/decide)?)?$/i.exec(
      hash,
    );
  const batchRoute =
    hash === '#/admin'
      ? '#/batch'
      : hash.replace(/^#\/admin\/imports/, '#/batch');
  const isBatch = batchRoute.startsWith('#/batch');
  const isProvider = hash === '#/admin/provider-usage';
  const isReview = hash === '#/supervisor-review';
  const isOverview = hash === '#/overview';
  const isAdmin = isBatch || hash.startsWith('#/admin');
  const isDiagnostics = hash === '#/admin/diagnostics';
  return (
    <div className={`workspace${compact ? ' sidebar-compact' : ''}`}>
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
      <aside
        className="sidebar"
        onKeyDown={(event) => {
          if (event.key === 'Escape' && menuOpen) {
            setMenuOpen(false);
            menuButton.current?.focus();
          }
        }}
      >
        <div className="sidebar-heading">
          <Brand />
          <button
            className="sidebar-toggle"
            aria-label={compact ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-expanded={!compact}
            onClick={() => setCompact((v) => !v)}
          >
            <Icon name="chevron" />
          </button>
          <button
            ref={menuButton}
            className="mobile-menu"
            aria-controls="workspace-menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
          >
            Menu
          </button>
        </div>
        <nav
          id="workspace-menu"
          className={menuOpen ? 'menu-open' : ''}
          aria-label="Workspace navigation"
          onClick={(e) => {
            if ((e.target as HTMLElement).closest('a')) setMenuOpen(false);
          }}
        >
          <a
            className={`nav-item ${isOverview ? 'active' : ''}`}
            href="#/overview"
            aria-label="Overview"
            aria-current={isOverview ? 'page' : undefined}
          >
            <Icon name="overview" />
            <span>Overview</span>
          </a>
          <a
            className={`nav-item ${!isAdmin && !isReview && !isOverview ? 'active' : ''}`}
            href="#/"
            aria-label="Cases"
            aria-current={
              !isAdmin && !isReview && !isOverview ? 'page' : undefined
            }
          >
            <Icon name="cases" />
            <span>Cases</span>
          </a>
          {session.user.role !== 'analyst' && (
            <a
              className={`nav-item ${hash === '#/supervisor-review' ? 'active' : ''}`}
              href="#/supervisor-review"
              aria-label="Review Queue"
            >
              <Icon name="inbox" />
              <span>Review Queue</span>
            </a>
          )}
          {session.user.role === 'admin' && (
            <a
              className={`nav-item ${isAdmin ? 'active' : ''}`}
              href="#/admin/imports"
              aria-label="Administration"
              aria-current={isAdmin ? 'page' : undefined}
            >
              <Icon name="shield" />
              <span>Administration</span>
            </a>
          )}
        </nav>
      </aside>
      <div className="work-area">
        <header className="topbar">
          <nav className="breadcrumb" aria-label="Breadcrumb">
            {isAdmin ? (
              <>
                <a href="#/admin/imports">Administration</a>
                <Icon name="chevron" />
                <span aria-current="page">
                  {isProvider
                    ? 'Provider usage'
                    : isDiagnostics
                      ? 'Diagnostics'
                      : 'CSV imports'}
                </span>
              </>
            ) : (
              <a href="#/">Cases</a>
            )}
            {!isAdmin && (isReview || isOverview || match) && (
              <>
                <Icon name="chevron" />
                <span>
                  {isOverview
                    ? 'Overview'
                    : isAdmin
                      ? 'Administration'
                      : isBatch
                        ? 'Imports'
                        : isReview
                          ? 'Reviews'
                          : `Case ${match![1].slice(0, 8)}`}
                </span>
              </>
            )}
          </nav>
          <div className="account">
            <button
              className="quiet topbar-refresh"
              onClick={() => setGeneration((n) => n + 1)}
              aria-label="Refresh page data"
              title="Refresh page data"
            >
              <Icon name="refresh" />
            </button>
            <span className="badge environment-badge" data-ui-guard-skip>
              Synthetic data
            </span>
            <span>
              <b>{session.user.username}</b>
              <small>{session.user.role}</small>
            </span>
            <button className="quiet" onClick={() => logout()}>
              <Icon name="logout" /> Sign out
            </button>
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          {isAdmin && session.user.role === 'admin' && (
            <nav
              className="admin-navigation"
              aria-label="Administration sections"
            >
              <a
                href="#/admin/imports"
                aria-current={
                  !isProvider && !isDiagnostics ? 'page' : undefined
                }
              >
                CSV Imports
              </a>
              <a
                href="#/admin/provider-usage"
                aria-current={isProvider ? 'page' : undefined}
              >
                Provider Usage
              </a>
              <a
                href="#/admin/diagnostics"
                aria-current={isDiagnostics ? 'page' : undefined}
              >
                Diagnostics
              </a>
            </nav>
          )}
          <Receipts.Provider value={receipts}>
            <InvestigationReceipts.Provider value={investigationMemory}>
              {guard !== 'ready' ? (
                <div className="state" role="status">
                  <h2>
                    {guard === 'checking'
                      ? 'Verifying access…'
                      : 'Access verification unavailable'}
                  </h2>
                  <p>
                    Protected information is hidden until access is verified.
                  </p>
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
              ) : isAdmin && session.user.role !== 'admin' ? (
                <section className="state" role="alert">
                  Administrator access required.
                </section>
              ) : isDiagnostics && session.user.role === 'admin' ? (
                <>
                  <PageHeader title="Diagnostics" />
                  <section className="panel diagnostics-panel">
                    <ReleaseIdentity
                      token={session.token}
                      onDenied={onDenied}
                    />
                  </section>
                </>
              ) : isProvider ? (
                session.user.role === 'admin' ? (
                  <ProviderUsage
                    key={generation}
                    token={session.token}
                    onDenied={onDenied}
                    signal={session.controller.signal}
                    before={
                      <AnthropicCard
                        token={session.token}
                        onDenied={onDenied}
                        signal={session.controller.signal}
                      />
                    }
                  />
                ) : (
                  <div className="state" role="alert">
                    Administrator access required.
                  </div>
                )
              ) : isOverview ? (
                <UploadWorkspace
                  token={session.token}
                  user={session.user}
                  onDenied={onDenied}
                  route={hash}
                >
                  {(active) => (
                    <OperationalOverview
                      key={`${active.id}:${generation}`}
                      api={workflowApi}
                      sessionId={active.id}
                    />
                  )}
                </UploadWorkspace>
              ) : isBatch || hash === '#/admin' ? (
                session.user.role === 'admin' ? (
                  <UploadWorkspace
                    token={session.token}
                    user={session.user}
                    onDenied={onDenied}
                    route={batchRoute}
                  >
                    {(active) => (
                      <BatchProcessing
                        key={`${active.id}:${hash}:${generation}`}
                        api={batchApi}
                        user={session.user}
                        route={
                          ['#/batch', '#/batch/', '#/admin'].includes(
                            batchRoute,
                          ) &&
                          active.uploads.find((u) => u.status !== 'expired')
                            ? active.uploads.find(
                                (u) => u.status !== 'expired',
                              )!.resume_route
                            : batchRoute
                        }
                        memory={sessionMemory(active.id)}
                        uploadSessionId={active.id}
                      />
                    )}
                  </UploadWorkspace>
                ) : (
                  <BatchProcessing
                    key={generation}
                    api={batchApi}
                    user={session.user}
                    route={hash}
                    memory={batchMemory}
                  />
                )
              ) : hash === '#/supervisor-review' &&
                session.user.role !== 'analyst' ? (
                <SupervisorQueue api={humanApi} />
              ) : match ? (
                <CaseView
                  key={`${hash}:${generation}`}
                  id={match[1]}
                  workflow={match[2] === '/assessment'}
                  evidence={match[2] === '/evidence'}
                  investigation={match[2] === '/investigation'}
                  investigationApi={investigationApi}
                  activity={match[2] === '/activity'}
                  casework={match[2]?.toLowerCase().startsWith('/casework')}
                  decide={match[2]?.toLowerCase() === '/casework/decide'}
                  humanApi={humanApi}
                  workflowApi={workflowApi}
                  api={api}
                  user={session.user}
                />
              ) : (
                <UploadWorkspace
                  token={session.token}
                  user={session.user}
                  onDenied={onDenied}
                  route={hash}
                >
                  {(active) => (
                    <Dashboard
                      key={`${active.id}:${generation}`}
                      api={api}
                      user={session.user}
                      workflowApi={workflowApi}
                      uploadSessionId={active.id}
                    />
                  )}
                </UploadWorkspace>
              )}
            </InvestigationReceipts.Provider>
          </Receipts.Provider>
        </main>
        <AppFooter />
      </div>
    </div>
  );
}
