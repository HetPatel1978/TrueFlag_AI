import { test, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync, renameSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import AxeBuilder from '@axe-core/playwright';

const fixturePath = process.env.TRUEFLAG_E2E_FIXTURE;
if (!fixturePath)
  throw new Error(
    'Use scripts/run_investigation_e2e.py with the isolated G2 clone.',
  );
const fixture: {
  password: string;
  cases: Record<string, string>;
  case_sources: Record<string, string>;
  users: Record<string, string>;
} = JSON.parse(readFileSync(fixturePath, 'utf8'));
const observations: {
  method: string;
  path: string;
  status?: number;
  calculation?: string;
  reason?: string;
}[] = [];
test.beforeEach(async ({ page }) => {
  observations.length = 0;
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (!path.startsWith('/api/')) return;
    observations.push({
      method: request.method(),
      path: path.replace(/[a-f0-9-]{36}/g, ':id'),
      ...(path.endsWith('/activity')
        ? { calculation: request.postDataJSON()?.calculation }
        : {}),
    });
  });
  page.on('response', (response) => {
    const path = new URL(response.url()).pathname;
    if (path.startsWith('/api/'))
      observations.push({
        method: response.request().method(),
        path: path.replace(/[a-f0-9-]{36}/g, ':id'),
        status: response.status(),
        ...(['clock_uncertainty', 'snapshot_stale'].includes(
          response.headers()['x-trueflag-reason'] ?? '',
        )
          ? { reason: response.headers()['x-trueflag-reason'] }
          : {}),
      });
  });
});
test.afterEach(async ({ browserName }, info) => {
  // Allowlisted transport diagnostics only: no tokens, request bodies or evidence values.
  writeFileSync(
    join(dirname(fixturePath!), `http-${info.testId}.json`),
    JSON.stringify({
      browser: browserName,
      status: info.status,
      requests: observations.slice(-200),
    }),
  );
});
async function control(command: {
  worker?: 'start' | 'pause';
  revoke_source?: string;
  clock_fault?: boolean;
}) {
  const directory = dirname(fixturePath!);
  const next =
    1 +
    Math.max(
      0,
      ...readdirSync(directory).map((f) =>
        Number(/^ack\.(\d+)\.json$/.exec(f)?.[1] || 0),
      ),
    );
  writeFileSync(
    join(directory, `command.${next}.tmp`),
    JSON.stringify({ sequence: next, ...command }),
  );
  renameSync(
    join(directory, `command.${next}.tmp`),
    join(directory, `command.${next}.json`),
  );
  await expect
    .poll(() => {
      try {
        return JSON.parse(
          readFileSync(join(directory, `ack.${next}.json`), 'utf8'),
        ).sequence;
      } catch {
        return 0;
      }
    })
    .toBe(next);
}
async function login(page: Page, name = 'uianalyst') {
  await (await import('./session-helpers')).resetBrowserSession(page);
  await page.getByLabel('Username', { exact: true }).fill(name);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in →', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Sign out', exact: true }),
  ).toBeVisible();
}
async function open(
  page: Page,
  name: string,
  view = 'evidence',
  user = 'uianalyst',
) {
  await page.goto(`/#/cases/${fixture.cases[name]}/${view}`);
  // The login helper explicitly ends any previous persisted session.
  await page.reload();
  await login(page, user);
}
async function evidence(page: Page) {
  await expect(
    page.getByRole('heading', { name: 'Supporting evidence', exact: true }),
  ).toBeVisible();
  await expect(page.locator('.evidence-record h4').first()).toBeVisible();
}

test('real RF, policy, SHAP, financial analytics, packet verification and idempotency', async ({
  page,
}) => {
  test.setTimeout(120000);
  await control({ worker: 'pause' });
  await open(page, 'connected', 'assessment');
  const accepted = page.waitForResponse(
    (r) => r.request().method() === 'POST' && r.url().endsWith('/assessments'),
  );
  await page
    .getByRole('button', { name: 'Request assessment', exact: true })
    .click();
  expect((await accepted).status()).toBe(202);
  await expect(
    page.getByText('Request received.', { exact: false }),
  ).toBeVisible();
  await control({ worker: 'start' });
  await expect(
    page.getByText('Assessment and key risk drivers saved.'),
  ).toBeVisible({ timeout: 45000 });
  await page.getByRole('link', { name: 'View verified results →' }).click();
  await expect(page.getByTestId('rf-score')).toBeVisible();
  const realScore = await page.getByTestId('rf-score').textContent();
  await (await import('./ux-helpers')).showAllFactors(page);
  await expect(
    page.getByRole('list', { name: 'Contributing Risk Factors' }).locator('li'),
  ).toHaveCount(27);
  await page
    .getByRole('navigation', { name: 'Case views' })
    .getByRole('link', { name: 'Evidence', exact: true })
    .click();
  await evidence(page);
  await (
    await import('./ux-helpers')
  ).expandSection(page, 'Assessment and evidence version');
  await page
    .locator('summary')
    .filter({ hasText: /^Key Risk Drivers$/ })
    .click();
  await expect(page.getByTestId('rf-score')).toHaveText(realScore!);
  await page
    .locator('summary')
    .filter({ hasText: /^Key Risk Drivers$/ })
    .click();
  const analytics = page.waitForResponse(
    (r) =>
      r.url().endsWith('/evidence/activity') &&
      r.request().postDataJSON().calculation === 'incoming_outgoing',
    { timeout: 15000 },
  );
  await page
    .getByRole('button', { name: 'Transaction Activity Analysis', exact: true })
    .click();
  await expect(
    page.getByRole('button', {
      name: 'Transaction Activity Analysis',
      exact: true,
    }),
  ).toHaveAttribute('aria-pressed', 'true');
  const totalsResponse = await analytics;
  expect(totalsResponse.status()).toBe(200);
  const totals = (await totalsResponse.json()).data;
  await expect(
    page.getByText(`USD ${totals.observed_total}`, { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole('table', { name: 'Authorized transaction observations' }),
  ).toBeVisible();
  await control({ worker: 'pause' });
  await page
    .getByRole('navigation', { name: 'Case views' })
    .getByRole('link', { name: 'Investigation', exact: true })
    .click();
  await page
    .getByRole('button', { name: 'Investigation Summary', exact: true })
    .click();
  const requested = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' && r.url().endsWith('/investigations'),
  );
  await page
    .getByRole('button', { name: 'Generate summary', exact: true })
    .click();
  const response = await requested;
  expect(response.status()).toBe(202);
  const request = response.request();
  const job = await response.json();
  await expect(
    page
      .getByRole('status')
      .filter({ hasText: 'Processing status:' })
      .filter({ hasText: 'Pending' }),
  ).toBeVisible();
  await control({ worker: 'start' });
  await expect(
    page.getByRole('heading', { name: /Investigation Summary \u00b7/ }),
  ).toBeVisible({ timeout: 45000 });
  await page.getByText(/^Supporting records \(/).click();
  await expect(page.locator('.evidence-reference').first()).toBeVisible();
  await expect(
    page.getByText(/Regulatory guidance has not been applied/),
  ).toBeVisible();
  const replay = await page.request.post(response.url(), {
    headers: {
      Authorization: request.headers().authorization,
      'Idempotency-Key': request.headers()['idempotency-key'],
    },
    data: request.postDataJSON(),
  });
  expect(replay.status()).toBe(202);
  expect((await replay.json()).run_id).toBe(job.run_id);
  await (
    await import('./ux-helpers')
  ).expandSection(page, /^Investigation History/);
  await expect(
    page.getByRole('table', { name: 'Investigation history' }),
  ).toBeVisible();
  await expect(
    page
      .getByRole('table', { name: 'Investigation history' })
      .getByRole('cell', { name: 'Completed', exact: true }),
  ).toBeVisible();
  const accessibility = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(
    accessibility.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
  await page.screenshot({
    path: '../runtime/g2-1/workbench.png',
    fullPage: true,
  });
});

test('incomplete history remains evidence-only and reports limitations or abstention', async ({
  page,
}) => {
  await control({ worker: 'start' });
  await open(page, 'incomplete');
  await evidence(page);
  await (
    await import('./ux-helpers')
  ).expandSection(page, 'Assessment and evidence version');
  await expect(
    page.getByText(/No completed assessment selected/),
  ).toBeVisible();
  await page
    .getByRole('navigation', { name: 'Case views' })
    .getByRole('link', { name: 'Investigation', exact: true })
    .click();
  await page
    .getByRole('button', { name: 'Investigation Summary', exact: true })
    .click();
  await page
    .getByRole('button', { name: 'Generate summary', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: /Investigation Summary \u00b7/ }),
  ).toBeVisible({ timeout: 45000 });
  await expect(
    page
      .getByRole('status')
      .filter({ hasText: 'Processing status:' })
      .filter({ hasText: 'Further evidence needed' }),
  ).toBeVisible();
  await expect(
    page.getByText(/An analyst must review these observations/),
  ).toBeVisible();
});

test('cross-case navigation is denied and assignment revocation clears the workspace', async ({
  page,
}) => {
  await open(page, 'connected_foreign');
  await expect(
    page.getByRole('heading', { name: 'Information unavailable' }),
  ).toBeVisible();
  await open(page, 'incomplete');
  await evidence(page);
  const auth = await page.request.post('/api/v1/auth/token', {
    data: { username: 'uiadmin', password: fixture.password },
  });
  expect(auth.status()).toBe(200);
  const headers = {
    Authorization: `Bearer ${(await auth.json()).access_token}`,
  };
  const summary = await page.request.get(
    `/api/v1/cases/${fixture.cases.incomplete}/overview`,
    { headers },
  );
  expect(summary.status()).toBe(200);
  const detail = await summary.json();
  const assigned = await page.request.put(
    `/api/v1/cases/${fixture.cases.incomplete}/assignment`,
    {
      headers,
      data: {
        expected_version: detail.version,
        assigned_to: fixture.users.uiother,
      },
    },
  );
  expect(assigned.status()).toBe(200);
  await expect(
    page.getByRole('heading', { name: 'Information unavailable' }),
  ).toBeVisible({ timeout: 20000 });
  await expect(page.locator('.evidence-record')).toHaveCount(0);
});

test('unassigned cases are explicit for administrators; source revocation and logout clear protected state', async ({
  page,
}) => {
  await open(page, 'connected_unassigned', 'investigation', 'uiadmin');
  await expect(page.getByText(/Unassigned/).first()).toBeVisible();
  await open(page, 'connected');
  await evidence(page);
  await control({ revoke_source: 'connected' });
  await expect(
    page.getByRole('heading', { name: 'Supporting records needed' }),
  ).toBeVisible({ timeout: 25000 });
  await expect(page.locator('.evidence-record')).toHaveCount(0);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
  const remaining: string[] = [];
  page.on('request', (r) => {
    if (/\/evidence|\/investigations/.test(r.url())) remaining.push(r.url());
  });
  await page.waitForTimeout(2500);
  expect(remaining).toEqual([]);
  expect(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
  ).toEqual([0, 0]);
});

test('controlled clock regression returns real 503 and clears financial evidence', async ({
  page,
}) => {
  await control({ worker: 'pause' });
  await open(page, 'connected_unassigned', 'evidence', 'uiadmin');
  await evidence(page);
  await control({ clock_fault: true });
  try {
    const unavailable = page.waitForResponse((r) =>
      /\/evidence$/.test(new URL(r.url()).pathname),
    );
    await page
      .getByRole('button', { name: 'Refresh evidence', exact: true })
      .click();
    const response = await unavailable;
    expect(response.status()).toBe(503);
    expect(response.headers()['x-trueflag-reason']).toBe('clock_uncertainty');
    await expect(
      page.getByText(/Service temporarily unavailable/),
    ).toBeVisible();
    await expect(page.locator('.evidence-record')).toHaveCount(0);
  } finally {
    await control({ clock_fault: false });
  }
});

test('feature-only cases show a single readiness card with optional details', async ({
  page,
}) => {
  await open(page, 'zero', 'investigation');
  await expect(
    page.getByRole('heading', { name: 'Supporting records needed' }),
  ).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Investigation readiness' }),
  ).toHaveCount(1);
  await expect(
    page.getByRole('navigation', { name: 'Investigation sections' }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('button', {
      name: 'Generate AI Investigation',
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('link', { name: 'View risk assessment', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Show details and history' }).click();
  await expect(
    page.getByText('Assessment and evidence version', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', {
      name: 'Generate AI Investigation',
      exact: true,
    }),
  ).toBeDisabled();
});
