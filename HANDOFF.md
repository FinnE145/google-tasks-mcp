# Handoff note for fe-home Claude instance

This document is for the Claude Code session that picks up this project on **fe-home**
(the final hosting machine). Read this before reading the original spec.

---

## What's been built (on Finn's laptop)

All code is complete through Phase 3 of the spec. Everything works locally:

- `src/tasks_bridge/` — full tool surface (all 11 tools from §7 of the spec)
- `src/tasks_bridge/auth.py` — `AllowlistGoogleProvider` (Google OAuth proxy + email allowlist)
- `src/tasks_bridge/server.py` — FastMCP Streamable HTTP server on port 45690
- `src/tasks_bridge/google_tasks.py` — Layer B Tasks API client
- `src/tasks_bridge/resolve.py` — name→id resolver
- `scripts/bootstrap_tasks_token.py` — one-time Layer B token bootstrap
- `deploy/tasks-bridge.service` — systemd unit
- `deploy/tunnel-ingress.example.yml` — Cloudflare Tunnel config example
- `.venv/` — Python 3.13 venv with all deps installed (re-create on fe-home)
- `token.json` — Layer B Tasks refresh token (copy from laptop, or re-bootstrap)

**Local smoke test passed:** Streamable HTTP transport verified, `list_task_lists`
returns Finn's real 4 task lists through the MCP protocol.

---

## What still needs doing on fe-home (in spec order)

### Phase 1 remainder — tunnel + connector validation

The spec's Phase 1 acceptance criterion ("From Claude.ai, `list_task_lists` returns
Finn's real lists through the tunnel") requires the tunnel to be set up and the server
running on fe-home. Do this **before** adding auth.

Steps:
1. Copy files (see Transfer checklist in README.md)
2. Re-create venv: `python3 -m venv .venv && .venv/bin/pip install -e .`
3. Determine tunnel management mode (config-file vs dashboard) — check
   `~/.cloudflared/config.yml` or `/etc/cloudflared/config.yml`. Report which it is.
4. Add tunnel ingress: `google-tasks.fmje.dev` → `http://localhost:45690`
   (see `deploy/tunnel-ingress.example.yml`)
5. Start server **without auth** for initial validation:
   ```bash
   AUTH=off .venv/bin/python -m tasks_bridge.server
   ```
   (or temporarily set `with_auth=False` in server.py — revert after Phase 1)
6. Verify `https://google-tasks.fmje.dev/health` returns `{"status":"ok"}`
7. Add as Claude.ai custom connector (no auth yet), confirm `list_task_lists` works

### Phase 2 — Auth Layer A

Once Phase 1 passes, re-enable auth (default) and reconnect the Claude.ai connector.
The connector will trigger Google OAuth. Sign in as `finne014@gmail.com`.

**Critical:** `https://google-tasks.fmje.dev/auth/callback` must be reachable through
the tunnel. If discovery 404s or the OAuth callback fails, **stop and report the
specific failure** — do not add Cloudflare Access as a workaround (see spec §13).

Acceptance: connector completes OAuth, `list_task_lists` works only when authenticated
as Finn, another Google account is rejected.

### Phase 4 — Productionize

After Phase 2 passes:
```bash
cp deploy/tasks-bridge.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tasks-bridge
```

Verify it survives reboot (`systemctl --user status tasks-bridge`).

---

## Differences from the original spec

| Spec says | What was actually built |
|-----------|------------------------|
| New project dir `tasks-bridge` (suggested name) | Built in `google-tasks-mcp` (Finn's existing project repo) |
| `uv` for env/deps | Standard `python3 -m venv` + `pip` (no uv on Finn's machine) |
| Python 3.12+ | Python 3.13 on laptop; ensure 3.12+ on fe-home |
| Phase 1 & 2 validated from Claude.ai | Transport validated locally; connector validation needs fe-home |
| `delete_task_list` deliberately omitted | Confirmed omitted as specified |
| `update_task` does NOT change parent or status | Confirmed — dedicated `complete_task`/`uncomplete_task` tools exist |

## GCP project details

- Project: `tasks-mcp-494320`
- Layer A OAuth client (Web app): `31889332847-vrrfqka7s9mvjq2hv82ursmvksmlksg1.apps.googleusercontent.com`
  - Redirect URI registered: `https://google-tasks.fmje.dev/auth/callback`
- Layer B OAuth client (Desktop): `31889332847-jk6acjmvtv7hemttr8bb702pipt2rtk0.apps.googleusercontent.com`
- Tasks API: enabled on project `tasks-mcp-494320`

## Files to transfer (not in git)

```
.env                          (chmod 600) — contains Layer A+B secrets
layer_b_client_secrets.json   (chmod 600) — Layer B GCP client JSON
token.json                    (chmod 600) — Layer B Tasks refresh token
```

The `token.json` from the laptop will work on fe-home. If you re-bootstrap
instead, use the same `layer_b_client_secrets.json` and run:
```bash
.venv/bin/python scripts/bootstrap_tasks_token.py
```
