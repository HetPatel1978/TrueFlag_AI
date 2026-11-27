import { test, expect, type Page, type Locator } from '@playwright/test';
import { expectFixtureAck, signInButton } from './session-helpers';
import {
  readFileSync,
  writeFileSync,
  renameSync,
  mkdirSync,
  existsSync,
  readdirSync,
} from 'node:fs';
import { dirname, join } from 'node:path';
import AxeBuilder from '@axe-core/playwright';

const file = process.env.TRUEFLAG_E2E_FIXTURE!,
  screenshots = process.env.TRUEFLAG_DRAFT_SCREENSHOTS!;
if (!file || !screenshots)
  throw new Error(
    'Use the guarded human-casework Linux/PostgreSQL browser launcher.',
  );
const fixture: { password: string; cases: Record<string, string> } = JSON.parse(
  readFileSync(file, 'utf8'),
);
mkdirSync(screenshots, { recursive: true });
const manifest: { name: string; width: number; height: number }[] = existsSync(
  join(screenshots, 'manifest.json'),
)
  ? JSON.parse(readFileSync(join(screenshots, 'manifest.json'), 'utf8'))
      .captures
  : [];
async function capture(page: Page, name: string, area?: Locator) {
  await (area ?? page).screenshot({
    path: join(screenshots, name + '.png'),
    ...(area ? {} : { fullPage: true }),
  });
  manifest.push({ name, ...page.viewportSize()! });
  writeFileSync(
    join(screenshots, 'manifest.json'),
    JSON.stringify(
      { synthetic_only: true, live_provider_used: false, captures: manifest },
      null,
      2,
    ),
  );
}
async function control(command: object) {
  const sequence =
    1 +
    Math.max(
      0,
      ...readdirSync(dirname(file)).map((n) =>
        Number(/^ack\.(\d+)\.json$/.exec(n)?.[1] ?? 0),
      ),
    );
  const p = join(dirname(file), `command.${sequence}.json`);
  writeFileSync(p + '.tmp', JSON.stringify({ sequence, ...command }));
  renameSync(p + '.tmp', p);
  await expect
    .poll(() => existsSync(join(dirname(file), `ack.${sequence}.json`)))
    .toBe(true);
  expectFixtureAck(dirname(file), sequence);
}
async function login(
  page: Page,
  name: string,
  username = 'uianalyst',
  suffix = 'casework',
) {
  await page.goto(`/#/cases/${fixture.cases[name]}/${suffix}`);
  await (await import('./session-helpers')).resetBrowserSession(page);
  await page.reload();
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await signInButton(page).click();
  await expect(
    page.getByRole('button', { name: 'Sign out', exact: true }),
  ).toBeVisible();
}
const workspace = (page: Page) =>
  page.getByRole('region', { name: 'Human investigation casework' });
async function write(
  page: Page,
  formName: string,
  button: string,
  text: string,
) {
  await (await import('./ux-helpers')).expandSection(page, formName);
  const form = page.getByRole('form', { name: formName, exact: true });
  await expect(form).toBeVisible();
  await form.locator('textarea').fill(text);
  const accepted = page.waitForResponse(
    (r) => r.request().method() === 'POST' && r.url().endsWith('/casework'),
  );
  await form.getByRole('button', { name: button, exact: true }).click();
  expect((await accepted).status()).toBe(201);
  await expect(workspace(page).getByText(text, { exact: true })).toBeVisible();
}

test('analyst evidence and simulated findings through independent supervisor resolution', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await control({ worker: 'start' });
  await login(page, 'draft-complete', 'uianalyst', 'investigation');
  await expect(
    page.getByRole('button', { name: 'AI-Assisted Findings', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'AI-Assisted Findings', exact: true })
    .click();
  const parent = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' && r.url().endsWith('/investigations'),
  );
  const draft = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().endsWith('/investigation-drafts'),
  );
  await page
    .getByRole('button', { name: 'Generate AI Investigation', exact: true })
    .click();
  expect((await parent).status()).toBe(202);
  expect((await draft).status()).toBe(202);
  await expect(
    page.getByRole('heading', { name: 'Financial Observations', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/Deterministic simulated content, not a live LLM result/),
  ).toBeVisible();
  await page
    .getByRole('link', { name: 'Notes & decisions', exact: true })
    .last()
    .click();
  await expect(
    page.getByRole('form', { name: 'Investigation Notes', exact: true }),
  ).toBeVisible();
  await capture(page, 'incomplete-casework-desktop', workspace(page));
  await (
    await import('./ux-helpers')
  ).expandSection(page, 'Link supporting evidence');
  await workspace(page)
    .getByRole('combobox', { name: 'Supporting record', exact: true })
    .selectOption({ index: 1 });
  await workspace(page)
    .getByRole('button', { name: 'Inspect supporting record', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Current supporting record' }),
  ).toBeVisible();
  await write(
    page,
    'Investigation Notes',
    'Submit investigation note',
    'Observed transaction records were reviewed. The simulation is only a draft for consideration.',
  );
  await capture(
    page,
    'investigation-notes-desktop',
    page.getByRole('region', { name: 'Casework Activity History' }),
  );
  await write(
    page,
    'Additional Information Requested',
    'Record information request',
    'Clarify the documented transaction using a current supporting source record.',
  );
  await expect(
    workspace(page).getByText('1 open', { exact: true }),
  ).toBeVisible();
  await capture(page, 'information-request-desktop', workspace(page));
  await (
    await import('./ux-helpers')
  ).expandSection(page, 'Link supporting evidence');
  await workspace(page)
    .getByRole('combobox', { name: 'Supporting record', exact: true })
    .selectOption({ index: 1 });
  await write(
    page,
    'Information Request Response',
    'Record request response',
    'The selected current source record supports this internal request response.',
  );
  await expect(
    workspace(page).getByText('0 open', { exact: true }),
  ).toBeVisible();
  await (
    await import('./ux-helpers')
  ).expandSection(page, 'Review AI findings');
  await page
    .getByRole('button', {
      name: 'Load my latest verified AI findings',
      exact: true,
    })
    .click();
  await (
    await import('./ux-helpers')
  ).expandSection(page, 'Finding Review Decision');
  const review = page.getByRole('form', {
    name: 'Finding Review Decision',
    exact: true,
  });
  await expect(review).toBeVisible();
  await review.getByLabel('Review decision').selectOption('reject');
  await capture(
    page,
    'finding-review-desktop',
    page.locator('details[aria-label="Review Findings"]'),
  );
  await write(
    page,
    'Finding Review Decision',
    'Record finding review',
    'Rejected for consideration: these observations alone do not justify a criminal inference.',
  );
  await write(
    page,
    'Supervisor Escalation',
    'Request supervisor review',
    'Independent supervisor review is requested for the documented internal case outcome.',
  );
  for (const [name, width, height] of [
    ['tablet', 834, 1112],
    ['mobile', 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height });
    const { overflowingElements } = await import('./ux-helpers');
    await expect.poll(() => overflowingElements(page)).toEqual([]);
    await capture(page, `casework-${name}`);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  const a11y = await new AxeBuilder({ page })
    .include('.human-casework')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(a11y.violations.map((v) => ({ id: v.id, impact: v.impact }))).toEqual(
    [],
  );
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await login(page, 'draft-complete', 'uisupervisor');
  await page.getByRole('link', { name: 'Reviews', exact: true }).click();
  await expect(
    page.getByRole('link', { name: new RegExp('Review case ') }),
  ).toBeVisible();
  await capture(page, 'supervisor-queue-desktop');
  await page.getByRole('link', { name: new RegExp('Review case ') }).click();
  await (await import('./ux-helpers')).expandSection(page, 'Supervisor Review');
  const supervisor = page.getByRole('form', {
    name: 'Supervisor Review',
    exact: true,
  });
  await expect(supervisor).toBeVisible();
  await supervisor
    .getByLabel('Supervisor decision')
    .selectOption('approve_resolution');
  await supervisor
    .getByLabel('Proposed outcome')
    .selectOption('investigation_completed');
  await supervisor
    .getByLabel('Decision rationale')
    .fill(
      'Independent supervisor review completed; the internal synthetic outcome is approved.',
    );
  await supervisor
    .getByRole('button', { name: 'Review supervisor response', exact: true })
    .click();
  const dialog = page.getByRole('dialog', { name: 'Confirm human decision' });
  await expect(dialog).toBeVisible();
  await capture(page, 'supervisor-review-confirmation', dialog);
  const approved = page.waitForResponse(
    (r) => r.request().method() === 'POST' && r.url().endsWith('/casework'),
  );
  await dialog
    .getByRole('button', { name: 'Confirm and record decision' })
    .click();
  expect((await approved).status()).toBe(201);
  await (await import('./ux-helpers')).expandSection(page, 'Case Resolution');
  const resolution = page.getByRole('form', {
    name: 'Case Resolution',
    exact: true,
  });
  await expect(
    resolution.getByRole('button', { name: 'Review final case resolution' }),
  ).toBeEnabled();
  await resolution
    .getByLabel('Decision rationale')
    .fill(
      'The supervisor records investigation completed as an internal synthetic workflow outcome.',
    );
  await resolution
    .getByRole('button', { name: 'Review final case resolution' })
    .click();
  await capture(page, 'case-resolution-confirmation', dialog);
  const finalized = page.waitForResponse(
    (r) => r.request().method() === 'POST' && r.url().endsWith('/casework'),
  );
  await dialog
    .getByRole('button', { name: 'Confirm and record decision' })
    .click();
  expect((await finalized).status()).toBe(201);
  await expect(workspace(page).locator('.human-summary')).toContainText(
    'Investigation completed',
  );
  await capture(page, 'completed-case-resolution-desktop', workspace(page));
  await page
    .getByRole('link', { name: 'Activity', exact: true })
    .last()
    .click();
  await expect(
    page.getByText('Human case resolution recorded', { exact: true }),
  ).toBeVisible();
  await capture(page, 'human-casework-activity-history');
  await page.reload();
  await expect(
    page.getByRole('button', { name: 'Sign out', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('Human case resolution recorded', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
  expect(
    await page.evaluate(() => localStorage.length + sessionStorage.length),
  ).toBe(0);
  await expect(
    page.getByText(
      'Independent supervisor review completed; the internal synthetic outcome is approved.',
    ),
  ).toHaveCount(0);
});

test('cross-analyst casework is denied and has no writing controls', async ({
  page,
}) => {
  await login(page, 'draft-foreign');
  await expect(page.locator('main')).toContainText(
    /unavailable|not found|no longer|cannot/i,
  );
  await expect(
    page.getByRole('form', { name: 'Investigation Notes' }),
  ).toHaveCount(0);
  await capture(page, 'casework-access-denied');
});

test('source revocation hides submitted rationale and disables future decisions', async ({
  page,
}) => {
  await login(page, 'draft-revoked');
  await write(
    page,
    'Investigation Notes',
    'Submit investigation note',
    'Current permitted evidence was reviewed before its source access changed.',
  );
  await control({ revoke_source: 'draft-revoked' });
  await workspace(page)
    .getByRole('button', { name: 'Refresh casework' })
    .click();
  await expect(
    page.getByText(
      'Current permitted evidence was reviewed before its source access changed.',
    ),
  ).toHaveCount(0);
  await expect(page.getByText(/Content withheld because source/)).toBeVisible();
  await capture(page, 'casework-source-revoked', workspace(page));
});
