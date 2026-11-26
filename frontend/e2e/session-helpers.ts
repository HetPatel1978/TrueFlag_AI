import { expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const fixtureHealth = `${process.env.TRUEFLAG_API_PROXY ?? 'http://127.0.0.1:18010'}/health`;

// A fixture that has exited makes the Vite proxy answer 500; name the real cause instead.
export async function expectFixtureReachable(page: Page) {
  const up = await page.request
    .get(fixtureHealth, { timeout: 5000 })
    .then((response) => response.ok())
    .catch(() => false);
  expect(up, 'fixture not reachable on :18010').toBe(true);
}

// Tests that intentionally switch accounts must sign out; refresh now restores.
export async function resetBrowserSession(page: Page) {
  const response = await page.request.post('/api/v1/auth/session/logout');
  if (response.status() !== 200) await expectFixtureReachable(page);
  expect(response.status()).toBe(200);
  await page.reload();
}

// The fixture acknowledges every control command; a failed command (for example an API
// restart that did not come back) carries an error and must fail the test that sent it.
export function expectFixtureAck(directory: string, sequence: number) {
  const ack: { sequence: number; error?: string } = JSON.parse(
    readFileSync(join(directory, `ack.${sequence}.json`), 'utf8'),
  );
  expect(ack.error, `fixture command ${sequence} failed`).toBeUndefined();
}

// One place for the sign-in control, matched by role and accessible name (not decoration).
export const signInButton = (page: Page) =>
  page.getByRole('button', { name: 'Sign in', exact: true });
