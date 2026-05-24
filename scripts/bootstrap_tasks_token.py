"""
Run once to authorise the server to access your Google Tasks.

Usage:
    python scripts/bootstrap_tasks_token.py

Opens a browser for Google sign-in. On success, saves token.json in the
project root (chmod 600). The server reads this file on every start.

If Google later revokes the token (typically after ~6 months of inactivity
or manual revocation), re-run this script to get a new one.
"""

import sys
from pathlib import Path

# Make the src package importable when run from the project root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tasks_bridge import config
from tasks_bridge.google_tasks import bootstrap_token

if __name__ == "__main__":
    secrets = config.LAYER_B_CLIENT_SECRETS_FILE
    token = config.TASKS_TOKEN_FILE

    if not secrets.exists():
        print(f"ERROR: client secrets file not found at {secrets}")
        print("Download it from Google Cloud Console > APIs & Services > Credentials")
        print("(Desktop app type, Tasks API enabled)")
        sys.exit(1)

    print(f"Token will be saved to: {token}")
    print()
    print("A URL will appear below. Copy it and open it in Chromium (or any browser).")
    print("After you authorize, the script will complete automatically.")
    print()
    bootstrap_token(secrets, token)
    print("Done. You can now start the server.")
