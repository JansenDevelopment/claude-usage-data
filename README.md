# claude-usage-data

Feeds the **Claude Usage** Tidbyt app. A free GitHub Actions cron reads your live
claude.ai session usage and publishes it, so you need no always-on laptop.

There are **two routes** — the workflow auto-detects which one you're on:

| | Route A — Raw URL | Route B — jsonbin |
| --- | --- | --- |
| Extra service | none | a free jsonbin.io bin |
| App reads | the `data` branch raw URL | the jsonbin bin |
| Freshness | ~cron cadence + ~5 min CDN cache | near real-time; a laptop hook can add per-turn updates |
| Reads count against | nothing (GitHub CDN) | jsonbin's request quota |
| Setup | 3 secrets | 5 secrets |

Route A is the simplest fork-and-go. Route B is more precise (and lets a laptop
Stop hook feed the same store), at the cost of jsonbin's request limit. You can start
on A and switch to B later just by adding two secrets.

> **Heads-up:** GitHub's scheduled cron is *best-effort* — it's often much later than
> every 10 min, and sometimes skips hours. The app recomputes the countdown live from
> `reset_at`, so that's usually fine; on Route B a laptop hook keeps it fresh between
> runs. Also: the runner's datacenter IP can hit a Cloudflare challenge where your home
> IP doesn't — test with **Run workflow** first.

## Common setup (both routes)

1. **Fork this repo**, keep it **public** (so the raw URL / a public bin is readable).
2. **Enable Actions on your fork** ⚠️ — forks have Actions **disabled by default**.
   Open the **Actions** tab and click *"I understand my workflows, go ahead and enable
   them."*
3. **Export your claude.ai session** on your PC (one-time):
   ```
   pip install playwright
   playwright install chromium
   python push_usage.py --login        # log in, LEAVE the browser open, press ENTER
   python push_usage.py --dump-state   # writes storage_state.json (keep it private)
   ```
4. **Find your org UUID** — logged into claude.ai, open
   `https://claude.ai/api/organizations` and copy the `uuid`. Your usage URL is
   `https://claude.ai/api/organizations/<UUID>/usage`.
5. **Create a fine-grained PAT** at
   <https://github.com/settings/personal-access-tokens> → **Generate new token**:
   resource owner = you, repository access = **only your fork**, permission
   **Contents: Read and write**. (Keeps the data-branch commit as activity so the cron
   isn't auto-disabled after 60 days.)
6. **Add these repo secrets** (your fork → Settings → Secrets and variables → Actions):

   | Secret | Value |
   | --- | --- |
   | `CLAUDE_SESSION_STATE` | the full contents of `storage_state.json` |
   | `CLAUDE_USAGE_URL` | `https://claude.ai/api/organizations/<UUID>/usage` |
   | `DATA_PUSH_PAT` | the fine-grained PAT from step 5 |

## Route A — Raw URL (simplest)

No extra secrets. The workflow writes `usage.json` to the `data` branch each run.

- **Point the app** — set `api_url` to
  `https://raw.githubusercontent.com/<your-username>/claude-usage-data/data/usage.json`,
  `read_key` empty.
- **Run it** — Actions → *push-usage* → **Run workflow**; confirm `usage.json` appears
  on the `data` branch.

## Route B — jsonbin (central, freshest)

1. **Create a free [jsonbin.io](https://jsonbin.io) bin**; note the **Bin ID** and a
   **read/write Access Key**. Make it **public** (app reads without a key) or private
   (use a read-only key in the app's `read_key`).
2. **Add two more secrets:** `JSONBIN_BIN_ID` and `JSONBIN_ACCESS_KEY`.
   The workflow now pushes to jsonbin (deduped) and mirrors it to the `data` branch.
3. **Point the app** — set `api_url` to `https://api.jsonbin.io/v3/b/<BIN_ID>/latest`
   (private bin → read-only key in `read_key`; public → empty).
4. **(Optional) Laptop Stop hook** — for per-turn freshness, run the same pump on your
   PC after each Claude Code turn, writing to the *same* bin. Put `bin_id`,
   `access_key` and `usage_url` in a `usage_config.json` next to `push_usage.py`
   (git-ignored), and add to `~/.claude/settings.json`:
   ```json
   { "hooks": { "Stop": [ { "hooks": [ { "type": "command",
     "command": "python \"/path/to/push_usage.py\"", "async": true } ] } ] } }
   ```
   Both writers dedup against the shared bin, so no duplicate points.

## Good to know

- **The session expires** (weeks). When a run fails with *"session expired?"*, redo the
  `--dump-state` step on your PC and update the `CLAUDE_SESSION_STATE` secret.
- **Privacy:** a public `data` branch or public bin **publishes your usage % and reset
  time** to anyone with the URL. Not a secret/token, but personal telemetry.
- **jsonbin quota (Route B):** the app polling jsonbin is the biggest consumer of your
  request quota — watch it, or stay on Route A (CDN reads are free).
- **The `/usage` endpoint is internal and unofficial** — it may change without notice.

## Files

| file | role |
| --- | --- |
| `push_usage.py` | reads your usage; writes to jsonbin or a local file (deduped) |
| `.github/workflows/push-usage.yml` | the cron that runs it and publishes the data |
