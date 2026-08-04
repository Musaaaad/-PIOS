// Frontend runtime tests for the defects fixed in Sprint 22.3.
//
// These run against the BUILT artifact produced by deploy/render/build_frontend.sh,
// not against frontend/ source, so they exercise exactly what Render and GitHub
// Pages publish - including the generated config.js.
//
// Run: cd frontend && npm test

import { test, before, describe } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const API = 'https://pios-api.onrender.com/api/v1';

let DIST;

before(() => {
  // Build the real artifact in live mode, exactly as Render does.
  DIST = mkdtempSync(join(tmpdir(), 'pios-dist-'));
  execFileSync('bash', [join(REPO, 'deploy', 'render', 'build_frontend.sh')], {
    env: { ...process.env, PIOS_API_BASE_URL: API, OUT_DIR: DIST },
    stdio: 'pipe',
  });
});

const json = (body, status = 200, statusText = '') => ({
  ok: status >= 200 && status < 300,
  status,
  statusText,
  headers: { get: () => 'application/json' },
  json: async () => body,
});

const STANDARDS = {
  snapshot: { id: 'snap-1', period_label: '2026-08' },
  standards: [
    { standard: 'MM.1', states: { EvidenceReady: 2, Partial: 1 }, total: 3 },
    { standard: 'MM.5', states: { CriticalBlocked: 2, Missing: 1 }, total: 3 },
  ],
};
const MES = [
  { me_id: 'MM.1.1', official_text: 'نص عنصر القياس الأول', esr: false },
  { me_id: 'MM.1.2', official_text: 'نص عنصر القياس الثاني', esr: true },
];

/** Boots the built artifact in jsdom with a routed fetch stub. */
async function boot({ routes = {}, fail = null, width = 390 } = {}) {
  const html = readFileSync(join(DIST, 'index.html'), 'utf8');
  const dom = new JSDOM(html, {
    runScripts: 'outside-only',
    url: 'https://pios-frontend.onrender.com/',
    pretendToBeVisual: true,
  });
  const w = dom.window;
  w.innerWidth = width; // iPhone-class viewport

  const calls = [];
  w.fetch = async (url, opts = {}) => {
    calls.push({ url, method: (opts.method || 'GET').toUpperCase(), opts });
    if (fail) return json(fail.body ?? { detail: 'boom' }, fail.status, fail.statusText ?? '');
    for (const [frag, res] of Object.entries(routes)) {
      if (url.includes(frag)) return json(res);
    }
    return json({}, 404, 'Not Found');
  };

  for (const f of ['config.js', 'demo-data.js', 'app.js']) {
    w.eval(readFileSync(join(DIST, f), 'utf8'));
  }
  await new Promise(r => setTimeout(r, 30)); // let load() settle
  return { dom, w, doc: w.document, calls };
}

const HAPPY = {
  '/dashboard/overview': {
    site: { code: 'TGH', name_ar: 'مستشفى طريف العام', name_en: 'Turaif General Hospital' },
    readiness: { score: 42, overall_status: 'CriticalOpenActions', critical_open_actions: true,
                 accepted: 86, partial: 52, missing: 128, esr_status: { 'MM.5': 'Red', 'MM.6': 'Amber' } },
    findings: { open_total: 3, by_severity: { P0: 1 } },
    capas: { by_status: {}, overdue: 0 },
    evidence: { overdue_requests: 0, under_review: 0 },
    documents: {}, notifications: { unread: 0, critical: 0 },
  },
  '/worklists/my': { items: [{ task_type: 'Finding', id: 'live-1', title: 'LIVE-TASK', status: 'Open', severity: 'Critical', due_at: '2026-08-10' }] },
  '/notifications': [],
  '/identity/me': { user_id: 'u1', display_name: 'مستخدم حي', roles: ['AccreditationLead'] },
  '/dashboard/standards': STANDARDS,
  '/measurable-elements': MES,
  '/readiness/snapshots/calculate': { id: 'snap-2', overall_status: 'EvidenceReady' },
};

describe('built artifact', () => {
  test('config.js is generated in live mode with no development token', async () => {
    const cfg = readFileSync(join(DIST, 'config.js'), 'utf8');
    assert.match(cfg, /apiBase: "https:\/\/pios-api\.onrender\.com\/api\/v1"/);
    assert.match(cfg, /demoMode: false/);
    assert.doesNotMatch(cfg, /dev:portal-user/);
  });

  test('demo mode is false when a live API base is present', async () => {
    const { w } = await boot({ routes: HAPPY });
    assert.equal(w.PIOS_CONFIG.demoMode, false);
    assert.equal(w.PIOS_CONFIG.apiBase, API);
    assert.equal(w.document.getElementById('demoNotice').hidden, true,
      'demo banner must be hidden when the live API answers');
  });

  test('Arabic RTL is intact', async () => {
    const { doc } = await boot({ routes: HAPPY });
    assert.equal(doc.documentElement.getAttribute('dir'), 'rtl');
    assert.equal(doc.documentElement.getAttribute('lang'), 'ar');
  });
});

describe('DEFECT 1 - mobile drawer', () => {
  test('drawer closes after EVERY menu navigation click', async () => {
    const { doc, w } = await boot({ routes: HAPPY });
    const items = [...doc.querySelectorAll('#nav [data-route]')];
    assert.ok(items.length >= 10, `expected the full nav, got ${items.length}`);

    for (const item of items) {
      const routeName = item.dataset.route;
      doc.getElementById('menuBtn').click();          // open drawer
      assert.equal(doc.querySelector('.sidebar').classList.contains('open'), true,
        `drawer should be open before selecting ${routeName}`);

      // re-query: render() replaces the nav nodes on hashchange
      const live = doc.querySelector(`#nav [data-route="${routeName}"]`) || item;
      live.click();
      await new Promise(r => setTimeout(r, 5));

      assert.equal(doc.querySelector('.sidebar').classList.contains('open'), false,
        `drawer MUST close after selecting ${routeName}`);
      assert.equal(doc.getElementById('navBackdrop').hidden, true,
        `backdrop must be hidden after selecting ${routeName}`);
      assert.equal(doc.getElementById('menuBtn').getAttribute('aria-expanded'), 'false',
        `hamburger must report collapsed after selecting ${routeName}`);
      assert.equal(w.document.body.classList.contains('nav-open'), false,
        'body scroll lock must be released');
    }
  });

  test('backdrop click closes the drawer', async () => {
    const { doc } = await boot({ routes: HAPPY });
    doc.getElementById('menuBtn').click();
    assert.equal(doc.querySelector('.sidebar').classList.contains('open'), true);
    assert.equal(doc.getElementById('navBackdrop').hidden, false, 'backdrop must be shown while open');

    doc.getElementById('navBackdrop').click();
    assert.equal(doc.querySelector('.sidebar').classList.contains('open'), false);
    assert.equal(doc.getElementById('navBackdrop').hidden, true);
  });

  test('Escape closes the drawer', async () => {
    const { doc, w } = await boot({ routes: HAPPY });
    doc.getElementById('menuBtn').click();
    doc.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    assert.equal(doc.querySelector('.sidebar').classList.contains('open'), false);
  });

  test('hamburger toggles rather than only opening', async () => {
    const { doc } = await boot({ routes: HAPPY });
    const btn = doc.getElementById('menuBtn');
    btn.click();
    assert.equal(doc.querySelector('.sidebar').classList.contains('open'), true);
    btn.click();
    assert.equal(doc.querySelector('.sidebar').classList.contains('open'), false);
  });

  test('selected page stays visible and is not covered by the drawer', async () => {
    const { doc } = await boot({ routes: HAPPY });
    doc.getElementById('menuBtn').click();
    doc.querySelector('#nav [data-route="readiness"]').click();
    await new Promise(r => setTimeout(r, 10));

    assert.equal(doc.querySelector('.sidebar').classList.contains('open'), false);
    assert.equal(doc.getElementById('navBackdrop').hidden, true);
    const main = doc.getElementById('main');
    assert.ok(main.innerHTML.trim().length > 0, 'the selected page must have rendered content');
    assert.ok(main.querySelector('#calcBtn'), 'the readiness page must be the one rendered');
  });
});

describe('DEFECT 2 - readiness actions', () => {
  test('Snapshot button POSTs to /readiness/snapshots/calculate', async () => {
    const { doc, calls } = await boot({ routes: HAPPY });
    doc.querySelector('#nav [data-route="readiness"]').click();
    await new Promise(r => setTimeout(r, 10));

    calls.length = 0;
    doc.getElementById('calcBtn').click();
    await new Promise(r => setTimeout(r, 30));

    const post = calls.find(c => c.method === 'POST' && c.url.includes('/readiness/snapshots/calculate'));
    assert.ok(post, `expected a POST to /readiness/snapshots/calculate, saw ${JSON.stringify(calls.map(c => c.method + ' ' + c.url))}`);
    assert.ok(post.url.startsWith(API), 'must call the configured live API base');
  });

  test('standard card click opens that standard measurable elements', async () => {
    const { doc, calls } = await boot({ routes: HAPPY });
    doc.querySelector('#nav [data-route="readiness"]').click();
    await new Promise(r => setTimeout(r, 10));

    const cell = doc.querySelector('.standard-cell[data-standard="MM.1"]');
    assert.ok(cell, 'standard cells must carry a data-standard hook');
    calls.length = 0;
    cell.click();
    await new Promise(r => setTimeout(r, 30));

    const get = calls.find(c => c.url.includes('/measurable-elements'));
    assert.ok(get, 'clicking a standard must request its measurable elements');
    assert.ok(get.url.includes('standard_code=MM.1'), `must filter by standard, got ${get.url}`);

    const results = doc.getElementById('meResults');
    assert.equal(results.hidden, false, 'results panel must be visible');
    assert.match(results.textContent, /MM\.1\.1/);
    assert.match(results.textContent, /MM\.1\.2/);
  });

  test('"فتح عناصر المعيار" button opens measurable elements', async () => {
    const { doc, calls } = await boot({ routes: HAPPY });
    doc.querySelector('#nav [data-route="readiness"]').click();
    await new Promise(r => setTimeout(r, 10));

    const btn = doc.querySelector('.open-standard[data-standard]');
    assert.ok(btn, 'the open-standard button must carry a data-standard hook');
    const code = btn.dataset.standard;
    calls.length = 0;
    btn.click();
    await new Promise(r => setTimeout(r, 30));

    const get = calls.find(c => c.url.includes('/measurable-elements'));
    assert.ok(get, '"فتح عناصر المعيار" must request measurable elements');
    assert.ok(get.url.includes(`standard_code=${encodeURIComponent(code)}`));
    assert.equal(doc.getElementById('meResults').hidden, false);
  });

  test('readiness renders LIVE standards, not bundled demo standards', async () => {
    const { doc } = await boot({ routes: HAPPY });
    doc.querySelector('#nav [data-route="readiness"]').click();
    await new Promise(r => setTimeout(r, 10));
    const cells = [...doc.querySelectorAll('.standard-cell[data-standard]')].map(c => c.dataset.standard);
    assert.deepEqual(cells, ['MM.1', 'MM.5'], 'must reflect the API payload, not demo-data.js 41 standards');
  });
});

describe('API errors are visible, never silent', () => {
  test('failed snapshot shows an Arabic message containing the HTTP status', async () => {
    const { doc } = await boot({ routes: HAPPY });
    doc.querySelector('#nav [data-route="readiness"]').click();
    await new Promise(r => setTimeout(r, 10));

    // Make every subsequent call fail with a real status.
    doc.defaultView.fetch = async () => json({ detail: 'Bearer token required' }, 401, 'Unauthorized');
    doc.getElementById('calcBtn').click();
    await new Promise(r => setTimeout(r, 30));

    const box = doc.getElementById('pageError');
    assert.equal(box.hidden, false, 'an error box must be shown');
    assert.match(box.textContent, /HTTP 401/, 'the HTTP status must be surfaced');
    assert.match(box.textContent, /الطلب مرفوض/, 'a 401 must be named in Arabic as a rejection');
    assert.match(box.textContent, /OIDC/, 'a 401 must name the missing prerequisite');
  });

  test('failed standard open reports the status instead of doing nothing', async () => {
    const { doc } = await boot({ routes: HAPPY });
    doc.querySelector('#nav [data-route="readiness"]').click();
    await new Promise(r => setTimeout(r, 10));

    doc.defaultView.fetch = async () => json({ detail: 'nope' }, 500, 'Server Error');
    doc.querySelector('.standard-cell[data-standard]').click();
    await new Promise(r => setTimeout(r, 30));

    const box = doc.getElementById('pageError');
    assert.equal(box.hidden, false);
    assert.match(box.textContent, /HTTP 500/);
  });

  test('a network/CORS failure is reported as such, NOT as a bare "Load failed"', async () => {
    // Safari raises TypeError("Load failed") when CORS blocks the request, so
    // there is no HTTP status at all. The message must say that and name the
    // fix, rather than echoing an opaque browser string.
    const { doc } = await boot({ routes: HAPPY });
    doc.querySelector('#nav [data-route="readiness"]').click();
    await new Promise(r => setTimeout(r, 10));

    doc.defaultView.fetch = async () => { throw new TypeError('Load failed'); };
    doc.getElementById('calcBtn').click();
    await new Promise(r => setTimeout(r, 30));

    const box = doc.getElementById('pageError');
    assert.equal(box.hidden, false);
    assert.match(box.textContent, /PIOS_CORS_ORIGINS/, 'must name the actual likely cause');
    assert.match(box.textContent, /قبل وصول أي استجابة HTTP/, 'must state that no HTTP response arrived');
    assert.doesNotMatch(box.textContent, /HTTP \d{3}/, 'must NOT invent a status code that never existed');
  });

  test('a 401 on load falls back to demo data AND states the reason', async () => {
    const { doc, w } = await boot({ fail: { status: 401, statusText: 'Unauthorized', body: { detail: 'Bearer token required' } } });
    const notice = doc.getElementById('demoNotice');
    assert.equal(notice.hidden, false, 'the demo banner must be shown when falling back');
    assert.match(notice.textContent, /HTTP 401/,
      'the banner must say WHY it fell back, not silently show synthetic data');
    assert.equal(w.PIOS_CONFIG.demoMode, false, 'config still declares live mode; the fallback is runtime');
  });
});

describe('no silent no-op controls on ANY route', () => {
  const ROUTES = ['dashboard','worklist','readiness','evidence','findings','documents','exports',
                  'pilot','deployment','operations','assurance','intelligence','actions',
                  'committee','institutional-pilot','governance','security'];

  test('every route renders, and every control is either wired or visibly disabled', async () => {
    const { doc } = await boot({ routes: HAPPY });
    const report = [];

    for (const r of ROUTES) {
      doc.defaultView.location.hash = '#/' + r;
      doc.defaultView.dispatchEvent(new doc.defaultView.HashChangeEvent('hashchange'));
      await new Promise(res => setTimeout(res, 15));

      const main = doc.getElementById('main');
      assert.ok(main.innerHTML.trim().length > 0, `route ${r} rendered nothing`);

      const controls = [...main.querySelectorAll('button, .filter')];
      for (const el of controls) {
        const wired = el.dataset.wired === '1';
        const disabled = el.disabled === true || el.getAttribute('aria-disabled') === 'true';
        assert.ok(wired || disabled,
          `route ${r}: control "${(el.textContent || '').trim().slice(0, 40)}" is neither wired nor disabled - it is a silent no-op`);
        if (!wired) {
          assert.ok((el.title || '').length > 0,
            `route ${r}: disabled control "${(el.textContent || '').trim().slice(0, 40)}" must explain why`);
        }
      }
      report.push(`${r}: ${controls.filter(e => e.dataset.wired === '1').length} wired / ${controls.length} total`);
    }
    console.log('   route control inventory:\n     ' + report.join('\n     '));
  });

  test('disabled controls carry an Arabic explanation', async () => {
    const { doc } = await boot({ routes: HAPPY });
    doc.defaultView.location.hash = '#/evidence';
    doc.defaultView.dispatchEvent(new doc.defaultView.HashChangeEvent('hashchange'));
    await new Promise(res => setTimeout(res, 15));

    const blocked = [...doc.querySelectorAll('#main button')].filter(b => b.dataset.wired !== '1');
    assert.ok(blocked.length > 0, 'evidence page is expected to have unimplemented actions');
    for (const b of blocked) {
      assert.match(b.title, /غير مُفعّل/, 'the reason must be written in Arabic');
      assert.equal(b.disabled, true);
    }
  });
});

// --------------------------------------------------------------------------
// Sprint 23 - institutional authentication (OIDC Authorization Code + PKCE)
// --------------------------------------------------------------------------

const ISSUER = 'https://pios-keycloak.onrender.com/realms/pios';

async function bootAuth({ oidc = true, routes = HAPPY, tokens = null, search = '', width = 390, seed = {} } = {}) {
  const html = readFileSync(join(DIST, 'index.html'), 'utf8');
  const dom = new JSDOM(html, {
    runScripts: 'outside-only',
    url: 'https://pios-frontend.onrender.com/' + search,
    pretendToBeVisual: true,
  });
  const w = dom.window;
  w.innerWidth = width;

  // jsdom has no WebCrypto; PKCE needs getRandomValues + SHA-256 digest.
  const { webcrypto } = await import('node:crypto');
  Object.defineProperty(w, 'crypto', { value: webcrypto, configurable: true });
  // TextEncoder is a standard browser global that jsdom does not expose on the
  // window. Supplying it closes a harness gap, not an application gap.
  w.TextEncoder = TextEncoder;

  const calls = [];
  const navigations = [];
  w.fetch = async (url, opts = {}) => {
    calls.push({ url, method: (opts.method || 'GET').toUpperCase(), body: opts.body, opts });
    if (String(url).includes('/protocol/openid-connect/token')) {
      return json({ access_token: 'AT-' + Date.now(), refresh_token: 'RT', id_token: 'IT', expires_in: 300 });
    }
    for (const [frag, res] of Object.entries(routes)) if (String(url).includes(frag)) return json(res);
    return json({}, 404, 'Not Found');
  };
  // navigations are captured via PIOS_AUTH.setNavigator once auth.js loads

  const cfg = readFileSync(join(DIST, 'config.js'), 'utf8');
  w.eval(cfg);
  if (oidc) w.eval(`window.PIOS_CONFIG.oidc = {issuer:${JSON.stringify(ISSUER)}, clientId:'pios-portal', scope:'openid profile email'};`);
  else w.eval(`window.PIOS_CONFIG.oidc = {issuer:'', clientId:''};`);

  w.eval(readFileSync(join(DIST, 'auth.js'), 'utf8'));
  w.PIOS_AUTH.setNavigator((u) => navigations.push(String(u)));
  if (tokens) w.sessionStorage.setItem('pios-oidc-tokens', JSON.stringify({ ...tokens, expires_at: Date.now() + 300000 }));
  for (const [k, v] of Object.entries(seed)) w.sessionStorage.setItem(k, v);
  w.eval(readFileSync(join(DIST, 'demo-data.js'), 'utf8'));
  w.eval(readFileSync(join(DIST, 'app.js'), 'utf8'));
  await new Promise(r => setTimeout(r, 40));
  return { dom, w, doc: w.document, calls, navigations };
}

describe('Sprint 23 - no secrets are published', () => {
  test('the built bundle contains no client secret and no dev token', () => {
    for (const f of ['config.js', 'auth.js', 'app.js']) {
      const src = readFileSync(join(DIST, f), 'utf8');
      assert.doesNotMatch(src, /client_?secret/i, `${f} must not reference a client secret`);
      assert.doesNotMatch(src, /dev:portal-user/, `${f} must not contain a development token`);
    }
  });

  test('auth.js never sends a client_secret in the token request', async () => {
    const src = readFileSync(join(DIST, 'auth.js'), 'utf8');
    assert.doesNotMatch(src, /client_secret/);
    assert.match(src, /code_challenge_method/, 'PKCE must be used instead');
  });

  test('tokens are kept in sessionStorage, not localStorage', async () => {
    const { w } = await bootAuth({ tokens: { access_token: 'AT', refresh_token: 'RT' } });
    assert.ok(w.sessionStorage.getItem('pios-oidc-tokens'), 'session storage holds the tokens');
    assert.equal(w.localStorage.getItem('pios-oidc-tokens'), null,
      'refresh tokens must not be written to localStorage');
  });
});

describe('Sprint 23 - login gate and Arabic login screen', () => {
  test('unauthenticated users see the Arabic login screen, not demo data', async () => {
    const { doc } = await bootAuth({});
    const screen = doc.getElementById('loginScreen');
    assert.equal(screen.hidden, false, 'the login gate must be shown');
    assert.match(doc.getElementById('loginTitle').textContent, /تسجيل الدخول المؤسسي/);
    assert.equal(doc.getElementById('loginBtn').disabled, false);
  });

  test('login screen is usable at an iPhone-class viewport', async () => {
    const { doc, w } = await bootAuth({ width: 390 });
    assert.equal(w.innerWidth, 390);
    const card = doc.querySelector('.login-card');
    assert.ok(card, 'the login card must render');
    assert.equal(doc.documentElement.getAttribute('dir'), 'rtl', 'RTL must hold on the login screen');
    const css = readFileSync(join(DIST, 'styles.css'), 'utf8');
    assert.match(css, /@media\(max-width:760px\)\{\.login-card/, 'login must have a mobile breakpoint');
    assert.match(css, /\.login-btn\{width:100%/, 'the sign-in control must be full width on mobile');
  });

  test('with no identity provider configured the app does not gate, it labels demo mode', async () => {
    // Gating on a sign-in that cannot exist would lock the app out entirely.
    // The correct behaviour is to fall through to demo mode and say so.
    const { doc } = await bootAuth({ oidc: false, routes: {} });
    assert.equal(doc.getElementById('loginScreen').hidden, true, 'no gate without an IdP');
    const notice = doc.getElementById('demoNotice');
    assert.equal(notice.hidden, false, 'demo mode must be visibly labelled');
    assert.match(notice.textContent, /بيانات عرض تجريبية/);
  });

  test('an authenticated session skips the gate and loads the app', async () => {
    const { doc } = await bootAuth({ tokens: { access_token: 'AT', refresh_token: 'RT' } });
    assert.equal(doc.getElementById('loginScreen').hidden, true);
    assert.ok(doc.getElementById('main').innerHTML.trim().length > 0);
    assert.equal(doc.getElementById('logoutBtn').hidden, false, 'sign-out must be offered');
  });
});

describe('Sprint 23 - Authorization Code + PKCE', () => {
  test('sign-in redirects with S256 challenge, state, and no secret', async () => {
    const { doc, w, navigations } = await bootAuth({});
    doc.getElementById('loginBtn').click();
    await new Promise(r => setTimeout(r, 40));

    assert.equal(navigations.length, 1, 'exactly one redirect to the identity provider');
    const url = new URL(navigations[0]);
    assert.ok(url.href.startsWith(ISSUER + '/protocol/openid-connect/auth'));
    assert.equal(url.searchParams.get('response_type'), 'code');
    assert.equal(url.searchParams.get('code_challenge_method'), 'S256');
    assert.ok(url.searchParams.get('code_challenge'), 'a PKCE challenge is required');
    assert.ok(url.searchParams.get('state'), 'a state value is required');
    assert.equal(url.searchParams.get('client_secret'), null, 'no secret may appear in the URL');
    // The verifier must stay in the browser and never travel in the redirect.
    assert.equal(url.searchParams.get('code_verifier'), null);
    assert.ok(JSON.parse(w.sessionStorage.getItem('pios-oidc-tx') || 'null')?.verifier, 'the verifier is retained locally');
  });

  test('callback exchanges the code using the verifier and clears the URL', async () => {
    // The app handles the redirect back during boot, so the PKCE state and
    // verifier must already be in session storage - exactly as they are after
    // a real sign-in redirect.
    const { w, calls } = await bootAuth({
      search: '?code=AUTHCODE&state=ST2',
      seed: { 'pios-oidc-tx': JSON.stringify({ state: 'ST2', verifier: 'VERIFIER2', ret: '#/dashboard', exp: Date.now() + 600000 }) },
    });

    const ex = calls.find(c => String(c.url).includes('/protocol/openid-connect/token') && c.method === 'POST');
    assert.ok(ex, 'the code must be exchanged at the token endpoint');
    const body = new URLSearchParams(ex.body);
    assert.equal(body.get('grant_type'), 'authorization_code');
    assert.equal(body.get('code'), 'AUTHCODE');
    assert.equal(body.get('code_verifier'), 'VERIFIER2', 'the PKCE verifier must be presented');
    assert.equal(body.get('client_secret'), null, 'a public client sends no secret');
    assert.ok(w.PIOS_AUTH.isAuthenticated(), 'the session must now be active');
    assert.doesNotMatch(w.location.href, /code=/, 'the code must be stripped from the URL');
    assert.equal(w.sessionStorage.getItem('pios-oidc-tx'), null, 'the transaction is discarded after use');
  });

  test('a mismatched state is rejected (CSRF defence)', async () => {
    const { w, doc, calls } = await bootAuth({
      search: '?code=AUTHCODE&state=ATTACKER',
      seed: { 'pios-oidc-tx': JSON.stringify({ state: 'GENUINE', verifier: 'V', ret: '#/dashboard', exp: Date.now() + 600000 }) },
    });
    assert.ok(!calls.find(c => String(c.url).includes('/protocol/openid-connect/token')),
      'a code arriving with an unexpected state must never be exchanged');
    assert.equal(w.PIOS_AUTH.isAuthenticated(), false);
    const screen = doc.getElementById('loginScreen');
    assert.equal(screen.hidden, false, 'the user must be returned to sign-in');
    assert.match(doc.getElementById('loginError').textContent, /state mismatch/);
  });

  test('API calls carry the OIDC bearer token', async () => {
    const { calls } = await bootAuth({ tokens: { access_token: 'AT-LIVE', refresh_token: 'RT' } });
    const apiCall = calls.find(c => String(c.url).includes('/dashboard/overview'));
    assert.ok(apiCall, 'the app must call the API once authenticated');
    assert.equal(apiCall.opts.headers.Authorization, 'Bearer AT-LIVE');
  });

  test('sign-out clears the session and redirects to end-session', async () => {
    const { doc, w, navigations } = await bootAuth({ tokens: { access_token: 'AT', refresh_token: 'RT', id_token: 'IT' } });
    doc.getElementById('logoutBtn').click();
    await new Promise(r => setTimeout(r, 20));
    assert.equal(w.sessionStorage.getItem('pios-oidc-tokens'), null, 'tokens must be cleared');
    const out = navigations.find(u => u.includes('/protocol/openid-connect/logout'));
    assert.ok(out, 'the identity provider session must also be ended');
    assert.match(out, /id_token_hint=IT/);
  });

  test('an expired access token is not sent', async () => {
    const { w } = await bootAuth({});
    w.sessionStorage.setItem('pios-oidc-tokens', JSON.stringify({ access_token: 'OLD', expires_at: Date.now() - 1000 }));
    assert.equal(w.PIOS_AUTH.accessToken(), null);
    assert.equal(w.PIOS_AUTH.isAuthenticated(), false);
  });
});
