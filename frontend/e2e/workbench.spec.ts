import { test, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync, renameSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import AxeBuilder from '@axe-core/playwright';

const fixturePath = process.env.TRUEFLAG_E2E_FIXTURE;
if (!fixturePath)
  throw new Error(
    'Use scripts/run_frontend_e2e.py for isolated real Linux/PostgreSQL acceptance.',
  );
const fixture: {
  password: string;
  cases: Record<string, string>;
  users: Record<string, string>;
} = JSON.parse(readFileSync(fixturePath, 'utf8'));
let sequence = 0;
async function control(command: {
  worker?: 'start' | 'pause';
  fail_next?: boolean;
}) {
  const directory = dirname(fixturePath!);
  for (const file of readdirSync(directory)) {
    const match = /^ack\.(\d+)\.json$/.exec(file);
    if (match) sequence = Math.max(sequence, Number(match[1]));
  }
  const next = ++sequence;
  writeFileSync(
    join(directory, `command.${next}.tmp`),
    JSON.stringify({ sequence: next, ...command }),
  );
  // Unique targets avoid Windows/Docker replacement of a concurrently open file.
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
  await page.goto('/');
  await (await import('./session-helpers')).resetBrowserSession(page);
  await page.getByLabel('Username', { exact: true }).fill(name);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in →', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Cases', exact: true }),
  ).toBeVisible();
}
async function open(page: Page, name: string, workflow = false) {
  await page.goto(
    `/#/cases/${fixture.cases[name]}${workflow ? '/assessment' : ''}`,
  );
  // Explicitly end any prior browser session before selecting this test user.
  await (await import('./session-helpers')).resetBrowserSession(page);
  await page.getByLabel('Username', { exact: true }).fill('uianalyst');
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in →', exact: true }).click();
  await expect(
    page.getByRole('heading', {
      name: `Case ${fixture.cases[name].slice(0, 8)}`,
      exact: true,
    }),
  ).toBeVisible();
}
async function admin(page: Page) {
  const response = await page.request.post(
    'http://127.0.0.1:18010/api/v1/auth/token',
    { data: { username: 'uiadmin', password: fixture.password } },
  );
  expect(response.status()).toBe(200);
  return { Authorization: `Bearer ${(await response.json()).access_token}` };
}
async function accessible(page: Page) {
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(
    result.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      nodes: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
}

test('login, assignment isolation, server search, pagination, filters and sorting', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByLabel('Username').fill('uianalyst');
  await page.getByLabel('Password').fill('wrong-password');
  await page.getByRole('button', { name: 'Sign in →' }).click();
  await expect(page.getByRole('alert')).toContainText('Sign-in failed');
  const listResponse = page.waitForResponse(
    (r) =>
      r.request().method() === 'GET' &&
      new URL(r.url()).pathname === '/api/v1/case-queue' &&
      r.status() === 200,
  );
  await login(page);
  const authorizedTotal = (await (await listResponse).json()).total;
  expect(authorizedTotal).toBeGreaterThan(20);
  await expect(page.getByText(`1–20 of ${authorizedTotal}`)).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'synthetic-ui-foreign' }),
  ).toHaveCount(0);
  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(
    page.getByText(`21–${Math.min(40, authorizedTotal)} of ${authorizedTotal}`),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Previous page' }).click();
  await page.getByLabel('Search cases').fill('synthetic-ui-alpha');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(
    page.getByRole('link', { name: 'synthetic-ui-alpha', exact: true }),
  ).toBeVisible();
  await page.getByLabel('Priority', { exact: true }).selectOption('High');
  await expect(
    page.getByRole('heading', { name: 'No matching cases' }),
  ).toBeVisible();
  await page.getByLabel('Priority', { exact: true }).selectOption('');
  await page.getByLabel('Sort by').selectOption('created_at:asc');
  await expect(
    page.getByRole('link', { name: 'synthetic-ui-alpha', exact: true }),
  ).toBeVisible();
  await accessible(page);
  await page.screenshot({
    path: '../runtime/phase29-dashboard.png',
    fullPage: true,
  });
});

test('real asynchronous request, isolated RF/SHAP execution, provenance and version history', async ({
  page,
}) => {
  await control({ worker: 'pause' });
  const rawPaths: string[] = [];
  page.on('request', (request) => {
    if (
      /\/api\/v1\/cases\/[a-f0-9-]{36}$/.test(new URL(request.url()).pathname)
    )
      rawPaths.push(request.url());
  });
  await open(page, 'alpha', true);
  await page.getByLabel('Review policy').selectOption('Coverage');
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
  const details = page.waitForResponse(
    (r) =>
      /\/assessments\/[a-f0-9-]{36}$/.test(new URL(r.url()).pathname) &&
      r.status() === 200,
  );
  await page.getByRole('link', { name: 'View verified results →' }).click();
  const detailResponse = await details;
  const detail = await detailResponse.json();
  await expect(page.getByTestId('rf-score')).toHaveText(
    `${(detail.score * 100).toFixed(2)}%`,
  );
  await (await import('./ux-helpers')).showAllFactors(page);
  await expect(
    page.getByRole('list', { name: 'Contributing Risk Factors' }).locator('li'),
  ).toHaveCount(27);
  await expect(
    page.getByText('This score is a model signal', { exact: false }),
  ).toBeVisible();
  await page.getByText('Advanced model details').click();
  await expect(
    page.getByText(detail.model_sha256, { exact: true }),
  ).toBeVisible();
  await (
    await import('./ux-helpers')
  ).expandSection(page, /^Assessment history/);
  await expect(
    page.getByRole('button', { name: 'View assessment version 1' }),
  ).toBeVisible();
  await accessible(page);
  await page.screenshot({
    path: '../runtime/phase29-details.png',
    fullPage: true,
  });
  expect(rawPaths).toEqual([]);
  expect(
    await page.evaluate(() => ({
      local: localStorage.length,
      session: sessionStorage.length,
    })),
  ).toEqual({ local: 0, session: 0 });
  // A new explicit request creates v2; transport retries never create a second run.
  await page
    .getByRole('link', { name: 'Request another assessment', exact: true })
    .click();
  await expect(
    page.getByText('Assessment and key risk drivers saved.'),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'Request assessment', exact: true })
    .click();
  await expect(
    page.getByText('Assessment and key risk drivers saved.'),
  ).toBeVisible({ timeout: 45000 });
  await page.getByRole('link', { name: 'View verified results →' }).click();
  await (
    await import('./ux-helpers')
  ).expandSection(page, /^Assessment history/);
  await expect(
    page.getByRole('button', { name: 'View assessment version 2' }),
  ).toBeVisible();
});

test('unauthorized case navigation clears data and supervisor/admin scope is enforced', async ({
  page,
}) => {
  await login(page);
  await page.evaluate((id) => {
    location.hash = `/cases/${id}`;
  }, fixture.cases.foreign);
  await expect(
    page.getByRole('heading', { name: 'Information unavailable' }),
  ).toBeVisible();
  await expect(
    page.getByText('synthetic-ui-foreign', { exact: true }),
  ).toHaveCount(0);
  await page.getByRole('button', { name: 'Sign out' }).click();
  await login(page, 'uisupervisor');
  await expect(page.getByLabel('Release identity')).toHaveCount(0);
  await page.getByLabel('Search cases').fill('synthetic-ui-foreign');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(
    page.getByRole('link', { name: 'synthetic-ui-foreign' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await login(page, 'uiadmin');
  const release = page.getByLabel('Release identity');
  await release.getByText('Release', { exact: true }).click();
  await expect(release).toContainText('Frontend v0.1.0');
  await expect(release).toContainText(/API [a-f0-9]{12} \(ready\)/);
  await expect(release).not.toContainText('Builds differ');
  await accessible(page);
  await page
    .getByLabel('Assignment', { exact: true })
    .selectOption('unassigned');
  await expect(
    page.getByRole('link', { name: 'synthetic-ui-unassigned' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByLabel('Release identity')).toHaveCount(0);
});

test('worker downtime persists Pending; terminal failure requires manual review and explicit reassessment', async ({
  page,
}) => {
  await control({ worker: 'pause' });
  await open(page, 'zero', true);
  await page
    .getByRole('button', { name: 'Request assessment', exact: true })
    .click();
  await expect(
    page.getByText('Request received.', { exact: false }),
  ).toBeVisible();
  await accessible(page);
  await page.screenshot({
    path: '../runtime/phase29-workflow.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: 'Sign out' }).click();
  await open(page, 'zero', true);
  await expect(
    page.getByText('Request received.', { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Assessment in progress' }),
  ).toBeDisabled();
  await control({ fail_next: true, worker: 'start' });
  await expect(
    page.getByText('Manual review required.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('No case decision was changed.', { exact: false }),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'Request assessment', exact: true })
    .click();
  await expect(
    page.getByText('Assessment and key risk drivers saved.'),
  ).toBeVisible({ timeout: 45000 });
});

test('assignment revocation clears visible results; logout and reload cannot restore private state', async ({
  page,
}) => {
  await open(page, 'alpha');
  await expect(page.getByTestId('rf-score')).toBeVisible();
  const headers = await admin(page);
  const assigned = await page.request.put(
    `http://127.0.0.1:18010/api/v1/cases/${fixture.cases.alpha}/assignment`,
    {
      headers,
      data: { assigned_to: fixture.users.uiother, expected_version: 1 },
    },
  );
  expect(assigned.status()).toBe(200);
  await expect(
    page.getByRole('heading', { name: 'Information unavailable' }),
  ).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId('rf-score')).toHaveCount(0);
  await expect(
    page.getByText('synthetic-ui-alpha', { exact: true }),
  ).toHaveCount(0);
  await page.getByRole('button', { name: 'Sign out' }).click();
  await page.goBack();
  await expect(
    page.getByRole('heading', { name: 'Welcome back' }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Welcome back' }),
  ).toBeVisible();
});

test('mobile layout and keyboard sign-in use real authorized data', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await accessible(page);
  await page.getByLabel('Username').fill('uianalyst');
  await page.getByLabel('Password').fill(fixture.password);
  await page.getByLabel('Password').press('Enter');
  await expect(
    page.getByRole('heading', { name: 'Cases', exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: '../runtime/phase29-mobile.png',
    fullPage: true,
  });
});
