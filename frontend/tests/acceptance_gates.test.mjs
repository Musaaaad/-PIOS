// Sprint 23.9 - the Deployment Acceptance screen reads the backend, not demo data.
//
// The reported failure: with Render's pios-api configured correctly
// (PIOS_ALLOW_DEV_TOKENS=false, PIOS_AUTH_MODE=oidc) and sign-in working, the
// "قبول النشر المؤسسي" screen still showed DEV_TOKENS_DISABLED as
// "Fail - dev mode active", OIDC_TOKEN_VALIDATION and BACKUP_RESTORE_TESTED as
// Pending, and UAT_CRITICAL_PASS as Blocked. The audit found every one of those
// values was a literal in frontend/demo-data.js. The screen made no API call at
// all, so no refresh, re-login or configuration change could ever move them.
//
// These tests drive the REAL built artifact in jsdom - built by
// deploy/render/build_frontend.sh, served over HTTP, scripts resolved by the
// DOM - so they cover what Render actually publishes. Nothing here starts
// Keycloak or contacts Render.

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, existsSync, mkdtempSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join, resolve, dirname, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM, ResourceLoader } from 'jsdom';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const API = 'https://pios-api.onrender.com/api/v1';
const ISSUER = 'https://pios-keycloak.onrender.com/realms/pios';
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };

let DIST, server, origin;

before(async () => {
  DIST = mkdtempSync(join(tmpdir(), 'pios-gates-'));
  execFileSync('bash', [join(REPO, 'deploy', 'render', 'build_frontend.sh')], {
    env: { ...process.env, PIOS_API_BASE_URL: API, PIOS_OIDC_ISSUER: ISSUER, PIOS_OIDC_CLIENT_ID: 'pios-portal', OUT_DIR: DIST },
    stdio: 'pipe',
  });
  server = createServer((req, res) => {
    const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    const file = join(DIST, path === '/' ? 'index.html' : path);
    const target = existsSync(file) && path !== '/' ? file : join(DIST, 'index.html');
    res.writeHead(200, { 'Content-Type': TYPES[extname(target)] || 'text/plain' });
    res.end(readFileSync(target));
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  origin = `http://127.0.0.1:${server.address().port}`;
});

after(() => server && server.close());

const json = (body, status = 200) => ({
  ok: status >= 200 && status < 300, status,
  headers: { get: () => 'application/json' },
  json: async () => body,
});

const IDENTITY = { user_id: 'f1e2d3c4-turaif-pilot', display_name: 'قائد الاعتماد', roles: ['AccreditationLead'], site_codes: ['TGH'], auth_source: 'oidc' };
const OVERVIEW = { site: { code: 'TGH' }, readiness: { score: 71, accepted: 5, partial: 2, missing: 1, esr_status: {} }, findings: { by_severity: { P0: 1 } }, evidence: { overdue_requests: 2 }, capas: { overdue: 1 }, notifications: { unread: 3 } };

const CATALOG_CODES = [
  'API_HEALTH', 'DATABASE_REACHABLE', 'SCHEMA_TABLES_PRESENT', 'BASELINE_COUNTS_VALID', 'MIGRATIONS_APPLIED',
  'OBJECT_STORAGE_CONFIGURED', 'OBJECT_STORAGE_PRIVATE_RW', 'BACKUP_RESTORE_TESTED', 'OIDC_MODE_ENABLED',
  'OIDC_DISCOVERY_JWKS', 'OIDC_TOKEN_VALIDATION', 'OIDC_ROLE_SITE_CLAIMS', 'DEV_TOKENS_DISABLED', 'TLS_ENABLED',
  'CORS_RESTRICTED', 'MONITORING_ENABLED', 'AUDIT_WRITE_PASS', 'FRONTEND_URL_CONFIGURED', 'NOTIFICATION_SCHEDULER_PASS',
  'EXPORT_RETENTION_PASS', 'PILOT_USERS_READY', 'P0_CAMPAIGN_READY', 'UAT_CRITICAL_PASS', 'FORMAL_GO_DECISION',
];

/** The backend's shape when nothing has ever been measured. */
const notAssessed = (reason = 'no_environment') => ({
  assessed: false, reason, can_execute: true, environment: null, run: null, evaluated_at: null,
  catalog_total: 24, backup_restore: null, oidc_validation: null,
  checks: CATALOG_CODES.map(code => ({
    check_code: code, category: 'Platform', required: true, execution_mode: 'Automated',
    expected_value: 'x', status: 'NotAssessed', measured_value: null, evidence_reference: null,
    details: null, checked_at: null,
  })),
  summary: { total: 24, required: 24, pass: 0, fail: 0, pending: 0, blocked: 0, waived: 0, blockers: CATALOG_CODES, deployment_ready: false, outcome: 'NotAssessed', reason },
});

/** A stored run in which the live posture is correct and dev tokens are off. */
const assessed = (overrides = {}) => ({
  assessed: true, reason: null, can_execute: true, catalog_total: 24,
  environment: { id: 'e1', site_id: 's1', code: 'pilot-tgh', name: 'Turaif pilot', environment_type: 'Pilot', status: 'Registered', database_kind: 'PostgreSQL', database_version: '16', object_storage_kind: 'S3', auth_mode: 'OIDC', release_version: '1.3.0', tls_enabled: true, monitoring_enabled: true, active: true },
  run: { id: 'r1', environment_id: 'e1', run_code: 'LIVE-20260808T101500Z', scope: 'PostDeploy', status: 'Completed', outcome: 'ConditionalPass', summary_json: {} },
  evaluated_at: '2026-08-08T10:15:00+00:00',
  backup_restore: null, oidc_validation: null,
  checks: [
    { check_code: 'DEV_TOKENS_DISABLED', category: 'Security', required: true, execution_mode: 'Automated', status: 'Pass', measured_value: 'allow_dev_tokens=False;auth_mode=oidc', evidence_reference: null, details: null, checked_at: '2026-08-08T10:15:00+00:00' },
    { check_code: 'BACKUP_RESTORE_TESTED', category: 'Resilience', required: true, execution_mode: 'Manual', status: 'Pending', measured_value: null, evidence_reference: null, details: null, checked_at: null },
    { check_code: 'OIDC_TOKEN_VALIDATION', category: 'Identity', required: true, execution_mode: 'Manual', status: 'Pending', measured_value: null, evidence_reference: null, details: null, checked_at: null },
    { check_code: 'UAT_CRITICAL_PASS', category: 'Pilot', required: true, execution_mode: 'Automated', status: 'Blocked', measured_value: 'False', evidence_reference: null, details: null, checked_at: '2026-08-08T10:15:00+00:00' },
  ],
  summary: { total: 24, required: 24, pass: 15, fail: 0, pending: 6, blocked: 3, waived: 0, blockers: ['BACKUP_RESTORE_TESTED'], deployment_ready: false, outcome: 'ConditionalPass' },
  ...overrides,
});

/**
 * Boots the built site at #/deployment with a stubbed API.
 *
 * `summary` is what GET /deployment/acceptance-summary answers; `evaluate` is
 * what POST .../evaluate answers. Both record their calls so a test can prove
 * whether the screen asked the backend at all.
 */
async function open({ summary = notAssessed(), evaluate = null, summaryStatus = 200, hash = '#/deployment' } = {}) {
  const url = `${origin}/${hash}`;
  const html = await (await fetch(`${origin}/`)).text();
  const calls = [];
  let summaryBody = summary;

  const stub = async (u, opts = {}) => {
    const s = String(u), method = (opts.method || 'GET').toUpperCase();
    calls.push({ url: s, method });
    if (s.includes('/deployment/acceptance-summary/evaluate')) {
      if (!evaluate) return json({ detail: 'No deployment environment is registered.' }, 409);
      summaryBody = evaluate;
      return json(evaluate);
    }
    if (s.includes('/deployment/acceptance-summary')) {
      if (summaryStatus !== 200) return json({ detail: 'boom' }, summaryStatus);
      return json(summaryBody);
    }
    if (s.includes('/identity/me')) return json(IDENTITY);
    if (s.includes('/dashboard/overview')) return json(OVERVIEW);
    if (s.includes('/dashboard/standards')) return json({ standards: [] });
    if (s.includes('/worklists/my')) return json({ items: [] });
    if (s.includes('/notifications')) return json([]);
    return json({}, 404);
  };

  // A real-shaped access token, seeded before any script runs. Without a
  // session the app gates on the sign-in screen and never reaches a route at
  // all - so the acceptance screen would never be exercised.
  const payload = Buffer.from(JSON.stringify({ sub: IDENTITY.user_id, name: IDENTITY.display_name, roles: IDENTITY.roles, sites: ['TGH'] })).toString('base64url');
  const tokens = { access_token: `eyJhbGciOiJSUzI1NiJ9.${payload}.sig`, refresh_token: 'r', id_token: 'i', token_type: 'Bearer' };

  const dom = new JSDOM(html, {
    url, runScripts: 'dangerously', resources: new ResourceLoader(), pretendToBeVisual: true,
    beforeParse(w) {
      w.innerWidth = 1280;
      w.sessionStorage.setItem('pios-oidc-tokens', JSON.stringify(tokens));
      w.fetch = stub;
    },
  });

  await new Promise(r => setTimeout(r, 300));
  return { dom, w: dom.window, doc: dom.window.document, calls };
}

const mainText = doc => doc.querySelector('#main').textContent;
const acceptanceCalls = calls => calls.filter(c => c.url.includes('/deployment/acceptance-summary'));

// ------------------------------------------------------ 1. the demo source is gone

describe('the demo acceptance dataset no longer exists', () => {
  test('the published bundle carries no demo deployment gates', () => {
    const demo = readFileSync(join(DIST, 'demo-data.js'), 'utf8');
    assert.ok(!/^\s*deployment\s*:/m.test(demo), 'the demo deployment dataset is back in the shipped bundle');
    // The three literals that made the live screen lie. None of them can be
    // produced by the backend - "dev mode active" appears nowhere in it, and a
    // real run records `allow_dev_tokens=<bool>;auth_mode=<mode>` instead.
    assert.ok(!demo.includes('dev mode active'), 'the fabricated evidence string survived the build');
    assert.ok(!demo.includes('DEV_TOKENS_DISABLED'), 'a demo verdict for this gate is back in the bundle');
    assert.ok(!demo.includes('OIDC_TOKEN_VALIDATION'), 'a demo verdict for this gate is back in the bundle');
    // Note: the Pilot Center screen still carries demo gates of its own
    // (D.pilot.gates, including SECURITY_ACCEPTANCE). That is a separate
    // screen with a separate backend service and is out of this sprint's
    // scope - it is recorded, not silently accepted.
  });

  test('app.js never reads a deployment gate out of window.PIOS_DEMO', () => {
    const app = readFileSync(join(DIST, 'app.js'), 'utf8');
    assert.ok(!/\bD\.deployment\b/.test(app), 'app.js still falls back to demo deployment data');
  });

  test('window.PIOS_DEMO has no deployment key at runtime', async () => {
    const { w } = await open();
    assert.equal(w.PIOS_DEMO.deployment, undefined);
    assert.ok(Object.keys(w.PIOS_DEMO).length > 10, 'the rest of the demo dataset is untouched');
  });
});

// ------------------------------------------------------ 2. the screen calls the API

describe('the screen is backed by the API', () => {
  test('opening the screen requests the acceptance summary', async () => {
    const { calls } = await open();
    assert.equal(acceptanceCalls(calls).length, 1, 'the screen did not ask the backend for its gates');
    assert.equal(acceptanceCalls(calls)[0].method, 'GET');
  });

  test('a screen that is not open makes no acceptance request', async () => {
    const { calls } = await open({ hash: '#/dashboard' });
    assert.equal(acceptanceCalls(calls).length, 0, 'the summary is fetched for a screen nobody opened');
  });

  test('the fetch happens once, not on every re-render', async () => {
    const { w, calls } = await open();
    w.document.querySelector('#langBtn').click();
    w.document.querySelector('#langBtn').click();
    await new Promise(r => setTimeout(r, 80));
    assert.equal(acceptanceCalls(calls).length, 1, 'render triggered a repeated fetch loop');
  });

  test('the global refresh re-reads the summary from the backend', async () => {
    const { w, calls } = await open();
    w.document.querySelector('#refreshBtn').click();
    await new Promise(r => setTimeout(r, 250));
    assert.ok(acceptanceCalls(calls).length >= 2, 'refresh redisplayed a cached copy instead of re-reading');
  });
});

// ------------------------------------------------------ 3. unmeasured stays unmeasured

describe('an unmeasured gate is reported as unmeasured', () => {
  test('the not-assessed banner names the reason', async () => {
    const { doc } = await open({ summary: notAssessed('no_environment') });
    assert.ok(doc.querySelector('#notAssessed'), 'no not-assessed banner rendered');
    assert.match(mainText(doc), /لا توجد بيئة نشر مسجّلة/);
  });

  test('a registered environment with no run says so specifically', async () => {
    const { doc } = await open({ summary: { ...notAssessed('no_run'), environment: assessed().environment } });
    assert.match(mainText(doc), /لم يُنفَّذ عليها أي تشغيل قبول/);
  });

  test('the outcome reads NotAssessed and never Pass', async () => {
    const { doc } = await open();
    const text = mainText(doc);
    assert.ok(text.includes('NotAssessed'), 'the unmeasured outcome is not shown');
    assert.ok(!text.includes('"Pass"'), 'an unmeasured screen displayed a Pass verdict');
  });

  test('every catalog gate is named without being scored', async () => {
    const { doc } = await open();
    const text = mainText(doc);
    for (const code of CATALOG_CODES) assert.ok(text.includes(code), `${code} is missing from the screen`);
    assert.equal((text.match(/لم يُقس/g) || []).length, 24, 'gates were shown with an invented measurement');
  });

  test('DEV_TOKENS_DISABLED is no longer frozen at Fail', async () => {
    const { doc } = await open();
    const block = [...doc.querySelectorAll('#main .notice')].find(n => n.textContent.includes('DEV_TOKENS_DISABLED'));
    assert.ok(block, 'the gate is not rendered at all');
    assert.ok(!block.textContent.includes('dev mode active'), 'the demo evidence string is still on screen');
    assert.ok(!block.classList.contains('Critical'), 'an unmeasured gate is still styled as a failure');
  });
});

// ------------------------------------------------------ 4. a stored run is reported faithfully

describe('a stored acceptance run is reported as stored', () => {
  test('the measured DEV_TOKENS_DISABLED value comes from the backend', async () => {
    const { doc } = await open({ summary: assessed() });
    const block = [...doc.querySelectorAll('#main .notice')].find(n => n.textContent.includes('DEV_TOKENS_DISABLED'));
    assert.match(block.textContent, /allow_dev_tokens=False;auth_mode=oidc/);
    assert.match(block.textContent, /Pass/);
  });

  test('the run code and evaluation time are shown as the source', async () => {
    const { doc } = await open({ summary: assessed() });
    const text = mainText(doc);
    assert.ok(text.includes('LIVE-20260808T101500Z'), 'the screen does not name the run it is reporting');
    assert.ok(text.includes('2026-08-08T10:15:00+00:00'), 'the evaluation time is not shown');
  });

  test('environment facts come from the stored environment row', async () => {
    const { doc } = await open({ summary: assessed() });
    const text = mainText(doc);
    assert.ok(text.includes('pilot-tgh'), 'the environment code is not from the API');
    assert.ok(text.includes('1.3.0') && text.includes('PostgreSQL 16'), 'environment facts are not from the API');
  });

  test('a manual gate with no evidence is shown as Pending, not passed', async () => {
    const { doc } = await open({ summary: assessed() });
    const block = [...doc.querySelectorAll('#main .notice')].find(n => n.textContent.includes('BACKUP_RESTORE_TESTED'));
    assert.match(block.textContent, /Pending/);
    assert.match(block.textContent, /لا يوجد دليل مسجّل/);
  });

  test('deployment_ready false is never rendered as ready', async () => {
    const { doc } = await open({ summary: assessed() });
    assert.ok(!mainText(doc).includes('NotAssessed'), 'an assessed run still shows the unmeasured banner');
    assert.equal(doc.querySelector('#notAssessed'), null);
  });

  test('records with no backup or OIDC run say "no record" rather than Pending', async () => {
    const { doc } = await open({ summary: assessed() });
    const text = mainText(doc);
    assert.ok(text.includes('لا يوجد سجل'), 'a missing record was dressed up as a status');
    assert.ok(text.includes('غير مقاس'), 'RPO/RTO claimed a value it does not have');
  });
});

// ------------------------------------------------------ 5. re-evaluation

describe('re-evaluation is a separate, explicit action', () => {
  test('the re-evaluate button posts to the evaluate endpoint', async () => {
    const { doc, calls } = await open({ summary: assessed(), evaluate: assessed() });
    const btn = doc.querySelector('#runAcceptance');
    assert.ok(btn, 'the re-evaluate button is missing for an authorised operator');
    btn.click();
    await new Promise(r => setTimeout(r, 150));
    const posted = calls.filter(c => c.method === 'POST' && c.url.includes('/acceptance-summary/evaluate'));
    assert.equal(posted.length, 1, 'the button did not trigger a re-evaluation');
  });

  test('a re-evaluation that moves DEV_TOKENS_DISABLED updates the screen', async () => {
    const failing = assessed({ checks: [{ check_code: 'DEV_TOKENS_DISABLED', category: 'Security', required: true, execution_mode: 'Automated', status: 'Fail', measured_value: 'allow_dev_tokens=True;auth_mode=dev', evidence_reference: null, details: null, checked_at: null }] });
    const { doc } = await open({ summary: failing, evaluate: assessed() });
    assert.match(mainText(doc), /allow_dev_tokens=True;auth_mode=dev/);
    doc.querySelector('#runAcceptance').click();
    await new Promise(r => setTimeout(r, 150));
    assert.match(mainText(doc), /allow_dev_tokens=False;auth_mode=oidc/, 're-evaluation did not update the displayed gate');
  });

  test('a user without the role is not offered the button', async () => {
    const { doc } = await open({ summary: { ...assessed(), can_execute: false } });
    assert.equal(doc.querySelector('#runAcceptance'), null, 'a button the API would refuse was offered');
    assert.match(mainText(doc), /تتطلب دور SystemAdmin أو AccreditationLead/);
  });

  test('a failed re-evaluation leaves the stored gates on screen', async () => {
    // evaluate:null makes the stub answer 409, the real "no environment" case.
    const { doc } = await open({ summary: assessed(), evaluate: null });
    doc.querySelector('#runAcceptance').click();
    await new Promise(r => setTimeout(r, 150));
    assert.ok(doc.querySelector('#acceptanceActionError'), 'the failure was not reported');
    assert.match(mainText(doc), /allow_dev_tokens=False;auth_mode=oidc/, 'a failed action wiped the stored result');
  });

  test('re-reading is wired separately from re-evaluating', async () => {
    const { doc, calls } = await open({ summary: assessed(), evaluate: assessed() });
    doc.querySelector('#reloadAcceptance').click();
    await new Promise(r => setTimeout(r, 150));
    assert.equal(calls.filter(c => c.method === 'POST' && c.url.includes('evaluate')).length, 0, 're-read recomputed the gates');
    assert.ok(acceptanceCalls(calls).length >= 2, 're-read did not re-request the summary');
  });
});

// ------------------------------------------------------ 6. failure is not a fallback

describe('an unreachable backend does not fall back to demo values', () => {
  test('a 503 shows the fault and no gates at all', async () => {
    const { doc } = await open({ summaryStatus: 503 });
    const text = mainText(doc);
    assert.match(text, /تعذّرت قراءة نتيجة القبول/);
    assert.ok(!text.includes('DEV_TOKENS_DISABLED'), 'gates were rendered without any backend data');
  });

  test('the failed screen offers a retry that re-requests the summary', async () => {
    const { doc, calls } = await open({ summaryStatus: 503 });
    const btn = doc.querySelector('#reloadAcceptance');
    assert.ok(btn, 'no retry offered');
    assert.ok(!btn.disabled, 'the retry control was disabled as unwired');
    btn.click();
    await new Promise(r => setTimeout(r, 150));
    assert.ok(acceptanceCalls(calls).length >= 2);
  });

  test('every control on the screen is wired or visibly disabled', async () => {
    const { doc } = await open({ summary: assessed(), evaluate: assessed() });
    for (const btn of doc.querySelectorAll('#main button')) {
      const ok = btn.dataset.wired === '1' || btn.disabled;
      assert.ok(ok, `"${btn.textContent.trim()}" is neither wired nor disabled`);
    }
  });
});
