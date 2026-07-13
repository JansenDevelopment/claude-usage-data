#!/usr/bin/env python3
"""Fetch your live Claude usage from claude.ai and push it to a jsonbin.io bin.

Uses a logged-in, persistent browser context (~/.claude_session) to query the
internal endpoint https://claude.ai/api/organizations/<org>/usage, which returns
the real session utilization + reset time. Runs headless, writes to the cloud and
exits -- no server, no open port. The Tidbyt app (claudeusage.star) reads that
jsonbin bin remotely.

Note: the /usage endpoint is internal/unofficial and may change. It runs on your
own logged-in session; keep ~/.claude_session and your jsonbin key private
(never commit them).

Requires:  pip install playwright  &&  playwright install chromium

Usage:
    python push_usage.py --login       # one-time: opens a browser, log in, press ENTER
    python push_usage.py --dump-state  # export the session as storage_state.json (for CI)
    python push_usage.py --show        # print the raw usage JSON (for debugging)
    python push_usage.py               # fetch -> map -> push (jsonbin or a local file)

Config comes from env vars (Windows: setx) or from usage_config.json next to this
script (git-ignored, keep private):
    JSONBIN_BIN_ID      / bin_id        your jsonbin bin id
    JSONBIN_ACCESS_KEY  / access_key    a read/write jsonbin access key
    JSONBIN_MASTER_KEY  / master_key    (alternative to the access key)
    CLAUDE_USAGE_URL    / usage_url     https://claude.ai/api/organizations/<org>/usage
    CLAUDE_SESSION_STATE/ session_state Playwright storage_state JSON -- use this instead
                                        of ~/.claude_session (e.g. in GitHub Actions)
    USAGE_OUTPUT_FILE   / output_file   write the payload to this file instead of jsonbin
                                        (for the git-commit / raw-URL flow)

See README.md for how to find your <org> id and set everything up.
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

USER_DATA_DIR = os.path.join(os.path.expanduser("~"), ".claude_session")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _load_config_file():
    """Local config next to this script (usage_config.json). Lets the push work
    even when env vars aren't in the process (e.g. a hook started before a
    restart). Do not commit -- it's in .gitignore."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage_config.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_CFG = _load_config_file()

# Env var wins; otherwise the local config file.
BIN_ID = os.environ.get("JSONBIN_BIN_ID") or _CFG.get("bin_id")
MASTER_KEY = os.environ.get("JSONBIN_MASTER_KEY") or _CFG.get("master_key")
# A read/write/update access key also works (scoped, safer than the master key).
ACCESS_KEY = os.environ.get("JSONBIN_ACCESS_KEY") or _CFG.get("access_key")
# Your org-specific usage endpoint (no personal default -- set via env/config).
USAGE_URL = os.environ.get("CLAUDE_USAGE_URL") or _CFG.get("usage_url")
# Playwright storage_state (cookies + localStorage) as JSON. When set we use a
# normal browser context with this state instead of the persistent
# ~/.claude_session dir -- that's how CI (no user profile on disk) authenticates.
SESSION_STATE = os.environ.get("CLAUDE_SESSION_STATE") or _CFG.get("session_state")
# When set, write the payload to this local file instead of pushing to jsonbin.
# The GitHub Actions flow commits that file and the app reads it via a raw URL.
OUTPUT_FILE = os.environ.get("USAGE_OUTPUT_FILE") or _CFG.get("output_file")

# Number of samples kept for the trend line (one point per push).
HISTORY_MAX = 120


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "Playwright is missing. Install it with:\n"
            "    pip install playwright\n"
            "    playwright install chromium"
        )
    return sync_playwright


def login():
    sync_playwright = _playwright()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR, headless=False, user_agent=UA
        )
        page = ctx.new_page()
        page.goto("https://claude.ai")
        print("Log in inside the browser (magic link).")
        print("Once you see the chat: LEAVE THE BROWSER OPEN and press ENTER here...")
        input()
        try:
            ctx.close()
        except Exception:
            # User already closed the window; the persistent context writes the
            # session to disk live, so it's saved anyway.
            pass
    print("Session saved to", USER_DATA_DIR)


def _session_state_dict():
    """The configured storage_state as a dict, or None to use ~/.claude_session."""
    if not SESSION_STATE:
        return None
    if isinstance(SESSION_STATE, dict):
        return SESSION_STATE
    try:
        return json.loads(SESSION_STATE)
    except (TypeError, ValueError):
        sys.exit(
            "CLAUDE_SESSION_STATE is not valid JSON -- it should be the output of "
            "`python push_usage.py --dump-state`."
        )


def dump_state(path):
    """Export the logged-in session (~/.claude_session) as a Playwright
    storage_state JSON. Paste its contents into the CLAUDE_SESSION_STATE secret so
    CI can authenticate without the on-disk profile."""
    sync_playwright = _playwright()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR, headless=True, user_agent=UA
        )
        try:
            state = ctx.storage_state()
        finally:
            ctx.close()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    print("Session state written to", path)
    print("Copy its FULL contents into the GitHub secret CLAUDE_SESSION_STATE.")
    print("Keep it private -- it grants access to your claude.ai session.")


def _fetch_with_context(ctx):
    """The actual usage request: cheap API request first, real navigation as a
    fallback (which runs any JS / Cloudflare challenge)."""
    r = ctx.request.get(USAGE_URL)
    if r.status == 200:
        return r.json()
    page = ctx.new_page()
    resp = page.goto(USAGE_URL)
    if resp and resp.ok:
        return json.loads(page.inner_text("body"))
    raise RuntimeError(
        "usage endpoint: request=%s nav=%s -- session expired? refresh it with "
        "--login (local) or --dump-state -> CLAUDE_SESSION_STATE (CI)"
        % (r.status, resp.status if resp else "none")
    )


def fetch():
    """Live usage JSON via the logged-in headless context.

    Uses the storage_state from CLAUDE_SESSION_STATE when set (CI), otherwise the
    persistent ~/.claude_session profile (local)."""
    if not USAGE_URL:
        sys.exit(
            "No usage URL configured. Set CLAUDE_USAGE_URL (or 'usage_url' in "
            "usage_config.json) to\n"
            "    https://claude.ai/api/organizations/<org>/usage\n"
            "See README.md for how to find your <org> id."
        )
    sync_playwright = _playwright()
    state = _session_state_dict()
    with sync_playwright() as p:
        if state is not None:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=UA, storage_state=state)
            try:
                return _fetch_with_context(ctx)
            finally:
                ctx.close()
                browser.close()
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR, headless=True, user_agent=UA
        )
        try:
            return _fetch_with_context(ctx)
        finally:
            ctx.close()


def _norm_ts(s):
    """To strict RFC3339-Z (no microseconds), which Starlark parses reliably."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return s  # unknown format: leave as-is, the app tries to parse it anyway
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract(data):
    """Map the claude.ai usage JSON to {active, percent, reset_at}.

    We show the 5-hour session block: five_hour.utilization + resets_at. Falls
    back to the "session" entry in the limits list if five_hour is missing.
    """
    fh = data.get("five_hour") or {}
    util = fh.get("utilization")
    reset_at = fh.get("resets_at")

    if util is None:
        for lim in data.get("limits") or []:
            if lim.get("kind") == "session":
                util = lim.get("percent")
                reset_at = lim.get("resets_at")
                break

    if util is None:
        return None

    return {
        "active": True,
        "percent": int(round(float(util))),
        "reset_at": _norm_ts(reset_at),
    }


def _auth_headers():
    headers = {"User-Agent": UA}
    if ACCESS_KEY:
        headers["X-Access-Key"] = ACCESS_KEY
    elif MASTER_KEY:
        headers["X-Master-Key"] = MASTER_KEY
    return headers


def _history_from_record(rec):
    """Pull valid {t, p} history points out of a record (older formats ignored)."""
    hist = rec.get("history") if isinstance(rec, dict) else None
    if not isinstance(hist, list):
        return []
    out = []
    for x in hist:
        if isinstance(x, dict) and "t" in x and "p" in x:
            out.append({"t": x["t"], "p": int(x["p"])})
    return out


def read_prev():
    """Read the existing state: (history, last_percent, last_reset). From the output
    file in file mode, otherwise from the jsonbin bin. Empty/None if unreadable."""
    rec = None
    if OUTPUT_FILE:
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                rec = json.load(f)
        except Exception:
            rec = None
    elif BIN_ID:
        req = urllib.request.Request(
            "https://api.jsonbin.io/v3/b/%s/latest" % BIN_ID, headers=_auth_headers()
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            rec = raw.get("record", raw) if isinstance(raw, dict) else {}
        except Exception:
            rec = None
    history = _history_from_record(rec)
    last_p = history[-1]["p"] if history else None
    last_reset = rec.get("reset_at") if isinstance(rec, dict) else None
    return history, last_p, last_reset


def push(payload):
    if OUTPUT_FILE:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        print("wrote %s: %s" % (OUTPUT_FILE, json.dumps(payload)))
        return
    if not BIN_ID or not (MASTER_KEY or ACCESS_KEY):
        print("[dry-run] JSONBIN_BIN_ID + MASTER_KEY/ACCESS_KEY not set -- not pushed.")
        print("[dry-run] payload:", json.dumps(payload))
        return
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Bin-Versioning": "false",
        # Without a browser User-Agent Cloudflare blocks with "error code: 1010".
        "User-Agent": UA,
    }
    # Access key wins (scoped); otherwise the master key.
    if ACCESS_KEY:
        headers["X-Access-Key"] = ACCESS_KEY
    else:
        headers["X-Master-Key"] = MASTER_KEY
    req = urllib.request.Request(
        "https://api.jsonbin.io/v3/b/" + BIN_ID,
        data=body,
        method="PUT",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print("pushed (%s): %s" % (resp.status, json.dumps(payload)))
    except Exception as ex:
        print("push failed: %s" % ex, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Push Claude usage to jsonbin or a file")
    ap.add_argument("--login", action="store_true", help="one-time browser login")
    ap.add_argument(
        "--dump-state",
        nargs="?",
        const="storage_state.json",
        metavar="PATH",
        help="export the session as a storage_state JSON (for the CI secret)",
    )
    ap.add_argument("--show", action="store_true", help="print the raw usage JSON")
    args = ap.parse_args()

    if args.login:
        login()
        return 0

    if args.dump_state:
        dump_state(args.dump_state)
        return 0

    data = fetch()

    if args.show:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    payload = extract(data)
    if payload is None:
        print(
            "Unknown JSON structure -- mapping did not match.\n"
            "Run `python push_usage.py --show` and inspect the output.",
            file=sys.stderr,
        )
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 1

    history, last_p, last_reset = read_prev()

    # Nothing changed since the last push (same percent and same reset window)?
    # Then don't touch the target -- it would only add a duplicate history point.
    # A new session resets the percent and reset_at, so that still gets pushed,
    # and the app's countdown keeps ticking on its own from reset_at.
    if last_p is not None and payload["percent"] == last_p and payload["reset_at"] == last_reset:
        print("unchanged (%d%%, reset %s) -- not pushed." % (last_p, last_reset))
        return 0

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    history.append({"t": now_iso, "p": payload["percent"]})
    payload["history"] = history[-HISTORY_MAX:]

    push(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
