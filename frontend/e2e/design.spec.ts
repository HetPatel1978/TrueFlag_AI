import { test, expect, type Page } from '@playwright/test';
import { expectFixtureAck, signInButton } from './session-helpers';
import {
  readFileSync,
  writeFileSync,
  renameSync,
  readdirSync,
  mkdirSync,
} from 'node:fs';
import { dirname, join } from 'node:path';
import AxeBuilder from '@axe-core/playwright';

const file = process.env.TRUEFLAG_E2E_FIXTURE;
if (!file)
  throw new Error(
    'Use the guarded investigation runner with --suite design or --suite all.',
  );
const fixture: {
  password: string;
  cases: Record<string, string>;
  csv_columns: string[];
  feature_contract_version: string;
} = JSON.parse(readFileSync(file, 'utf8'));
const screenshots =
  process.env.TRUEFLAG_DESIGN_SCREENSHOTS ?? '../runtime/g2-2/screenshots';
mkdirSync(screenshots, { recursive: true });
async function control(worker: 'start' | 'pause') {
  const directory = dirname(file!);
  const sequence =
    1 +
    Math.max(
      0,
      ...readdirSync(directory).map((f) =>
        Number(/^ack\.(\d+)\.json$/.exec(f)?.[1] ?? 0),
      ),
    );
  const stem = join(directory, `command.${sequence}`);
  writeFileSync(stem + '.tmp', JSON.stringify({ sequence, worker }));
  renameSync(stem + '.tmp', stem + '.json');
  await expect
    .poll(() => {
      try {
        return JSON.parse(
          readFileSync(join(directory, `ack.${sequence}.json`), 'utf8'),
        ).sequence;
      } catch {
        return 0;
      }
    })
    .toBe(sequence);
  expectFixtureAck(directory, sequence);
}
async function login(page: Page, username = 'uianalyst') {
  await page.goto('/');
  await (await import('./session-helpers')).resetBrowserSession(page);
  await page.reload();
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await signInButton(page).click();
  await expect(
    page.getByRole('heading', { name: 'Cases', exact: true }),
  ).toBeVisible();
}
async function capture(page: Page, name: string, width = 1440, height = 1000) {
  await page.setViewportSize({ width, height });
  await page.evaluate(() => {
    (document.activeElement as HTMLElement | null)?.blur();
    window.scrollTo(0, 0);
  });
  await (await import('./ux-helpers')).expectNoHorizontalOverflow(page);
  // Wide tables may scroll inside their labelled container; page actions must remain reachable.
  const clipped = await page.locator('button:visible').evaluateAll((buttons) =>
    buttons
      .filter((button) => {
        if (button.closest('.table-wrap')) return false;
        const bounds = button.getBoundingClientRect();
        return bounds.left < -1 || bounds.right > innerWidth + 1;
      })
      .map((button) => button.textContent),
  );
  expect(clipped).toEqual([]);
  const findings = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(
    findings.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      nodes: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
  await page.screenshot({ path: `${screenshots}/${name}.png`, fullPage: true });
}
async function caseTab(page: Page, name: string) {
  await page
    .getByRole('navigation', { name: 'Case views' })
    .getByRole('link', { name, exact: true })
    .click();
}

test('real analyst workspace: desktop/tablet hierarchy, keyboard navigation and persisted investigation', async ({
  page,
}) => {
  test.setTimeout(150000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/');
  await capture(page, 'desktop-login');
  await login(page);
  await expect(
    page.getByRole('table', { name: 'Authorized alerts and cases' }),
  ).toBeVisible();
  await capture(page, 'desktop-cases');
  await capture(page, 'tablet-cases', 1024, 768);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate((id) => {
    location.hash = `/cases/${id}`;
  }, fixture.cases.design);
  await expect(
    page.getByRole('heading', {
      name: `Case ${fixture.cases.design.slice(0, 8)}`,
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'No assessment yet', exact: true }),
  ).toBeVisible();
  await capture(page, 'desktop-case-empty');
  await control('pause');
  await page.getByRole('link', { name: /Assess risk/ }).click();
  await page
    .getByRole('button', { name: 'Request assessment', exact: true })
    .click();
  await expect(
    page.getByText('Request received.', { exact: false }),
  ).toBeVisible();
  await capture(page, 'desktop-assessment-pending');
  await control('start');
  await expect(
    page.getByText('Assessment and key risk drivers saved.', { exact: true }),
  ).toBeVisible({ timeout: 45000 });
  await caseTab(page, 'Overview');
  await expect(page.getByTestId('rf-score')).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Key Risk Drivers', exact: true }),
  ).toBeVisible();
  await capture(page, 'desktop-case-overview');
  await capture(page, 'tablet-case-overview', 1024, 768);
  await caseTab(page, 'Evidence');
  await expect(page.locator('.evidence-record h4').first()).toBeVisible();
  await capture(page, 'tablet-customer-profile', 1024, 768);
  await capture(page, 'desktop-customer-profile');
  await page
    .getByRole('button', { name: 'Supporting Evidence', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Evidence Source Details', exact: true }),
  ).toBeVisible();
  await capture(page, 'desktop-supporting-evidence');
  await page
    .getByRole('button', { name: 'Transaction Activity Analysis', exact: true })
    .click();
  await expect(
    page.getByRole('table', { name: 'Authorized transaction observations' }),
  ).toBeVisible();
  await capture(page, 'desktop-transaction-analysis');
  await capture(page, 'tablet-transaction-analysis', 1024, 768);
  await caseTab(page, 'Investigation');
  await page
    .getByRole('button', { name: 'Investigation Summary', exact: true })
    .click();
  await page
    .getByRole('button', { name: 'Generate summary', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: /Investigation Summary ·/ }),
  ).toBeVisible({ timeout: 45000 });
  await capture(page, 'tablet-investigation-summary', 1024, 768);
  await capture(page, 'desktop-investigation-summary');
  // Original 900-second token policy and real permission checks are used throughout.
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
  expect(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
  ).toEqual([0, 0]);
});

test('real batch onboarding: authorized desktop/tablet screens and validation preview', async ({
  page,
}) => {
  test.setTimeout(90000);
  await login(page, 'uiadmin');
  // CSV upload: Administration › CSV imports, then the session menu's "Add CSV".
  await page
    .getByRole('navigation', { name: 'Workspace navigation' })
    .getByRole('link', { name: 'Administration', exact: true })
    .click();
  await page.getByLabel('Session options', { exact: true }).click();
  await page.getByRole('menuitem', { name: 'Add CSV', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Upload CSV', exact: true }),
  ).toBeVisible();
  await capture(page, 'desktop-batch-upload');
  await capture(page, 'tablet-batch-upload', 1024, 768);
  const text = [
    fixture.csv_columns.join(','),
    ...['', '0'].map((income, index) =>
      fixture.csv_columns
        .map((field) =>
          field === 'source_id'
            ? `synthetic-design-${index}`
            : field === 'data_classification'
              ? 'synthetic'
              : field === 'feature_contract_version'
                ? fixture.feature_contract_version
                : field === 'income'
                  ? income
                  : field === 'state'
                    ? 'QZ'
                    : '0',
        )
        .join(','),
    ),
  ].join('\r\n');
  await page.getByLabel('Choose a CSV file').setInputFiles({
    name: 'synthetic-design.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(text),
  });
  await page.getByRole('button', { name: 'Upload CSV', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Column mapping', exact: true }),
  ).toBeVisible();
  await capture(page, 'desktop-batch-mapping');
  await page
    .getByRole('checkbox', { name: /Values use the required source units/ })
    .check();
  await page
    .getByRole('button', { name: 'Validate mapped file', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Validation preview', exact: true }),
  ).toBeVisible();
  await capture(page, 'desktop-batch-validation');
  await capture(page, 'tablet-batch-validation', 1024, 768);
  await expect(
    page.getByRole('checkbox', { name: /I approve importing only/ }),
  ).not.toBeChecked();
});

test('keyboard focus and reduced motion remain usable at a narrow viewport', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.getByRole('link', { name: 'Skip to content' }).focus();
  expect(
    await page
      .getByRole('link', { name: 'Skip to content' })
      .evaluate((e) => e.getBoundingClientRect().top),
  ).toBeGreaterThanOrEqual(0);
  await page.keyboard.press('Enter');
  await expect(page.locator('#main-content')).toBeFocused();
  await capture(page, 'mobile-cases', 390, 844);
});
