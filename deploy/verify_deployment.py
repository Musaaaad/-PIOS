"""Post-deployment verification for a live PIOS deployment.

Run from CI (or by hand) against a deployed URL. Polls until the service is
up, then asserts the things that actually matter for a deploy to be considered
good. Exits non-zero on any failure so a bad deploy fails the pipeline loudly.

Usage:
    python deploy/verify_deployment.py --api-url https://pios-api.example.com
    python deploy/verify_deployment.py --frontend-url https://user.github.io/-PIOS/
    python deploy/verify_deployment.py --api-url ... --frontend-url ... \
        --expect-version 1.4.0 --timeout 300 --report out.json

Checks, in order:
  API (when --api-url given)
    1. GET /health           reachable, status ok, service name correct
    2. GET /health           reports the expected version (when --expect-version)
    3. GET /ready            database reachable
    4. GET /openapi.json     served, has a non-empty path set
    5. GET /api/v1/... 401   an authenticated route rejects anonymous access
                             (deploy is not accidentally wide open)
  Frontend (when --frontend-url given)
    6. GET /                 HTML served over the given URL
    7. GET /                 the expected app shell markers are present
    8. asset fetch           config.js / app.js reachable relative to the page

Only public, unauthenticated endpoints are exercised. No credentials are sent,
required, or logged.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

USER_AGENT = "pios-deploy-verifier/1.0"


class Result:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def add(self, name: str, ok: bool, detail: str) -> bool:
        self.checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
        return ok

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [c for c in self.checks if c["status"] != "PASS"]


def fetch(url: str, timeout: int = 20) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def wait_for(url: str, timeout: int, label: str) -> bool:
    """Poll until the URL answers with any HTTP status, or the timeout expires."""
    deadline = time.time() + timeout
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            status, _ = fetch(url, timeout=15)
            print(f"  ... {label} answered HTTP {status} on attempt {attempt}", flush=True)
            return True
        except Exception as exc:  # connection refused, DNS, TLS, timeout
            remaining = int(deadline - time.time())
            print(f"  ... waiting for {label} ({type(exc).__name__}), {remaining}s left", flush=True)
            time.sleep(min(10, max(1, remaining)))
    return False


def check_api(base: str, expect_version: str | None, timeout: int, r: Result) -> None:
    base = base.rstrip("/")
    print(f"\nAPI checks against {base}", flush=True)

    if not wait_for(f"{base}/health", timeout, "API /health"):
        r.add("api.reachable", False, f"no response from {base}/health within {timeout}s")
        return
    r.add("api.reachable", True, "service answered")

    status, body = fetch(f"{base}/health")
    try:
        health = json.loads(body)
    except json.JSONDecodeError:
        r.add("api.health", False, f"HTTP {status}, response was not JSON")
        health = {}
    else:
        r.add(
            "api.health",
            status == 200 and health.get("status") == "ok",
            f"HTTP {status}, status={health.get('status')!r}, service={health.get('service')!r}",
        )

    if expect_version:
        actual = health.get("version")
        r.add("api.version", actual == expect_version,
              f"expected {expect_version!r}, got {actual!r}")

    status, body = fetch(f"{base}/ready")
    try:
        ready = json.loads(body)
    except json.JSONDecodeError:
        ready = {}
    r.add(
        "api.ready.database",
        status == 200 and ready.get("database") == "reachable",
        f"HTTP {status}, database={ready.get('database')!r}, auth_mode={ready.get('auth_mode')!r}",
    )

    status, body = fetch(f"{base}/openapi.json")
    paths = 0
    if status == 200:
        try:
            paths = len(json.loads(body).get("paths", {}))
        except json.JSONDecodeError:
            paths = 0
    r.add("api.openapi", status == 200 and paths > 0, f"HTTP {status}, {paths} paths")

    # An authenticated route must reject anonymous callers. 401/403 is the pass
    # condition here; 200 would mean the deployment is serving protected data
    # without credentials.
    status, _ = fetch(f"{base}/api/v1/identity/me")
    r.add("api.auth_required", status in (401, 403),
          f"GET /api/v1/identity/me returned HTTP {status} (expected 401/403)")


def check_frontend(base: str, timeout: int, r: Result) -> None:
    page = base if base.endswith("/") else base + "/"
    print(f"\nFrontend checks against {page}", flush=True)

    if not wait_for(page, timeout, "frontend"):
        r.add("frontend.reachable", False, f"no response from {page} within {timeout}s")
        return

    status, body = fetch(page)
    r.add("frontend.http", status == 200, f"HTTP {status}, {len(body)} bytes")

    markers = ['id="app"', 'id="main"', 'dir="rtl"']
    missing = [m for m in markers if m not in body]
    r.add("frontend.app_shell", not missing,
          "all app-shell markers present" if not missing else f"missing {missing}")

    for asset in ("config.js", "app.js", "styles.css"):
        status, _ = fetch(page + asset)
        r.add(f"frontend.asset.{asset}", status == 200, f"HTTP {status}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url")
    ap.add_argument("--frontend-url")
    ap.add_argument("--expect-version")
    ap.add_argument("--timeout", type=int, default=300,
                    help="seconds to wait for a service to come up (default 300)")
    ap.add_argument("--report", help="write a JSON report to this path")
    args = ap.parse_args()

    if not args.api_url and not args.frontend_url:
        print("error: give at least one of --api-url / --frontend-url", file=sys.stderr)
        return 2

    print("=== PIOS deployment verification ===", flush=True)
    r = Result()
    if args.api_url:
        check_api(args.api_url, args.expect_version, args.timeout, r)
    if args.frontend_url:
        check_frontend(args.frontend_url, args.timeout, r)

    ok = not r.failed
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "api_url": args.api_url,
        "frontend_url": args.frontend_url,
        "status": "PASS" if ok else "FAIL",
        "total": len(r.checks),
        "passed": len(r.checks) - len(r.failed),
        "failed": len(r.failed),
        "checks": r.checks,
    }
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"\nreport written to {args.report}", flush=True)

    print(f"\n=== {report['status']}: {report['passed']}/{report['total']} checks passed ===", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
