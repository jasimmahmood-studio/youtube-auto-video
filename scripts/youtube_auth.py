#!/usr/bin/env python3
"""
One-time OAuth 2.0 setup for YouTube Data API v3 upload access.
Run this once to get a refresh token, then add it to your .env file.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def setup_oauth():
    """Run the OAuth 2.0 consent flow and save the refresh token."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("ERROR: Install google-auth-oauthlib first:")
        print("  pip install google-auth-oauthlib --break-system-packages")
        sys.exit(1)

    # Check for client secrets
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

    if not client_id or not client_secret:
        # Try client_secrets.json file
        secrets_file = Path("client_secrets.json")
        if secrets_file.exists():
            flow = InstalledAppFlow.from_client_secrets_file(
                str(secrets_file),
                scopes=["https://www.googleapis.com/auth/youtube.upload",
                         "https://www.googleapis.com/auth/youtube"],
            )
        else:
            print("ERROR: No OAuth credentials found.")
            print("Either:")
            print("  1. Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env")
            print("  2. Download client_secrets.json from Google Cloud Console")
            sys.exit(1)
    else:
        # Build flow from env vars
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        flow = InstalledAppFlow.from_client_config(
            client_config,
            scopes=["https://www.googleapis.com/auth/youtube.upload",
                     "https://www.googleapis.com/auth/youtube"],
        )

    print("Opening browser for Google OAuth consent...")
    print("(If browser doesn't open, check the URL in the terminal)\n")

    credentials = flow.run_local_server(port=8080)

    refresh_token = credentials.refresh_token
    access_token = credentials.token

    print(f"\n{'='*60}")
    print("OAuth setup complete!")
    print(f"{'='*60}")
    print(f"\nRefresh Token: {refresh_token}")
    print(f"\nAdd this to your .env file:")
    print(f"YOUTUBE_REFRESH_TOKEN={refresh_token}")

    # Also save to a token file for backup
    token_file = Path("youtube_token.json")
    with open(token_file, "w") as f:
        json.dump({
            "refresh_token": refresh_token,
            "access_token": access_token,
            "client_id": client_id or "from_secrets_file",
            "created_at": str(__import__("datetime").datetime.now()),
        }, f, indent=2)

    print(f"\nToken also saved to: {token_file}")
    print("IMPORTANT: Keep this file secure — it grants YouTube upload access.")


if __name__ == "__main__":
    setup_oauth()
