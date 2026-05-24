"""FastMCP server: HTTP transport, auth wiring, tool registration, health route."""

from __future__ import annotations

import logging
import logging.config

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from tasks_bridge import config
from tasks_bridge.auth import AllowlistGoogleProvider
from tasks_bridge.tools import register_tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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
    """Return the Starlette ASGI app with an added /health route."""
    mcp = build_app(with_auth=with_auth)

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "server": "google-tasks-bridge"})

    http_app = mcp.http_app(transport="streamable-http")
    # Inject /health at the Starlette router level
    http_app.router.routes.insert(0, Route("/health", health, methods=["GET"]))
    return http_app


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Google Tasks Bridge on port %d", config.PORT)
    app = build_starlette_app()
    uvicorn.run(app, host="127.0.0.1", port=config.PORT, log_level="info")
