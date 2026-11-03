import { test, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync, renameSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { randomUUID } from 'node:crypto';
import AxeBuilder from '@axe-core/playwright';

test.use({ actionTimeout: 10000 });

const fixturePath = process.env.TRUEFLAG_E2E_FIXTURE;
if (!fixturePath) throw new Error('Use scripts/run_frontend_e2e.py');
const fixture: {
  password: string;
  csv_columns: string[];
  feature_contract_version: string;
} = JSON.parse(readFileSync(fixturePath, 'utf8'));
async function control(command: {
  worker?: 'start' | 'pause';
  fail_next?: boolean;
  revoke_batch_admin?: boolean;
  restart_api?: boolean;
}) {
  const directory = dirname(fixturePath!);
  const sequence =
    1 +
    Math.max(
      0,
      ...readdirSync(directory).map((f) =>
        Number(/^ack\.(\d+)\.json$/.exec(f)?.[1] ?? 0),
      ),
    );
  const stem = join(directory, `command.${sequence}`);
  writeFileSync(stem + '.tmp', JSON.stringify({ sequence, ...command }));
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
}
async function login(page: Page, username = 'uiadmin') {
  await page.goto('/');
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByLabel('Password', { exact: true }).press('Enter');
  await expect(
    page.getByRole('heading', { name: 'Alert dashboard', exact: true }),
  ).toBeVisible();
}
function csv(incomes: string[]) {
  return Buffer.from(
    [
      fixture.csv_columns
        .map((f) => (f === 'income' ? 'Annual Income' : f))
        .join(','),
      ...incomes.map((income) =>
        fixture.csv_columns
          .map((field) => {
            if (field === 'source_id')
              return `synthetic-browser-${randomUUID()}`;
            if (field === 'data_classification') return 'synthetic';
            if (field === 'feature_contract_version')
              return fixture.feature_contract_version;
            if (field === 'income') return income;
            if (field === 'state') return 'QZ';
            if (field === 'kycRiskScore') return '3';
            return '0';
          })
          .join(','),
      ),
    ].join('\r\n'),
  );
}
async function validate(page: Page, incomes: string[]) {
  await page
    .getByRole('link', { name: 'Batch Processing', exact: true })
    .click();
  await page.getByLabel('Choose a CSV file').setInputFiles({
    name: 'synthetic-only.csv',
    mimeType: 'text/csv',
    buffer: csv(incomes),
  });
  await page.getByRole('button', { name: 'Upload CSV', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Column mapping', exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel('Map income', { exact: true })).toHaveValue('');
  await page
    .getByLabel('Map income', { exact: true })
    .selectOption('Annual Income');
  await page
    .getByRole('checkbox', { name: /Values use the original baseline/ })
    .check();
  await page
    .getByRole('button', { name: 'Validate mapped file', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Validation preview', exact: true }),
  ).toBeVisible();
}
async function approve(page: Page) {
  await page
    .getByRole('checkbox', { name: /I approve importing only/ })
    .check();
  await page
    .getByRole('button', { name: 'Import valid records', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Start ML assessment', exact: true }),
  ).toBeVisible({ timeout: 25000 });
  return new URL(page.url()).hash.split('/')[3];
}
async function start(page: Page) {
  await page
    .getByRole('button', { name: 'Start ML Assessment', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Assessment progress', exact: true }),
  ).toBeVisible();
}
function stat(page: Page, name: string) {
  return page
    .locator('.batch-stats > div')
    .filter({ has: page.getByText(name, { exact: true }) })
    .locator('dd');
}
async function accessible(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(
    results.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
}

test('CSV to real RF/SHAP results, lost approval response, idempotency, resume and audited export', async ({
  page,
}) => {
  test.setTimeout(90000);
  await control({ worker: 'pause' });
  await login(page);
  await validate(page, ['', '0', '=1+1']);
  await expect(stat(page, 'Valid rows')).toHaveText('2');
  await expect(stat(page, 'Invalid rows')).toHaveText('1');
  await expect(page.getByText('=1+1', { exact: true })).toHaveCount(0);
  let originalID = '',
    originalKey = '';
  const approvalPath = '**/api/v1/batch-uploads/*/validations/*/imports';
  await page.route(
    approvalPath,
    async (route) => {
      originalKey = route.request().headers()['idempotency-key'];
      const response = await route.fetch();
      expect(response.status()).toBe(202);
      originalID = (await response.json()).import_id;
      await route.abort('connectionreset');
    },
    { times: 1 },
  );
  await page
    .getByRole('checkbox', { name: /I approve importing only/ })
    .check();
  await page
    .getByRole('button', { name: 'Import valid records', exact: true })
    .click();
  await expect(
    page.getByRole('button', { name: 'Retry import request' }),
  ).toBeEnabled();
  const retried = page.waitForRequest(
    (r) => r.method() === 'POST' && r.url().endsWith('/imports'),
  );
  await page.getByRole('button', { name: 'Retry import request' }).click();
  expect((await retried).headers()['idempotency-key']).toBe(originalKey);
  await expect(
    page.getByRole('heading', { name: 'Start ML assessment', exact: true }),
  ).toBeVisible({ timeout: 25000 });
  expect(page.url()).toContain(`/import/${originalID}`);
  await expect(stat(page, 'New cases')).toHaveText('2');
  await expect(stat(page, 'Invalid rows')).toHaveText('1');
  // Resume committed work by import ID; no browser-persisted credentials or data.
  await page.getByRole('link', { name: 'New upload', exact: true }).click();
  await page.getByLabel('Import ID', { exact: true }).fill(originalID);
  await page
    .getByRole('button', { name: 'Resume import', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Start ML assessment', exact: true }),
  ).toBeVisible();
  await page
    .getByLabel('Review policy', { exact: true })
    .selectOption('Coverage');
  await start(page);
  await expect(stat(page, 'Queued')).toHaveText('2', { timeout: 15000 });
  await expect(stat(page, 'Succeeded')).toHaveText('0');
  await control({ worker: 'start' });
  await expect(stat(page, 'Succeeded')).toHaveText('2', { timeout: 45000 });
  await expect(
    page.getByRole('button', { name: 'View explanation', exact: true }),
  ).toHaveCount(2);
  await page
    .getByRole('button', { name: 'View explanation', exact: true })
    .first()
    .click();
  await expect(
    page
      .getByRole('list', { name: 'SHAP feature contributions' })
      .locator('li'),
  ).toHaveCount(27);
  await accessible(page);
  await page.evaluate(() => {
    (document.activeElement as HTMLElement | null)?.blur();
    window.scrollTo(0, 0);
  });
  await page.screenshot({
    path: '../runtime/phase2-10-5-results.png',
    fullPage: true,
  });
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download results CSV' }).click();
  const file = await downloaded;
  const text = readFileSync((await file.path())!, 'utf8');
  expect(text.startsWith('\ufeff"case_id"')).toBe(true);
  expect(text.trim().split('\r\n')).toHaveLength(3);
  expect(text.split('\r\n')[0]).not.toMatch(
    /income|source_id|features|username/,
  );
  expect(text).not.toContain('=1+1');
  expect(text).toContain('Coverage');
  await page.setViewportSize({ width: 390, height: 844 });
  await accessible(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.evaluate(() => {
    (document.activeElement as HTMLElement | null)?.blur();
    window.scrollTo(0, 0);
  });
  await page.screenshot({
    path: '../runtime/phase2-10-5-mobile.png',
    fullPage: true,
  });
  await page
    .getByRole('link', { name: 'Case & history', exact: true })
    .first()
    .click();
  await expect(page.getByTestId('rf-score')).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'View assessment version 1' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByTestId('rf-score')).toHaveCount(0);
  expect(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
  ).toEqual([0, 0]);
});

test('bounded validation diagnostics paginate without revealing rejected cells', async ({
  page,
}) => {
  await login(page);
  await validate(page, [
    '',
    ...Array.from({ length: 25 }, () => '=SENSITIVE_SYNTHETIC()'),
  ]);
  await expect(stat(page, 'Invalid rows')).toHaveText('25');
  await expect(page.getByRole('table')).toBeVisible();
  await expect(page.getByText('1–20 of 25', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Next batch page' }).click();
  await expect(page.getByText('21–25 of 25', { exact: true })).toBeVisible();
  await expect(
    page.getByText('=SENSITIVE_SYNTHETIC()', { exact: true }),
  ).toHaveCount(0);
  await accessible(page);
});

test('worker downtime and partial failures retain manual-review cases', async ({
  page,
}) => {
  test.setTimeout(90000);
  await control({ worker: 'pause' });
  await login(page);
  await validate(page, ['', '0']);
  await approve(page);
  await start(page);
  await expect(stat(page, 'Queued')).toHaveText('2');
  await control({ worker: 'start', fail_next: true });
  await expect(stat(page, 'Succeeded')).toHaveText('1', { timeout: 45000 });
  await expect(stat(page, 'Failed / manual review')).toHaveText('1');
  await expect(
    page.getByText('Manual review required', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'View explanation', exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByRole('link', { name: 'Case & history', exact: true }),
  ).toHaveCount(2);
});

test('analyst restrictions and batch-admin revocation clear protected workflow state', async ({
  page,
}) => {
  await login(page, 'uianalyst');
  await expect(
    page.getByRole('link', { name: 'Batch Processing', exact: true }),
  ).toHaveCount(0);
  await page.evaluate(() => {
    location.hash = '#/batch';
  });
  await expect(
    page.getByRole('heading', { name: 'Batch processing unavailable' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await login(page, 'uibatchadmin');
  await validate(page, ['0']);
  await approve(page);
  await control({ worker: 'pause' });
  await start(page);
  await expect(stat(page, 'Queued')).toHaveText('1');
  await control({ revoke_batch_admin: true, worker: 'start' });
  await expect(
    page.getByRole('heading', { name: /Information unavailable|Welcome back/ }),
  ).toBeVisible({ timeout: 20000 });
  await expect(
    page.getByRole('heading', { name: 'Batch results', exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'View explanation', exact: true }),
  ).toHaveCount(0);
});

test('API/dispatcher restart and browser reload resume one durable batch without reassessment', async ({
  page,
}) => {
  test.setTimeout(90000);
  await control({ worker: 'pause' });
  await login(page);
  await validate(page, ['', '0']);
  const importID = await approve(page);
  await start(page);
  await expect(stat(page, 'Queued')).toHaveText('2');
  const saved = new URL(page.url()).hash;
  await control({ restart_api: true });
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Welcome back' }),
  ).toBeVisible();
  await expect(page.getByTestId('rf-score')).toHaveCount(0);
  await page.getByLabel('Username', { exact: true }).fill('uiadmin');
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByLabel('Password', { exact: true }).press('Enter');
  await expect(stat(page, 'Queued')).toHaveText('2');
  expect(new URL(page.url()).hash).toBe(saved);
  await control({ worker: 'start' });
  await expect(stat(page, 'Succeeded')).toHaveText('2', { timeout: 45000 });
  await page.getByRole('link', { name: 'New upload', exact: true }).click();
  await page.getByLabel('Import ID', { exact: true }).fill(importID);
  await page
    .getByRole('button', { name: 'Resume import', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Start ML assessment', exact: true }),
  ).toBeVisible();
  await start(page);
  expect(new URL(page.url()).hash).toBe(saved);
  await expect(stat(page, 'Succeeded')).toHaveText('2');
  await expect(
    page.getByRole('button', { name: 'View explanation', exact: true }),
  ).toHaveCount(2);
  await page
    .getByRole('link', { name: 'Case & history', exact: true })
    .first()
    .click();
  await expect(
    page.getByRole('button', { name: 'View assessment version 1' }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'View assessment version 2' }),
  ).toHaveCount(0);
  await page.getByRole('button', { name: 'Sign out' }).click();
  expect(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
  ).toEqual([0, 0]);
});
