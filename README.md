# claude-usage-data

Runs [`push_usage.py`](push_usage.py) on a free GitHub Actions cron and stores the
result as `usage.json` on the **`data`** branch. A Tidbyt "Claude Usage" app reads it
over a raw URL — no laptop and no jsonbin needed.

The app reads:

```
https://raw.githubusercontent.com/JansenDevelopment/claude-usage-data/data/usage.json
```

> **The one real risk:** GitHub runners use datacenter IPs, which Cloudflare
> challenges more often than a home IP. The fetch that works on your PC *may* be
> blocked here. Test with **Run workflow** first (step 5). If it's blocked, run the
> pump on a home device (Pi/NAS/Home Assistant) instead — same script.

## One-time setup

1. **Export your session** on your PC (needs the `~/.claude_session` from a prior
   `python push_usage.py --login`):

   ```
   python push_usage.py --dump-state
   ```

   This writes `storage_state.json`. Keep it private — it grants access to your
   claude.ai session.

2. **Create a fine-grained PAT** (GitHub → Settings → Developer settings →
   Fine-grained tokens): access limited to **only this repo**, permission
   **Contents: Read and write**.

3. **Add three repo secrets** (Settings → Secrets and variables → Actions → New
   repository secret):

   | Secret | Value |
   | --- | --- |
   | `CLAUDE_SESSION_STATE` | the full contents of `storage_state.json` |
   | `CLAUDE_USAGE_URL` | `https://claude.ai/api/organizations/<UUID>/usage` |
   | `DATA_PUSH_PAT` | the fine-grained PAT from step 2 |

   Find `<UUID>`: logged into claude.ai, open `https://claude.ai/api/organizations`
   and copy the `uuid`.

4. **Point the app** — set the app's `api_url` to the raw URL above. Leave `read_key`
   empty (this repo is public).

5. **Test it** — Actions → *push-usage* → **Run workflow**. In the run log:
   - success = the usage JSON came back and `usage.json` appears on the `data` branch;
   - a Cloudflare "checking your browser" page or a non-200 status = the datacenter IP
     was blocked → use a home runner instead.

   After that the cron takes over (every ~10 min) and the app's trend line fills in.

## Refreshing the session

The stored session eventually expires (weeks). When a run starts failing with
"session expired?", redo step 1 on your PC and update the `CLAUDE_SESSION_STATE`
secret.
