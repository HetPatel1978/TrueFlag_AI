import { test, expect, type Page } from '@playwright/test';
import { expectFixtureAck, signInButton } from './session-helpers';
import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  readdirSync,
  renameSync,
} from 'node:fs';
import { dirname, join } from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { resetBrowserSession } from './session-helpers';
import { expandSection } from './ux-helpers';

const file = process.env.TRUEFLAG_E2E_FIXTURE;
const shots = process.env.TRUEFLAG_DESIGN_SCREENSHOTS;
test.skip(!file || !shots, 'Requires isolated Linux/PostgreSQL fixture');
const fixture = file ? JSON.parse(readFileSync(file, 'utf8')) : null;
const captures: { name: string; width: number; height: number }[] = [];
const responses: { path: string; status: number; reason: string }[] = [];
const recoveries: string[] = [];
test.beforeEach(async ({ page }) => {
  responses.length = 0;
  recoveries.length = 0;
  page.on('response', (response) => {
    const path = new URL(response.url()).pathname;
    if (!path.startsWith('/api/')) return;
    const reason = response.headers()['x-trueflag-reason'] ?? '';
    responses.push({
      path: path.replace(/[a-f0-9-]{36}/g, ':id'),
      status: response.status(),
      reason: ['clock_uncertainty', 'snapshot_stale'].includes(reason)
        ? reason
        : '',
    });
  });
});
test.afterEach(async ({ browserName }, info) => {
  mkdirSync(shots!, { recursive: true });
  writeFileSync(
    join(shots!, `http-${info.testId}.json`),
    JSON.stringify(
      {
        browser: browserName,
        status: info.status,
        recoveries,
        responses: responses.slice(-200),
      },
      null,
      2,
    ),
  );
});
async function readyCasework(page: Page, formName: string) {
  const form = page.getByRole('form', { name: formName, exact: true });
  const panel = page.getByRole('region', {
    name: 'Human investigation casework',
  });
  for (let attempt = 0; attempt < 3; attempt++) {
    await expect
      .poll(
        async () =>
          (await form.count()) > 0 ||
          (await panel.getByRole('alert').count()) > 0,
      )
      .toBe(true);
    if (await form.count()) return;
    const last = responses
      .filter(
        (value) =>
          value.path.endsWith('/casework') || value.path.endsWith('/evidence'),
      )
      .at(-1);
    expect(last?.status).toBe(503);
    expect(last?.reason).toBe('clock_uncertainty');
    await expect(form).toHaveCount(0);
    await expect(panel).toContainText(
      'Casework is withheld until current access and evidence can be verified.',
    );
    recoveries.push('explicit_casework_refresh_after_clock_denial');
    await page.waitForTimeout(2000);
    await panel
      .getByRole('button', { name: 'Refresh casework', exact: true })
      .click();
  }
  await expect(form).toBeVisible();
}
async function capture(page: Page, name: string) {
  mkdirSync(shots!, { recursive: true });
  await page.screenshot({ path: join(shots!, name + '.png'), fullPage: true });
  captures.push({ name, ...page.viewportSize()! });
  writeFileSync(
    join(shots!, 'workflow-manifest.json'),
    JSON.stringify(
      { synthetic_only: true, live_provider_used: false, captures },
      null,
      2,
    ),
  );
  const overflow = await page.evaluate(() =>
    [...document.querySelectorAll('main *, header *')]
      .filter((element) => {
        const box = element.getBoundingClientRect();
        return box.width > 0 && box.right > window.innerWidth + 1;
      })
      .slice(0, 12)
      .map((element) => ({
        tag: element.tagName,
        class: element.className,
        right: Math.round(element.getBoundingClientRect().right),
      })),
  );
  if (overflow.length)
    writeFileSync(
      join(shots!, name + '-overflow.json'),
      JSON.stringify(overflow),
    );
  await (await import('./ux-helpers')).expectNoHorizontalOverflow(page);
}
async function login(page: Page, username: string, route: string) {
  await page.goto('/#' + route);
  await resetBrowserSession(page);
  await page.reload();
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await signInButton(page).click();
  await expect(
    page.getByRole('button', { name: 'Sign out', exact: true }),
  ).toBeVisible();
}
async function startWorker(command: object = { worker: 'start' }) {
  const directory = dirname(file!);
  const sequence =
    1 +
    Math.max(
      0,
      ...readdirSync(directory).map((name) =>
        Number(/^ack\.(\d+)\.json$/.exec(name)?.[1] ?? 0),
      ),
    );
  const target = join(directory, `command.${sequence}.json`);
  writeFileSync(target + '.tmp', JSON.stringify({ sequence, ...command }));
  renameSync(target + '.tmp', target);
  await expect
    .poll(() => readdirSync(directory).includes(`ack.${sequence}.json`))
    .toBe(true);
  expectFixtureAck(directory, sequence);
}
test('guided workflow: admin overview and grouped operations', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page, 'uiadmin', '/overview');
  await expect(
    page.getByRole('heading', { name: 'Overview', exact: true }),
  ).toBeVisible();
  const nav = page.getByRole('navigation', { name: 'Workspace navigation' });
  await expect(nav.getByRole('link')).toHaveCount(4);
  await expect(
    nav.getByRole('link', { name: 'Imports', exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('region', { name: 'Case summary' }),
  ).toBeVisible();
  await capture(page, 'overview-desktop');
  await page.getByRole('button', { name: 'Collapse sidebar' }).click();
  await expect(page.locator('.workspace')).toHaveClass(/sidebar-compact/);
  await nav.getByRole('link', { name: 'Administration' }).click();
  await expect(
    page.getByRole('navigation', { name: 'Administration sections' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Imports', exact: true }),
  ).toBeVisible();
  await capture(page, 'administration-imports-desktop');
  await page.evaluate(() => {
    window.location.hash = '/admin';
  });
  await expect(
    page.getByRole('heading', { name: 'Imports', exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  const menu = page.getByRole('button', { name: 'Menu', exact: true });
  await expect(menu).toBeVisible();
  await menu.click();
  await expect(
    nav.getByRole('link', { name: 'Cases', exact: true }),
  ).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(menu).toBeFocused();
  await expect(nav).not.toBeVisible();
  await capture(page, 'administration-mobile');
});
test('guided workflow: four stages, verified findings, notes and retained history', async ({
  page,
}) => {
  test.setTimeout(180000);
  await startWorker();
  const id = fixture.cases['draft-one-click'];
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page, 'uianalyst', `/cases/${id}`);
  const workflow = page.getByRole('navigation', { name: 'Case workflow' });
  await expect(workflow.getByRole('link')).toHaveCount(4);
  await expect(
    page.getByRole('heading', { name: 'No assessment yet' }),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Assess risk', exact: false }).click();
  await page
    .getByRole('button', { name: 'Request assessment', exact: true })
    .click({ timeout: 15000 });
  await page
    .getByRole('link', { name: 'View verified results', exact: false })
    .click({ timeout: 45000 });
  await expect(page.getByTestId('rf-score')).toBeVisible();
  await expect(
    page.getByRole('list', { name: 'Contributing Risk Factors' }).locator('li'),
  ).toHaveCount(3);
  await capture(page, 'assess-alert-desktop');
  await page.setViewportSize({ width: 834, height: 1112 });
  await capture(page, 'assess-alert-tablet');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await workflow.getByRole('link', { name: /Review Evidence/ }).click();
  await expect(
    page.getByRole('heading', { name: 'Customer Profile', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', {
      name: 'Transaction observations',
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText(/Loading transactions/)).toHaveCount(0);
  await capture(page, 'review-evidence-desktop');
  await page.setViewportSize({ width: 834, height: 1112 });
  await capture(page, 'review-evidence-tablet');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await workflow.getByRole('link', { name: /AI Investigation/ }).click();
  await expect(
    page.getByRole('button', {
      name: 'Generate AI Investigation',
      exact: true,
    }),
  ).toHaveCount(1);
  const accepted = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().endsWith('/investigation-drafts/start'),
  );
  await page
    .getByRole('button', { name: 'Generate AI Investigation', exact: true })
    .click();
  expect((await accepted).status()).toBe(202);
  await expect(
    page.getByRole('heading', { name: 'Financial Observations' }),
  ).toBeVisible({ timeout: 45000 });
  await expect(
    page.getByText('OFFLINE SIMULATION', { exact: true }),
  ).toBeVisible();
  await expandSection(page, 'Regulatory Guidance');
  await page
    .getByLabel('Search guidance', { exact: true })
    .fill('suspicious activity reporting');
  const guidance = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().includes('/regulatory-context'),
  );
  await page.getByRole('button', { name: 'Search approved guidance' }).click();
  const response = await guidance;
  expect(response.status()).toBe(200);
  expect((await response.json()).status).toBe('unavailable');
  await expect(
    page.getByText(
      'Approved guidance is unavailable for this search and scope.',
    ),
  ).toBeVisible();
  await capture(page, 'ai-investigation-desktop');
  const accessibility = await new AxeBuilder({ page })
    .include('main')
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(accessibility.violations).toEqual([]);
  await page.setViewportSize({ width: 834, height: 1112 });
  await capture(page, 'ai-investigation-tablet');
  await workflow.getByRole('link', { name: /Human Decision/ }).click();
  await readyCasework(page, 'Investigation Notes');
  const notes = page.getByRole('form', {
    name: 'Investigation Notes',
    exact: true,
  });
  await notes
    .getByLabel('Investigation note', { exact: true })
    .fill(
      'Reviewed synthetic source observations. Additional information is required before a final decision.',
    );
  const written = page.waitForResponse(
    (r) => r.request().method() === 'POST' && r.url().endsWith('/casework'),
  );
  await notes
    .getByRole('button', { name: 'Submit investigation note' })
    .click();
  expect((await written).status()).toBe(201);
  await capture(page, 'human-decision-tablet');
  await expandSection(page, 'Casework history');
  await expect(
    page.getByText(
      'Reviewed synthetic source observations. Additional information is required before a final decision.',
      { exact: true },
    ),
  ).toBeVisible();
  await expandSection(page, 'Supervisor Escalation');
  const escalation = page.getByRole('form', {
    name: 'Supervisor Escalation',
    exact: true,
  });
  await escalation
    .getByLabel('Decision rationale')
    .fill(
      'Request independent supervisory review of these synthetic financial observations.',
    );
  await escalation
    .getByRole('button', { name: 'Request supervisor review' })
    .click();
  const confirm = page.getByRole('dialog', { name: 'Confirm human decision' });
  await expect(confirm).toBeVisible();
  const escalated = page.waitForResponse(
    (r) => r.request().method() === 'POST' && r.url().endsWith('/casework'),
  );
  await confirm
    .getByRole('button', { name: 'Confirm and record decision' })
    .click();
  expect((await escalated).status()).toBe(201);
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Human Decision', exact: true }),
  ).toBeVisible();
  await expandSection(page, 'Casework history');
  await expect(
    page.getByText(
      'Reviewed synthetic source observations. Additional information is required before a final decision.',
      { exact: true },
    ),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
  await expect(
    page.getByText(
      'Reviewed synthetic source observations. Additional information is required before a final decision.',
      { exact: true },
    ),
  ).toHaveCount(0);
  await login(page, 'uisupervisor', `/cases/${id}/casework`);
  await page.getByRole('link', { name: 'Review Queue', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Review Queue', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('link', { name: `Review case ${id.slice(0, 8)}`, exact: true })
    .click();

  await expandSection(page, 'Supervisor Review');
  const supervision = page.getByRole('form', {
    name: 'Supervisor Review',
    exact: true,
  });
  await supervision
    .getByLabel('Supervisor decision')
    .selectOption('return_for_investigation');
  await supervision
    .getByLabel('Decision rationale')
    .fill(
      'Independent supervisor requests further supporting evidence before any final resolution.',
    );
  await supervision
    .getByRole('button', { name: 'Review supervisor response' })
    .click();
  const returned = page.waitForResponse(
    (r) => r.request().method() === 'POST' && r.url().endsWith('/casework'),
  );
  await page
    .getByRole('dialog', { name: 'Confirm human decision' })
    .getByRole('button', { name: 'Confirm and record decision' })
    .click();
  expect((await returned).status()).toBe(201);
  await capture(page, 'supervisor-human-decision-tablet');
  await page
    .getByRole('link', { name: 'Activity History', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Activity History', exact: true }),
  ).toBeVisible();
});

test('guided workflow: foreign cases and revoked sources stay protected', async ({
  page,
}) => {
  await login(
    page,
    'uiother',
    `/cases/${fixture.cases['draft-revoked']}/investigation`,
  );
  await expect(page.locator('main')).toContainText(
    /unavailable|not found|no longer/i,
  );
  await expect(
    page.getByRole('button', {
      name: 'Generate AI Investigation',
      exact: true,
    }),
  ).toHaveCount(0);
  await login(
    page,
    'uianalyst',
    `/cases/${fixture.cases['draft-revoked']}/evidence`,
  );
  await expect(
    page.getByRole('heading', { name: 'Customer Profile' }),
  ).toBeVisible();
  await startWorker({ revoke_source: 'draft-revoked' });
  await page
    .getByRole('button', { name: 'Refresh evidence', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Supporting records needed' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Customer Profile' }),
  ).toHaveCount(0);
});

test('guided workflow: supervisor assignment grants only the selected analyst access', async ({
  page,
}) => {
  const id = fixture.cases.workflow;
  await login(page, 'uisupervisor', `/cases/${id}`);
  await page
    .getByRole('button', { name: 'Assign investigator', exact: true })
    .click();
  await expect(
    page.getByRole('option', { name: 'uianalyst', exact: true }),
  ).toBeAttached();
  await page
    .getByLabel('Assigned Investigator', { exact: true })
    .selectOption(fixture.users.uianalyst);
  const assigned = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' &&
      response.url().endsWith('/assignment'),
  );
  await page
    .getByRole('button', { name: 'Confirm assignment', exact: true })
    .click();
  expect((await assigned).status()).toBe(200);
  await expect(page.locator('.assignment-row')).toContainText('uianalyst');
  await login(page, 'uianalyst', `/cases/${id}`);
  await expect(
    page.getByRole('navigation', { name: 'Case workflow' }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Reassign investigator', exact: true }),
  ).toHaveCount(0);
  const activity = page.waitForResponse(
    (response) =>
      response.request().method() === 'GET' &&
      response.url().includes('/activity?'),
  );
  await page
    .getByRole('link', { name: 'Activity History', exact: true })
    .click();
  const response = await activity;
  expect(response.status()).toBe(200);
  expect(
    (await response.json()).items.some(
      (item: { assignment_change: string | null }) =>
        item.assignment_change === 'assigned',
    ),
  ).toBe(true);
});
