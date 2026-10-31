import { useEffect, useState, type FormEvent } from 'react';
import { currentUser, health, signIn, type User } from './api';

const milestones = [
  ['01', 'Foundation', 'Authentication, data model, service checks'],
  [
    '02',
    'Risk intelligence',
    'Frozen RF baseline, policy routing, explanations',
  ],
  ['03', 'Evidence & investigation', 'Scoped retrieval and cited AI drafts'],
  ['04', 'Analyst workbench', 'Case review, approval, and audit history'],
  [
    '05',
    'Evaluation & deployment',
    'Measured performance and release acceptance',
  ],
];

export default function App() {
  const [online, setOnline] = useState<boolean | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    health()
      .then((value) => {
        if (active) setOnline(value);
      })
      .catch(() => {
        if (active) setOnline(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function login(event: FormEvent) {
    event.preventDefault();
    setError('');
    setBusy(true);
    try {
      const token = await signIn(username, password);
      // Foundation checks identity only. Tokens are never persisted in browser storage.
      setUser(await currentUser(token));
      setPassword('');
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : 'Service unavailable.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="shell">
      <header>
        <a className="brand" href="/" aria-label="TrueFlag AI home">
          <span className="mark">TF</span> TrueFlag <b>AI</b>
        </a>
        <span className="environment">SYNTHETIC DATA ONLY</span>
      </header>
      <main>
        <section className="intro">
          <p className="eyebrow">INVESTIGATION PLATFORM / FOUNDATION</p>
          <h1>
            Evidence first.
            <br />
            <span>Human decisions.</span>
          </h1>
          <p className="lead">
            A secure foundation for alert intelligence, grounded investigation,
            and accountable review.
          </p>
          <p className="service" role="status">
            <span className={online ? 'dot online' : 'dot'} />
            {online === null
              ? 'Checking backend'
              : online
                ? 'Backend reachable'
                : 'Backend unavailable'}
            <small> Liveness only; database readiness is separate.</small>
          </p>
          <div className="boundary">
            <b>Current build</b>
            <p>
              Account verification and platform setup. Alert ingestion, live
              scoring, case workflows, and AI investigations are not enabled
              yet.
            </p>
          </div>
        </section>
        <section className="access" aria-labelledby="access-title">
          <p className="eyebrow">AUTHORIZED ACCESS</p>
          <h2 id="access-title">
            {user ? 'Identity verified' : 'Sign in to verify access'}
          </h2>
          {user ? (
            <div>
              <p>
                Signed in as <b>{user.username}</b>.
              </p>
              <p className="role">Server-assigned role: {user.role}</p>
              <p>
                This verifies your account. Persistent application sessions and
                case access follow in Week 1.
              </p>
              <button onClick={() => setUser(null)}>Clear account view</button>
            </div>
          ) : (
            <form
              onSubmit={(event) => {
                void login(event);
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
                onChange={(event) => setUsername(event.target.value)}
              />
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                maxLength={1024}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              {error && (
                <p role="alert" className="error">
                  {error}
                </p>
              )}
              <button disabled={busy}>
                {busy ? 'Verifying…' : 'Verify account →'}
              </button>
              <p className="hint">
                Accounts are provisioned by an administrator. There are no
                default credentials.
              </p>
            </form>
          )}
        </section>
        <section className="roadmap" aria-label="Development milestones">
          {milestones.map(([week, title, detail]) => (
            <article key={week}>
              <span className="week">WEEK {week}</span>
              <h3>{title}</h3>
              <p>{detail}</p>
              <span className="tag">
                {week === '01' ? 'Foundation in progress' : 'Planned'}
              </span>
            </article>
          ))}
        </section>
      </main>
      <footer>
        TrueFlag AI · Production-oriented demonstration · No live banking
        integration
      </footer>
    </div>
  );
}
