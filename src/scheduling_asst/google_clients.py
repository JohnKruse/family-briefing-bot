from __future__ import annotations

from pathlib import Path
from typing import Iterable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def build_credentials(token_file: str, scopes: Iterable[str] | None = None) -> Credentials:
    token_path = Path(token_file).expanduser().resolve()
    if not token_path.exists():
        raise FileNotFoundError(f"Google token file not found: {token_path}")

    scope_list = list(scopes) if scopes else None
    if scope_list:
        creds = Credentials.from_authorized_user_file(str(token_path), scope_list)
    else:
        creds = Credentials.from_authorized_user_file(str(token_path))
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise RuntimeError("Google token is invalid and not refreshable")
    return creds


def build_calendar_service(token_file: str):
    creds = build_credentials(token_file=token_file, scopes=None)
    return build("calendar", "v3", credentials=creds)


def build_gmail_service(token_file: str):
    creds = build_credentials(token_file=token_file, scopes=None)
    return build("gmail", "v1", credentials=creds)
