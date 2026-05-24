"""Load and validate configuration from environment / .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file)
_project_root = Path(__file__).parent.parent.parent
load_dotenv(_project_root / ".env")


def _require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(f"Required env var {name!r} is not set. See .env.example.")
    return val


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# Auth Layer A
LAYER_A_CLIENT_ID: str = _require("LAYER_A_CLIENT_ID")
LAYER_A_CLIENT_SECRET: str = _require("LAYER_A_CLIENT_SECRET")

# Auth Layer B
LAYER_B_CLIENT_SECRETS_FILE: Path = Path(_require("LAYER_B_CLIENT_SECRETS_FILE"))
TASKS_TOKEN_FILE: Path = Path(_require("TASKS_TOKEN_FILE"))

# Server
PORT: int = int(_get("PORT", "45690"))
BASE_URL: str = _require("BASE_URL")

# Email allowlist — parsed at import time so a misconfigured empty list fails loud
_raw_emails = _get("ALLOWED_EMAILS")
if not _raw_emails:
    raise RuntimeError(
        "ALLOWED_EMAILS must be set to a non-empty comma-separated list of emails. "
        "An empty allowlist would allow no one (or everyone, depending on the check). "
        "Set it explicitly."
    )
ALLOWED_EMAILS: frozenset[str] = frozenset(
    e.strip().lower() for e in _raw_emails.split(",") if e.strip()
)
