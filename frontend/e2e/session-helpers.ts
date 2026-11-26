import { expect, type Page } from '@playwright/test';

// Tests that intentionally switch accounts must sign out; refresh now restores.
export async function resetBrowserSession(page: Page) {
  const response = await page.request.post('/api/v1/auth/session/logout');
  expect(response.status()).toBe(200);
  await page.reload();
}
