import { test, expect, type Page, type Locator } from '@playwright/test';
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

const file = process.env.TRUEFLAG_E2E_FIXTURE;
const screenshots = process.env.TRUEFLAG_DRAFT_SCREENSHOTS;
if (!file || !screenshots)
  throw new Error(
    'Use scripts/run_investigation_e2e.py --suite drafts with the isolated fixture.',
  );
const fixture: { password: string; cases: Record<string, string> } = JSON.parse(
  readFileSync(file, 'utf8'),
);
mkdirSync(screenshots, { recursive: true });
const responses: {
  method: string;
  path: string;
  status: number;
  reason: string;
}[] = [];
test.beforeEach(async ({ page }) => {
  responses.length = 0;
  page.on('response', (response) => {
    const path = new URL(response.url()).pathname;
    if (!path.startsWith('/api/')) return;
    const reason = response.headers()['x-trueflag-reason'] ?? '';
    responses.push({
      method: response.request().method(),
      path: path.replace(/[a-f0-9-]{36}/g, ':id'),
      status: response.status(),
      reason: [
        'clock_uncertainty',
        'snapshot_stale',
        'simulation_unavailable',
      ].includes(reason)
        ? reason
        : '',
    });
  });
});
test.afterEach(async ({ browserName }, info) => {
  writeFileSync(
    join(dirname(file!), `http-${info.testId}.json`),
    JSON.stringify(
      {
        browser: browserName,
        status: info.status,
        responses: responses.slice(-200),
      },
      null,
      2,
    ),
  );
});
const captures: { name: string; width: number; height: number }[] = existsSync(
  join(screenshots, 'manifest.json'),
)
  ? JSON.parse(readFileSync(join(screenshots, 'manifest.json'), 'utf8'))
      .captures
  : [];
async function capture(page: Page, name: string, area?: Locator) {
  await (area ?? page).screenshot({
    path: join(screenshots!, name + '.png'),
    ...(area ? {} : { fullPage: true }),
  });
  captures.push({ name, ...page.viewportSize()! });
  writeFileSync(
    join(screenshots!, 'manifest.json'),
    JSON.stringify(
      { synthetic_only: true, live_provider_used: false, captures },
      null,
      2,
    ),
  );
}
async function control(command: object) {
  const id =
    1 +
    Math.max(
      0,
      ...readdirSync(dirname(file!)).map((name) =>
        Number(/^ack\.(\d+)\.json$/.exec(name)?.[1] ?? 0),
      ),
    );
  const target = join(dirname(file!), `command.${id}.json`);
  writeFileSync(target + '.tmp', JSON.stringify({ sequence: id, ...command }));
  renameSync(target + '.tmp', target);
  await expect
    .poll(() => existsSync(join(dirname(file!), `ack.${id}.json`)))
    .toBe(true);
}
async function open(page: Page, name: string, username = 'uianalyst') {
  await page.goto(`/#/cases/${fixture.cases[name]}/investigation`);
  await (await import('./session-helpers')).resetBrowserSession(page);
  await page.reload();
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in →', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Sign out', exact: true }),
  ).toBeVisible();
}
async function parent(page: Page, name: string, username = 'uianalyst') {
  await control({ worker: 'start' });
  await open(page, name, username);
  await expect(
    page.getByRole('button', { name: 'AI-Assisted Findings', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'Investigation Summary', exact: true })
    .click();
  const accepted = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' && r.url().endsWith('/investigations'),
  );
  await page
    .getByRole('button', { name: 'Generate summary', exact: true })
    .click();
  expect((await accepted).status()).toBe(202);
  await expect(
    page.getByRole('heading', { name: /Investigation Summary ·/ }),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'AI-Assisted Findings', exact: true })
    .click();
  await expect(
    page.getByRole('button', {
      name: 'Generate Simulated Investigation Draft',
    }),
  ).toBeEnabled();
}

test('one action verifies an evidence packet before starting offline findings', async ({
  page,
}) => {
  test.setTimeout(90000);
  await control({ worker: 'start' });
  await open(page, 'draft-one-click');
  const draft = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().endsWith('/investigation-drafts/start'),
  );
  await page
    .getByRole('button', { name: 'Generate AI Investigation', exact: true })
    .click();
  const submitted = await draft;
  expect(submitted.status()).toBe(202);
  const outcome = await submitted.json();
  const packetIdentity = { run_id: outcome.investigation_run_id };
  expect(packetIdentity.run_id).toMatch(/^[a-f0-9-]{36}$/);
  expect(outcome.mode).toBe('offline_simulation');
  expect(outcome.live_provider_used).toBe(false);
  await expect(
    page.getByRole('heading', { name: 'Financial Observations' }),
  ).toBeVisible({ timeout: 45000 });
  await expect(
    page.getByText(/No regulatory source or legal citation has been applied/),
  ).toBeVisible();
  await page
    .locator('summary')
    .filter({ hasText: 'Regulatory Guidance' })
    .click();
  await page
    .getByLabel('Search guidance')
    .fill('suspicious activity reporting');
  const reference = page.waitForResponse(
    (r) =>
      r
        .url()
        .endsWith(
          `/investigations/${packetIdentity.run_id}/regulatory-context`,
        ) && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Search approved guidance' }).click();
  const retrieved = await reference;
  expect(retrieved.status()).toBe(200);
  const regulatoryContext = await retrieved.json();
  expect(regulatoryContext.status).toBe('unavailable');
  expect(regulatoryContext.investigation_run_id).toBe(packetIdentity.run_id);
  expect(regulatoryContext.binding_sha256).toMatch(/^[a-f0-9]{64}$/);
  await expect(
    page.getByText(/Approved guidance is unavailable/),
  ).toBeVisible();
  await capture(page, 'one-action-investigation-desktop');
  await page.setViewportSize({ width: 834, height: 1112 });
  await capture(page, 'one-action-investigation-tablet');
});
async function submit(page: Page) {
  const accepted = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      r.url().endsWith('/investigation-drafts'),
  );
  await page
    .getByRole('button', { name: 'Generate Simulated Investigation Draft' })
    .click();
  const response = await accepted;
  expect(response.status()).toBe(202);
  const value = await response.json();
  expect(value.mode).toBe('offline_simulation');
  expect(value.live_provider_used).toBe(false);
  return value.draft_run_id as string;
}
const workspace = (page: Page) =>
  page.getByRole('region', { name: 'AI-Assisted Findings', exact: true });

test('assigned analyst completes real simulated draft, inspects evidence, resumes history and logs out', async ({
  page,
}) => {
  test.setTimeout(120000); // Includes at most one real server Retry-After window.
  await page.setViewportSize({ width: 1440, height: 1000 });
  await parent(page, 'draft-complete');
  await capture(page, 'case-investigation-desktop');
  await control({ worker: 'pause' });
  const run = await submit(page);
  await expect(workspace(page).locator('.draft-state-line .badge')).toHaveText(
    'Pending',
  );
  await capture(page, 'simulated-draft-pending', workspace(page));
  await control({ worker: 'start' });
  await expect(
    workspace(page).getByRole('heading', { name: 'Financial Observations' }),
  ).toBeVisible();
  await expect(
    workspace(page).getByText(/No live model interpretation is present/),
  ).toBeVisible();
  await expect(
    workspace(page).getByText(
      /No regulatory source or legal citation has been applied/,
    ),
  ).toBeVisible();
  await capture(page, 'verified-simulated-draft-desktop', workspace(page));
  await workspace(page).locator('.draft-references summary').first().click();
  await workspace(page)
    .getByRole('button', { name: 'Inspect supporting record 1', exact: true })
    .first()
    .click();
  const inspector = page.getByRole('region', {
    name: 'Supporting record details',
  });
  await expect(inspector.getByText('Record provenance')).toBeVisible();
  await capture(page, 'supporting-record-details', inspector);
  await inspector.getByRole('button', { name: 'Close record' }).click();
  for (const kind of ['Customer', 'Account']) {
    const choice = workspace(page).getByLabel('Supporting record', {
      exact: true,
    });
    const value = await choice
      .locator('option')
      .filter({ hasText: new RegExp(`^${kind} record`) })
      .first()
      .getAttribute('value');
    expect(value).toBeTruthy();
    await choice.selectOption(value!);
    await workspace(page)
      .getByRole('button', { name: 'Inspect selected record', exact: true })
      .click();
    await expect(inspector.getByText('Record provenance')).toBeVisible();
    await capture(page, `${kind.toLowerCase()}-supporting-record`, inspector);
    await inspector.getByRole('button', { name: 'Close record' }).click();
  }
  const findings = workspace(page);
  const a11y = await new AxeBuilder({ page })
    .include('.drafts-workspace')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(a11y.violations).toEqual([]);
  let newRequests = 0;
  page.on('request', (r) => {
    if (
      r.method() === 'POST' &&
      new URL(r.url()).pathname.endsWith('/investigation-drafts')
    )
      newRequests++;
  });
  const contextResponse = page.waitForResponse(
    (r) =>
      r.request().method() === 'GET' &&
      new URL(r.url()).pathname.endsWith('/evidence'),
  );
  await page.reload();
  const context = await contextResponse;
  if (context.status() === 429) {
    const retry = Number(context.headers()['retry-after']);
    expect(Number.isInteger(retry) && retry > 0 && retry <= 60).toBe(true);
    // Respect actual server backpressure; do not reset quotas or bypass authorization.
    await page.waitForTimeout(retry * 1000);
    await page
      .getByRole('button', { name: 'Refresh evidence', exact: true })
      .click();
  }
  await expect(
    page.getByRole('button', { name: 'Sign out', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'AI-Assisted Findings', exact: true })
    .click();
  await page
    .getByRole('button', { name: 'Open simulated draft', exact: true })
    .click();
  await expect(
    findings.getByRole('heading', { name: 'Financial Observations' }),
  ).toBeVisible();
  expect(newRequests).toBe(0);
  await capture(
    page,
    'draft-history-desktop',
    findings.locator('section.panel').last(),
  );
  for (const [name, width, height] of [
    ['tablet', 834, 1112],
    ['mobile', 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height });
    await expect(
      page.getByRole('heading', { name: 'Financial Observations' }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await capture(page, `verified-simulated-draft-${name}`);
  }
  expect(run).toMatch(/^[a-f0-9-]{36}$/);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
  await expect(workspace(page)).toHaveCount(0);
  expect(
    await page.evaluate(() => localStorage.length + sessionStorage.length),
  ).toBe(0);
});

test('partial evidence produces verified abstention and explicit limitations', async ({
  page,
}) => {
  await parent(page, 'draft-incomplete');
  await submit(page);
  await expect(
    workspace(page).getByText(/The simulation abstained/),
  ).toBeVisible();
  await expect(
    workspace(page).getByRole('heading', { name: 'Investigation Limitations' }),
  ).toBeVisible();
  await capture(page, 'missing-evidence-abstention', workspace(page));
});

test('another analyst case cannot expose findings or draft history', async ({
  page,
}) => {
  await open(page, 'draft-foreign');
  await expect(
    page.getByRole('heading', { name: 'Information unavailable' }),
  ).toBeVisible();
  await expect(workspace(page)).toHaveCount(0);
  await capture(page, 'access-denied');
});

test('source revocation fences a queued draft and clears disclosed content', async ({
  page,
}) => {
  // Capture the already-authenticated browser request in memory only. Never log/store the token.
  let authorization = '';
  page.on('request', (request) => {
    if (request.url().includes('/investigation-drafts'))
      authorization = request.headers()['authorization'] ?? authorization;
  });
  const phases: string[] = [];
  const checkpoint = (phase: string) => {
    phases.push(phase);
    writeFileSync(
      join(dirname(file!), 'revocation-checkpoints.json'),
      JSON.stringify({ phases, live_provider_requests: 0 }),
    );
  };
  await parent(page, 'draft-revoked');
  checkpoint('verified_parent_ready');
  await control({ worker: 'pause' });
  const run = await submit(page);
  checkpoint('durable_draft_requested');
  expect(Boolean(authorization)).toBe(true);
  const resource = `/api/v1/cases/${fixture.cases['draft-revoked']}/investigation-drafts/${run}`;
  const pending = await page.request.get(resource, {
    headers: { Authorization: authorization },
  });
  expect(pending.status()).toBe(200);
  expect((await pending.json()).status).toBe('pending');
  checkpoint('pending_job_verified');
  await control({ revoke_source: 'draft-revoked' });
  checkpoint('source_revocation_acknowledged');
  const revoked = await page.request.get(resource, {
    headers: { Authorization: authorization },
  });
  expect(revoked.status()).toBe(200);
  const result = await revoked.json();
  expect(result.status).toBe('invalidated');
  expect(result.draft === null).toBe(true);
  checkpoint('server_denied_publication_after_revocation');
  // Either draft polling or the existing evidence guard may observe revocation first.
  // Do not require a status button after the protected subtree has already unmounted.
  const refresh = page.getByRole('button', { name: 'Check draft status' });
  if (await refresh.isVisible()) await refresh.click();
  await expect(
    page
      .getByText(
        /The source evidence or access has changed|No accessible supporting records are linked|This summary is no longer current/,
      )
      .first(),
  ).toBeVisible();
  expect(run).toMatch(/^[a-f0-9-]{36}$/);
  await expect(
    page.getByRole('heading', { name: 'Financial Observations' }),
  ).toHaveCount(0);
  await capture(page, 'source-revoked');
  checkpoint('ui_source_denial_and_no_findings_verified');
  await control({ worker: 'start' });
});

test('controlled clock regression hides a previously completed draft', async ({
  page,
}) => {
  // Independent scenario: retain default per-user limits rather than sharing a spent cohort budget.
  await parent(page, 'draft-clock', 'uisupervisor');
  const run = await submit(page);
  await expect(
    workspace(page).getByRole('heading', { name: 'Financial Observations' }),
  ).toBeVisible();
  try {
    await control({ clock_fault: true });
    const denied = page.waitForResponse((r) =>
      r.url().endsWith('/investigation-drafts/' + run),
    );
    await page.getByRole('button', { name: 'Check draft status' }).click();
    const response = await denied;
    expect(response.status()).toBe(503);
    expect(response.headers()['x-trueflag-reason']).toBe('clock_uncertainty');
    await expect(
      page.getByText(/time verification could not be completed/),
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Financial Observations' }),
    ).toHaveCount(0);
    await capture(page, 'clock-unavailable');
  } finally {
    await control({ clock_fault: false });
  }
});
