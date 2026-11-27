/*
 * Walk the demo case set through the dry-run stack (scripts/demo_dry_run.py up) and save
 * screenshots to docs/demo/screens/. No AI provider request is made: research execution
 * needs an owner scope and approval that the dry run does not have.
 *
 *   node scripts/capture_demo_walkthrough.cjs <phase>
 *
 * Phases run in order: upload, assess, assign, analyst, casework, oversight.
 */
const path = require('node:path');
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');

const ROOT = path.resolve(__dirname, '..');
const { chromium } = require(path.join(ROOT, 'frontend/node_modules/@playwright/test'));
const marker = JSON.parse(fs.readFileSync(path.join(ROOT, 'runtime/demo-dry-run/current.json'), 'utf8'));
const state = JSON.parse(fs.readFileSync(path.join(marker.directory, 'state.json'), 'utf8'));
const logins = JSON.parse(fs.readFileSync(path.join(marker.directory, 'login.json'), 'utf8'));
const BASE = `http://127.0.0.1:${state.frontend_port}`;
const SCREENS = path.join(ROOT, 'docs/demo/screens');
const CSV = path.join(ROOT, 'docs/demo/trueflag_demo_cases.csv');
const NOTES = path.join(marker.directory, 'walkthrough.json');
fs.mkdirSync(SCREENS, { recursive: true });

const notes = fs.existsSync(NOTES) ? JSON.parse(fs.readFileSync(NOTES, 'utf8')) : {};
const save = () => fs.writeFileSync(NOTES, JSON.stringify(notes, null, 2));

async function shot(page, name, options = {}) {
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(SCREENS, `${name}.png`), fullPage: options.full ?? false });
  console.log('screenshot', name);
}

async function signIn(page, username) {
  await page.goto(BASE + '/');
  const out = page.getByRole('button', { name: 'Sign out', exact: true });
  if (await out.isVisible().catch(() => false)) {
    await out.click();
  }
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill(logins[username].password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await out.waitFor({ timeout: 30000 });
}

async function sessionMenu(page, item) {
  await page.getByLabel('Session options', { exact: true }).click();
  await page.getByRole('menuitem', { name: item, exact: true }).click();
}

const phases = {
  async upload(page) {
    await page.goto(BASE + '/');
    await shot(page, '01-sign-in');
    await signIn(page, 'windowsadmin');
    await page.getByLabel('Workspace navigation').getByRole('link', { name: 'Administration', exact: true }).click();
    await page.getByRole('link', { name: 'CSV Imports', exact: true }).click();
    await shot(page, '02-csv-imports');
    await sessionMenu(page, 'Add CSV');
    await page.waitForURL('**/#/batch/new');
    await page.getByLabel('Choose a CSV file').setInputFiles(CSV);
    await shot(page, '03-upload-csv');
    await page.getByRole('button', { name: 'Upload CSV', exact: true }).click();
    await page.getByRole('heading', { name: 'Column mapping', exact: true }).waitFor();
    await shot(page, '04-column-mapping');
    await page.getByRole('checkbox', { name: /Values use the required source units/ }).check();
    await page.getByRole('button', { name: 'Validate mapped file', exact: true }).click();
    await page.getByRole('heading', { name: 'Validation preview', exact: true }).waitFor();
    await shot(page, '05-validation-preview');
    await page.getByRole('checkbox', { name: /I approve importing only/ }).check();
    await page.getByRole('button', { name: 'Import valid records', exact: true }).click();
    await page.getByRole('heading', { name: 'Assess imported alerts', exact: true }).waitFor({ timeout: 60000 });
    notes.importRoute = new URL(page.url()).hash;
    await shot(page, '06-import-finished');
    save();
  },
  async assess(page) {
    await signIn(page, 'windowsadmin');
    await page.goto(BASE + '/' + notes.importRoute);
    await page.getByRole('heading', { name: 'Assess imported alerts', exact: true }).waitFor();
    await page.getByLabel('Review policy').selectOption('Balanced');
    await shot(page, '07-choose-policy');
    await page.getByRole('button', { name: 'Start assessments', exact: true }).click();
    await page.getByRole('heading', { name: 'Assessment progress', exact: true }).waitFor();
    await shot(page, '08-assessment-progress');
    await page
      .locator('[data-stat="Completed" i]')
      .locator('strong, dd')
      .first()
      .filter({ hasText: /^8$/ })
      .waitFor({ timeout: 240000 });
    notes.batchRoute = new URL(page.url()).hash;
    await page.reload();
    await page.getByRole('region', { name: 'Batch assessment results' }).waitFor({ timeout: 60000 });
    await shot(page, '09-batch-results', { full: true });
    await page.getByRole('button', { name: 'View explanation', exact: true }).first().click();
    await shot(page, '10-batch-explanation');
    save();
  },
  async assign(page) {
    // Case IDs are created at import; map each SYN- source to its case from the attach output.
    const map = JSON.parse(process.env.DEMO_CASES || '{}');
    if (Object.keys(map).length !== 8) throw new Error('DEMO_CASES must map 8 SYN- ids to case ids');
    notes.cases = map;
    save();
    await signIn(page, 'windowssupervisor');
    let first = true;
    for (const [source, caseId] of Object.entries(map)) {
      await openCase(page, caseId);
      await page.getByRole('button', { name: 'Assign investigator' }).click();
      await page.getByLabel('Assigned Investigator').selectOption({ label: 'windowsanalyst' });
      if (first) await shot(page, '11-assign-investigator');
      await page.getByRole('button', { name: 'Confirm assignment', exact: true }).click();
      await page
        .getByRole('complementary', { name: 'Case summary' })
        .getByText('windowsanalyst')
        .first()
        .waitFor({ timeout: 30000 });
      console.log('assigned', source);
      first = false;
    }
  },
  async analyst(page) {
    const c = notes.cases;
    await signIn(page, 'windowsanalyst');
    await page.getByLabel('Workspace navigation').getByRole('link', { name: 'Overview', exact: true }).click();
    await page.waitForTimeout(2500);
    await shot(page, '12-overview', { full: true });
    await page.getByLabel('Workspace navigation').getByRole('link', { name: 'Cases', exact: true }).click();
    await page.getByRole('region', { name: 'Case results' }).waitFor();
    await page.waitForTimeout(1500);
    await shot(page, '13-cases-list', { full: true });
    const views = [
      ['SYN-01-STRUCTURING', null, '14-assess-syn01'],
      ['SYN-01-STRUCTURING', 'Review Evidence', '15-evidence-syn01'],
      ['SYN-01-STRUCTURING', 'AI Investigation', '16-ai-investigation-syn01'],
      ['SYN-05-HIGHKYC', null, '17-assess-syn05'],
      ['SYN-06-PARTIAL', 'Review Evidence', '18-evidence-syn06'],
      ['SYN-02-PASSTHROUGH', 'Review Evidence', '19-evidence-syn02'],
      ['SYN-07-DORMANT', 'Review Evidence', '20-evidence-syn07'],
      ['SYN-08-INCOME', 'Review Evidence', '21-evidence-syn08'],
      ['SYN-04-SAVER', null, '22-assess-syn04'],
    ];
    for (const [source, step, name] of views) {
      await page.waitForTimeout(4000); // stay under the shared per-user request limit
      await openCase(page, c[source], step);
      await page.waitForTimeout(step ? 5000 : 3000);
      await shot(page, name, { full: true });
    }
  },
  async ai(page) {
    // Offline simulation only (dry run): labelled in the UI, no provider request.
    const c = notes.cases;
    await signIn(page, 'windowsanalyst');
    const only = (process.env.DEMO_ONLY || '').split(',').filter(Boolean);
    for (const [source, name] of [
      ['SYN-01-STRUCTURING', '28-ai-result-syn01'],
      ['SYN-06-PARTIAL', '29-ai-abstain-syn06'],
      ['SYN-04-SAVER', '30-ai-result-syn04'],
    ]) {
      if (only.length && !only.includes(source)) continue;
      await page.waitForTimeout(45000); // shared per-user request limit (120/min)
      await openCase(page, c[source], 'AI Investigation');
      const generate = page.getByRole('button', { name: /Generate (new )?investigation/ });
      await generate.waitFor({ timeout: 30000 });
      await generate.click();
      await page
        .getByText(/Investigation complete|abstain|Not enough evidence|Findings|Verified/i)
        .first()
        .waitFor({ timeout: 180000 })
        .catch(() => {});
      await page.waitForTimeout(8000);
      await shot(page, name, { full: true });
    }
  },
  async review(page) {
    // Analyst: review the (offline simulated) findings, answer open requests, then escalate.
    const c = notes.cases;
    await signIn(page, 'windowsanalyst');
    const human = async (source) => {
      await page.waitForTimeout(45000); // shared per-user request limit (120/min)
      await openCase(page, c[source], 'Human Decision');
      const action = page.getByRole('combobox', { name: 'Action', exact: true });
      await action.waitFor({ timeout: 30000 });
      return action;
    };
    const confirm = async (name) => {
      await page.getByRole('button', { name: 'Confirm and record decision' }).waitFor();
      if (name) await shot(page, name);
      await page.getByRole('button', { name: 'Confirm and record decision' }).click();
      await page.getByText('Human casework recorded').first().waitFor({ timeout: 30000 });
    };
    const reviewFinding = async (source, rationale, name, confirmName) => {
      const action = await human(source);
      await action.selectOption({ label: 'Review AI findings' });
      await page.getByRole('button', { name: 'Load my latest verified AI findings' }).click();
      await page.getByRole('combobox', { name: 'Review decision' }).selectOption({ label: 'Accept for consideration' });
      await page.getByRole('textbox', { name: 'Decision rationale' }).fill(rationale);
      if (name) await shot(page, name, { full: true });
      await page.getByRole('button', { name: 'Record finding review' }).click();
      await confirm(confirmName);
    };
    const escalate = async (source, rationale, name) => {
      const action = await human(source);
      await action.selectOption({ label: 'Escalate to supervisor' });
      await page.getByRole('textbox', { name: 'Decision rationale' }).fill(rationale);
      await page.getByRole('button', { name: 'Request supervisor review' }).click();
      await confirm(null);
      if (name) await shot(page, name, { full: true });
    };
    await reviewFinding(
      'SYN-04-SAVER',
      'The observed salary, bills and small transfers match the declared profile.',
      '31-finding-review-syn04',
      '32-confirm-decision',
    );
    await escalate(
      'SYN-04-SAVER',
      'Recommend closing as a false positive: activity is consistent with the declared salary and bills. No further action proposed.',
      '33-escalated-syn04',
    );
    const action = await human('SYN-01-STRUCTURING');
    await action.selectOption({ label: 'Respond to information request' });
    await page.getByRole('combobox', { name: 'Supporting record' }).selectOption({ index: 1 });
    await page.getByRole('textbox', { name: 'Decision rationale' }).fill(
      'No source-of-cash documents are on file for this synthetic customer. Request closed; the deposits remain unexplained.',
    );
    await shot(page, '34-info-response-syn01', { full: true });
    await page.getByRole('button', { name: 'Record request response' }).click();
    await page.getByText('Human casework recorded').first().waitFor({ timeout: 30000 });
    await reviewFinding(
      'SYN-01-STRUCTURING',
      'Ten cash-like deposits just under USD 10,000 within 90 days are confirmed in the transactions.',
      null,
      null,
    );
    await escalate(
      'SYN-01-STRUCTURING',
      'Repeated deposits just under the USD 10,000 reporting threshold followed by large transfers out. Recommend compliance review for a possible SAR referral.',
      '35-escalated-syn01',
    );
  },
  async escalate(page) {
    // No simulation: notes, an information request and escalations (each confirmed).
    const c = notes.cases;
    await signIn(page, 'windowsanalyst');
    const human = async (source) => {
      await page.waitForTimeout(45000); // shared per-user request limit (120/min)
      await openCase(page, c[source], 'Human Decision');
      const action = page.getByRole('combobox', { name: 'Action', exact: true });
      await action.waitFor({ timeout: 30000 });
      return action;
    };
    const recorded = () =>
      page.getByText('Human casework recorded').first().waitFor({ timeout: 30000 });
    let action = await human('SYN-04-SAVER');
    await action.selectOption({ label: 'Write note' });
    await page.getByRole('textbox', { name: 'Investigation note' }).fill(
      'Salary direct deposits every two weeks, regular bill payments and two small P2P transfers. Matches the declared income and a normal saver profile.',
    );
    await shot(page, '23-note-syn04', { full: true });
    await page.getByRole('button', { name: 'Submit investigation note' }).click();
    await recorded();
    action = await human('SYN-04-SAVER');
    await action.selectOption({ label: 'Escalate to supervisor' });
    await page.getByRole('textbox', { name: 'Decision rationale' }).fill(
      'Recommend closing as a false positive: activity is consistent with the declared salary and bills. No further action proposed.',
    );
    await page.getByRole('button', { name: 'Request supervisor review' }).click();
    await page.getByRole('button', { name: 'Confirm and record decision' }).waitFor();
    await shot(page, '32-confirm-decision');
    await page.getByRole('button', { name: 'Confirm and record decision' }).click();
    await recorded();
    await shot(page, '33-escalated-syn04', { full: true });
    action = await human('SYN-01-STRUCTURING');
    await action.selectOption({ label: 'Request information' });
    await page.getByRole('textbox', { name: 'Decision rationale' }).fill(
      'Ten cash-like deposits between USD 9,400 and 9,900 in 90 days. Request the customer’s source of cash and expected activity.',
    );
    await shot(page, '25-request-info-syn01', { full: true });
    await page.getByRole('button', { name: 'Record information request' }).click();
    await recorded();
    action = await human('SYN-01-STRUCTURING');
    await action.selectOption({ label: 'Escalate to supervisor' });
    await page.getByRole('textbox', { name: 'Decision rationale' }).fill(
      'Repeated cash deposits just under the USD 10,000 report level, then large transfers out. Recommend compliance review.',
    );
    await page.getByRole('button', { name: 'Request supervisor review' }).click();
    await page.getByRole('button', { name: 'Confirm and record decision' }).click();
    await recorded();
    await shot(page, '35-escalated-syn01', { full: true });
    await signIn(page, 'windowssupervisor');
    await page.getByLabel('Workspace navigation').getByRole('link', { name: 'Review Queue', exact: true }).click();
    await page.waitForTimeout(4000);
    await shot(page, '36-review-queue', { full: true });
  },
  async queue(page) {
    await signIn(page, 'windowssupervisor');
    await page.waitForTimeout(5000);
    await page.getByLabel('Workspace navigation').getByRole('link', { name: 'Review Queue', exact: true }).click();
    await page.getByRole('heading', { name: 'Review Queue' }).waitFor({ timeout: 30000 });
    await page.waitForTimeout(4000);
    await shot(page, '36-review-queue', { full: true });
  },
  async supervisor(page) {
    // Supervisor: independent review of each escalation, then the final internal resolution.
    const c = notes.cases;
    await signIn(page, 'windowssupervisor');
    await page.getByLabel('Workspace navigation').getByRole('link', { name: 'Review Queue', exact: true }).click();
    await page.waitForTimeout(4000);
    await shot(page, '36-review-queue', { full: true });
    const confirm = async () => {
      await page.getByRole('button', { name: 'Confirm and record decision' }).click();
      await page.getByText('Human casework recorded').first().waitFor({ timeout: 30000 });
    };
    for (const [source, outcome, rationale, shots] of [
      [
        'SYN-04-SAVER',
        /No further action/i,
        'Agree: salary, bills and small transfers are consistent with the declared profile. Close as a false positive.',
        ['37-supervisor-review-syn04', '38-resolved-syn04'],
      ],
      [
        'SYN-01-STRUCTURING',
        /compliance review/i,
        'Agree: repeated sub-threshold cash deposits with transfers out need compliance review. Any SAR decision stays with compliance.',
        [null, '39-resolved-syn01'],
      ],
    ]) {
      const only = (process.env.DEMO_ONLY || '').split(',').filter(Boolean);
      if (only.length && !only.includes(source)) continue;
      await page.waitForTimeout(45000);
      await openCase(page, c[source], 'Human Decision');
      const action = page.getByRole('combobox', { name: 'Action', exact: true });
      await action.waitFor({ timeout: 30000 });
      await action.selectOption({ label: 'Supervisor review' });
      await page.getByRole('combobox', { name: 'Supervisor decision' }).selectOption('approve_resolution');
      const outcomes = page.getByRole('combobox', { name: 'Proposed outcome' });
      const labels = await outcomes.locator('option').allInnerTexts();
      await outcomes.selectOption({ label: labels.find((l) => outcome.test(l)) });
      await page.getByRole('textbox', { name: 'Decision rationale' }).fill(rationale);
      if (shots[0]) await shot(page, shots[0], { full: true });
      await page.getByRole('button', { name: 'Review supervisor response' }).click();
      await confirm();
      await page.waitForTimeout(45000);
      await openCase(page, c[source], 'Human Decision');
      await action.waitFor({ timeout: 30000 });
      await action.selectOption({ label: 'Record resolution' });
      await page.getByRole('textbox', { name: 'Decision rationale' }).fill('Final internal outcome recorded after independent supervisor review.');
      await page.getByRole('button', { name: 'Review final case resolution' }).click();
      await page.getByRole('button', { name: 'Confirm and record decision' }).click();
      // A resolution reloads the case; wait for the recorded outcome instead of the notice.
      await page.getByText(/Resolution: (?!Not recorded)/).first().waitFor({ timeout: 30000 });
      await page.waitForTimeout(3000);
      await shot(page, shots[1], { full: true });
    }
  },
  async note01(page) {
    await signIn(page, 'windowsanalyst');
    await page.waitForTimeout(30000);
    await openCase(page, notes.cases['SYN-01-STRUCTURING'], 'Human Decision');
    const action = page.getByRole('combobox', { name: 'Action', exact: true });
    await action.waitFor({ timeout: 30000 });
    await action.selectOption({ label: 'Write note' });
    await page.getByRole('textbox', { name: 'Investigation note' }).fill(
      'Ten cash-like deposits of USD 9,400 to 9,900 over 90 days, then USD 84,000 transferred out to one bank account. No source-of-cash documents on file.',
    );
    await page.getByRole('button', { name: 'Submit investigation note' }).click();
    await page.getByText('Human casework recorded').first().waitFor({ timeout: 30000 });
  },
  async oversight(page) {
    const c = notes.cases;
    const offline = JSON.parse(fs.readFileSync(path.join(ROOT, 'docs/demo/demo_cases_offline.json'), 'utf8'));
    await signIn(page, 'windowsadmin');
    await page.waitForTimeout(20000);
    await openCase(page, c['SYN-01-STRUCTURING']);
    await page.getByRole('link', { name: 'Activity History' }).click();
    await page.waitForTimeout(5000);
    await shot(page, '40-activity-history', { full: true });
    await page.waitForTimeout(30000);
    await openCase(page, c['SYN-01-STRUCTURING']);
    await page.locator('summary').filter({ hasText: 'Audit details' }).first().click();
    await page.waitForTimeout(2500);
    await shot(page, '41-audit-details', { full: true });
    await page.getByLabel('Workspace navigation').getByRole('link', { name: 'Administration', exact: true }).click();
    await page.getByRole('link', { name: 'Provider Usage', exact: true }).click();
    await page.getByRole('heading', { name: 'Provider usage' }).waitFor();
    await page.waitForTimeout(4000);
    await shot(page, '42-provider-usage', { full: true });
    // Each case's evidence-pattern words (retrieval v5 rule table), tested on their own.
    for (const [words, name] of [
      ['structured currency reports aggregation', '43-test-retrieval-syn01'],
      ['transfer transmittal originator beneficiary', '44-test-retrieval-syn02'],
    ]) {
      const box = page.getByRole('textbox', { name: 'Test retrieval' });
      await box.fill(words);
      await page.getByRole('button', { name: 'Test retrieval', exact: true }).click();
      await page.getByText(/strong match/).first().waitFor({ timeout: 30000 });
      await page.waitForTimeout(1500);
      await page.getByRole('heading', { name: 'Regulatory retrieval corpus' }).scrollIntoViewIfNeeded();
      await shot(page, name);
    }
    await page.getByRole('link', { name: 'Diagnostics', exact: true }).click();
    await page.waitForTimeout(5000);
    await shot(page, '45-diagnostics', { full: true });
  },
  async retrieval(page) {
    await signIn(page, 'windowsadmin');
    await page.getByLabel('Workspace navigation').getByRole('link', { name: 'Administration', exact: true }).click();
    await page.getByRole('link', { name: 'Provider Usage', exact: true }).click();
    await page.getByRole('heading', { name: 'Provider usage' }).waitFor();
    for (const [words, name] of [
      ['structured currency reports aggregation', '43-test-retrieval-syn01'],
      ['transfer transmittal originator beneficiary', '44-test-retrieval-syn02'],
    ]) {
      await page.getByRole('textbox', { name: 'Test retrieval' }).fill(words);
      await page.getByRole('button', { name: 'Test retrieval', exact: true }).click();
      await page.getByText(/strong match/).first().waitFor({ timeout: 30000 });
      await page.waitForTimeout(1500);
      await page.getByRole('heading', { name: 'Regulatory retrieval corpus' }).scrollIntoViewIfNeeded();
      await shot(page, name);
    }
  },
  async verifyanalyst(page) {
    // Verification only (dry run with --simulation; nothing here goes into docs/demo).
    const c = notes.cases['SYN-04-SAVER'];
    await signIn(page, 'windowsanalyst');
    await openCase(page, c, 'Human Decision');
    const action = page.getByRole('combobox', { name: 'Action', exact: true });
    await action.waitFor({ timeout: 60000 });
    await action.selectOption({ label: 'Review AI findings' });
    await page.getByRole('button', { name: 'Load my latest verified AI findings' }).click();
    await page.getByRole('combobox', { name: 'Review decision' }).selectOption({ label: 'Accept for consideration' });
    await page.getByRole('textbox', { name: 'Decision rationale' }).fill('Verification of the case decision display only.');
    await page.getByRole('button', { name: 'Record finding review' }).click();
    await page.getByRole('button', { name: 'Confirm and record decision' }).click();
    await page.getByText('Human casework recorded').first().waitFor({ timeout: 30000 });
    console.log('finding reviewed');
  },
  async verifysupervisor(page) {
    const c = notes.cases['SYN-04-SAVER'];
    await signIn(page, 'windowssupervisor');
    await openCase(page, c, 'Human Decision');
    const action = page.getByRole('combobox', { name: 'Action', exact: true });
    await action.waitFor({ timeout: 60000 });
    if (process.env.STEP !== 'resolve') {
      await action.selectOption({ label: 'Supervisor review' });
      await page.getByRole('combobox', { name: 'Supervisor decision' }).selectOption('approve_resolution');
      const outcomes = page.getByRole('combobox', { name: 'Proposed outcome' });
      const labels = await outcomes.locator('option').allInnerTexts();
      await outcomes.selectOption({ label: labels.find((l) => /compliance review/i.test(l)) });
      await page.getByRole('textbox', { name: 'Decision rationale' }).fill('Verification of the case decision display only.');
      await page.getByRole('button', { name: 'Review supervisor response' }).click();
      await page.getByRole('button', { name: 'Confirm and record decision' }).click();
      await page.getByText('Human casework recorded').first().waitFor({ timeout: 30000 });
      console.log('approved');
      return;
    }
    await action.selectOption({ label: 'Record resolution' });
    await page.getByRole('textbox', { name: 'Decision rationale' }).fill('Verification of the case decision display only.');
    await page.getByRole('button', { name: 'Review final case resolution' }).click();
    await page.getByRole('button', { name: 'Confirm and record decision' }).click();
    await page.getByText(/Resolution: (?!Not recorded)/).first().waitFor({ timeout: 30000 });
    await page.waitForTimeout(4000);
    await page.screenshot({ path: path.join(marker.directory, 'verify-decision.png'), fullPage: true });
    const rail = await page.getByRole('complementary', { name: 'Case summary' }).innerText();
    console.log('RAIL', rail.replace(/\s+/g, ' '));
  },
  async resolved(page) {
    await signIn(page, 'windowssupervisor');
    await page.waitForTimeout(30000);
    await openCase(page, notes.cases['SYN-04-SAVER'], 'Human Decision');
    await page.getByText(/Resolution: (?!Not recorded)/).first().waitFor({ timeout: 30000 });
    await page.waitForTimeout(3000);
    await shot(page, '38-resolved-syn04', { full: true });
  },
  async casework(page) {
    const c = notes.cases;
    await signIn(page, 'windowsanalyst');
    const act = async (source, action, fill, name) => {
      await page.waitForTimeout(4000);
      await openCase(page, c[source], 'Human Decision');
      const select = page.getByRole('combobox', { name: 'Action', exact: true });
      await select.waitFor({ timeout: 30000 });
      await select.selectOption({ label: action });
      await fill();
      if (name) await shot(page, name, { full: true });
    };
    await act('SYN-04-SAVER', 'Write note', async () => {
      await page.getByRole('textbox', { name: 'Investigation note' }).fill(
        'Salary direct deposits every two weeks, regular bill payments and two small P2P transfers. Matches the declared income and a normal saver profile.',
      );
    }, '23-note-syn04');
    await page.getByRole('button', { name: 'Submit investigation note' }).click();
    await page.waitForTimeout(2500);
    await act('SYN-04-SAVER', 'Escalate to supervisor', async () => {
      await page.getByRole('textbox', { name: 'Decision rationale' }).fill(
        'Recommend closing as a false positive: activity is consistent with the declared salary and bills. No further action proposed.',
      );
    }, '24-escalate-syn04');
    await page.getByRole('button', { name: 'Request supervisor review' }).click();
    await page.waitForTimeout(2500);
    await act('SYN-01-STRUCTURING', 'Request information', async () => {
      await page.getByRole('textbox', { name: 'Decision rationale' }).fill(
        'Ten cash-like deposits between USD 9,400 and 9,900 in 90 days. Request the customer’s source of cash and expected activity.',
      );
    }, '25-request-info-syn01');
    await page.getByRole('button', { name: 'Record information request' }).click();
    await page.waitForTimeout(2500);
    await act('SYN-01-STRUCTURING', 'Escalate to supervisor', async () => {
      await page.getByRole('textbox', { name: 'Decision rationale' }).fill(
        'Repeated deposits just under the USD 10,000 reporting threshold followed by large transfers out. Recommend supervisor review for a possible SAR referral.',
      );
    }, '26-escalate-syn01');
    await page.getByRole('button', { name: 'Request supervisor review' }).click();
    await page.waitForTimeout(2500);
    await openCase(page, c['SYN-01-STRUCTURING'], 'Human Decision');
    await page.waitForTimeout(4000);
    await shot(page, '27-casework-history-syn01', { full: true });
  },
};

async function openCase(page, caseId, step) {
  const short = caseId.slice(0, 8);
  await page.getByLabel('Workspace navigation').getByRole('link', { name: 'Cases', exact: true }).click();
  await page.getByRole('link', { name: `Case ${short}`, exact: true }).first().click();
  await page.getByRole('heading', { name: `Case ${short}`, exact: true }).waitFor();
  if (step) {
    await page.getByRole('navigation', { name: 'Case workflow' }).getByRole('link', { name: step }).click();
  }
}

(async () => {
  const phase = process.argv[2];
  if (!phases[phase]) throw new Error('unknown phase ' + phase);
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  try {
    await phases[phase](page);
  } catch (error) {
    await page.screenshot({ path: path.join(marker.directory, `failure-${phase}.png`), fullPage: true });
    fs.writeFileSync(path.join(marker.directory, `failure-${phase}.txt`), await page.locator('body').ariaSnapshot());
    throw error;
  } finally {
    await browser.close();
  }
})();
