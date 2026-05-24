"""Auth Layer A: GoogleProvider subclass with email allowlist."""

from __future__ import annotations

import logging

from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider

from tasks_bridge import config

logger = logging.getLogger(__name__)


class AllowlistGoogleProvider(GoogleProvider):
    """
    Google OAuth provider restricted to a configured email allowlist.

    On every token validation the email claim is checked. If the email is
    absent or not in the allowlist, the token is rejected as if it were
    invalid. This is the only gate keeping the public endpoint private.

    An empty or missing ALLOWED_EMAILS config raises at startup (see config.py)
    so the server never runs open.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not config.ALLOWED_EMAILS:
            raise RuntimeError(
                "ALLOWED_EMAILS is empty — server would reject all users. "
                "Set at least one email in .env."
            )
        logger.info(
            "AllowlistGoogleProvider initialised; %d allowed email(s)",
            len(config.ALLOWED_EMAILS),
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        validated = await super().load_access_token(token)
        if validated is None:
            return None

        email = (validated.claims or {}).get("email")
        if not email:
            logger.warning("Auth rejected: token has no email claim")
            return None

        if email.lower() not in config.ALLOWED_EMAILS:
            logger.warning("Auth rejected: email %s not in allowlist", email)
            return None

        return validated
