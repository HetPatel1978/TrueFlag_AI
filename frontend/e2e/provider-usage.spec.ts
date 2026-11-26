import { test, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync, renameSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';

const file = process.env.TRUEFLAG_E2E_FIXTURE;
if (!file) throw new Error('Use the isolated provider-usage browser harness.');
const fixture: { password: string } = JSON.parse(readFileSync(file, 'utf8'));
async function login(page: Page, username: string) {
  await page.goto('/#/admin/provider-usage');
  await (await import('./session-helpers')).resetBrowserSession(page);
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in →', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Sign out', exact: true }),
  ).toBeVisible();
}

test('administrator sees real blocked accounting, disabled refresh, responsive layout and logout cleanup', async ({
  page,
}) => {
  await login(page, 'uiadmin');
  await expect(
    page.getByRole('heading', { name: 'Administration' }),
  ).toBeVisible();
  await expect(
    page.getByText('Minimum preserved balance', { exact: true }),
  ).toHaveCount(0);
  await page
    .getByText('Financial controls and usage details', { exact: true })
    .click();
  await expect(page.getByText('$1.00', { exact: true })).toBeVisible();
  const research = page.waitForResponse(
    (response) =>
      response.url().includes('/api/v1/internal/regulatory-research?') &&
      response.status() === 200,
  );
  await page.getByRole('button', { name: 'Search research' }).click();
  expect((await (await research).json()).status).toBe(
    'unapproved_research_only',
  );
  await expect(
    page.getByRole('button', { name: 'Refresh provider balance' }),
  ).toBeDisabled();
  await expect(page.getByText(/Paid requests blocked/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole('heading', { name: 'Regulatory research' }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  if (process.env.TRUEFLAG_DRAFT_SCREENSHOTS)
    await page.screenshot({
      path: join(
        process.env.TRUEFLAG_DRAFT_SCREENSHOTS,
        'provider-usage-mobile.png',
      ),
      fullPage: true,
    });
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Regulatory research' }),
  ).toHaveCount(0);
});

test('analyst cannot open provider administration', async ({ page }) => {
  await login(page, 'uianalyst');
  await expect(
    page.getByText('Administrator access required.', { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Administration' })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole('heading', { name: 'Regulatory research' }),
  ).toHaveCount(0);
});

test('server role revocation clears previously displayed financial state', async ({
  page,
}) => {
  await login(page, 'uibatchadmin');
  await expect(
    page.getByRole('heading', { name: 'Regulatory research' }),
  ).toBeVisible();
  const control = join(dirname(file!), 'command.1.json');
  const temporary = control + '.tmp';
  writeFileSync(
    temporary,
    JSON.stringify({ sequence: 1, revoke_batch_admin: true }),
  );
  renameSync(temporary, control);
  await expect
    .poll(() => existsSync(join(dirname(file!), 'ack.1.json')))
    .toBe(true);
  const denied = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/internal/provider-usage') &&
      response.status() === 403,
  );
  await page.getByRole('button', { name: 'Reload status' }).click();
  await denied;
  await expect(
    page.getByRole('heading', { name: 'Regulatory research' }),
  ).toHaveCount(0);
});
