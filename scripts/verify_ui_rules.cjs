/*
 * Read-only live check of the main-view display rules on every page of the native app.
 * Never clicks Generate, Approve or any casework action; it only signs in and navigates.
 *
 *   node scripts/verify_ui_rules.cjs <output-dir> [--enforce page,page,...]
 *
 * Rules mirror frontend/src/ui-rules.ts. Text inside [data-ui-guard-skip] (Audit details,
 * the global footer, the header "Synthetic data" badge) is exempt. Each page is also measured
 * with all sections collapsed against a 1920×1080 viewport.
 */
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '..');
const { chromium } = createRequire(path.join(root, 'frontend/package.json'))('@playwright/test');
const directory = JSON.parse(fs.readFileSync(path.join(root, 'runtime/windows-native/current.json'))).directory;
const state = JSON.parse(fs.readFileSync(path.join(directory, 'state.json')));
const logins = JSON.parse(fs.readFileSync(path.join(directory, 'login.json')));
const cases = JSON.parse(fs.readFileSync(path.join(directory, 'academic-demo/onboarding.json'))).cases;
const base = `http://127.0.0.1:${state.frontend_port}`;

const terminology = fs.readFileSync(path.join(root, 'frontend/src/terminology.ts'), 'utf8');
const featureBlock = /MODEL_FEATURES[^=]*=\s*Object\.freeze\(\[([^\]]*)\]/.exec(terminology)[1];
const features = [...featureBlock.matchAll(/'([A-Za-z0-9]+)'/g)].map((m) => m[1]);
if (features.length !== 27) throw new Error('model feature list not found');
const camel = features.filter((n) => /[a-z][A-Z0-9]/.test(n));
const RULES = [
  // Regulation section numbers such as "§ 1020.320" are identifiers, not decimals.
  ['more_than_2_decimals', /(?<!§\s*\d*)\d\.\d{3,}\b/g],
  ['midnight_time', /\b00:00:00\b/g],
  ['sha256', /\b[0-9a-f]{64}\b/gi],
  ['uuid', /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi],
  // Case-insensitive: a capitalised raw name (e.g. "TotalMerchCred90d") is still a raw name.
  ['model_field_name', new RegExp(`\\b(?:${camel.join('|')})\\b`, 'gi')],
  // Raw retrieval input codes such as "risk_driver:totalSpend90d" must use human labels.
  ['raw_input_code', /\b(?:risk_driver|missing_evidence|calculation|conflict):\w+/g],
  [
    'disclaimer_outside_footer',
    /Human review required|No automatic case actions|Synthetic data|Not regulatory guidance|Academic demo/gi,
  ],
];

const out = process.argv[2];
const enforceAt = process.argv.indexOf('--enforce');
const enforce = enforceAt > 0 ? process.argv[enforceAt + 1].split(',') : [];
fs.mkdirSync(out, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  await context.route('**/*', (r) => (new URL(r.request().url()).origin === base ? r.continue() : r.abort()));
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e.message).slice(0, 200)));
  await page.goto(base);
  await page.getByLabel('Username', { exact: true }).fill('windowsadmin');
  await page.getByLabel('Password', { exact: true }).fill(logins.windowsadmin.password);
  await page.getByRole('button', { name: /Sign in/ }).click();
  await page.getByRole('button', { name: 'Sign out', exact: true }).waitFor();
  const routes = [
    ['overview', '#/overview'],
    ['cases', '#/'],
    ['review-queue', '#/supervisor-review'],
    ['admin-imports', '#/admin/imports'],
    ['admin-provider', '#/admin/provider-usage'],
    ['admin-diagnostics', '#/admin/diagnostics'],
  ];
  for (const [name, id] of Object.entries(cases))
    for (const step of ['', 'evidence', 'investigation', 'casework', 'activity'])
      routes.push([`${name}-${step || 'assessment'}`, `#/cases/${id}${step ? '/' + step : ''}`]);
  const report = { pages: {}, page_errors: errors };
  let failed = false;
  for (const [name, hash] of routes) {
    await page.goto(`${base}/${hash}`);
    await page.waitForTimeout(5000);
    // Collapse every disclosure to measure the default layout.
    await page.evaluate(() => document.querySelectorAll('details[open]').forEach((d) => (d.open = false)));
    const text = await page.evaluate(() => {
      const clone = document.querySelector('.work-area').cloneNode(true);
      clone.querySelectorAll('[data-ui-guard-skip], script, style').forEach((n) => n.remove());
      // Join text nodes with spaces so adjacent cells never merge into one token.
      const walker = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT);
      const parts = [];
      while (walker.nextNode()) parts.push(walker.currentNode.nodeValue);
      return parts.join(' ');
    });
    const violations = [];
    for (const [rule, pattern] of RULES)
      for (const m of text.matchAll(pattern)) violations.push(`${rule}: ${m[0]}`);
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    await page.screenshot({ path: path.join(out, `${name}.png`), fullPage: true });
    fs.writeFileSync(path.join(out, `${name}.txt`), await page.locator('body').innerText());
    report.pages[name] = { height, fits_1080: height <= 1080, violations: [...new Set(violations)] };
    if (enforce.includes(name) && violations.length) failed = true;
  }
  fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 1));
  console.log(JSON.stringify(report, null, 1));
  await browser.close();
  if (failed || errors.length) process.exitCode = 1;
})().catch((e) => {
  console.log('FAILED', e.message.slice(0, 300));
  process.exitCode = 1;
});
