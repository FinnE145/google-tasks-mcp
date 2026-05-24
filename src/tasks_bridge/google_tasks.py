"""Auth Layer B: Google Tasks API client with stored refresh token."""

import json
import logging
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tasks_bridge import config

logger = logging.getLogger(__name__)

TASKS_SCOPE = "https://www.googleapis.com/auth/tasks"


def _load_credentials() -> Credentials:
    token_path: Path = config.TASKS_TOKEN_FILE
    secrets_path: Path = config.LAYER_B_CLIENT_SECRETS_FILE

    if not token_path.exists():
        raise RuntimeError(
            f"Tasks token file not found at {token_path}. "
            "Run: python scripts/bootstrap_tasks_token.py"
        )

    token_data = json.loads(token_path.read_text())
    secrets_data = json.loads(secrets_path.read_text())
    installed = secrets_data.get("installed") or secrets_data.get("web", {})

    expiry_ms = token_data.get("expiry_date", 0)
    expiry = datetime.utcfromtimestamp(expiry_ms / 1000) if expiry_ms else None

    creds = Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=installed.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=installed["client_id"],
        client_secret=installed["client_secret"],
        scopes=[TASKS_SCOPE],
        expiry=expiry,
    )
    return creds


def _save_credentials(creds: Credentials) -> None:
    token_path = config.TASKS_TOKEN_FILE
    token_path.write_text(json.dumps({
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "scope": TASKS_SCOPE,
        "token_type": "Bearer",
        "expiry_date": int(creds.expiry.timestamp() * 1000) if creds.expiry else 0,
    }, indent=2))
    token_path.chmod(0o600)


def get_service():
    """Return an authenticated Google Tasks service, refreshing if needed."""
    creds = _load_credentials()

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
            logger.debug("Tasks credentials refreshed")
        except Exception as exc:
            error_str = str(exc)
            if "invalid_grant" in error_str:
                raise RuntimeError(
                    "Google Tasks refresh token is invalid or revoked (invalid_grant). "
                    "Re-run: python scripts/bootstrap_tasks_token.py"
                ) from exc
            raise

    return build("tasks", "v1", credentials=creds)


def fetch_all_tasks(service, list_id: str, include_completed: bool) -> list[dict]:
    """Paginate through all tasks in a list."""
    tasks = []
    page_token = None
    while True:
        kwargs: dict = dict(
            tasklist=list_id,
            showCompleted=include_completed,
            showHidden=include_completed,
            maxResults=100,
        )
        if page_token:
            kwargs["pageToken"] = page_token
        result = service.tasks().list(**kwargs).execute()
        tasks.extend(result.get("items", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return tasks


def handle_http_error(exc: HttpError, context: str) -> dict:
    """Convert an HttpError into a structured error dict."""
    code = exc.resp.status
    if code == 401:
        return {"error": "auth_error", "detail": "Not authorised — re-run bootstrap_tasks_token.py"}
    if code == 403:
        return {"error": "permission_denied", "detail": str(exc)}
    if code == 404:
        return {"error": "not_found", "detail": f"{context} not found"}
    return {"error": "api_error", "status": code, "detail": str(exc)}


def bootstrap_token(secrets_file: Path, token_file: Path) -> None:
    """Run InstalledAppFlow once to get and store a refresh token."""
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), scopes=[TASKS_SCOPE])
    creds = flow.run_local_server(port=0, open_browser=False)
    token_file.write_text(json.dumps({
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "scope": TASKS_SCOPE,
        "token_type": "Bearer",
        "expiry_date": int(creds.expiry.timestamp() * 1000) if creds.expiry else 0,
    }, indent=2))
    token_file.chmod(0o600)
    print(f"Token saved to {token_file}")
