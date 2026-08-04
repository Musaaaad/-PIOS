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
  const KEY_VERIFIER = 'pios-oidc-verifier';
  const KEY_STATE = 'pios-oidc-state';
  const KEY_RETURN = 'pios-oidc-return';

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
    if (!configured()) throw new Error('OIDC is not configured');
    const verifier = randomString(64);
    const st = randomString(32);
    const kept = store.set(KEY_VERIFIER, verifier) && store.set(KEY_STATE, st);
    store.set(KEY_RETURN, returnHash || location.hash || '#/dashboard');

    // Fail here, before leaving for the identity provider. Without these two
    // values the return trip cannot succeed, and the user would otherwise
    // authenticate correctly at Keycloak only to be bounced back to the
    // sign-in screen with a message blaming CSRF.
    if (!kept) {
      throw new Error(
        'المتصفح يمنع تخزين الجلسة (sessionStorage). عطّل التصفح الخاص أو امنع حجب ' +
        'البيانات لهذا الموقع ثم أعد المحاولة. / Browser storage is blocked: sign-in ' +
        'state cannot be kept. Disable Private Browsing or site data blocking, then retry.',
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
    navigate(`${endpoints().authorize}?${p.toString()}`);
  }

  /** Handles ?code=...&state=... on return from the identity provider. */
  async function completeLogin() {
    const q = new URLSearchParams(location.search);
    const code = q.get('code');
    const returnedState = q.get('state');
    const oidcError = q.get('error');

    if (oidcError) {
      cleanUrl();
      throw new Error(q.get('error_description') || oidcError);
    }
    if (!code) return false;

    const expected = store.get(KEY_STATE);
    const verifier = store.get(KEY_VERIFIER);
    store.del(KEY_STATE); store.del(KEY_VERIFIER);

    // CSRF defence: a code arriving with a state we did not issue is rejected.
    // The two cases are reported apart because they need opposite responses.
    // No stored state at all means our own record vanished between the two
    // page loads (blocked or evicted sessionStorage) - the sign-in was fine and
    // retrying can work. A state that differs is a genuine CSRF signal.
    if (!expected) {
      cleanUrl();
      throw new Error(
        'انتهت حالة تسجيل الدخول قبل العودة من مزود الهوية (تخزين المتصفح غير متاح). ' +
        'أعد المحاولة في نافذة عادية غير خاصة. / Sign-in state was lost before the ' +
        'return from the identity provider (browser storage unavailable). Retry in a ' +
        'normal, non-private window.',
      );
    }
    if (returnedState !== expected) {
      cleanUrl();
      throw new Error('state mismatch');
    }
    if (!verifier) { cleanUrl(); throw new Error('missing PKCE verifier'); }

    const body = new URLSearchParams({
      grant_type: 'authorization_code',
      code,
      redirect_uri: redirectUri(),
      client_id: OIDC.clientId,
      code_verifier: verifier,
    });
    const r = await fetch(endpoints().token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    if (!r.ok) {
      const detail = await r.json().catch(() => ({}));
      cleanUrl();
      throw Object.assign(new Error(detail.error_description || detail.error || 'token exchange failed'), { status: r.status });
    }
    writeTokens(await r.json());
    const back = store.get(KEY_RETURN) || '#/dashboard';
    store.del(KEY_RETURN);
    cleanUrl(back);
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
    if (!r.ok) { writeTokens(null); return false; }
    writeTokens(await r.json());
    return true;
  }

  function logout() {
    const t = readTokens();
    writeTokens(null);
    store.del(KEY_STATE); store.del(KEY_VERIFIER); store.del(KEY_RETURN);
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
    setNavigator,
    _internals: { s256, randomString, readTokens, writeTokens },
  };
})();
