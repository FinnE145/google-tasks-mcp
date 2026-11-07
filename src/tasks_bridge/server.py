"""FastMCP server: HTTP transport, auth wiring, tool registration, health route."""

from __future__ import annotations

import logging
import logging.config

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from tasks_bridge import config
from tasks_bridge.auth import AllowlistGoogleProvider
from tasks_bridge.tools import register_tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
# httpx logs every request URL at INFO, and FastMCP's Google check sends the access token in the query string
# (oauth2.googleapis.com/tokeninfo?access_token=...), so at INFO the tokens ended up in the log.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


# Google requires a privacy policy link to publish the OAuth consent screen.
PRIVACY_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Google Tasks Bridge: privacy</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5">
<h1>Google Tasks Bridge: privacy</h1>
<p>This is a personal, single-user server. It connects one person's Claude.ai account to that same person's
Google Tasks. Sign-in is restricted to an allowlist containing only the owner's Google account; nobody else can
use it.</p>
<ul>
<li><strong>What it accesses:</strong> the owner's Google Tasks (read and write) and the email address of the
Google account signing in, which is checked against the allowlist.</li>
<li><strong>What it stores:</strong> OAuth tokens for the owner's account, on the owner's own server. It keeps no
copy of task contents.</li>
<li><strong>Where data goes:</strong> task data is sent only to the owner's own Claude.ai session that requested it.
Nothing is sold, shared with anyone else, or used for advertising.</li>
<li><strong>Removing access:</strong> revoke it at any time at
<a href="https://myaccount.google.com/connections">myaccount.google.com/connections</a>.</li>
</ul>
<p>Source: <a href="https://github.com/FinnE145/google-tasks-mcp">github.com/FinnE145/google-tasks-mcp</a>.</p>
</body></html>
"""


def build_app(with_auth: bool = True) -> FastMCP:
    if with_auth:
        auth = AllowlistGoogleProvider(
            client_id=config.LAYER_A_CLIENT_ID,
            client_secret=config.LAYER_A_CLIENT_SECRET,
            base_url=config.BASE_URL,
            required_scopes=["openid", "email"],
        )
        mcp = FastMCP("Google Tasks Bridge", auth=auth)
    else:
        mcp = FastMCP("Google Tasks Bridge")

    register_tools(mcp)
    return mcp


def build_starlette_app(with_auth: bool = True):
    """Return the Starlette ASGI app with added /health and /privacy routes."""
    mcp = build_app(with_auth=with_auth)

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "server": "google-tasks-bridge"})

    async def privacy(request: Request) -> HTMLResponse:
        return HTMLResponse(PRIVACY_HTML)

    http_app = mcp.http_app(transport="streamable-http")
    # Inject /health and /privacy at the Starlette router level (no login needed)
    http_app.router.routes.insert(0, Route("/health", health, methods=["GET"]))
    http_app.router.routes.insert(0, Route("/privacy", privacy, methods=["GET"]))
    return http_app


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Google Tasks Bridge on port %d", config.PORT)
    app = build_starlette_app()
    uvicorn.run(app, host="127.0.0.1", port=config.PORT, log_level="info")
