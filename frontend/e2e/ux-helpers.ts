import type { Page } from '@playwright/test';

/** Exercise the same explicit disclosure action as a user; never bypass API checks. */
export async function expandSection(page: Page, title: string | RegExp) {
  const summary = page.locator('summary').filter({ hasText: title }).first();
  const section = summary.locator('..');
  if ((await section.getAttribute('open')) === null) await summary.click();
}

export async function showAllFactors(page: Page) {
  const button = page
    .getByRole('button', { name: /^View all risk factors \(\d+\)$/ })
    .first();
  if (await button.count()) await button.click();
}
