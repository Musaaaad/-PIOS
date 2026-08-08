// Shared plumbing for browser-driven end-to-end suites.
//
// Kept apart from the tests so a suite reads as scenarios rather than setup,
// and so the Chromium resolution rule lives in exactly one place.

import { execFileSync } from 'node:child_process';
import { readFileSync, existsSync, mkdtempSync, readdirSync } from 'node:fs';
import { createServer } from 'node:https';
import { tmpdir } from 'node:os';
import { join, extname } from 'node:path';
import { createSign, createVerify, generateKeyPairSync } from 'node:crypto';
import { chromium } from 'playwright';

/* HTTPS throughout, deliberately: the published site carries
 * `connect-src 'self' https:`, so an http:// backend would be blocked by the
 * app's own CSP - a test artifact that would hide real behaviour. */
export const TLS = (() => {
  const dir = mkdtempSync(join(tmpdir(), 'pios-tls-'));
  const key = join(dir, 'k.pem'), cert = join(dir, 'c.pem');
  execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key,
    '-out', cert, '-days', '2', '-subj', '/CN=127.0.0.1',
    '-addext', 'subjectAltName=IP:127.0.0.1,DNS:localhost'], { stdio: 'pipe' });
  return { key: readFileSync(key), cert: readFileSync(cert) };
})();

export const listen = handler => new Promise(res => {
  const s = createServer(TLS, handler);
  s.listen(0, '127.0.0.1', () => res({ s, origin: `https://127.0.0.1:${s.address().port}` }));
});

export const readBody = req => new Promise(r => { let b = ''; req.on('data', c => b += c); req.on('end', () => r(b)); });

export const send = (res, code, type, payload, extra = {}) => {
  res.writeHead(code, {
    'Content-Type': type, 'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': '*', ...extra,
  });
  res.end(payload);
};

export const json = (res, code, obj) => send(res, code, 'application/json', JSON.stringify(obj));

/* Chromium resolution: Playwright's own install first, a pre-installed build
 * only as a sandbox fallback, and a loud failure if neither exists. Never a
 * hard-coded path - that is what broke CI in Sprint 23.6A. */
function discoverLocalChromium() {
  const explicit = process.env.PIOS_E2E_CHROMIUM;
  if (explicit && existsSync(explicit)) return explicit;
  const root = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (!root || !existsSync(root)) return null;
  for (const entry of readdirSync(root)) {
    if (!entry.startsWith('chromium-')) continue;
    const candidate = join(root, entry, 'chrome-linux', 'chrome');
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

export async function launchChromium() {
  const args = ['--no-sandbox'];
  try { return await chromium.launch({ args }); }
  catch (err) {
    const fallback = discoverLocalChromium();
    if (!fallback) throw err;
    return chromium.launch({ executablePath: fallback, args });
  }
}

const b64u = b => Buffer.from(b).toString('base64url');

/** An RSA keypair plus JWT mint/verify shaped like a real Keycloak token. */
export function identityKit({ issuer, audience = 'pios-api' }) {
  const KEY = generateKeyPairSync('rsa', { modulusLength: 2048 });
  const jwks = { keys: [{ ...KEY.publicKey.export({ format: 'jwk' }), kid: 'e2e', use: 'sig', alg: 'RS256' }] };

  /* Mirrors what the pios realm actually emits: Keycloak's own default roles
   * always ride along in realm_access.roles, and the realm-role mapper copies
   * them into the custom `roles` claim the backend reads. A test that omitted
   * them would be asserting against a token Keycloak never issues. */
  const KEYCLOAK_DEFAULTS = ['default-roles-pios', 'offline_access', 'uma_authorization'];

  const mint = ({ roles = [], sites = ['TGH'], sub = 'pios-test-sub', username = 'pios-test', name = 'PIOS Test', expiresIn = 300, ...over } = {}) => {
    const all = [...KEYCLOAK_DEFAULTS, ...roles];
    const header = b64u(JSON.stringify({ alg: 'RS256', typ: 'JWT', kid: 'e2e' }));
    const now = Math.floor(Date.now() / 1000);
    const payload = b64u(JSON.stringify({
      sub, iss: issuer(), aud: audience, iat: now, exp: now + expiresIn,
      preferred_username: username, name,
      realm_access: { roles: all }, roles: all, sites, ...over,
    }));
    const sig = createSign('RSA-SHA256').update(`${header}.${payload}`).end()
      .sign(KEY.privateKey).toString('base64url');
    return `${header}.${payload}.${sig}`;
  };

  /** Validates a bearer token the way the backend does: signature, iss, aud, exp. */
  const verify = token => {
    const [h, p, s] = String(token || '').split('.');
    if (!h || !p || !s) return null;
    if (!createVerify('RSA-SHA256').update(`${h}.${p}`).end().verify(KEY.publicKey, Buffer.from(s, 'base64url'))) return null;
    const claims = JSON.parse(Buffer.from(p, 'base64url').toString());
    if (claims.iss !== issuer() || claims.aud !== audience) return null;
    if (claims.exp * 1000 < Date.now()) return null;
    return claims;
  };

  return { jwks, mint, verify, KEYCLOAK_DEFAULTS };
}

/** Builds the production artifact exactly as Render does, and serves it. */
export async function serveProductionBuild(repo, env) {
  const dist = mkdtempSync(join(tmpdir(), 'pios-dist-'));
  execFileSync('bash', [join(repo, 'deploy', 'render', 'build_frontend.sh')], {
    env: { ...process.env, ...env, OUT_DIR: dist }, stdio: 'pipe',
  });
  const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };
  const { s, origin } = await listen((req, res) => {
    const p = new URL(req.url, 'https://x').pathname;
    const f = join(dist, p === '/' ? 'index.html' : p);
    const target = existsSync(f) && p !== '/' ? f : join(dist, 'index.html');
    send(res, 200, TYPES[extname(target)] || 'text/plain', readFileSync(target));
  });
  return { dist, server: s, origin };
}
