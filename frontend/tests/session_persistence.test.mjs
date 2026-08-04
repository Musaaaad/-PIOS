// Sprint 23.4 - why a successful Keycloak sign-in landed back on the
// "الدخول عبر الهوية المؤسسية" screen.
//
// Three defects, all in the repository, none of them the user's password:
//
//   A. app.js startup gated on isAuthenticated() alone and never tried
//      AUTH.refresh(), so once the short-lived access token aged out the next
//      page load sent the user to the login screen while a valid refresh token
//      sat unused in sessionStorage. api() already refreshed on a 401; startup
//      contradicted it.
//
//   B. writeTokens() defaulted a missing expires_in to 60s and accessToken()
//      subtracted a flat 30 000 ms margin. Against a 60s token that is half its
//      life; with no expires_in at all it manufactured a 30-second session.
//
//   C. store.set() swallowed a failed sessionStorage write, so blocked storage
//      surfaced on the return trip as "state mismatch" - a CSRF accusation
//      aimed at a user whose storage was simply unavailable.
//
// These drive the real auth.js and app.js. No Keycloak, no network, no Render.

import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';
import { webcrypto } from 'node:crypto';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const SRC = join(REPO, 'frontend');
const ISSUER = 'https://pios-keycloak.onrender.com/realms/pios';
const TOKEN_URL = `${ISSUER}/protocol/openid-connect/token`;

const read = f => readFileSync(join(SRC, f), 'utf8');

// jsdom defines window.crypto as a non-writable accessor, so a plain
// assignment is silently dropped and crypto.subtle stays undefined.
function inject(w) {
  Object.defineProperty(w, 'crypto', { configurable: true, value: webcrypto });
  w.TextEncoder = TextEncoder;
}

/** A window with auth.js loaded against a given config. */
function authWindow({ url = 'https://pios-frontend.onrender.com/', storage = 'ok' } = {}) {
  const dom = new JSDOM('<!doctype html><body></body>', { url, runScripts: 'outside-only' });
  const w = dom.window;
  inject(w);

  if (storage === 'blocked') {
    // iOS Safari in Private Browsing / with site data blocked: setItem throws.
    Object.defineProperty(w, 'sessionStorage', {
      configurable: true,
      value: {
        getItem: () => null,
        setItem() { throw new Error('QuotaExceededError'); },
        removeItem: () => {},
      },
    });
  }

  w.eval(`window.PIOS_CONFIG=${JSON.stringify({
    apiBase: 'https://pios-api.onrender.com/api/v1',
    demoMode: false,
    oidc: { issuer: ISSUER, clientId: 'pios-portal', scope: 'openid profile email' },
  })};`);
  w.eval(read('auth.js'));
  return { w, auth: w.PIOS_AUTH };
}

const tokenResponse = (over = {}) => ({
  access_token: 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1In0.sig',
  refresh_token: 'refresh-token-value',
  id_token: 'id-token-value',
  token_type: 'Bearer',
  expires_in: 60,
  ...over,
});

// =============================================================== defect B

describe('access-token lifetime accounting', () => {
  test('a 60s token is usable well past the first 30 seconds', () => {
    const { auth } = authWindow();
    auth._internals.writeTokens(tokenResponse({ expires_in: 60 }));
    const stored = auth._internals.readTokens();

    // The margin must not exceed half the lifetime.
    assert.equal(stored.skew_ms, 30000, 'half of 60s is 30s, so the full margin applies');
    const usableFor = stored.expires_at - stored.skew_ms - Date.now();
    assert.ok(usableFor > 25000,
      `a 60s token must stay usable for ~30s, got ${usableFor}ms`);
    assert.equal(auth.isAuthenticated(), true);
  });

  test('a very short token keeps at least half its life', () => {
    const { auth } = authWindow();
    auth._internals.writeTokens(tokenResponse({ expires_in: 20 }));
    const stored = auth._internals.readTokens();
    assert.equal(stored.skew_ms, 10000,
      'the margin must scale down with the token, not swallow it whole');
    assert.equal(auth.isAuthenticated(), true,
      'a freshly issued 20s token was treated as already expired');
  });

  test('a missing expires_in does not manufacture a 30-second session', () => {
    const { auth } = authWindow();
    const t = tokenResponse();
    delete t.expires_in;
    auth._internals.writeTokens(t);
    const stored = auth._internals.readTokens();
    assert.equal(stored.expires_at, undefined,
      'no expiry may be invented when the provider did not send one');
    assert.equal(auth.isAuthenticated(), true);
  });

  test('a genuinely expired token is still rejected', () => {
    const { w, auth } = authWindow();
    // Write a session whose expiry is already in the past, bypassing
    // writeTokens so the stored expiry is exactly what we intend to test.
    w.sessionStorage.setItem('pios-oidc-tokens', JSON.stringify({
      ...tokenResponse(), expires_at: Date.now() - 1000, skew_ms: 0,
    }));
    assert.equal(auth.accessToken(), null, 'an expired token must never be sent');
    assert.equal(auth.isAuthenticated(), false,
      'loosening the margin must not resurrect genuinely dead tokens');
  });
});

// =============================================================== defect C

describe('blocked browser storage is reported honestly', () => {
  test('login() refuses to leave rather than guaranteeing a failed return', async () => {
    const { auth } = authWindow({ storage: 'blocked' });
    let navigated = null;
    auth.setNavigator(u => { navigated = u; });

    await assert.rejects(() => auth.login('#/dashboard'), err => {
      assert.match(err.message, /storage|sessionStorage/i);
      return true;
    });
    assert.equal(navigated, null,
      'the app must not send the user to Keycloak when the return trip cannot work');
  });

  test('lost state is not reported as a CSRF mismatch', async () => {
    const { auth } = authWindow({ url: 'https://pios-frontend.onrender.com/?code=c&state=s' });
    // Nothing stored: the record vanished between the two page loads.
    await assert.rejects(() => auth.completeLogin(), err => {
      assert.ok(!/state mismatch/.test(err.message),
        'a user with blocked storage must not be told their sign-in looked like CSRF');
      assert.match(err.message, /storage|تخزين/i);
      return true;
    });
  });

  test('a genuinely different state is still rejected as a mismatch', async () => {
    const { w, auth } = authWindow({ url: 'https://pios-frontend.onrender.com/?code=c&state=FORGED' });
    w.sessionStorage.setItem('pios-oidc-state', 'issued');
    w.sessionStorage.setItem('pios-oidc-verifier', 'v'.repeat(64));
    await assert.rejects(() => auth.completeLogin(), /state mismatch/,
      'CSRF defence must remain intact');
  });
});

// =============================================================== defect A

describe('startup renews the session instead of bouncing to login', () => {
  /** Boots app.js over the real markup with a session already in storage. */
  async function boot({ tokens, refreshOk = true }) {
    const dom = new JSDOM(read('index.html'), {
      url: 'https://pios-frontend.onrender.com/',
      runScripts: 'outside-only',
      pretendToBeVisual: true,
    });
    const w = dom.window;
    inject(w);
    w.eval(`window.PIOS_CONFIG=${JSON.stringify({
      apiBase: 'https://pios-api.onrender.com/api/v1',
      demoMode: false, appVersion: '1.0.0', refreshSeconds: 60,
      oidc: { issuer: ISSUER, clientId: 'pios-portal', scope: 'openid profile email' },
    })};`);
    w.eval(read('auth.js'));
    w.sessionStorage.setItem('pios-oidc-tokens', JSON.stringify(tokens));

    const calls = [];
    w.fetch = async (u, opts = {}) => {
      calls.push(String(u));
      const body = { ok: true, status: 200, headers: { get: () => 'application/json' } };
      if (String(u) === TOKEN_URL) {
        return refreshOk
          ? { ...body, json: async () => tokenResponse({ expires_in: 300 }) }
          : { ok: false, status: 400, headers: { get: () => 'application/json' }, json: async () => ({ error: 'invalid_grant' }) };
      }
      if (String(u).includes('/identity/me')) {
        return { ...body, json: async () => ({ user_id: 'u', roles: ['AccreditationLead'], site_codes: ['TGH'], auth_source: 'oidc' }) };
      }
      if (String(u).includes('/dashboard/overview')) {
        return { ...body, json: async () => ({ site: { code: 'TGH' }, readiness: {}, findings: {}, evidence: {}, capas: {}, notifications: {} }) };
      }
      return { ...body, json: async () => ({ items: [], standards: [] }) };
    };
    w.eval(read('demo-data.js'));
    w.eval(read('app.js'));
    await new Promise(r => setTimeout(r, 80));
    return { w, doc: w.document, calls };
  }

  /** An access token that has aged out, with a good refresh token beside it. */
  const agedOut = () => ({
    ...tokenResponse(),
    expires_at: Date.now() - 5000,
    skew_ms: 30000,
  });

  test('an aged-out access token is renewed, not treated as signed out', async () => {
    const { doc, calls } = await boot({ tokens: agedOut() });
    assert.ok(calls.includes(TOKEN_URL),
      'startup never attempted a refresh - this is the bounce-to-login defect');
    assert.equal(doc.querySelector('#loginScreen').hidden, true,
      'the user was returned to the sign-in screen while holding a valid refresh token');
    assert.equal(doc.body.classList.contains('login-open'), false);
  });

  test('after renewal the dashboard renders the real session', async () => {
    const { doc } = await boot({ tokens: agedOut() });
    assert.equal(doc.querySelector('#userRole').textContent, 'AccreditationLead');
    assert.ok(doc.querySelector('#main').innerHTML.trim().length > 200,
      'the dashboard did not render after a successful renewal');
  });

  test('a still-valid token needs no refresh call', async () => {
    const { calls, doc } = await boot({
      tokens: { ...tokenResponse({ expires_in: 300 }), expires_at: Date.now() + 300000, skew_ms: 30000 },
    });
    assert.ok(!calls.includes(TOKEN_URL), 'a live session must not be refreshed needlessly');
    assert.equal(doc.querySelector('#loginScreen').hidden, true);
  });

  test('when the refresh token really is dead the user is asked to sign in', async () => {
    const { doc, calls } = await boot({ tokens: agedOut(), refreshOk: false });
    assert.ok(calls.includes(TOKEN_URL), 'a refresh must at least be attempted');
    assert.equal(doc.querySelector('#loginScreen').hidden, false,
      'an unrecoverable session must still gate the app - no silent demo data');
  });

  test('with no tokens at all the app still gates correctly', async () => {
    const dom = new JSDOM(read('index.html'), {
      url: 'https://pios-frontend.onrender.com/', runScripts: 'outside-only', pretendToBeVisual: true,
    });
    const w = dom.window;
    inject(w);
    w.eval(`window.PIOS_CONFIG=${JSON.stringify({
      apiBase: 'https://pios-api.onrender.com/api/v1', demoMode: false, appVersion: '1.0.0',
      oidc: { issuer: ISSUER, clientId: 'pios-portal' },
    })};`);
    w.eval(read('auth.js'));
    w.fetch = async () => ({ ok: false, status: 401, headers: { get: () => 'application/json' }, json: async () => ({}) });
    w.eval(read('demo-data.js'));
    w.eval(read('app.js'));
    await new Promise(r => setTimeout(r, 60));
    assert.equal(w.document.querySelector('#loginScreen').hidden, false);
  });
});

// ============================================== no regression to the OIDC path

describe('the authorization-code path is unchanged', () => {
  test('login still uses PKCE S256 and carries no secret', async () => {
    const { auth } = authWindow();
    let url = null;
    auth.setNavigator(u => { url = u; });
    await auth.login('#/dashboard');
    const q = new URL(url).searchParams;
    assert.equal(q.get('response_type'), 'code');
    assert.equal(q.get('code_challenge_method'), 'S256');
    assert.equal(q.get('client_id'), 'pios-portal');
    assert.ok(q.get('code_challenge'));
    assert.ok(!url.includes('client_secret'), 'a public client must never send a secret');
  });

  test('a full callback still authenticates and cleans the address bar', async () => {
    const { w, auth } = authWindow({ url: 'https://pios-frontend.onrender.com/' });
    auth.setNavigator(() => {});
    await auth.login('#/dashboard');
    const st = w.sessionStorage.getItem('pios-oidc-state');

    const dom2 = authWindow({ url: `https://pios-frontend.onrender.com/?code=abc&state=${st}` });
    dom2.w.sessionStorage.setItem('pios-oidc-state', st);
    dom2.w.sessionStorage.setItem('pios-oidc-verifier', w.sessionStorage.getItem('pios-oidc-verifier'));
    dom2.w.fetch = async () => ({
      ok: true, status: 200, headers: { get: () => 'application/json' },
      json: async () => tokenResponse({ expires_in: 300 }),
    });
    assert.equal(await dom2.auth.completeLogin(), true);
    assert.equal(dom2.auth.isAuthenticated(), true);
    assert.ok(!dom2.w.location.search.includes('code='), 'the code was left in the URL');
  });
});
