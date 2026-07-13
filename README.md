# claude-usage-data

Feeds the **Claude Usage** Tidbyt app. A free GitHub Actions cron reads your live
claude.ai session usage and writes `usage.json` to this repo's **`data`** branch; the
app reads it over a raw GitHub URL — **no laptop and no jsonbin needed.**

> The app itself is just a small JSON reader and lives in the *community-apps* repo
> (`apps/usage/`). **This** repo is only the data producer.

## How it works

- `push_usage.py` queries the internal `/usage` endpoint as **your logged-in claude.ai
  session** and maps it to `{active, percent, reset_at, history}`.
- `.github/workflows/push-usage.yml` runs it every ~10 min and force-pushes
  `usage.json` as a single commit to the `data` branch.
- Your app reads:
  ```
  https://raw.githubusercontent.com/<your-username>/claude-usage-data/data/usage.json
  ```

## Privacy first

A public `data` branch **publishes your usage % and reset time to anyone** (and it
stays in git history / the CDN). That's not a secret or token — but it *is* personal
telemetry. If that's not OK for you, this cloud route isn't a fit; run the pump on a
home device instead (see the bottom).

## Set it up — fork & go

1. **Fork this repo.** Keep the fork **public** (the app reads the raw URL without a
   key).
2. **Enable Actions on your fork** ⚠️ — forks have Actions **disabled by default**.
   Open the **Actions** tab and click *"I understand my workflows, go ahead and enable
   them."*
3. **Export your claude.ai session** on your PC (one-time):
   ```
   pip install playwright
   playwright install chromium
   python push_usage.py --login        # log in, LEAVE the browser open, press ENTER
   python push_usage.py --dump-state   # writes storage_state.json
   ```
   Keep `storage_state.json` private — it grants access to your claude.ai session.
4. **Find your org UUID** — logged into claude.ai, open
   `https://claude.ai/api/organizations` and copy the `uuid`. Your usage URL is
   `https://claude.ai/api/organizations/<UUID>/usage`.
5. **Create a fine-grained PAT** at
   <https://github.com/settings/personal-access-tokens> → **Generate new token**:
   - **Resource owner:** you
   - **Repository access → Only select repositories:** your fork
   - **Permissions → Repository → Contents: Read and write** (nothing else)

   (This lets the data commits count as activity, so the cron isn't auto-disabled after
   60 days of inactivity.)
6. **Add three repo secrets** (your fork → Settings → Secrets and variables → Actions →
   *New repository secret*):

   | Secret | Value |
   | --- | --- |
   | `CLAUDE_SESSION_STATE` | the full contents of `storage_state.json` |
   | `CLAUDE_USAGE_URL` | `https://claude.ai/api/organizations/<UUID>/usage` |
   | `DATA_PUSH_PAT` | the fine-grained PAT from step 5 |

7. **Run it** — Actions → *push-usage* → **Run workflow**. Check the log:
   - success = the usage JSON came back and `usage.json` appears on the `data` branch;
   - a Cloudflare *"checking your browser"* page or a non-200 status = the runner's
     datacenter IP was blocked (see below).
8. **Point the app** — set the app's `api_url` to your raw URL (see *How it works*).
   Leave `read_key` empty.

After that the cron takes over (~every 10 min) and the app's trend line fills in.

## Good to know

- **The session expires** (weeks). When a run fails with *"session expired?"*, redo
  step 3 on your PC and update the `CLAUDE_SESSION_STATE` secret.
- **Cloudflare / datacenter IP:** the `/usage` endpoint sits behind Cloudflare, which
  challenges GitHub's datacenter IPs more often than a home IP. If the runner is
  blocked, run `push_usage.py` on a **home device** instead (Raspberry Pi, NAS, Home
  Assistant — on a cron/scheduler) and let it push `usage.json` from there.
- **The `/usage` endpoint is internal and unofficial** — it may change without notice.

## Files

| file | role |
| --- | --- |
| `push_usage.py` | reads your usage and writes `usage.json` (also supports a jsonbin bin) |
| `.github/workflows/push-usage.yml` | the cron that runs it and commits the data |
