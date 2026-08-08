#!/usr/bin/env bash
# Build the PIOS static frontend for a host that serves a directory.
#
# Used by the pios-frontend service in render.yaml. Exists as a committed
# script rather than an inline buildCommand so that it is unambiguous (an
# inline multi-line heredoc gets folded into an escaped YAML scalar), testable
# locally, and identical between Render and any other static host.
#
# Mirrors the Pages build in .github/workflows/deploy-pages.yml. Both generate
# config.js at build time and never modify the committed frontend/config.js.
#
# Environment:
#   PIOS_API_BASE_URL   Base URL of the live API, e.g.
#                       https://pios-api.onrender.com/api/v1
#                       When empty the site builds in demo mode.
#   PIOS_DEMO_MODE      Force demo mode on/off. Defaults to demo mode when
#                       PIOS_API_BASE_URL is empty, live mode when it is set.
#   PIOS_REQUEST_TIMEOUT_MS
#                       How long an API call may take before the app shows a
#                       retryable "backend unreachable" state. Defaults to
#                       25000. Raise it if the backend is on a plan whose
#                       instances sleep and cold-start slowly.
#   OUT_DIR             Output directory. Defaults to ./dist.
#
# Usage:  bash deploy/render/build_frontend.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO_ROOT/frontend"
OUT="${OUT_DIR:-$REPO_ROOT/dist}"

API_BASE="${PIOS_API_BASE_URL:-}"
if [ -n "${PIOS_DEMO_MODE:-}" ]; then
  DEMO="$PIOS_DEMO_MODE"
elif [ -n "$API_BASE" ]; then
  DEMO=false
else
  DEMO=true
fi

TIMEOUT_MS="${PIOS_REQUEST_TIMEOUT_MS:-25000}"
case "$TIMEOUT_MS" in ''|*[!0-9]*) echo "[build_frontend] FATAL: PIOS_REQUEST_TIMEOUT_MS must be an integer, got '$TIMEOUT_MS'" >&2; exit 1;; esac

echo "[build_frontend] source : $SRC"
echo "[build_frontend] output : $OUT"
if [ -n "$API_BASE" ]; then
  echo "[build_frontend] api    : $API_BASE"
else
  echo "[build_frontend] api    : (none) - building in demo mode"
fi
echo "[build_frontend] demo   : $DEMO"

[ -d "$SRC" ] || { echo "[build_frontend] FATAL: $SRC not found" >&2; exit 1; }

rm -rf "$OUT"
mkdir -p "$OUT"
cp -r "$SRC"/. "$OUT"/

# Build/test inputs, not site content. node_modules in particular must never be
# published: it is added by the frontend test harness and would otherwise ship
# thousands of dependency files to a public URL.
rm -rf "$OUT/tests" "$OUT/Dockerfile" "$OUT/nginx.conf" "$OUT/MANIFEST.txt" \
       "$OUT/node_modules" "$OUT/package.json" "$OUT/package-lock.json"

# Generated fresh every build. defaultToken is deliberately empty: the value in
# the committed frontend/config.js is a development token and must never be
# published to a public URL.
cat > "$OUT/config.js" <<EOF
window.PIOS_CONFIG = {
  apiBase: "${API_BASE}",
  demoMode: ${DEMO},
  defaultToken: "",
  refreshSeconds: 60,
  requestTimeoutMs: ${TIMEOUT_MS},
  appVersion: "1.0.0",
  oidc: {
    issuer: "${PIOS_OIDC_ISSUER:-}",
    clientId: "${PIOS_OIDC_CLIENT_ID:-pios-portal}",
    scope: "openid profile email"
  }
};
EOF

# Static hosts that cannot serve custom response headers still get the CSP.
# Render is configured with real headers in render.yaml as well; a meta tag is
# harmless there and essential on GitHub Pages.
python3 - "$OUT" <<'PY'
import sys
from pathlib import Path
out = Path(sys.argv[1])
page = out / "index.html"
html = page.read_text(encoding="utf-8")
if "Content-Security-Policy" in html:
    print("[build_frontend] CSP meta already present, leaving as is")
else:
    csp = ('<meta http-equiv="Content-Security-Policy" content="'
           "default-src 'self'; connect-src 'self' https:; "
           "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
           "img-src 'self' data:; base-uri 'self'; form-action 'none'\">\n  ")
    marker = '<meta name="viewport"'
    if marker not in html:
        raise SystemExit("[build_frontend] FATAL: CSP injection point not found in index.html")
    page.write_text(html.replace(marker, csp + marker, 1), encoding="utf-8")
    print("[build_frontend] CSP meta tag injected")
PY

touch "$OUT/.nojekyll"

# Fail the build rather than publish a development token.
if grep -q "dev:portal-user" "$OUT/config.js"; then
  echo "[build_frontend] FATAL: development token present in generated config.js" >&2
  exit 1
fi

# A public OIDC client uses PKCE precisely so that no secret is needed. Any
# secret-looking value reaching the published bundle is a hard failure.
if grep -qiE "client_?secret|PIOS_OIDC_CLIENT_SECRET" "$OUT/config.js"; then
  echo "[build_frontend] FATAL: a client secret must never be published to the frontend" >&2
  exit 1
fi

for required in index.html app.js auth.js styles.css config.js demo-data.js; do
  [ -f "$OUT/$required" ] || { echo "[build_frontend] FATAL: missing $required" >&2; exit 1; }
done

FILE_COUNT=$(find "$OUT" -type f | wc -l)
echo "[build_frontend] built $FILE_COUNT files"

# The site is a fixed, small set of static assets. A large count means build or
# test inputs leaked into the published output (node_modules being the likely
# culprit), so fail rather than publish them.
if [ "$FILE_COUNT" -gt 25 ]; then
  echo "[build_frontend] FATAL: $FILE_COUNT files in output - build inputs leaked into the site" >&2
  find "$OUT" -maxdepth 1 >&2
  exit 1
fi

echo "[build_frontend] OK"
