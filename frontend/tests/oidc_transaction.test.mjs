// Sprint 23.5 - the OIDC transaction must survive the trip to Keycloak.
//
// Live symptom after PR #12 shipped: sign-in succeeded at Keycloak, the browser
// came back with a valid authorization code, and the app showed
//   "Sign-in state was lost before the return from the identity provider"
// on a normal (non-private) iPhone Safari window with cookies allowed.
//
// PR #12 made that case *legible* - it stopped mislabelling it "state mismatch"
// - but it did not make the transaction survive. The state and PKCE verifier
// lived in sessionStorage and nowhere else, so anything that dropped the tab's
// session storage across the cross-origin round trip stranded a sign-in that
// had already succeeded.
//
// Sprint 23.5 keeps the transaction in sessionStorage AND a TTL-bounded
// localStorage copy, consumes it once, and erases both copies whatever the
// outcome. These tests pin that, and pin that none of the CSRF/PKCE checks were
// loosened to get there.
//
// Everything drives the real auth.js / app.js. No Keycloak, no network.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';
import { webcrypto } from 'node:crypto';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, '..');
const ISSUER = 'https://pios-keycloak.onrender.com/realms/pios';
const TOKEN_URL = `${ISSUER}/protocol/openid-connect/token`;
const ORIGIN = 'https://pios-frontend.onrender.com';
const TX_KEY = 'pios-oidc-tx';

const read = f => readFileSync(join(SRC, f), 'utf8');

function inject(w) {
  Object.defineProperty(w, 'crypto', { configurable: true, value: webcrypto });
  w.TextEncoder = TextEncoder;
}

const dead = () => ({
  getItem: () => null,
  setItem() { throw new Error('QuotaExceededError'); },
  removeItem: () => {},
});

/**
 * A window with auth.js loaded.
 *
 * `carry` seeds storage before auth.js runs, which is how a returning page is
 * simulated: whatever the previous page left behind is what this one finds.
 */
function win({ url = `${ORIGIN}/`, carry = {}, kill = [] } = {}) {
  const dom = new JSDOM('<!doctype html><body></body>', { url, runScripts: 'outside-only' });
  const w = dom.window;
  inject(w);
  for (const [k, v] of Object.entries(carry.session || {})) w.sessionStorage.setItem(k, v);
  for (const [k, v] of Object.entries(carry.local || {})) w.localStorage.setItem(k, v);
  for (const which of kill) {
    Object.defineProperty(w, which, { configurable: true, value: dead() });
  }
  w.eval(`window.PIOS_CONFIG=${JSON.stringify({
    apiBase: 'https://pios-api.onrender.com/api/v1',
    demoMode: false,
    oidc: { issuer: ISSUER, clientId: 'pios-portal', scope: 'openid profile email' },
  })};`);
  w.eval(read('auth.js'));
  return { w, auth: w.PIOS_AUTH };
}

const tokens = () => ({
  access_token: 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1In0.sig',
  refresh_token: 'r', id_token: 'i', token_type: 'Bearer', expires_in: 300,
});

const okToken = () => ({
  ok: true, status: 200, headers: { get: () => 'application/json' },
  json: async () => tokens(),
});

/** Runs a real login() and returns what was stored plus the authorize URL. */
async function startLogin(opts = {}) {
  const { w, auth } = win(opts);
  let url = null;
  auth.setNavigator(u => { url = u; });
  await auth.login('#/readiness');
  return {
    w, auth, url,
    session: w.sessionStorage.getItem(TX_KEY),
    local: w.localStorage.getItem(TX_KEY),
    state: new URL(url).searchParams.get('state'),
  };
}

// ===================================================== 1. written before redirect

describe('the transaction is written to both stores before leaving', () => {
  test('login() stores state + verifier in sessionStorage AND localStorage', async () => {
    const { session, local, state } = await startLogin();
    assert.ok(session, 'no session copy was written');
    assert.ok(local, 'no durable copy was written - this is the whole fix');
    const a = JSON.parse(session), b = JSON.parse(local);
    assert.equal(a.state, state, 'the stored state must match the one sent to Keycloak');
    assert.deepEqual(a, b, 'the two copies must be identical');
    assert.ok(a.verifier && a.verifier.length >= 43, 'PKCE verifier missing or too short');
    assert.ok(a.exp > Date.now(), 'the transaction must carry a future expiry');
  });

  test('the stored transaction contains no token, password or secret', async () => {
    const { session } = await startLogin();
    const raw = session.toLowerCase();
    for (const forbidden of ['password', 'client_secret', 'clientsecret', 'access_token', 'refresh_token', 'id_token']) {
      assert.ok(!raw.includes(forbidden), `the transaction leaked ${forbidden}`);
    }
    assert.deepEqual(Object.keys(JSON.parse(session)).sort(), ['exp', 'ret', 'state', 'verifier']);
  });

  test('sign-in still starts when sessionStorage alone is refused', async () => {
    const { url, local } = await startLogin({ kill: ['sessionStorage'] });
    assert.ok(url, 'the redirect to Keycloak must still happen');
    assert.ok(local, 'the durable copy must carry the transaction');
  });
});

// ============================ 2. sessionStorage lost across the redirect (the bug)

describe('sessionStorage lost between login and callback', () => {
  test('the callback recovers the transaction and completes the exchange', async () => {
    // Page 1: start sign-in normally.
    const started = await startLogin();
    const durable = started.local;

    // Page 2: the browser comes back from Keycloak having dropped the tab's
    // session storage. Only the durable copy survives. This is the live bug.
    const back = win({
      url: `${ORIGIN}/?code=real-code&state=${started.state}`,
      carry: { local: { [TX_KEY]: durable } },
    });
    const posted = [];
    back.w.fetch = async (u, opts = {}) => { posted.push({ u: String(u), body: String(opts.body || '') }); return okToken(); };

    assert.equal(await back.auth.completeLogin(), true,
      'a sign-in Keycloak already completed must not be thrown away');
    assert.equal(back.auth.isAuthenticated(), true);

    const exchange = posted.find(p => p.u === TOKEN_URL);
    assert.ok(exchange, 'no token exchange was attempted');
    assert.match(exchange.body, /grant_type=authorization_code/);
    assert.match(exchange.body, /code_verifier=/, 'PKCE verifier must still be sent');
    assert.ok(!/client_secret/.test(exchange.body), 'a public client must send no secret');
  });

  test('the recovered transaction restores the intended destination', async () => {
    const started = await startLogin();
    const back = win({
      url: `${ORIGIN}/?code=c&state=${started.state}`,
      carry: { local: { [TX_KEY]: started.local } },
    });
    back.w.fetch = async () => okToken();
    await back.auth.completeLogin();
    assert.equal(back.w.location.hash, '#/readiness',
      'the page the user was heading for must survive the round trip');
  });
});

// ================================================== 3. CSRF and PKCE not weakened

describe('CSRF and PKCE checks are unchanged in strength', () => {
  test('a forged state is still rejected, even with a durable copy present', async () => {
    const started = await startLogin();
    const back = win({
      url: `${ORIGIN}/?code=c&state=ATTACKER-SUPPLIED`,
      carry: { local: { [TX_KEY]: started.local }, session: { [TX_KEY]: started.session } },
    });
    let called = false;
    back.w.fetch = async () => { called = true; return okToken(); };
    await assert.rejects(() => back.auth.completeLogin(), /state mismatch/);
    assert.equal(called, false, 'no code may be redeemed after a state mismatch');
    assert.equal(back.auth.isAuthenticated(), false);
  });

  test('a transaction without a verifier is refused', async () => {
    const raw = JSON.stringify({ state: 'S', ret: '#/dashboard', exp: Date.now() + 600000 });
    const back = win({ url: `${ORIGIN}/?code=c&state=S`, carry: { local: { [TX_KEY]: raw } } });
    let called = false;
    back.w.fetch = async () => { called = true; return okToken(); };
    await assert.rejects(() => back.auth.completeLogin());
    assert.equal(called, false, 'no exchange without a PKCE verifier');
  });

  test('a code arriving with no transaction at all is refused', async () => {
    const back = win({ url: `${ORIGIN}/?code=c&state=S` });
    let called = false;
    back.w.fetch = async () => { called = true; return okToken(); };
    await assert.rejects(() => back.auth.completeLogin());
    assert.equal(called, false);
  });

  test('the authorize request still uses PKCE S256 and no secret', async () => {
    const { url } = await startLogin();
    const q = new URL(url).searchParams;
    assert.equal(q.get('code_challenge_method'), 'S256');
    assert.equal(q.get('response_type'), 'code');
    assert.ok(q.get('code_challenge'));
    assert.ok(!url.includes('client_secret'));
  });
});

// ============================================================ 4. expiry is enforced

describe('an expired transaction is rejected', () => {
  test('a transaction past its TTL cannot be redeemed', async () => {
    const raw = JSON.stringify({
      state: 'S', verifier: 'v'.repeat(64), ret: '#/dashboard', exp: Date.now() - 1,
    });
    const back = win({ url: `${ORIGIN}/?code=c&state=S`, carry: { local: { [TX_KEY]: raw } } });
    let called = false;
    back.w.fetch = async () => { called = true; return okToken(); };
    await assert.rejects(() => back.auth.completeLogin());
    assert.equal(called, false, 'an expired transaction must never reach the token endpoint');
  });

  test('an expired durable copy is swept on load, not left lying around', () => {
    const raw = JSON.stringify({ state: 'S', verifier: 'v', exp: Date.now() - 1 });
    const { w } = win({ carry: { local: { [TX_KEY]: raw } } });
    assert.equal(w.localStorage.getItem(TX_KEY), null,
      'a stranded transaction must not persist across visits');
  });

  test('a live durable copy is not swept', () => {
    const raw = JSON.stringify({ state: 'S', verifier: 'v', exp: Date.now() + 600000 });
    const { w } = win({ carry: { local: { [TX_KEY]: raw } } });
    assert.ok(w.localStorage.getItem(TX_KEY), 'a live transaction was destroyed on load');
  });

  test('the TTL is bounded and short', async () => {
    const { auth, session } = await startLogin();
    const ttl = auth._internals.TX_TTL_MS;
    assert.ok(ttl > 0 && ttl <= 15 * 60 * 1000, `TTL ${ttl}ms is not a bounded sign-in window`);
    assert.ok(JSON.parse(session).exp - Date.now() <= ttl + 1000);
  });
});

// ======================================================= 5. cleanup after success

describe('the transaction is erased once used', () => {
  test('both copies are gone after a successful sign-in', async () => {
    const started = await startLogin();
    const back = win({
      url: `${ORIGIN}/?code=c&state=${started.state}`,
      carry: { session: { [TX_KEY]: started.session }, local: { [TX_KEY]: started.local } },
    });
    back.w.fetch = async () => okToken();
    await back.auth.completeLogin();
    assert.equal(back.w.sessionStorage.getItem(TX_KEY), null, 'session copy survived');
    assert.equal(back.w.localStorage.getItem(TX_KEY), null, 'durable copy survived - it is replayable');
  });

  test('both copies are gone after a FAILED sign-in too', async () => {
    const started = await startLogin();
    const back = win({
      url: `${ORIGIN}/?code=c&state=${started.state}`,
      carry: { session: { [TX_KEY]: started.session }, local: { [TX_KEY]: started.local } },
    });
    back.w.fetch = async () => ({
      ok: false, status: 400, headers: { get: () => 'application/json' },
      json: async () => ({ error: 'invalid_grant' }),
    });
    await assert.rejects(() => back.auth.completeLogin());
    assert.equal(back.w.sessionStorage.getItem(TX_KEY), null);
    assert.equal(back.w.localStorage.getItem(TX_KEY), null,
      'a failed attempt must not leave a redeemable verifier behind');
  });

  test('replaying the callback URL cannot redeem the transaction again', async () => {
    const started = await startLogin();
    const first = win({
      url: `${ORIGIN}/?code=c&state=${started.state}`,
      carry: { session: { [TX_KEY]: started.session }, local: { [TX_KEY]: started.local } },
    });
    first.w.fetch = async () => okToken();
    assert.equal(await first.auth.completeLogin(), true);

    // Whatever storage the successful attempt left behind, carried into a
    // fresh load of the SAME callback URL - i.e. the URL being replayed from
    // history or by an attacker.
    const replay = win({
      url: `${ORIGIN}/?code=c&state=${started.state}`,
      carry: {
        session: Object.fromEntries(Object.entries({ [TX_KEY]: first.w.sessionStorage.getItem(TX_KEY) }).filter(([, v]) => v)),
        local: Object.fromEntries(Object.entries({ [TX_KEY]: first.w.localStorage.getItem(TX_KEY) }).filter(([, v]) => v)),
      },
    });
    let called = false;
    replay.w.fetch = async () => { called = true; return okToken(); };
    await assert.rejects(() => replay.auth.completeLogin(),
      'a consumed transaction must not be redeemable again');
    assert.equal(called, false, 'the replayed code reached the token endpoint');
  });

  test('logout clears any in-flight transaction', async () => {
    const { w, auth } = await startLogin();
    auth.setNavigator(() => {});
    auth.logout();
    assert.equal(w.sessionStorage.getItem(TX_KEY), null);
    assert.equal(w.localStorage.getItem(TX_KEY), null);
  });
});

// ================================================ 6. retry after a failed attempt

describe('a new attempt can follow a failed one', () => {
  test('starting again mints a fresh state and verifier', async () => {
    const first = await startLogin();
    const second = await startLogin({ carry: { local: { [TX_KEY]: first.local } } });
    assert.notEqual(second.state, first.state, 'a retry must not reuse the previous state');
    assert.notEqual(JSON.parse(second.session).verifier, JSON.parse(first.session).verifier,
      'a retry must mint a fresh PKCE verifier');
  });

  test('the stale transaction is replaced, not accumulated', async () => {
    const first = await startLogin();
    const second = await startLogin({ carry: { local: { [TX_KEY]: first.local } } });
    assert.equal(JSON.parse(second.local).state, second.state,
      'the durable copy must describe the CURRENT attempt');
  });

  test('a retry after a lost-transaction failure completes', async () => {
    // Attempt 1 comes back with nothing stored and fails.
    const failed = win({ url: `${ORIGIN}/?code=c&state=S` });
    await assert.rejects(() => failed.auth.completeLogin());

    // Attempt 2 starts cleanly and completes.
    const retry = await startLogin();
    const back = win({
      url: `${ORIGIN}/?code=c2&state=${retry.state}`,
      carry: { local: { [TX_KEY]: retry.local } },
    });
    back.w.fetch = async () => okToken();
    assert.equal(await back.auth.completeLogin(), true);
    assert.equal(back.auth.isAuthenticated(), true);
  });
});

// ================================================== 7. the button is never stuck

describe('the sign-in button always returns to a usable state', () => {
  /** Boots the full app over the real markup at a given URL. */
  async function app({ url = `${ORIGIN}/`, carry = {}, navigateThrows = false } = {}) {
    const dom = new JSDOM(read('index.html'), { url, runScripts: 'outside-only', pretendToBeVisual: true });
    const w = dom.window;
    inject(w);
    for (const [k, v] of Object.entries(carry.local || {})) w.localStorage.setItem(k, v);
    w.eval(`window.PIOS_CONFIG=${JSON.stringify({
      apiBase: 'https://pios-api.onrender.com/api/v1', demoMode: false, appVersion: '1.0.0',
      oidc: { issuer: ISSUER, clientId: 'pios-portal', scope: 'openid profile email' },
    })};`);
    w.eval(read('auth.js'));
    let navigated = null;
    w.PIOS_AUTH.setNavigator(u => {
      if (navigateThrows) throw new Error('redirect blocked');
      navigated = u;
    });
    w.fetch = async () => ({ ok: false, status: 401, headers: { get: () => 'application/json' }, json: async () => ({}) });
    w.eval(read('demo-data.js'));
    w.eval(read('app.js'));
    await new Promise(r => setTimeout(r, 60));
    return { w, doc: w.document, btn: () => w.document.querySelector('#loginBtn'), nav: () => navigated };
  }

  test('after a failed callback the button is enabled and pressable', async () => {
    const { btn, doc } = await app({ url: `${ORIGIN}/?code=c&state=NOTHING-STORED` });
    assert.equal(doc.querySelector('#loginScreen').hidden, false, 'the login screen must be shown');
    assert.equal(btn().disabled, false, 'the button was left disabled - the user is stuck');
    assert.notEqual(btn().dataset.busy, '1', 'the button was left in its busy state');
    assert.ok(doc.querySelector('#loginError').hidden === false, 'the reason must be visible');
  });

  test('pressing sign-in after that failure really starts a new attempt', async () => {
    const a = await app({ url: `${ORIGIN}/?code=c&state=NOTHING-STORED` });
    a.btn().dispatchEvent(new a.w.Event('click', { bubbles: true }));
    await new Promise(r => setTimeout(r, 60));
    assert.ok(a.nav(), 'the second attempt never reached the identity provider');
    assert.match(a.nav(), /\/protocol\/openid-connect\/auth\?/);
    assert.ok(a.w.localStorage.getItem(TX_KEY), 'the retry stored no transaction');
  });

  test('the button shows progress while redirecting', async () => {
    const a = await app();
    a.btn().dispatchEvent(new a.w.Event('click', { bubbles: true }));
    assert.equal(a.btn().disabled, true, 'the button must not accept a second press mid-redirect');
    assert.equal(a.btn().dataset.busy, '1');
  });

  test('a redirect that throws restores the button instead of hanging', async () => {
    const a = await app({ navigateThrows: true });
    a.btn().dispatchEvent(new a.w.Event('click', { bubbles: true }));
    await new Promise(r => setTimeout(r, 60));
    assert.equal(a.btn().disabled, false, 'a failed redirect left the button dead');
    assert.notEqual(a.btn().dataset.busy, '1');
    assert.equal(a.btn().textContent, a.btn().dataset.label,
      'the original label must be restored, not left reading "Redirecting…"');
  });
});
