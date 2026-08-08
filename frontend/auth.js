/* PIOS institutional authentication - OpenID Connect Authorization Code + PKCE.
 *
 * Public client, so there is NO client secret anywhere in this file or in the
 * built artifact - that is the entire reason PKCE exists. The code_verifier is
 * generated per attempt, never leaves the browser, and is discarded as soon as
 * the code is exchanged.
 *
 * Token storage is sessionStorage, not localStorage: it is scoped to the tab,
 * cleared when the tab closes, and not shared with other tabs or persisted to
 * disk the way localStorage is. frontend/RUNTIME_CHECKLIST.md item 4 asks that
 * production refresh tokens stay out of localStorage; this satisfies that, and
 * the residual exposure (a refresh token readable by script in this tab) is
 * documented in docs/OIDC_SETUP.md rather than hidden.
 */
(() => {
  const C = window.PIOS_CONFIG || {};
  const OIDC = C.oidc || {};
  const KEY_TOKENS = 'pios-oidc-tokens';
  const KEY_TX = 'pios-oidc-tx';

  // How long an in-flight sign-in may take. Keycloak's authorization code is
  // itself single-use and short-lived, so this only bounds how long a stranded
  // transaction can sit in storage; it is not a session lifetime.
  const TX_TTL_MS = 10 * 60 * 1000;

  const store = {
    get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
    // Returns whether the value survived. Swallowing a failed write silently
    // is what turned a blocked/full sessionStorage into a bogus "state
    // mismatch" on return from the identity provider - a CSRF message shown to
    // a user whose only mistake was having storage unavailable.
    set(k, v) {
      try { sessionStorage.setItem(k, v); return sessionStorage.getItem(k) === v; }
      catch (e) { return false; }
    },
    del(k) { try { sessionStorage.removeItem(k); } catch (e) {} },
  };

  const local = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) {
      try { localStorage.setItem(k, v); return localStorage.getItem(k) === v; }
      catch (e) { return false; }
    },
    del(k) { try { localStorage.removeItem(k); } catch (e) {} },
  };

  /* The in-flight OIDC transaction: {state, verifier, ret, exp}.
   *
   * Written to sessionStorage AND localStorage. sessionStorage is the right
   * home for it - tab-scoped and cleared with the tab - but it is not reliably
   * carried across the cross-origin round trip to the identity provider on
   * iOS Safari, and losing it strands a sign-in that Keycloak already
   * completed. localStorage is the durable copy, and is read only when the
   * session copy is gone.
   *
   * What is stored is deliberately not sensitive: the PKCE code_verifier, the
   * CSRF state, and a return hash. There is no password and no client secret -
   * this is a public client, which is why PKCE exists. The verifier is useless
   * on its own: redeeming it also requires the single-use authorization code,
   * which Keycloak binds to this client and redirect_uri. Tokens are NEVER
   * written here; they stay in sessionStorage alone.
   *
   * Single use: consumed and erased from both stores on the return trip,
   * whatever the outcome, and expired entries are swept whenever this module
   * loads.
   */
  const tx = {
    save(t) {
      const raw = JSON.stringify(t);
      // Both are attempted; either surviving is enough to complete sign-in.
      const inSession = store.set(KEY_TX, raw);
      const inLocal = local.set(KEY_TX, raw);
      return { inSession, inLocal, kept: inSession || inLocal };
    },
    /** The live transaction, or null. Never returns an expired one. */
    load() {
      for (const raw of [store.get(KEY_TX), local.get(KEY_TX)]) {
        if (!raw) continue;
        let t = null;
        try { t = JSON.parse(raw); } catch (e) { continue; }
        if (!t || !t.state || !t.verifier) continue;
        if (!(Number(t.exp) > Date.now())) continue;   // expired or malformed
        return t;
      }
      return null;
    },
    clear() { store.del(KEY_TX); local.del(KEY_TX); },
    /** Drops a stranded/expired transaction so it cannot linger in storage. */
    sweep() {
      const raw = local.get(KEY_TX);
      if (!raw) return;
      let t = null;
      try { t = JSON.parse(raw); } catch (e) { local.del(KEY_TX); return; }
      if (!t || !(Number(t.exp) > Date.now())) local.del(KEY_TX);
    },
  };
  tx.sweep();

  /* Auth-stage reporting.
   *
   * Enough to tell WHERE a sign-in stopped without ever recording WHAT was
   * exchanged. Only a stage name and a coarse error category are kept - never
   * an access or refresh token, never the authorization code, never the PKCE
   * verifier or state value, never a password. `stage()` takes no free-form
   * data, so there is no path by which a secret could be passed in.
   */
  const STAGES = [
    'AUTH_START', 'REDIRECTING', 'CALLBACK_RECEIVED', 'STATE_VALID',
    'TOKEN_EXCHANGE_START', 'TOKEN_EXCHANGE_OK', 'SESSION_ESTABLISHED',
    'API_AUTH_OK', 'REFRESH_OK', 'SIGNED_OUT',
  ];
  let last = null;
  function stage(name, errorCategory) {
    if (!STAGES.includes(name)) return last;
    last = { stage: name, at: new Date().toISOString() };
    if (errorCategory) last.error = String(errorCategory);
    try {
      // eslint-disable-next-line no-console
      console.log(`[pios-auth] ${name}${errorCategory ? ' ' + errorCategory : ''}`);
    } catch (e) { /* console may be unavailable */ }
    return last;
  }
  const lastStage = () => (last ? { ...last } : null);

  const configured = () => !!(OIDC.issuer && OIDC.clientId);

  // Top-level navigation is funnelled through one seam. Browsers make
  // location.assign non-configurable, so without this a test harness cannot
  // observe the redirect to the identity provider without actually leaving the
  // page. Production behaviour is unchanged.
  let navigate = (url) => { location.assign(url); };
  const setNavigator = (fn) => { navigate = typeof fn === 'function' ? fn : navigate; };

  function b64url(bytes) {
    let s = '';
    for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function randomString(len = 64) {
    const a = new Uint8Array(len);
    crypto.getRandomValues(a);
    return b64url(a).slice(0, len);
  }

  async function s256(verifier) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
    return b64url(digest);
  }

  const endpoints = () => {
    const base = String(OIDC.issuer || '').replace(/\/+$/, '');
    return {
      authorize: `${base}/protocol/openid-connect/auth`,
      token: `${base}/protocol/openid-connect/token`,
      logout: `${base}/protocol/openid-connect/logout`,
    };
  };

  function readTokens() {
    try { return JSON.parse(store.get(KEY_TOKENS) || 'null'); } catch (e) { return null; }
  }

  function writeTokens(t) {
    if (!t) { store.del(KEY_TOKENS); return; }
    const lifetime = Number(t.expires_in);
    if (Number.isFinite(lifetime) && lifetime > 0) {
      t.expires_at = Date.now() + lifetime * 1000;
      // Never let the safety margin eat more than half the token's own life.
      // A flat 30s against Keycloak's short default access-token lifespan
      // discarded a large slice of every session - and against a 60s token it
      // made the token look expired 30 seconds after it was issued.
      t.skew_ms = Math.min(30000, Math.floor(lifetime * 1000 / 2));
    } else {
      // No usable expires_in: do NOT invent one. The previous `|| 60` default
      // combined with the flat 30s margin produced a 30-second session out of
      // thin air. Rely on the server's 401 and refresh() instead.
      delete t.expires_at;
      delete t.skew_ms;
    }
    store.set(KEY_TOKENS, JSON.stringify(t));
  }

  function accessToken() {
    const t = readTokens();
    if (!t || !t.access_token) return null;
    const skew = Number.isFinite(t.skew_ms) ? t.skew_ms : 30000;
    if (t.expires_at && Date.now() > t.expires_at - skew) return null;
    return t.access_token;
  }

  function isAuthenticated() { return !!accessToken(); }

  /** Decoded access-token claims. Display only - the backend re-verifies. */
  function claims() {
    const t = readTokens();
    if (!t || !t.access_token) return null;
    try {
      const p = t.access_token.split('.')[1];
      return JSON.parse(atob(p.replace(/-/g, '+').replace(/_/g, '/')));
    } catch (e) { return null; }
  }

  function redirectUri() {
    return location.origin + location.pathname;
  }

  async function login(returnHash) {
    stage('AUTH_START');
    if (!configured()) throw new Error('OIDC is not configured');
    const verifier = randomString(64);
    const st = randomString(32);
    // A previous attempt may have been abandoned midway. Only one sign-in can
    // be in flight, and a stale transaction must never be redeemable.
    tx.clear();
    const kept = tx.save({
      state: st,
      verifier,
      ret: returnHash || location.hash || '#/dashboard',
      exp: Date.now() + TX_TTL_MS,
    }).kept;

    // Fail here, before leaving for the identity provider. Without the state
    // and verifier the return trip cannot succeed, and the user would
    // otherwise authenticate correctly at Keycloak only to be bounced back to
    // the sign-in screen. This now requires BOTH stores to be unavailable.
    if (!kept) {
      stage('AUTH_START', 'STORAGE_BLOCKED');
      throw new Error(
        'المتصفح يمنع تخزين بيانات الموقع بالكامل، ولا يمكن إتمام تسجيل الدخول. ' +
        'اسمح ببيانات الموقع لهذا العنوان ثم أعد المحاولة. / The browser is blocking ' +
        'all site storage, so sign-in cannot complete. Allow site data for this ' +
        'address and retry.',
      );
    }

    const p = new URLSearchParams({
      client_id: OIDC.clientId,
      redirect_uri: redirectUri(),
      response_type: 'code',
      scope: OIDC.scope || 'openid profile email',
      state: st,
      code_challenge: await s256(verifier),
      code_challenge_method: 'S256',
    });
    stage('REDIRECTING');
    navigate(`${endpoints().authorize}?${p.toString()}`);
  }

  /** Handles ?code=...&state=... on return from the identity provider. */
  async function completeLogin() {
    const q = new URLSearchParams(location.search);
    const code = q.get('code');
    const returnedState = q.get('state');
    const oidcError = q.get('error');

    if (oidcError) {
      stage('CALLBACK_RECEIVED', 'IDP_ERROR');
      // The attempt is over, so its transaction must go with it. Leaving the
      // state and PKCE verifier behind broke the single-use guarantee: an
      // unconsumed verifier survived in both stores and remained matchable by
      // a later callback. Keycloak reports authentication_expired here, among
      // others, and every one of them ends the attempt.
      tx.clear();
      cleanUrl();
      throw new Error(q.get('error_description') || oidcError);
    }
    if (!code) return false;
    stage('CALLBACK_RECEIVED');

    // Read from whichever store still holds it (session first, then the
    // durable copy), then erase it from BOTH immediately. The transaction is
    // single use: whatever happens below, this code can never be replayed
    // against a surviving verifier.
    const t = tx.load();
    tx.clear();

    // CSRF defence, unchanged in strength: the code must arrive with exactly
    // the state we issued. The cases are reported apart because they need
    // opposite responses - a missing transaction is recoverable by retrying, a
    // differing state is a genuine CSRF signal and never is.
    if (!t) {
      stage('CALLBACK_RECEIVED', 'TRANSACTION_MISSING');
      cleanUrl();
      throw new Error(
        'انتهت مهلة تسجيل الدخول أو تعذّر حفظ بياناته. اضغط زر الدخول مرة أخرى. / ' +
        'The sign-in attempt expired or could not be stored. Press the sign-in button ' +
        'again to start a new attempt.',
      );
    }
    if (returnedState !== t.state) {
      stage('CALLBACK_RECEIVED', 'STATE_MISMATCH');
      cleanUrl();
      throw new Error('state mismatch');
    }
    if (!t.verifier) { stage('CALLBACK_RECEIVED', 'VERIFIER_MISSING'); cleanUrl(); throw new Error('missing PKCE verifier'); }
    stage('STATE_VALID');
    const verifier = t.verifier;

    const body = new URLSearchParams({
      grant_type: 'authorization_code',
      code,
      redirect_uri: redirectUri(),
      client_id: OIDC.clientId,
      code_verifier: verifier,
    });
    stage('TOKEN_EXCHANGE_START');
    const r = await fetch(endpoints().token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    if (!r.ok) {
      const detail = await r.json().catch(() => ({}));
      stage('TOKEN_EXCHANGE_START', 'TOKEN_EXCHANGE_FAILED');
      cleanUrl();
      throw Object.assign(new Error(detail.error_description || detail.error || 'token exchange failed'), { status: r.status });
    }
    stage('TOKEN_EXCHANGE_OK');
    writeTokens(await r.json());
    // The transaction was already erased from both stores above; `ret` came
    // with it, so nothing is left behind after a successful sign-in.
    cleanUrl(t.ret || '#/dashboard');
    return true;
  }

  function cleanUrl(hash) {
    // Strip code/state from the address bar so they are not left in history.
    const clean = location.origin + location.pathname + (hash || location.hash || '');
    history.replaceState({}, '', clean);
  }

  async function refresh() {
    const t = readTokens();
    if (!t || !t.refresh_token || !configured()) return false;
    const body = new URLSearchParams({
      grant_type: 'refresh_token',
      refresh_token: t.refresh_token,
      client_id: OIDC.clientId,
    });
    const r = await fetch(endpoints().token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    if (!r.ok) { writeTokens(null); stage('REFRESH_OK', 'REFRESH_FAILED'); return false; }
    writeTokens(await r.json());
    stage('REFRESH_OK');
    return true;
  }

  function logout() {
    const t = readTokens();
    writeTokens(null);
    tx.clear();
    stage('SIGNED_OUT');
    if (!configured()) { location.hash = '#/dashboard'; location.reload(); return; }
    const p = new URLSearchParams({
      client_id: OIDC.clientId,
      post_logout_redirect_uri: location.origin + location.pathname,
    });
    if (t && t.id_token) p.set('id_token_hint', t.id_token);
    navigate(`${endpoints().logout}?${p.toString()}`);
  }

  window.PIOS_AUTH = {
    configured, login, completeLogin, refresh, logout,
    accessToken, isAuthenticated, claims,
    setNavigator, stage, lastStage,
    _internals: { s256, randomString, readTokens, writeTokens, tx, TX_TTL_MS },
  };
})();
