from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


@dataclass
class CalendarEvent:
    event_id: str
    title: str
    start_local: datetime
    end_local: datetime
    calendar_name: str


def _parse_google_dt(raw: dict[str, Any], tz: ZoneInfo) -> datetime:
    if "dateTime" in raw:
        dt = datetime.fromisoformat(raw["dateTime"].replace("Z", "+00:00"))
        return dt.astimezone(tz)
    day = date.fromisoformat(raw["date"])
    return datetime(day.year, day.month, day.day, tzinfo=tz)


def list_calendar_ids(service, include_all: bool, explicit_ids: list[str] | None) -> list[tuple[str, str]]:
    explicit = [x for x in (explicit_ids or []) if x]
    if explicit:
        return [(cid, cid) for cid in explicit]
    if not include_all:
        return [("primary", "primary")]

    out: list[tuple[str, str]] = []
    page_token = None
    while True:
        result = service.calendarList().list(pageToken=page_token).execute()
        for item in result.get("items", []):
            cid = str(item.get("id", "")).strip()
            summary = str(item.get("summary", cid)).strip()
            if cid:
                out.append((cid, summary))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return out or [("primary", "primary")]


def fetch_events(service, timezone: str, days_ahead: int, include_all: bool, calendar_ids: list[str] | None) -> list[CalendarEvent]:
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    calendars = list_calendar_ids(service, include_all=include_all, explicit_ids=calendar_ids)

    merged: dict[str, CalendarEvent] = {}
    for calendar_id, calendar_name in calendars:
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=250,
        ).execute()

        for item in result.get("items", []):
            if item.get("status") == "cancelled":
                continue
            start_raw = item.get("start") or {}
            end_raw = item.get("end") or {}
            if not start_raw or not end_raw:
                continue
            start_local = _parse_google_dt(start_raw, tz)
            end_local = _parse_google_dt(end_raw, tz)
            title = str(item.get("summary", "Appointment")).strip() or "Appointment"
            event_id = str(item.get("id", "")).strip() or f"{calendar_id}:{start_local.isoformat()}:{title}"
            key = f"{event_id}|{start_local.isoformat()}"
            merged[key] = CalendarEvent(
                event_id=event_id,
                title=title,
                start_local=start_local,
                end_local=end_local,
                calendar_name=calendar_name,
            )

    return sorted(merged.values(), key=lambda e: (e.start_local, e.end_local, e.title.lower()))
