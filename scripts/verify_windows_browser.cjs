/* Actual native API/browser checks. No route mocks, provider calls or secret output. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const { randomUUID } = require('node:crypto');
const root = path.resolve(__dirname, '..');
const { chromium, request } = createRequire(path.join(root, 'frontend/package.json'))('@playwright/test');
const directory = JSON.parse(fs.readFileSync(path.join(root, 'runtime/windows-native/current.json'))).directory;
const state = JSON.parse(fs.readFileSync(path.join(directory, 'state.json')));
const logins = JSON.parse(fs.readFileSync(path.join(directory, 'login.json')));
const caseId = process.argv[2];
assert.match(caseId || '', /^[a-f0-9-]{36}$/);
const base = `http://127.0.0.1:${state.frontend_port}`;
const output = path.join(directory, `browser-${randomUUID()}`);
fs.mkdirSync(output);
let stage = 'initialization';
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  const api = await request.newContext({ baseURL: base });
  const report = { live_provider_requests: 0, regulatory_source_approval: 'missing', case_id: caseId };
  try {
    const login = async username => {
      const r = await api.post('/api/v1/auth/session', { data: { username, password: logins[username].password } });
      assert.equal(r.status(), 200);
      return (await r.json()).access_token;
    };
    stage = 'authorized-assignment';
    const admin = await login('windowsadmin');
    const analyst = await login('windowsanalyst');
    const analystMe = await api.get('/api/v1/auth/me', { headers: { Authorization: `Bearer ${analyst}` } });
    const analystId = (await analystMe.json()).id;
    const detail = await api.get(`/api/v1/cases/${caseId}`, { headers: { Authorization: `Bearer ${admin}` } });
    assert.equal(detail.status(), 200);
    const record = await detail.json();
    if (record.assigned_to !== analystId) {
      const assigned = await api.put(`/api/v1/cases/${caseId}/assignment`, {
        headers: { Authorization: `Bearer ${admin}` },
        data: { expected_version: record.version, assigned_to: analystId },
      });
      assert.equal(assigned.status(), 200);
    }
    stage = 'browser-login';
    await page.goto(base);
    stage = 'browser-login-fields';
    await page.getByLabel('Username', { exact: true }).fill('windowsanalyst');
    await page.getByLabel('Password', { exact: true }).fill(logins.windowsanalyst.password);
    const signInResponse = page.waitForResponse(r => r.url().endsWith('/api/v1/auth/session') && r.request().method() === 'POST');
    await page.getByRole('button', { name: /Sign in/ }).click();
    const loginHttp = await signInResponse;
    report.browser_login_http = loginHttp.status();
    assert.equal(loginHttp.status(), 200);
    stage = 'browser-login-navigation';
    await page.getByRole('button', { name: 'Sign out', exact: true }).waitFor();
    report.login = true;
    stage = 'actual-assessment';
    const headers = { Authorization: `Bearer ${analyst}` };
    const historyResponse = await api.get(`/api/v1/cases/${caseId}/assessments`, { headers });
    assert.equal(historyResponse.status(), 200);
    const history = await historyResponse.json();
    assert.ok(history.items.length > 0);
    const assessmentId = history.items[0].assessment_id;
    const assessedResponse = await api.get(`/api/v1/cases/${caseId}/assessments/${assessmentId}`, { headers });
    assert.equal(assessedResponse.status(), 200);
    const assessed = await assessedResponse.json();
    assert.equal(assessed.explanation.status, 'verified');
    assert.equal(assessed.explanation.features.length, 27);
    const reconstructed = assessed.explanation.base_value + assessed.explanation.features.reduce((sum, f) => sum + f.contribution, 0);
    assert.ok(Math.abs(reconstructed - assessed.score) <= 1e-6);
    report.rf_and_shap = true;
    stage = 'evidence-packet';
    const evidenceResponse = await api.get(`/api/v1/cases/${caseId}/evidence?assessment_id=${assessmentId}`, { headers });
    assert.equal(evidenceResponse.status(), 200);
    const evidence = await evidenceResponse.json();
    assert.ok(evidence.sources.length > 0 && evidence.evidence.length > 0);
    const body = {
      expected_case_version: evidence.snapshot.case_version,
      expected_evidence_revision: evidence.snapshot.evidence_revision,
      expected_access_revision: evidence.snapshot.access_revision,
      assessment_id: assessmentId, window: evidence.sources[0].window, currencies: ['USD'],
    };
    const accepted = await api.post(`/api/v1/cases/${caseId}/investigations`, {
      headers: { ...headers, 'Idempotency-Key': `native-browser-${randomUUID()}` }, data: body,
    });
    assert.equal(accepted.status(), 202);
    const runId = (await accepted.json()).run_id;
    let packet;
    for (let i = 0; i < 30; i++) {
      const current = await api.get(`/api/v1/cases/${caseId}/investigations/${runId}`, { headers });
      assert.equal(current.status(), 200);
      packet = await current.json();
      if (!['pending', 'running'].includes(packet.status)) break;
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    assert.ok(['succeeded', 'abstained'].includes(packet.status));
    assert.equal(packet.verification.status, 'source_numeric_reference_checks_passed');
    report.evidence_verification = packet.verification.status;
    report.packet_run_id = runId;
    stage = 'regulatory-denial';
    const regulatory = await api.post(`/api/v1/cases/${caseId}/investigations/${runId}/regulatory-context`, {
      headers, data: { query: 'bank suspicious activity report', limit: 5 },
    });
    assert.equal(regulatory.status(), 200);
    const guidance = await regulatory.json();
    assert.equal(guidance.status, 'unavailable');
    assert.equal(guidance.passages.length, 0);
    report.unapproved_guidance_withheld = true;
    stage = 'browser-case-and-refresh';
    await page.goto(`${base}/#/cases/${caseId}`);
    await page.getByRole('navigation', { name: 'Case workflow' }).waitFor();
    await page.screenshot({ path: path.join(output, 'assessment-desktop.png'), fullPage: true });
    await page.reload();
    await page.getByRole('navigation', { name: 'Case workflow' }).waitFor();
    assert.equal(await page.getByLabel('Username', { exact: true }).count(), 0);
    report.refresh_preserves_login_and_case = true;
    await page.goto(`${base}/#/cases/${caseId}/evidence`);
    await page.getByRole('navigation', { name: 'Case workflow' }).waitFor();
    await page.screenshot({ path: path.join(output, 'evidence-desktop.png'), fullPage: true });
    await page.goto(`${base}/#/cases/${caseId}/investigation`);
    await page.getByRole('heading', { name: 'Investigation', exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, 'ai-unavailable-desktop.png'), fullPage: true });
    report.live_ai = 'blocked-not-simulated';
    stage = 'human-note';
    await page.goto(`${base}/#/cases/${caseId}/casework`);
    stage = 'human-note-form';
    const form = page.getByRole('form', { name: 'Investigation Notes', exact: true });
    await form.waitFor();
    const note = `Native Windows acceptance: reviewed source-linked activity; no criminal conclusion or automated action. ${randomUUID()}`;
    await form.locator('textarea').fill(note);
    await form.getByRole('button', { name: 'Submit investigation note', exact: true }).click();
    stage = 'human-note-history';
    await page.getByText(note, { exact: true }).waitFor({state:'attached'});
    await page.locator('summary').filter({hasText:'Casework history'}).click();
    await page.getByText(note, { exact: true }).waitFor();
    await page.reload();
    stage = 'human-note-refresh';
    await page.getByText(note, { exact: true }).waitFor({state:'attached'});
    await page.locator('summary').filter({hasText:'Casework history'}).click();
    await page.getByText(note, { exact: true }).waitFor();
    report.human_note_persisted = true;
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.screenshot({ path: path.join(output, 'casework-tablet.png'), fullPage: true });
    stage = 'logout-isolation';
    await page.getByRole('button', { name: 'Sign out', exact: true }).click();
    await page.getByLabel('Username', { exact: true }).waitFor();
    const denied = await page.evaluate(async id => (await fetch(`/api/v1/cases/${id}`)).status, caseId);
    assert.equal(denied, 401);
    report.logout_denies_case = true;
    report.status = 'non-live-native-journey-passed';
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } catch(error) {
    await page.screenshot({path:path.join(output,'failure.png'),fullPage:true});
    fs.writeFileSync(path.join(output,'partial-report.json'),JSON.stringify(report,null,2));
    throw error;
  } finally {
    await api.dispose();
    await context.close();
    await browser.close();
  }
})().catch(error => {
  fs.writeFileSync(path.join(output, 'failure.json'), JSON.stringify({ stage, error_type: error.name, live_provider_requests: 0 }));
  console.log(JSON.stringify({ status: 'failed', stage, error_type: error.name, live_provider_requests: 0 }));
  process.exitCode = 1;
});
