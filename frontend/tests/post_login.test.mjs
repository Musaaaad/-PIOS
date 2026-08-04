// Sprint 23.3 - the post-OIDC-callback page.
//
// The reported failure: after a successful institutional sign-in the dashboard
// rendered unstyled, every control was dead, and the user chip still read
// "Accreditation Lead".
//
// Why the existing 31 tests in ui.test.mjs could not catch it: their boot()
// helper does `w.eval(readFileSync(...))` for each script. That bypasses the
// browser entirely - it never resolves `<script src="app.js">` or
// `<link href="styles.css">` against the page URL, so an asset that 404s, or
// that is answered with index.html instead of JavaScript, looks identical to
// one that loads. Everything here goes through the real DOM: jsdom fetches the
// referenced assets over HTTP from a server that emulates the static host, so a
// mis-served asset fails the test the way it fails a browser.
//
// Nothing here starts Keycloak or contacts Render.

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

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
};

let DIST;
let server;
let origin;

/**
 * Serves the built artifact.
 *
 * `shadowAssets` reproduces a catch-all SPA rewrite that is applied ahead of
 * real files - i.e. every path, assets included, answered with index.html. That
 * is the failure mode the removed `source: /*` rewrite in render.yaml could
 * produce, and the tests below assert the app survives the correct behaviour
 * and visibly fails under the broken one.
 */
let shadowAssets = false;

before(async () => {
  DIST = mkdtempSync(join(tmpdir(), 'pios-dist-'));
  execFileSync('bash', [join(REPO, 'deploy', 'render', 'build_frontend.sh')], {
    env: {
      ...process.env,
      PIOS_API_BASE_URL: API,
      PIOS_OIDC_ISSUER: ISSUER,
      PIOS_OIDC_CLIENT_ID: 'pios-portal',
      OUT_DIR: DIST,
    },
    stdio: 'pipe',
  });

  server = createServer((req, res) => {
    const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    const file = join(DIST, path === '/' ? 'index.html' : path);
    const serveIndex = shadowAssets || path === '/' || !existsSync(file);
    const target = serveIndex ? join(DIST, 'index.html') : file;
    res.writeHead(200, { 'Content-Type': TYPES[extname(target)] || 'text/plain' });
    res.end(readFileSync(target));
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  origin = `http://127.0.0.1:${server.address().port}`;
});

after(() => server && server.close());

const json = (body, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  headers: { get: () => 'application/json' },
  json: async () => body,
});

const IDENTITY = {
  user_id: 'f1e2d3c4-turaif-pilot',
  display_name: 'قائد الاعتماد',
  roles: ['AccreditationLead'],
  site_codes: ['TGH'],
  auth_source: 'oidc',
};

const OVERVIEW = {
  site: { code: 'TGH' },
  readiness: { score: 71, accepted: 5, partial: 2, missing: 1, esr_status: {} },
  findings: { by_severity: { P0: 1 } },
  evidence: { overdue_requests: 2 },
  capas: { overdue: 1 },
  notifications: { unread: 3 },
};

/**
 * Boots the built site through the real DOM at `url`.
 *
 * Scripts and stylesheets are fetched over HTTP by jsdom, exactly as a browser
 * resolves them relative to the page URL.
 */
async function open({ url = `${origin}/`, session = {}, tokenStatus = 200 } = {}) {
  const loaded = [];
  class Loader extends ResourceLoader {
    fetch(u, opts) {
      loaded.push(u);
      return super.fetch(u, opts);
    }
  }

  const dom = await JSDOM.fromURL(url, {
    runScripts: 'dangerously',
    resources: new Loader(),
    pretendToBeVisual: true,
  }).catch(async () => {
    // fromURL cannot seed sessionStorage before scripts run; fall back to
    // constructing from the fetched HTML with the same URL semantics.
    const html = await (await fetch(url)).text();
    return new JSDOM(html, { url, runScripts: 'dangerously', resources: new Loader(), pretendToBeVisual: true });
  });

  const w = dom.window;
  w.innerWidth = 390;
  for (const [k, v] of Object.entries(session)) w.sessionStorage.setItem(k, v);

  const calls = [];
  w.fetch = async (u, opts = {}) => {
    calls.push({ url: String(u), method: (opts.method || 'GET').toUpperCase() });
    if (String(u).includes('/protocol/openid-connect/token')) {
      if (tokenStatus !== 200) return json({ error: 'invalid_grant' }, tokenStatus);
      // A real-shaped JWT: header.payload.signature, payload base64url-decodable.
      const payload = Buffer.from(JSON.stringify({
        sub: IDENTITY.user_id, roles: IDENTITY.roles, sites: ['TGH'],
      })).toString('base64url');
      return json({
        access_token: `eyJhbGciOiJSUzI1NiJ9.${payload}.sig`,
        refresh_token: 'r', id_token: 'i', expires_in: 300, token_type: 'Bearer',
      });
    }
    if (String(u).includes('/identity/me')) return json(IDENTITY);
    if (String(u).includes('/dashboard/overview')) return json(OVERVIEW);
    if (String(u).includes('/dashboard/standards')) return json({ standards: [] });
    if (String(u).includes('/worklists/my')) return json({ items: [] });
    if (String(u).includes('/notifications')) return json([]);
    return json({}, 404);
  };

  await new Promise(r => setTimeout(r, 120));
  return { dom, w, doc: w.document, loaded, calls };
}

const asset = (loaded, name) => loaded.find(u => u.endsWith(name));

// ------------------------------------------------- 1. the built artifact itself

describe('built artifact asset integrity', () => {
  test('every referenced script and stylesheet exists in the published output', () => {
    const html = readFileSync(join(DIST, 'index.html'), 'utf8');
    const refs = [...html.matchAll(/(?:src|href)="([^"#][^"]*)"/g)]
      .map(m => m[1])
      .filter(r => !/^(https?:)?\/\//.test(r) && /\.(js|css)$/.test(r));

    assert.ok(refs.length >= 5, `expected the app's assets to be referenced, saw ${refs}`);
    for (const ref of refs) {
      assert.ok(existsSync(join(DIST, ref)), `${ref} is referenced by index.html but absent from the build`);
    }
  });

  test('index.html carries no placeholder identity that could pass for a session', () => {
    const html = readFileSync(join(DIST, 'index.html'), 'utf8');
    const chip = html.slice(html.indexOf('user-chip'), html.indexOf('</header>'));
    for (const placeholder of ['Accreditation Lead', 'قائد الاعتماد']) {
      assert.ok(
        !chip.includes(placeholder),
        `the user chip ships the literal ${placeholder}; when app.js does not run this is ` +
        `indistinguishable from a real signed-in identity`,
      );
    }
    assert.match(html, /id="userRole"><\/small>/, 'userRole must ship empty and be filled by render()');
  });
});

// --------------------------------------------- 2. the static host must not lie

describe('render.yaml static routing', () => {
  test('no catch-all rewrite can shadow a real asset', () => {
    const yaml = readFileSync(join(REPO, 'render.yaml'), 'utf8');
    const front = yaml.slice(yaml.indexOf('name: pios-frontend'));
    const routes = front.slice(0, front.indexOf('headers:'));
    assert.ok(
      !/type:\s*rewrite[\s\S]*?source:\s*\/\*/.test(routes),
      'a `source: /*` rewrite answers asset requests with index.html, so the browser ' +
      'gets HTML where it asked for CSS/JS - no styling and no JavaScript. The app is ' +
      'hash-routed and needs no SPA fallback.',
    );
  });
});

// ------------------------------------------- 3. the reproduction and the guard

describe('post-OIDC-callback page', () => {
  const CALLBACK = { code: 'auth-code-123', state: 'st-abc' };
  const session = () => ({
    'pios-oidc-state': CALLBACK.state,
    'pios-oidc-verifier': 'v'.repeat(64),
    'pios-oidc-return': '#/dashboard',
  });
  const callbackUrl = () => `${origin}/?code=${CALLBACK.code}&state=${CALLBACK.state}`;

  test('assets load and scripts execute at the callback URL', async () => {
    const { w, loaded } = await open({ url: callbackUrl(), session: session() });
    assert.ok(asset(loaded, 'app.js'), `app.js was never requested; requested: ${loaded}`);
    assert.ok(asset(loaded, 'styles.css'), 'styles.css was never requested');
    assert.equal(typeof w.PIOS_AUTH, 'object', 'auth.js did not execute');
    assert.equal(typeof w.PIOS_CONFIG, 'object', 'config.js did not execute');
  });

  test('stylesheet is served as CSS, not as index.html', async () => {
    const res = await fetch(`${origin}/styles.css`);
    assert.match(res.headers.get('content-type'), /text\/css/);
    const body = await res.text();
    assert.ok(!body.includes('<!doctype html'), 'styles.css was answered with HTML');
    assert.ok(body.length > 500, 'styles.css is suspiciously small');
  });

  test('dashboard initializes: content rendered and identity comes from the session', async () => {
    const { doc } = await open({ url: callbackUrl(), session: session() });
    assert.ok(doc.querySelector('#main').innerHTML.trim().length > 200, 'the dashboard did not render');
    assert.equal(doc.querySelector('#userRole').textContent, 'AccreditationLead',
      'the role must come from the verified session, not from markup');
    assert.equal(doc.querySelector('#nav').children.length > 0, true, 'navigation did not render');
  });

  test('CSS remains applied after the callback', async () => {
    const { doc } = await open({ url: callbackUrl(), session: session() });
    const link = doc.querySelector('link[rel="stylesheet"]');
    assert.ok(link, 'the stylesheet link is gone from the document');
    const res = await fetch(new URL(link.getAttribute('href'), callbackUrl()).href);
    assert.match(res.headers.get('content-type'), /text\/css/);
  });

  test('buttons remain functional after the callback', async () => {
    const { doc, w } = await open({ url: callbackUrl(), session: session() });
    const menu = doc.querySelector('#menuBtn');
    menu.dispatchEvent(new w.Event('click', { bubbles: true }));
    assert.equal(doc.querySelector('.sidebar').classList.contains('open'), true,
      'the menu button no longer opens navigation');

    const alerts = doc.querySelector('#alertsBtn');
    alerts.dispatchEvent(new w.Event('click', { bubbles: true }));
    assert.equal(doc.querySelector('#alertDrawer').classList.contains('open'), true,
      'the notifications button no longer opens the drawer');

    assert.ok(doc.querySelector('#refreshBtn'), 'the refresh control is missing');
    const navBtns = doc.querySelectorAll('#nav [data-route]');
    assert.ok(navBtns.length > 0 && typeof navBtns[0].onclick === 'function',
      'navigation items are not wired');
  });

  test('the authorization code and state are stripped from the address bar', async () => {
    const { w } = await open({ url: callbackUrl(), session: session() });
    assert.ok(!w.location.search.includes('code='), 'the authorization code was left in the URL');
    assert.ok(!w.location.search.includes('state='), 'the state was left in the URL');
  });

  test('the token exchange actually happened', async () => {
    const { calls } = await open({ url: callbackUrl(), session: session() });
    const exchange = calls.find(c => c.url.includes('/protocol/openid-connect/token'));
    assert.ok(exchange, 'no token exchange was attempted');
    assert.equal(exchange.method, 'POST');
  });
});

// ------------------------------------------------------ 4. failure paths honest

describe('callback failure does not leave a fake session on screen', () => {
  test('a state mismatch shows the login screen and no placeholder identity', async () => {
    const { doc } = await open({
      url: `${origin}/?code=c&state=WRONG`,
      session: { 'pios-oidc-state': 'expected', 'pios-oidc-verifier': 'v'.repeat(64) },
    });
    assert.equal(doc.querySelector('#loginScreen').hidden, false, 'the login screen was not shown');
    const role = doc.querySelector('#userRole').textContent.trim();
    assert.equal(role, '', `the user chip still reads ${role} after a failed sign-in`);
  });

  test('a failed token exchange does not authenticate', async () => {
    const { doc, w } = await open({
      url: `${origin}/?code=c&state=st`,
      session: { 'pios-oidc-state': 'st', 'pios-oidc-verifier': 'v'.repeat(64) },
      tokenStatus: 400,
    });
    assert.equal(w.PIOS_AUTH.isAuthenticated(), false);
    assert.equal(doc.querySelector('#loginScreen').hidden, false);
  });
});

// -------------------------------------------- 5. the broken host, demonstrated

describe('the failure mode this sprint fixes', () => {
  test('shadowing assets with index.html reproduces the reported symptom', async () => {
    shadowAssets = true;
    try {
      const { doc, w } = await open({ url: `${origin}/` });
      assert.equal(typeof w.PIOS_CONFIG, 'undefined',
        'with assets shadowed, no script should execute - the reproduction is invalid');
      assert.equal(doc.querySelector('#main').innerHTML.trim(), '',
        'nothing can render when app.js is served as HTML');
      // And the reason the old markup made this look like a working session:
      assert.equal(doc.querySelector('#userRole').textContent.trim(), '',
        'the chip must be empty now; previously it read "Accreditation Lead" here');
    } finally {
      shadowAssets = false;
    }
  });
});

// ------------------------------------------------- 6. no regression elsewhere

describe('unauthenticated and non-OIDC behaviour is unchanged', () => {
  test('without a callback the login screen gates the app', async () => {
    const { doc } = await open({ url: `${origin}/` });
    assert.equal(doc.querySelector('#loginScreen').hidden, false,
      'an unauthenticated visitor must be gated, not shown data');
  });

  test('OIDC config is intact in the built artifact', () => {
    const cfg = readFileSync(join(DIST, 'config.js'), 'utf8');
    assert.match(cfg, /issuer: "https:\/\/pios-keycloak\.onrender\.com\/realms\/pios"/);
    assert.match(cfg, /clientId: "pios-portal"/);
    assert.match(cfg, /apiBase: "https:\/\/pios-api\.onrender\.com\/api\/v1"/);
    assert.ok(!/client_?secret/i.test(cfg), 'no secret may reach the bundle');
  });
});
