// Sprint 23.7 - what the user sees AFTER a successful sign-in.
//
// Sprint 23.6 proved authentication works end to end. It did not prove the
// application becomes usable, and live it did not: a real user signed in with
// Keycloak, the login screen disappeared, and the app sat on its static shell -
// navigation empty, main content empty, nothing to act on.
//
// The cause was structural. render() ran only after all four bootstrap requests
// settled, so until the backend answered there was no navigation, no content
// and no message. On a platform whose free instances sleep, "the backend has
// not answered yet" is routine, and it was indistinguishable from a dead app.
//
// A second defect hid behind it: a live API that REJECTED the user (401/403)
// fell back to the demo dataset, so an account with no assigned role saw a
// populated dashboard and a user chip showing the demo identity's role.
//
// Every scenario below asserts on what is VISIBLE - computed styles and
// innerText - never merely that a node exists.
//
// Tokens carry the claim shape the pios realm actually emits, including the
// Keycloak default roles every user carries.
//
// NOT covered, stated plainly: WebKit. Only Chromium is available in this
// environment, so nothing here reproduces iOS Safari. See the PR.

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { listen, readBody, send, json, launchChromium, identityKit, serveProductionBuild } from './support/e2e_support.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const IPHONE = { width: 390, height: 844 };

let browser, idp, api, site, IDP_ORIGIN, API_ORIGIN, SITE_ORIGIN, DIST, kit;

/** Per-test backend behaviour. */
let backend = { mode: 'ok', roles: ['AccreditationLead'], idpError: null };
const resetBackend = () => { backend = { mode: 'ok', roles: ['AccreditationLead'], idpError: null }; };

const OVERVIEW = {
  site: { code: 'TGH' },
  readiness: { score: 71, accepted: 5, partial: 2, missing: 1, esr_status: { 'MM.1': 'Green' } },
  findings: { by_severity: { P0: 1 } }, evidence: { overdue_requests: 2 },
  capas: { overdue: 1 }, notifications: { unread: 3 },
};
const WORK = { items: [{ task_type: 'Evidence', title: 'مهمة تجريبية', status: 'Open', severity: 'P1', due_at: '2026-09-01', href: '#/evidence' }] };

before(async () => {
  ({ s: idp, origin: IDP_ORIGIN } = await listen(async (req, res) => {
    const u = new URL(req.url, IDP_ORIGIN);
    if (u.pathname.endsWith('/certs')) return json(res, 200, kit.jwks);
    if (req.method === 'GET' && u.pathname.endsWith('/openid-connect/auth')) {
      const q = u.searchParams;
      return send(res, 200, 'text/html; charset=utf-8', `<!doctype html><meta charset=utf-8>
        <form method="POST" action="${u.pathname}?${q.toString()}">
          <input name="username" id="username"><input name="password" id="password" type="password">
          <button id="kc-login" type="submit">Sign In</button></form>`);
    }
    if (req.method === 'POST' && u.pathname.endsWith('/openid-connect/auth')) {
      const q = u.searchParams;
      const back = new URL(q.get('redirect_uri'));
      if (backend.idpError) {
        // Keycloak returns the failure on the redirect, not as a code.
        back.searchParams.set('error', backend.idpError);
        back.searchParams.set('state', q.get('state'));
      } else {
        back.searchParams.set('code', 'code-' + Date.now());
        back.searchParams.set('state', q.get('state'));
      }
      return send(res, 302, 'text/plain', '', { Location: back.toString() });
    }
    if (u.pathname.endsWith('/token')) {
      await readBody(req);
      return json(res, 200, {
        access_token: kit.mint({ roles: backend.roles }), refresh_token: 'refresh-1',
        id_token: kit.mint({ roles: backend.roles }), expires_in: 300, token_type: 'Bearer',
      });
    }
    if (u.pathname.endsWith('/logout')) return send(res, 302, 'text/plain', '', { Location: SITE_ORIGIN + '/' });
    json(res, 404, {});
  }));

  ({ s: api, origin: API_ORIGIN } = await listen((req, res) => {
    if (req.method === 'OPTIONS') return send(res, 204, 'text/plain', '');
    const u = new URL(req.url, API_ORIGIN);
    const claims = kit.verify((req.headers.authorization || '').replace(/^Bearer /, ''));
    if (!claims) return json(res, 401, { detail: 'not authenticated' });

    if (backend.mode === 'hang') return;                       // never answers
    if (backend.mode === '500') return json(res, 500, { detail: 'boom' });
    if (backend.mode === '401') return json(res, 401, { detail: 'Invalid OIDC token: signature verification failed' });
    if (backend.mode === '503') return json(res, 503, { detail: 'identity provider is not configured on this service' });
    // Deny by default: a token with no PIOS role is refused, as the real backend does.
    const pios = (claims.roles || []).filter(r => !kit.KEYCLOAK_DEFAULTS.includes(r));
    if (backend.mode === '403' || pios.length === 0) return json(res, 403, { detail: 'no mapped roles' });

    const p = u.pathname;
    const empty = backend.mode === 'empty';
    if (p.endsWith('/identity/me')) return json(res, 200, { user_id: claims.sub, display_name: claims.name, roles: pios, site_codes: claims.sites, auth_source: 'oidc' });
    if (p.endsWith('/dashboard/overview')) return json(res, 200, empty ? { site: { code: 'TGH' }, readiness: {}, findings: {}, evidence: {}, capas: {}, notifications: {} } : OVERVIEW);
    if (p.endsWith('/worklists/my')) return json(res, 200, empty ? { items: [] } : WORK);
    if (p.endsWith('/dashboard/standards')) return json(res, 200, { standards: [] });
    json(res, 200, []);
  }));

  kit = identityKit({ issuer: () => `${IDP_ORIGIN}/realms/pios` });

  ({ dist: DIST, server: site, origin: SITE_ORIGIN } = await serveProductionBuild(REPO, {
    PIOS_API_BASE_URL: `${API_ORIGIN}/api/v1`,
    PIOS_OIDC_ISSUER: `${IDP_ORIGIN}/realms/pios`,
    PIOS_OIDC_CLIENT_ID: 'pios-portal',
    PIOS_REQUEST_TIMEOUT_MS: '1500',
  }));

  browser = await launchChromium();
});

after(async () => {
  if (browser) await browser.close();
  for (const s of [idp, api, site]) if (s) s.close();
});

async function newPage() {
  const ctx = await browser.newContext({ viewport: IPHONE, ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  return { ctx, page, errors };
}

/** Signs in for real: app -> IdP form -> submit -> back to the app.
 *
 * `settle` waits past the loading view to the terminal state. Pass false when
 * the point of the test IS the first paint (e.g. a backend that never answers). */
async function signIn(page, { settle = true } = {}) {
  await page.goto(`${SITE_ORIGIN}/`);
  await page.waitForSelector('#loginBtn', { state: 'visible' });
  await page.click('#loginBtn');
  await page.waitForSelector('#kc-login');
  await page.fill('#username', 'pios-test');
  await page.fill('#password', 'whatever');
  await page.click('#kc-login');
  await page.waitForFunction(() => {
    const m = document.querySelector('#main');
    return m && m.innerText.trim().length > 0;
  }, { timeout: 20000 });
  if (settle) {
    await page.waitForFunction(() => !document.querySelector('#main [aria-busy="true"]'), { timeout: 20000 });
  }
}

/** Signs out and waits for the provider's redirect to land back on the app.
 *
 * logout() navigates to the provider's end-session endpoint, which redirects
 * back here. Issuing our own goto() while that is in flight aborts it with
 * "interrupted by another navigation", so wait for it rather than race it. */
async function signOutAndLand(page) {
  await page.evaluate(() => window.PIOS_AUTH.logout());
  await page.waitForURL(u => u.toString().startsWith(SITE_ORIGIN), { timeout: 25000 });
  await page.waitForSelector('#loginScreen', { state: 'visible', timeout: 25000 });
}

/** Waits for a bootstrap cycle to start AND finish.
 *
 * Checking only for the absence of the busy flag races the click that triggers
 * it: if the check runs first, the PREVIOUS render still satisfies it and the
 * assertion reads stale content. Wait for busy to appear, then to clear. */
async function awaitReload(page) {
  await page.waitForSelector('#main [aria-busy="true"]', { timeout: 10000 }).catch(() => {});
  await page.waitForFunction(() => !document.querySelector('#main [aria-busy="true"]'), { timeout: 25000 });
}

/** What the user can actually see. */
const view = page => page.evaluate(() => {
  const vis = s => { const e = document.querySelector(s); return !!e && getComputedStyle(e).display !== 'none' && e.getClientRects().length > 0; };
  return {
    loginVisible: vis('#loginScreen'),
    navItems: document.querySelectorAll('#nav .nav-item').length,
    navText: document.querySelector('#nav')?.innerText.trim() || '',
    mainText: document.querySelector('#main')?.innerText.trim() || '',
    demoVisible: vis('#demoNotice'),
    userRole: document.querySelector('#userRole')?.textContent || '',
    hasRetry: !!document.querySelector('#retryBoot'),
    hasReAuth: !!document.querySelector('#reAuth'),
  };
});

// ================================================== SCENARIO 1 - authorized user

describe('scenario 1: an authorized user gets a usable application', () => {
  test('navigation and dashboard are visible and populated', async () => {
    resetBackend();
    const { ctx, page, errors } = await newPage();
    try {
      await signIn(page);
      const v = await view(page);
      assert.equal(v.loginVisible, false, 'the login screen is still covering the app');
      assert.ok(v.navItems >= 10, `navigation shows ${v.navItems} items - the drawer is effectively empty`);
      assert.ok(v.navText.includes('لوحة التشغيل'), 'navigation has no readable operational entries');
      assert.ok(v.mainText.length > 100, `main content is ${v.mainText.length} chars - effectively blank`);
      assert.ok(/جاهزية|Evidence readiness/.test(v.mainText), 'the dashboard did not render real KPI content');
      assert.equal(v.userRole, 'AccreditationLead', 'the user chip must show the session role');
      assert.equal(v.demoVisible, false, 'a live authorized session must not show the demo banner');
      assert.deepEqual(errors, [], 'uncaught JavaScript errors during sign-in');
    } finally { await ctx.close(); }
  });

  test('the dashboard reflects backend data, not demo data', async () => {
    resetBackend();
    const { ctx, page } = await newPage();
    try {
      await signIn(page);
      const v = await view(page);
      assert.ok(v.mainText.includes('71'), 'the readiness score from the backend is not on screen');
    } finally { await ctx.close(); }
  });
});

// ================================ SCENARIO 2 - authenticated, no application role

describe('scenario 2: authenticated without a PIOS role', () => {
  test('an explicit access message appears - never a blank page or demo data', async () => {
    resetBackend(); backend.roles = [];      // only Keycloak's default roles
    const { ctx, page, errors } = await newPage();
    try {
      await signIn(page);
      const v = await view(page);
      assert.ok(v.mainText.length > 50, 'a user without a role got an empty page');
      assert.ok(/لا توجد صلاحية|no platform role/i.test(v.mainText), `expected an access message, got: ${v.mainText.slice(0, 120)}`);
      assert.ok(v.mainText.includes('AccreditationLead'), 'the message must name the roles that would grant access');
      assert.equal(v.demoVisible, false, 'demo data must never stand in for a real rejected session');
      assert.ok(!/جاهزية الأدلة\n?\s*\d+%/.test(v.mainText), 'demo KPI figures are being shown to an unauthorized user');
      assert.equal(v.userRole, '', 'the chip must not claim a role the user does not have');
      assert.deepEqual(errors, [], 'uncaught JavaScript errors');
    } finally { await ctx.close(); }
  });

  test('navigation still renders, so the app is not a dead end', async () => {
    resetBackend(); backend.roles = [];
    const { ctx, page } = await newPage();
    try {
      await signIn(page);
      const v = await view(page);
      assert.ok(v.navItems >= 10, 'the shell must remain navigable');
      assert.equal(v.hasRetry, true, 'the user needs a way to retry after a role is granted');
    } finally { await ctx.close(); }
  });
});

// ========================================= SCENARIOS 3/4/5 - backend rejections

describe('scenario 3/4: 401, 403 and 503 are three different answers', () => {
  /* The Sprint 23.8 defect: all three collapsed into "no permission". A 401
   * told a user with a perfectly good role that they lacked permission, which
   * is both wrong and unactionable - the fix is to sign in again, not to be
   * granted something they already have. */

  test('401 says the SESSION is the problem, not the permissions', async () => {
    resetBackend(); backend.mode = '401';
    const { ctx, page, errors } = await newPage();
    try {
      await signIn(page);
      const v = await view(page);
      assert.ok(/انتهت|expired|Session/i.test(v.mainText),
        `a 401 must be reported as a session problem, got: ${v.mainText.slice(0, 140)}`);
      assert.ok(!/لا توجد صلاحية|no platform role/i.test(v.mainText),
        'a 401 must NOT be reported as missing permission - that is unactionable and false');
      assert.equal(v.hasReAuth, true, 'a 401 must offer signing in again');
      assert.equal(v.demoVisible, false);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('403 says the ROLE is the problem, and names the roles', async () => {
    resetBackend(); backend.mode = '403';
    const { ctx, page, errors } = await newPage();
    try {
      await signIn(page);
      const v = await view(page);
      assert.ok(/لا توجد صلاحية|no platform role/i.test(v.mainText),
        `a 403 must be reported as an authorization problem, got: ${v.mainText.slice(0, 140)}`);
      assert.ok(v.mainText.includes('AccreditationLead'), 'it must name the roles that grant access');
      assert.ok(!/انتهت صلاحية جلستك|Your session has expired/i.test(v.mainText),
        'a 403 must not be described as an expired session');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('503 blames the service, not the account', async () => {
    resetBackend(); backend.mode = '503';
    const { ctx, page, errors } = await newPage();
    try {
      await signIn(page);
      const v = await view(page);
      assert.ok(/غير متاح|unavailable/i.test(v.mainText),
        `a 503 must be reported as a service outage, got: ${v.mainText.slice(0, 140)}`);
      assert.ok(!/لا توجد صلاحية|no platform role/i.test(v.mainText),
        'a service outage must never be described as a permissions problem');
      assert.equal(v.hasRetry, true, 'an outage must be retryable');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

describe('scenario 5: bootstrap failure', () => {
  test('a 500 shows an actionable, retryable error', async () => {
    resetBackend(); backend.mode = '500';
    const { ctx, page, errors } = await newPage();
    try {
      await signIn(page);
      const v = await view(page);
      assert.ok(/تعذّر|could not|failed/i.test(v.mainText), `expected an error state, got: ${v.mainText.slice(0, 120)}`);
      assert.equal(v.hasRetry, true, 'an error state must offer a retry');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a backend that never answers times out into a visible state', async () => {
    resetBackend(); backend.mode = 'hang';
    const { ctx, page, errors } = await newPage();
    try {
      await signIn(page, { settle: false });   // stop at the first paint
      const loading = await view(page);
      assert.ok(loading.navItems >= 10, 'navigation must paint before the data arrives');
      assert.ok(loading.mainText.length > 0, 'the first paint must never be blank');

      await page.waitForFunction(() => /تعذّر|could not/i.test(document.querySelector('#main')?.innerText || ''), { timeout: 20000 });
      const v = await view(page);
      assert.equal(v.hasRetry, true, 'a stalled backend must end in a retryable state');
      assert.equal(v.demoVisible, false);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

// ============================================== SCENARIO 6 - legitimately empty

describe('scenario 6: authorized but no data yet', () => {
  test('an empty dataset renders an empty state, not an empty page', async () => {
    resetBackend(); backend.mode = 'empty';
    const { ctx, page, errors } = await newPage();
    try {
      await signIn(page);
      const v = await view(page);
      assert.ok(v.mainText.length > 100, 'an authorized user with no data got a blank page');
      assert.ok(v.navItems >= 10);
      assert.equal(v.demoVisible, false);
      assert.deepEqual(errors, [], 'empty collections must not throw');
    } finally { await ctx.close(); }
  });
});

// ================================================ SCENARIO 7/8 - refresh, logout

describe('scenario 7: reload after signing in', () => {
  test('the session and a usable UI survive a reload', async () => {
    resetBackend();
    const { ctx, page } = await newPage();
    try {
      await signIn(page);
      await page.reload();
      await page.waitForFunction(() => (document.querySelector('#main')?.innerText || '').length > 100, { timeout: 20000 });
      const v = await view(page);
      assert.equal(v.loginVisible, false, 'a reload bounced the user back to sign-in');
      assert.ok(v.navItems >= 10);
      assert.equal(v.userRole, 'AccreditationLead');
    } finally { await ctx.close(); }
  });
});

describe('scenario 8: logout', () => {
  test('signing out clears the session and returns to the login screen', async () => {
    resetBackend();
    const { ctx, page } = await newPage();
    try {
      await signIn(page);
      await signOutAndLand(page);
      const cleared = await page.evaluate(() => ({
        tokens: sessionStorage.getItem('pios-oidc-tokens'),
        tx: sessionStorage.getItem('pios-oidc-tx') || localStorage.getItem('pios-oidc-tx'),
        authed: window.PIOS_AUTH.isAuthenticated(),
      }));
      assert.equal(cleared.tokens, null, 'tokens survived sign-out');
      assert.equal(cleared.tx, null, 'an in-flight transaction survived sign-out');
      assert.equal(cleared.authed, false);
    } finally { await ctx.close(); }
  });
});

// ================================================= SCENARIO 9 - mobile viewport

describe('scenario 9: iPhone-class viewport', () => {
  test('the drawer opens and shows usable entries at 390x844', async () => {
    resetBackend();
    const { ctx, page } = await newPage();
    try {
      await signIn(page);
      await page.click('#menuBtn');
      const drawer = await page.evaluate(() => {
        const s = document.querySelector('.sidebar');
        const items = [...document.querySelectorAll('#nav .nav-item')];
        const first = items[0]?.getBoundingClientRect();
        return {
          open: s.classList.contains('open'),
          items: items.length,
          firstItemVisible: !!first && first.width > 0 && first.height > 0,
          firstItemText: items[0]?.innerText.trim() || '',
        };
      });
      assert.equal(drawer.open, true, 'the drawer did not open');
      assert.ok(drawer.items >= 10, `the drawer shows ${drawer.items} entries`);
      assert.equal(drawer.firstItemVisible, true, 'drawer entries have no rendered box - invisible to the user');
      assert.ok(drawer.firstItemText.length > 0, 'drawer entries have no label');
    } finally { await ctx.close(); }
  });
});

// ============================================ production artifact, not source

describe('the production artifact itself', () => {
  test('config carries the real endpoints and no secret', () => {
    const cfg = readFileSync(join(DIST, 'config.js'), 'utf8');
    assert.match(cfg, /issuer: "https:\/\/127\.0\.0\.1:\d+\/realms\/pios"/);
    assert.match(cfg, /clientId: "pios-portal"/);
    assert.match(cfg, /requestTimeoutMs: \d+/, 'the bootstrap timeout must be baked into config');
    assert.ok(!/client_?secret/i.test(cfg), 'no client secret may reach the bundle');
    assert.ok(!/dev:portal-user/.test(cfg), 'no development token may be published');
  });

  test('the login overlay still hides when hidden (Sprint 23.6 guard)', () => {
    const css = readFileSync(join(DIST, 'styles.css'), 'utf8');
    assert.match(css, /\.login-screen\[hidden\]\s*\{\s*display:\s*none/, 'the 23.6 CSS fix is missing from the build');
  });
});


// ======================== a role granted AFTER sign-in (Sprint 23.8 section G)

describe('a role granted after the session began', () => {
  test('the existing token does not gain the role, and a fresh sign-in does', async () => {
    resetBackend(); backend.roles = [];          // signed in before any grant
    const { ctx, page } = await newPage();
    try {
      await signIn(page);
      let v = await view(page);
      assert.ok(/لا توجد صلاحية|no platform role/i.test(v.mainText),
        'a user with no role must be told so');

      // An administrator grants the role now.
      backend.roles = ['AccreditationLead'];

      // The token already in the browser predates the grant. Retrying with it
      // must NOT suddenly work - claims are fixed at issue time.
      await page.click('#retryBoot');
      await awaitReload(page);
      v = await view(page);
      assert.ok(/لا توجد صلاحية|no platform role/i.test(v.mainText),
        'an old token must not acquire a role it was never issued with');

      // A full sign-out and fresh sign-in mints a token that carries it.
      await signOutAndLand(page);
      await signIn(page);
      v = await view(page);
      assert.equal(v.userRole, 'AccreditationLead', 'a fresh sign-in must carry the new role');
      assert.ok(v.mainText.length > 100 && !/لا توجد صلاحية/.test(v.mainText),
        'the dashboard must be usable after re-authenticating with the granted role');
    } finally { await ctx.close(); }
  });
});

// ============ Keycloak's own callback errors (Sprint 23.8 section H)

describe('the identity provider returns an error on the callback', () => {
  test('authentication_expired is reported and a new attempt is possible', async () => {
    resetBackend(); backend.idpError = 'authentication_expired';
    const { ctx, page, errors } = await newPage();
    try {
      await page.goto(`${SITE_ORIGIN}/`);
      await page.waitForSelector('#loginBtn', { state: 'visible' });
      await page.click('#loginBtn');
      await page.waitForSelector('#kc-login');
      await page.fill('#username', 'pios-test');
      await page.fill('#password', 'whatever');
      await page.click('#kc-login');
      await page.waitForSelector('#loginScreen', { state: 'visible', timeout: 20000 });

      const box = await page.evaluate(() => ({
        errVisible: getComputedStyle(document.querySelector('#loginError')).display !== 'none',
        errText: document.querySelector('#loginError')?.textContent || '',
        btnDisabled: document.querySelector('#loginBtn')?.disabled,
        url: location.href,
        authed: window.PIOS_AUTH.isAuthenticated(),
        tx: sessionStorage.getItem('pios-oidc-tx') || localStorage.getItem('pios-oidc-tx'),
      }));
      assert.equal(box.errVisible, true, 'the provider error must be shown, not swallowed');
      assert.match(box.errText, /authentication_expired/);
      assert.equal(box.btnDisabled, false, 'the user must be able to try again');
      assert.equal(box.authed, false, 'a failed callback must not produce a session');
      assert.equal(box.tx, null, 'the transaction must be cleared after a failed callback');
      assert.ok(!box.url.includes('error='), 'the error must be stripped from the address bar');
      assert.deepEqual(errors, [], 'no uncaught errors on a provider failure');

      // And a genuine retry still works.
      backend.idpError = null;
      await signIn(page);
      assert.equal((await view(page)).userRole, 'AccreditationLead');
    } finally { await ctx.close(); }
  });
});
