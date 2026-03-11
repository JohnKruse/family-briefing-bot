from __future__ import annotations

from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]


def build_credentials(google_creds_path: str) -> Credentials:
    token_path = Path(google_creds_path).expanduser().resolve()
    if not token_path.exists():
        raise FileNotFoundError(f"Google credential file not found: {token_path}")

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    if not creds.valid:
        raise RuntimeError("Google credentials are invalid")
    return creds


def build_calendar_service(google_creds_path: str):
    creds = build_credentials(google_creds_path=google_creds_path)
    return build("calendar", "v3", credentials=creds)


def build_gmail_service(google_creds_path: str):
    creds = build_credentials(google_creds_path=google_creds_path)
    return build("gmail", "v1", credentials=creds)
