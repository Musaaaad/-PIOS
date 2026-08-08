// Sprint 23.6 - end-to-end authentication through a real browser.
//
// Every other suite in this directory stops at a seam: jsdom, or a stubbed
// fetch. This one drives a real Chromium against the real built artifact and a
// controlled identity provider that implements the protocol properly:
//
//   * /auth  renders a login form and checks credentials against a known
//            account, so a WRONG PASSWORD is a distinct, observable outcome
//            from a broken callback - the two were being conflated
//   * /token verifies client_id, redirect_uri, the single-use code AND the
//            PKCE S256 code_verifier against the stored challenge, then issues
//            a genuinely RS256-signed JWT
//   * /certs publishes the matching JWKS
//   * the API verifies that JWT's signature, issuer and audience before
//            answering, so a token the browser obtained is proven acceptable
//
// What this does NOT cover, stated plainly: it is not the live Keycloak and not
// the live Render deployment, and Chromium is not WebKit - only Chromium is
// available in this environment, so nothing here reproduces iOS Safari
// behaviour. See the "manual runtime verification" notes in the PR.

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, existsSync, mkdtempSync } from 'node:fs';
import { createServer } from 'node:https';
import { execFileSync as _exec } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, resolve, dirname, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash, generateKeyPairSync, createSign, createVerify, randomUUID } from 'node:crypto';

// The harness runs over HTTPS on purpose. The published site carries
// `connect-src 'self' https:` (render.yaml header + the meta tag injected by
// build_frontend.sh), so an http:// identity provider would be blocked by the
// app's own CSP - a test artifact that would hide real behaviour. Serving TLS
// keeps the production CSP genuinely in force during the test.
const TLS = (() => {
  const dir = mkdtempSync(join(tmpdir(), 'pios-tls-'));
  const key = join(dir, 'k.pem'), cert = join(dir, 'c.pem');
  _exec('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key,
    '-out', cert, '-days', '2', '-subj', '/CN=127.0.0.1',
    '-addext', 'subjectAltName=IP:127.0.0.1,DNS:localhost'], { stdio: 'pipe' });
  return { key: readFileSync(key), cert: readFileSync(cert) };
})();
import { chromium } from 'playwright';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

// The one account that exists in this controlled realm.
const USER = { username: 'pilot.lead', password: 'correct-horse-battery', sub: 'f1e2d3c4-turaif-pilot' };
const ROLES = ['AccreditationLead', 'MedicationSafety'];
const AUDIENCE = 'pios-api';

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };
const b64u = b => Buffer.from(b).toString('base64url');

let DIST, browser, idp, api, site, IDP_ORIGIN, API_ORIGIN, SITE_ORIGIN, KEY, JWKS;
const issued = new Map();   // code -> {challenge, redirect_uri, client_id}
let apiCalls = [];

function jwt(claims, { kid = 'e2e' } = {}) {
  const header = b64u(JSON.stringify({ alg: 'RS256', typ: 'JWT', kid }));
  const now = Math.floor(Date.now() / 1000);
  const payload = b64u(JSON.stringify({
    sub: USER.sub, iss: `${IDP_ORIGIN}/realms/pios`, aud: AUDIENCE,
    iat: now, exp: now + 300, roles: ROLES, sites: ['TGH'],
    preferred_username: USER.username, name: 'قائد الاعتماد', ...claims,
  }));
  const sig = createSign('RSA-SHA256').update(`${header}.${payload}`).end()
    .sign(KEY.privateKey).toString('base64url');
  return `${header}.${payload}.${sig}`;
}

/** Verifies a bearer token the way the real backend does: sig + iss + aud. */
function verify(token) {
  const [h, p, s] = String(token || '').split('.');
  if (!h || !p || !s) return null;
  const ok = createVerify('RSA-SHA256').update(`${h}.${p}`).end()
    .verify(KEY.publicKey, Buffer.from(s, 'base64url'));
  if (!ok) return null;
  const claims = JSON.parse(Buffer.from(p, 'base64url').toString());
  if (claims.iss !== `${IDP_ORIGIN}/realms/pios`) return null;
  if (claims.aud !== AUDIENCE) return null;
  if (claims.exp * 1000 < Date.now()) return null;
  return claims;
}

const listen = (handler) => new Promise(res => {
  const s = createServer(TLS, handler);
  s.listen(0, '127.0.0.1', () => res({ s, origin: `https://127.0.0.1:${s.address().port}` }));
});

const body = req => new Promise(r => { let b = ''; req.on('data', c => b += c); req.on('end', () => r(b)); });
const send = (res, code, type, payload, extra = {}) => {
  res.writeHead(code, { 'Content-Type': type, 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', ...extra });
  res.end(payload);
};

before(async () => {
  KEY = generateKeyPairSync('rsa', { modulusLength: 2048 });
  const jwk = KEY.publicKey.export({ format: 'jwk' });
  JWKS = { keys: [{ ...jwk, kid: 'e2e', use: 'sig', alg: 'RS256' }] };

  // ---- controlled identity provider ------------------------------------
  ({ s: idp, origin: IDP_ORIGIN } = await listen(async (req, res) => {
    const url = new URL(req.url, IDP_ORIGIN);
    if (url.pathname.endsWith('/openid-connect/certs')) return send(res, 200, 'application/json', JSON.stringify(JWKS));

    if (req.method === 'GET' && url.pathname.endsWith('/openid-connect/auth')) {
      const q = url.searchParams;
      // A real IdP renders a form; the browser must actually submit it.
      return send(res, 200, 'text/html; charset=utf-8', `<!doctype html><meta charset=utf-8>
        <form method="POST" action="${url.pathname}?${q.toString()}">
          <input name="username" id="username"><input name="password" id="password" type="password">
          <button id="kc-login" type="submit">Sign In</button>
        </form>`);
    }

    if (req.method === 'POST' && url.pathname.endsWith('/openid-connect/auth')) {
      const form = new URLSearchParams(await body(req));
      const q = url.searchParams;
      if (form.get('username') !== USER.username || form.get('password') !== USER.password) {
        // The credential failure surfaces HERE, on the IdP, exactly as Keycloak
        // does - it never becomes a callback error in the app.
        return send(res, 200, 'text/html; charset=utf-8',
          `<!doctype html><meta charset=utf-8><p id="kc-error">Invalid username or password.</p>`);
      }
      const code = randomUUID();
      issued.set(code, {
        challenge: q.get('code_challenge'),
        redirect_uri: q.get('redirect_uri'),
        client_id: q.get('client_id'),
      });
      const back = new URL(q.get('redirect_uri'));
      back.searchParams.set('code', code);
      back.searchParams.set('state', q.get('state'));
      return send(res, 302, 'text/plain', '', { Location: back.toString() });
    }

    if (url.pathname.endsWith('/openid-connect/token')) {
      const form = new URLSearchParams(await body(req));
      if (form.get('grant_type') === 'refresh_token') {
        if (form.get('refresh_token') !== 'refresh-1') return send(res, 400, 'application/json', JSON.stringify({ error: 'invalid_grant' }));
        return send(res, 200, 'application/json', JSON.stringify({
          access_token: jwt({}), refresh_token: 'refresh-1', id_token: jwt({}), expires_in: 300, token_type: 'Bearer',
        }));
      }
      const code = form.get('code');
      const rec = issued.get(code);
      if (!rec) return send(res, 400, 'application/json', JSON.stringify({ error: 'invalid_grant', error_description: 'unknown or reused code' }));
      issued.delete(code);   // single use, like Keycloak
      if (form.get('client_id') !== rec.client_id) return send(res, 400, 'application/json', JSON.stringify({ error: 'invalid_client' }));
      if (form.get('redirect_uri') !== rec.redirect_uri) return send(res, 400, 'application/json', JSON.stringify({ error: 'invalid_grant', error_description: 'redirect_uri mismatch' }));
      // Real PKCE S256 verification.
      const derived = createHash('sha256').update(form.get('code_verifier') || '').digest('base64url');
      if (derived !== rec.challenge) return send(res, 400, 'application/json', JSON.stringify({ error: 'invalid_grant', error_description: 'PKCE verification failed' }));
      return send(res, 200, 'application/json', JSON.stringify({
        access_token: jwt({}), refresh_token: 'refresh-1', id_token: jwt({}), expires_in: 300, token_type: 'Bearer',
      }));
    }
    if (url.pathname.endsWith('/openid-connect/logout')) return send(res, 302, 'text/plain', '', { Location: SITE_ORIGIN + '/' });
    send(res, 404, 'application/json', '{}');
  }));

  // ---- API that actually validates the token ---------------------------
  ({ s: api, origin: API_ORIGIN } = await listen(async (req, res) => {
    if (req.method === 'OPTIONS') return send(res, 204, 'text/plain', '');
    const url = new URL(req.url, API_ORIGIN);
    const claims = verify((req.headers.authorization || '').replace(/^Bearer /, ''));
    apiCalls.push({ path: url.pathname, authorized: !!claims });
    if (!claims) return send(res, 401, 'application/json', JSON.stringify({ detail: 'not authenticated' }));
    const p = url.pathname;
    if (p.endsWith('/identity/me')) return send(res, 200, 'application/json', JSON.stringify({
      user_id: claims.sub, display_name: claims.name, roles: claims.roles, site_codes: claims.sites, auth_source: 'oidc',
    }));
    if (p.endsWith('/dashboard/overview')) return send(res, 200, 'application/json', JSON.stringify({
      site: { code: 'TGH' }, readiness: { score: 71, accepted: 5, partial: 2, missing: 1, esr_status: {} },
      findings: { by_severity: { P0: 1 } }, evidence: { overdue_requests: 2 }, capas: { overdue: 1 }, notifications: { unread: 3 },
    }));
    if (p.endsWith('/dashboard/standards')) return send(res, 200, 'application/json', JSON.stringify({ standards: [] }));
    if (p.endsWith('/worklists/my')) return send(res, 200, 'application/json', JSON.stringify({ items: [] }));
    send(res, 200, 'application/json', JSON.stringify([]));
  }));

  // ---- the real built site ---------------------------------------------
  DIST = mkdtempSync(join(tmpdir(), 'pios-e2e-'));
  execFileSync('bash', [join(REPO, 'deploy', 'render', 'build_frontend.sh')], {
    env: {
      ...process.env, OUT_DIR: DIST,
      PIOS_API_BASE_URL: `${API_ORIGIN}/api/v1`,
      PIOS_OIDC_ISSUER: `${IDP_ORIGIN}/realms/pios`,
      PIOS_OIDC_CLIENT_ID: 'pios-portal',
    },
    stdio: 'pipe',
  });
  ({ s: site, origin: SITE_ORIGIN } = await listen((req, res) => {
    const p = decodeURIComponent(new URL(req.url, SITE_ORIGIN).pathname);
    const f = join(DIST, p === '/' ? 'index.html' : p);
    const target = existsSync(f) && p !== '/' ? f : join(DIST, 'index.html');
    send(res, 200, TYPES[extname(target)] || 'text/plain', readFileSync(target));
  }));

  browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
});

after(async () => {
  if (browser) await browser.close();
  for (const s of [idp, api, site]) if (s) s.close();
});

async function newPage() {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  const stages = [];
  page.on('console', m => { const t = m.text(); if (t.startsWith('[pios-auth]')) stages.push(t); });
  return { ctx, page, stages };
}

/** Walks the whole journey: open -> login -> IdP form -> back -> dashboard. */
async function signIn(page, { username = USER.username, password = USER.password } = {}) {
  await page.goto(`${SITE_ORIGIN}/`);
  await page.waitForSelector('#loginBtn', { state: 'visible' });
  await page.click('#loginBtn');
  await page.waitForSelector('#kc-login');
  await page.fill('#username', username);
  await page.fill('#password', password);
  await page.click('#kc-login');
}

// ================================================== the full journey, in a browser

describe('end-to-end sign-in through a real browser', () => {
  test('a correct credential completes the whole journey', async () => {
    apiCalls = [];
    const { ctx, page } = await newPage();
    try {
      await signIn(page);
      await page.waitForFunction(() => document.querySelector('#userRole')?.textContent?.length > 0, { timeout: 15000 });

      // 12/13/15: session established, API called with a valid token, UI rendered.
      assert.equal(await page.textContent('#userRole'), 'AccreditationLead');
      assert.equal(await page.isVisible('#loginScreen'), false, 'the login screen must be gone');
      const main = await page.innerHTML('#main');
      assert.ok(main.length > 200, 'the dashboard did not render');

      const me = apiCalls.find(c => c.path.endsWith('/identity/me'));
      assert.ok(me && me.authorized, 'the API was not called with a token it accepts');
      assert.ok(!apiCalls.some(c => !c.authorized), 'some API call went out unauthenticated');

      // 11: tokens are in sessionStorage, and NOT in localStorage.
      const store = await page.evaluate(() => ({
        session: !!sessionStorage.getItem('pios-oidc-tokens'),
        local: !!localStorage.getItem('pios-oidc-tokens'),
        tx: sessionStorage.getItem('pios-oidc-tx') || localStorage.getItem('pios-oidc-tx'),
      }));
      assert.equal(store.session, true, 'no token was stored');
      assert.equal(store.local, false, 'tokens must never reach localStorage');
      assert.equal(store.tx, null, 'the transaction must be erased after success');

      // 7: the address bar is clean.
      assert.ok(!page.url().includes('code='), `code left in the URL: ${page.url()}`);
      assert.ok(!page.url().includes('state='), 'state left in the URL');
    } finally { await ctx.close(); }
  });

  test('a reload keeps the user signed in', async () => {
    const { ctx, page } = await newPage();
    try {
      await signIn(page);
      await page.waitForFunction(() => document.querySelector('#userRole')?.textContent?.length > 0, { timeout: 15000 });
      await page.reload();
      await page.waitForFunction(() => document.querySelector('#userRole')?.textContent?.length > 0, { timeout: 15000 });
      assert.equal(await page.isVisible('#loginScreen'), false, 'a reload bounced the user back to sign-in');
      assert.equal(await page.textContent('#userRole'), 'AccreditationLead');
    } finally { await ctx.close(); }
  });

  test('an aged-out access token is refreshed rather than dropped', async () => {
    const { ctx, page } = await newPage();
    try {
      await signIn(page);
      await page.waitForFunction(() => document.querySelector('#userRole')?.textContent?.length > 0, { timeout: 15000 });
      // Age the access token out, exactly as time would.
      await page.evaluate(() => {
        const t = JSON.parse(sessionStorage.getItem('pios-oidc-tokens'));
        t.expires_at = Date.now() - 1000;
        sessionStorage.setItem('pios-oidc-tokens', JSON.stringify(t));
      });
      await page.reload();
      await page.waitForFunction(() => document.querySelector('#userRole')?.textContent?.length > 0, { timeout: 15000 });
      assert.equal(await page.isVisible('#loginScreen'), false,
        'an expired access token sent the user back to sign-in despite a valid refresh token');
    } finally { await ctx.close(); }
  });
});

// ====================================== credential failure is NOT callback failure

describe('a wrong password is distinguishable from a broken callback', () => {
  test('the identity provider rejects it and the app is never reached', async () => {
    const { ctx, page } = await newPage();
    try {
      await signIn(page, { password: 'not-the-password' });
      await page.waitForSelector('#kc-error');
      assert.match(await page.textContent('#kc-error'), /Invalid username or password/);
      // The browser is still on the IdP: no callback, no app error.
      assert.ok(page.url().startsWith(IDP_ORIGIN), `expected to remain on the IdP, at ${page.url()}`);
      assert.ok(!page.url().includes('code='), 'no authorization code may be issued for a bad credential');
    } finally { await ctx.close(); }
  });

  test('an unknown username is rejected the same way', async () => {
    const { ctx, page } = await newPage();
    try {
      await signIn(page, { username: 'admin', password: 'anything' });
      await page.waitForSelector('#kc-error');
      assert.ok(page.url().startsWith(IDP_ORIGIN));
    } finally { await ctx.close(); }
  });
});

// ========================================================= security still holds

describe('security boundaries hold in a real browser', () => {
  test('a forged state is rejected and no code is redeemed', async () => {
    const { ctx, page } = await newPage();
    try {
      await page.goto(`${SITE_ORIGIN}/`);
      await page.waitForSelector('#loginBtn', { state: 'visible' });
      await page.click('#loginBtn');
      await page.waitForSelector('#kc-login');
      // Return to the app with a state the app never issued.
      await page.goto(`${SITE_ORIGIN}/?code=fabricated&state=ATTACKER`);
      await page.waitForSelector('#loginScreen', { state: 'visible' });
      assert.equal(await page.isVisible('#loginScreen'), true);
      const authed = await page.evaluate(() => window.PIOS_AUTH.isAuthenticated());
      assert.equal(authed, false, 'a forged state produced a session');
    } finally { await ctx.close(); }
  });

  test('an expired transaction cannot be redeemed', async () => {
    const { ctx, page } = await newPage();
    try {
      await page.goto(`${SITE_ORIGIN}/`);
      await page.evaluate(() => {
        const tx = JSON.stringify({ state: 'S', verifier: 'v'.repeat(64), ret: '#/dashboard', exp: Date.now() - 1 });
        sessionStorage.setItem('pios-oidc-tx', tx);
        localStorage.setItem('pios-oidc-tx', tx);
      });
      await page.goto(`${SITE_ORIGIN}/?code=c&state=S`);
      await page.waitForSelector('#loginScreen', { state: 'visible' });
      assert.equal(await page.evaluate(() => window.PIOS_AUTH.isAuthenticated()), false);
    } finally { await ctx.close(); }
  });

  test('the sign-in button is usable again after a failed callback', async () => {
    const { ctx, page } = await newPage();
    try {
      await page.goto(`${SITE_ORIGIN}/?code=c&state=NOTHING`);
      await page.waitForSelector('#loginScreen', { state: 'visible' });
      assert.equal(await page.isDisabled('#loginBtn'), false, 'the button was left disabled');
      await page.click('#loginBtn');
      await page.waitForSelector('#kc-login', { timeout: 15000 });
      assert.ok(page.url().startsWith(IDP_ORIGIN), 'the retry did not reach the identity provider');
    } finally { await ctx.close(); }
  });

  test('no secret or token is present in the served bundle', async () => {
    const cfg = readFileSync(join(DIST, 'config.js'), 'utf8');
    assert.ok(!/client_?secret/i.test(cfg));
    assert.ok(!/dev:portal-user/.test(cfg), 'a development token must never be published');
  });
});

// ================================================== observability (Sprint 23.6)

describe('auth stages are observable without leaking secrets', () => {
  test('a successful journey reports its stages in order', async () => {
    const { ctx, page, stages } = await newPage();
    try {
      await signIn(page);
      await page.waitForFunction(() => document.querySelector('#userRole')?.textContent?.length > 0, { timeout: 15000 });
      const seen = stages.join(' ');
      for (const stage of ['CALLBACK_RECEIVED', 'STATE_VALID', 'TOKEN_EXCHANGE_START', 'TOKEN_EXCHANGE_OK', 'SESSION_ESTABLISHED']) {
        assert.ok(seen.includes(stage), `stage ${stage} was never reported; saw: ${seen}`);
      }
    } finally { await ctx.close(); }
  });

  test('stage reporting never contains a token, code or verifier', async () => {
    const { ctx, page, stages } = await newPage();
    try {
      await signIn(page);
      await page.waitForFunction(() => document.querySelector('#userRole')?.textContent?.length > 0, { timeout: 15000 });
      const seen = stages.join(' ');
      for (const secret of ['eyJhbGciOi', 'refresh-1', 'code_verifier', USER.password]) {
        assert.ok(!seen.includes(secret), `diagnostics leaked ${secret}`);
      }
      const last = await page.evaluate(() => window.PIOS_AUTH.lastStage && window.PIOS_AUTH.lastStage());
      // API_AUTH_OK is the final stage: the session is established and then a
      // request is authorised with it.
      assert.equal(last && last.stage, 'API_AUTH_OK');
      assert.ok(!last.error, 'a successful journey must record no error category');
      assert.ok(!JSON.stringify(last).includes('eyJhbGciOi'), 'lastStage() leaked a token');
    } finally { await ctx.close(); }
  });

  test('a failed callback records the stage it failed at', async () => {
    const { ctx, page } = await newPage();
    try {
      await page.goto(`${SITE_ORIGIN}/?code=c&state=NOTHING`);
      await page.waitForSelector('#loginScreen', { state: 'visible' });
      const last = await page.evaluate(() => window.PIOS_AUTH.lastStage());
      assert.equal(last.stage, 'CALLBACK_RECEIVED');
      assert.equal(last.error, 'TRANSACTION_MISSING');
      assert.ok(!('code' in last), 'the authorization code must not be recorded');
    } finally { await ctx.close(); }
  });
});
