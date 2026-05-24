# Google Tasks MCP Bridge

Remote FastMCP server exposing Google Tasks to the Claude.ai custom connector.

## Architecture

```
Claude.ai connector
    ↕  MCP over Streamable HTTP + OAuth 2.1 (Auth Layer A)
Cloudflare Tunnel  →  cloudflared on fe-home
    ↕
FastMCP server, 127.0.0.1:45690, systemd, user finne
    ↕  server-held refresh token (Auth Layer B)
Google Tasks API
```

**Auth Layer A** — Google OAuth proxy (GoogleProvider). Only `finne014@gmail.com`
can authenticate. This is the only thing keeping the public endpoint private.

**Auth Layer B** — Separate server-held refresh token scoped to Tasks. Generated
once via `scripts/bootstrap_tasks_token.py`. Independent of who is connected.

**No Cloudflare Access** in front of the tunnel — it would intercept the
connector's own OAuth discovery and break the flow. Auth Layer A is the sole gate.

---

## File layout

```
.env                          # secrets (never committed)
.env.example                  # template
layer_b_client_secrets.json   # GCP Desktop-app OAuth client (chmod 600)
token.json                    # Tasks refresh token (chmod 600, bootstrap once)
src/tasks_bridge/
  config.py                   # env loading + allowlist validation
  google_tasks.py             # Layer B: Tasks API client
  resolve.py                  # name→id resolver (used by all tools)
  tools.py                    # all 11 MCP tools
  auth.py                     # AllowlistGoogleProvider (Layer A gate)
  server.py                   # FastMCP HTTP server + /health
scripts/bootstrap_tasks_token.py
deploy/tasks-bridge.service
deploy/tunnel-ingress.example.yml
```

---

## First-time setup (on the hosting machine, fe-home)

### 1. Clone / copy the project

Copy the whole directory to fe-home. See **Transfer checklist** below for what
files to include.

### 2. Python environment

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

### 3. Secret files

These are **not in git**. Copy them from the dev machine or re-create:

| File | What it is | How to get it |
|------|-----------|---------------|
| `.env` | All config + secrets | Copy from dev machine (or re-fill from `.env.example`) |
| `layer_b_client_secrets.json` | GCP Desktop OAuth client | Download from GCP Console |
| `token.json` | Tasks refresh token | Run `bootstrap_tasks_token.py` |

Check permissions after copying:
```bash
chmod 600 .env layer_b_client_secrets.json token.json
```

### 4. Bootstrap the Tasks token (Layer B) — if not copying from dev machine

```bash
.venv/bin/python scripts/bootstrap_tasks_token.py
```

Prints a URL — open it in a browser. Authorises the server to read/write Tasks.
Saves `token.json`. Only needed once (token auto-refreshes). Re-run if you see
`invalid_grant` errors (Google revokes after ~6 months inactivity).

### 5. GCP OAuth client for Auth Layer A

The **Web application** OAuth client (`layer_a`) must have this redirect URI registered:
```
https://google-tasks.fmje.dev/auth/callback
```
This is already done. The client ID and secret are in `.env`.

### 6. Cloudflare Tunnel

See `deploy/tunnel-ingress.example.yml`. Add an ingress rule pointing
`google-tasks.fmje.dev` → `http://localhost:45690`.

**Determine first** whether your tunnel is config-file managed or dashboard managed:
- Config-file: edit `~/.cloudflared/config.yml`, add the ingress entry, restart cloudflared.
- Dashboard: Cloudflare Zero Trust → Networks → Tunnels → edit → add Public Hostname.

After adding: verify `https://google-tasks.fmje.dev/health` returns `{"status":"ok"}`.

### 7. systemd service

```bash
# Copy the unit file
cp deploy/tasks-bridge.service ~/.config/systemd/user/

# Enable and start
systemctl --user daemon-reload
systemctl --user enable tasks-bridge
systemctl --user start tasks-bridge
systemctl --user status tasks-bridge

# View logs
journalctl --user -u tasks-bridge -f
```

The service runs as user `finne`, binds only `127.0.0.1:45690`, and restarts on failure.

### 8. Add to Claude.ai as a custom connector

1. claude.ai → Settings → Integrations → Add custom integration
2. URL: `https://google-tasks.fmje.dev`
3. Claude will trigger an OAuth flow — sign in as `finne014@gmail.com`
4. Verify `list_task_lists` returns your real lists

---

## Tools reference

| Tool | Purpose |
|------|---------|
| `list_task_lists` | All lists |
| `list_tasks(list_id)` | General view — flat + nested, no dropped childless tasks |
| `list_tasks_by_category(list_id, category_ids?)` | Parent-as-category view (Satura-style) |
| `get_task(list_id, task_id)` | One task, full notes |
| `create_task(list_id, title, notes?, due?, parent_id?)` | Create task/subtask |
| `update_task(list_id, task_id, title?, notes?, due?)` | Partial merge edit |
| `complete_task(list_id, task_id)` | Mark done |
| `uncomplete_task(list_id, task_id)` | Mark not done, clears hidden flag |
| `delete_task(list_id, task_id)` | Delete by id only (no fuzzy) |
| `search_tasks(query, regex?, lists?, parents?, include_completed?)` | Cross-list search |
| `create_task_list(name)` | New list |

All `list_id` parameters accept a **name or id** (case-insensitive, substring match).

### `search_tasks` modes
- Default (`regex=False`): plain substring, metacharacters are literal — safe for queries like `2.5 flash` or `satura.dev`
- `regex=True`: Python regex, case-insensitive; returns `{"error": "invalid_regex", ...}` on bad pattern

---

## Migration from old local server

The old stdio server (`~/.claude/mcp-servers/google-tasks-mcp/`) is replaced.
**Satura skill changes required:**

| Old | New |
|-----|-----|
| `list_tasks(list_id, parent_ids=...)` | `list_tasks_by_category(list_id, category_ids=...)` |
| `update_task(..., status="completed")` | `complete_task(list_id, task_id)` |
| `update_task(..., status="needsAction")` | `uncomplete_task(list_id, task_id)` |
| Returned formatted strings | Returns structured JSON dicts |

`list_id` and `task_id` parameters work the same (still accept ids; now also accept names).

---

## Known limitations

- `due` is date-only (`YYYY-MM-DD`). No timed reminders — Google Tasks has no alarms.
- Re-parenting / reordering tasks not supported (requires the Tasks `move` endpoint, out of scope v1).
- Subtasks nest one level only (Google's limit).
- Text search is client-side (no server-side search in the API).
- The endpoint's security rests entirely on Auth Layer A's email allowlist. Test the negative case after deploy.

---

## Transfer checklist

Files to copy to fe-home (everything not in git):

```
.env                          (chmod 600)
layer_b_client_secrets.json   (chmod 600)
token.json                    (chmod 600)
```

Everything else (`src/`, `scripts/`, `deploy/`, `pyproject.toml`, etc.) is in git
and should be cloned/pulled on fe-home.
