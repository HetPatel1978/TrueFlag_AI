import { test, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import AxeBuilder from '@axe-core/playwright';

const file = process.env.TRUEFLAG_E2E_FIXTURE;
if (!file) throw new Error('Use the guarded Linux/PostgreSQL workflow runner.');
const fixture: {
  password: string;
  cases: Record<string, string>;
  users: Record<string, string>;
} = JSON.parse(readFileSync(file, 'utf8'));
const shots = '../runtime/g2-3/screenshots';
mkdirSync(shots, { recursive: true });
const captures: {
  file: string;
  width: number;
  height: number;
  accessibility_violations: number;
}[] = [];
async function login(page: Page, username: string) {
  await page.goto('/');
  await (await import('./session-helpers')).resetBrowserSession(page);
  await page.reload();
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in →', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Cases', exact: true }),
  ).toBeVisible();
}
async function open(page: Page, id: string, suffix = '') {
  await page.evaluate((value) => {
    location.hash = value;
  }, `/cases/${id}${suffix}`);
  await expect(
    page.getByRole('heading', { name: `Case ${id.slice(0, 8)}`, exact: true }),
  ).toBeVisible();
}
async function capturesAtAllSizes(page: Page, name: string) {
  for (const [size, width, height] of [
    ['desktop', 1440, 1000],
    ['tablet', 1024, 768],
    ['mobile', 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const violations = (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze()
    ).violations;
    expect(
      violations.map((v) => ({
        id: v.id,
        targets: v.nodes.map((n) => n.target),
      })),
    ).toEqual([]);
    const clipped = await page
      .locator('button:visible,select:visible,input:visible')
      .evaluateAll((elements) =>
        elements
          .filter((e) => !e.closest('.table-wrap'))
          .filter((e) => {
            const r = e.getBoundingClientRect();
            return r.left < -1 || r.right > innerWidth + 1;
          })
          .map((e) => e.tagName),
      );
    expect(clipped).toEqual([]);
    const path = `${size}-${name}.png`;
    await page.screenshot({ path: `${shots}/${path}`, fullPage: true });
    captures.push({
      file: path,
      width,
      height,
      accessibility_violations: violations.length,
    });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
}
test('supervisor assignment, analyst discovery, revocation and recorded history use real APIs', async ({
  page,
  browser,
}) => {
  test.setTimeout(240000);
  const id = fixture.cases.workflow;
  await login(page, 'uisupervisor');
  await expect(
    page.getByRole('table', { name: 'Authorized alerts and cases' }),
  ).toBeVisible();
  await capturesAtAllSizes(page, 'case-queue');
  await page
    .getByLabel('Case Queue', { exact: true })
    .selectOption('unassigned');
  await open(page, id);
  await expect(
    page.getByRole('button', { name: 'Assign investigator', exact: true }),
  ).toBeVisible();
  await capturesAtAllSizes(page, 'case-overview');
  const opener = page.getByRole('button', {
    name: 'Assign investigator',
    exact: true,
  });
  await opener.click();
  await expect(
    page.getByRole('option', { name: 'uianalyst', exact: true }),
  ).toBeAttached();
  await capturesAtAllSizes(page, 'assignment-dialog');
  await page.getByLabel('Find active analyst').focus();
  await page.keyboard.press('Shift+Tab');
  expect(
    await page
      .getByRole('dialog')
      .evaluate(
        (dialog) =>
          dialog.contains(document.activeElement) ||
          document.activeElement === document.body,
      ),
  ).toBe(true);
  // Chromium may move to browser chrome at a tab boundary; page background stays inert.
  await page.keyboard.press('Tab');
  expect(
    await page
      .getByRole('dialog')
      .evaluate((dialog) => dialog.contains(document.activeElement)),
  ).toBe(true);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(opener).toBeFocused();
  await opener.click();
  await page.getByLabel('Find active analyst').fill('uianalyst');
  await expect(
    page.getByRole('option', { name: 'uiother', exact: true }),
  ).not.toBeAttached();
  await page
    .getByLabel('Assigned Investigator', { exact: true })
    .selectOption(fixture.users.uianalyst);
  await page
    .getByRole('button', { name: 'Confirm assignment', exact: true })
    .click();
  await expect(
    page.getByRole('button', { name: 'Reassign investigator', exact: true }),
  ).toBeVisible();
  await expect(page.locator('.assignment-row')).toContainText('uianalyst');
  await open(page, id, '/activity');
  await expect(
    page.getByText('Investigator assigned', { exact: true }),
  ).toBeVisible();
  await capturesAtAllSizes(page, 'activity-history');
  await page.getByLabel('Event category').selectOption('assignment');
  await expect(
    page.getByText('Investigator assigned', { exact: true }),
  ).toBeVisible();

  const context = await browser.newContext();
  const analyst = await context.newPage();
  try {
    await login(analyst, 'uianalyst');
    await expect(
      analyst.getByRole('table', { name: 'Authorized alerts and cases' }),
    ).toBeVisible();
    await capturesAtAllSizes(analyst, 'assigned-cases');
    await open(analyst, id, '/evidence');
    await expect(analyst.locator('.evidence-record h4').first()).toBeVisible();
    expect(
      await analyst
        .getByRole('button', { name: 'Reassign investigator', exact: true })
        .count(),
    ).toBe(0);
    await capturesAtAllSizes(analyst, 'investigation-workbench');
    await page
      .getByRole('button', { name: 'Reassign investigator', exact: true })
      .click();
    await page
      .getByLabel('Assigned Investigator', { exact: true })
      .selectOption(fixture.users.uiother);
    await page
      .getByRole('button', { name: 'Confirm assignment', exact: true })
      .click();
    await expect(page.getByRole('dialog')).not.toBeVisible();
    await expect(page.locator('.assignment-row')).toContainText('uiother');
    await expect(
      analyst.getByRole('heading', {
        name: 'Information unavailable',
        exact: true,
      }),
    ).toBeVisible({ timeout: 20000 });
    expect(await analyst.locator('.evidence-record').count()).toBe(0);
    await capturesAtAllSizes(analyst, 'authorization-error');
    await analyst
      .getByRole('button', { name: 'Sign out', exact: true })
      .click();
    await expect(analyst.getByLabel('Username', { exact: true })).toBeVisible();
    expect(
      await analyst.locator('.activity-list,.evidence-record').count(),
    ).toBe(0);
  } finally {
    await context.close();
  }
  await open(page, id, '/activity');
  await page.getByLabel('Event category').selectOption('assignment');
  await expect(
    page.getByText('Investigator reassigned', { exact: true }),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Cases', exact: true }).first().click();
  await page
    .getByLabel('Search cases', { exact: true })
    .fill('no-such-synthetic-case');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'No matching cases', exact: true }),
  ).toBeVisible();
  await capturesAtAllSizes(page, 'empty-queue');
  writeFileSync(
    `${shots}/workflow-captures.json`,
    JSON.stringify({ synthetic_only: true, captures }, null, 2),
  );
});

test('analyst cannot enumerate foreign workflow, directory or activity and logout clears views', async ({
  page,
}) => {
  await login(page, 'uianalyst');
  const statuses = await page.evaluate(
    async ({ password, id }) => {
      const auth = await fetch('/api/v1/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'uianalyst', password }),
      });
      const { access_token } = await auth.json();
      const headers = { Authorization: `Bearer ${access_token}` };
      const results = [];
      for (const suffix of ['workflow', 'activity', 'assignment-options'])
        results.push(
          (await fetch(`/api/v1/cases/${id}/${suffix}`, { headers })).status,
        );
      results.push(
        (await fetch('/api/v1/case-queue?queue=unassigned', { headers }))
          .status,
      );
      return results;
    },
    { password: fixture.password, id: fixture.cases.connected_foreign },
  );
  expect(statuses).toEqual([404, 404, 403, 403]);
  await page.evaluate((id) => {
    location.hash = `/cases/${id}`;
  }, fixture.cases.connected_foreign);
  await expect(
    page.getByRole('heading', { name: 'Information unavailable', exact: true }),
  ).toBeVisible();
  expect(
    await page
      .locator('.assignment-row,.activity-list,.evidence-record')
      .count(),
  ).toBe(0);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
  expect(
    await page.evaluate(() => localStorage.length + sessionStorage.length),
  ).toBe(0);
});
