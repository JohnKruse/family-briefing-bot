from __future__ import annotations

import hashlib
import json
import os
import random
import re
import tempfile
from shutil import copy2
from html import escape
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .calendar_data import CalendarEvent, fetch_events
from .config import abs_path
from .google_clients import build_calendar_service, build_gmail_service
from .notifiers import send_email_via_gmail, send_telegram_messages

CLOSE_LINES = [
    "The secret of getting ahead is getting started.",
    "Small progress is still progress.",
    "Consistency beats intensity over the long run.",
    "What gets scheduled gets done.",
    "Start where you are. Use what you have. Do what you can.",
]


OPEN_METEO_CODE_MAP = {
    0: ("☀️", "Clear sky"),
    1: ("🌤️", "Mainly clear"),
    2: ("⛅", "Partly cloudy"),
    3: ("☁️", "Overcast"),
    45: ("🌫️", "Fog"),
    48: ("🌫️", "Depositing rime fog"),
    51: ("🌦️", "Light drizzle"),
    53: ("🌦️", "Moderate drizzle"),
    55: ("🌦️", "Dense drizzle"),
    56: ("🌧️", "Light freezing drizzle"),
    57: ("🌧️", "Dense freezing drizzle"),
    61: ("🌧️", "Slight rain"),
    63: ("🌧️", "Moderate rain"),
    65: ("🌧️", "Heavy rain"),
    66: ("🌧️", "Light freezing rain"),
    67: ("🌧️", "Heavy freezing rain"),
    71: ("❄️", "Slight snow fall"),
    73: ("❄️", "Moderate snow fall"),
    75: ("❄️", "Heavy snow fall"),
    77: ("❄️", "Snow grains"),
    80: ("🌦️", "Slight rain showers"),
    81: ("🌧️", "Moderate rain showers"),
    82: ("🌧️", "Violent rain showers"),
    85: ("❄️", "Slight snow showers"),
    86: ("❄️", "Heavy snow showers"),
    95: ("⛈️", "Thunderstorm"),
    96: ("⛈️", "Thunderstorm with slight hail"),
    99: ("⛈️", "Thunderstorm with heavy hail"),
}


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tf:
        tf.write(content)
        tmp_name = tf.name
    Path(tmp_name).replace(path)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def _copy_reports_to_agent_zero_uploads(report_path: Path, html_path: Path) -> None:
    uploads_dir = Path("/Users/john/Documents/Python/agent-zero/usr/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    copy2(report_path, uploads_dir / report_path.name)
    copy2(html_path, uploads_dir / html_path.name)


def _google_weather_icon(cond_type: str) -> str:
    t = (cond_type or "").upper()
    if t in {"CLEAR", "MOSTLY_CLEAR"}:
        return "☀️"
    if t in {"PARTLY_CLOUDY", "MOSTLY_CLOUDY"}:
        return "⛅"
    if t == "CLOUDY":
        return "☁️"
    if "SNOW" in t:
        return "❄️"
    if "THUNDER" in t or t == "STORM":
        return "⛈️"
    if "RAIN" in t or "SHOWERS" in t:
        return "🌧️"
    if "WIND" in t:
        return "💨"
    if "FOG" in t or "MIST" in t or "HAZE" in t:
        return "🌫️"
    return "❓"


def _load_google_maps_api_key() -> str:
    for key in ("GOOGLE_MAPS_KEY", "GOOGLE_MAPS_API_KEY", "GOOGLE_API_KEY", "MAPS_API_KEY"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def _normalize_weather_entries(entries: list[dict[str, Any]], timezone_name: str, days: int = 3) -> list[dict[str, Any]]:
    if not entries:
        return []
    today = datetime.now(ZoneInfo(timezone_name)).date()
    dated: list[tuple[datetime.date, dict[str, Any]]] = []
    undated: list[dict[str, Any]] = []
    for entry in entries:
        raw_iso = str(entry.get("date_iso", "")).strip()
        try:
            day = datetime.strptime(raw_iso, "%Y-%m-%d").date()
            dated.append((day, entry))
        except Exception:
            undated.append(entry)
    dated.sort(key=lambda item: item[0])
    filtered = [entry for day, entry in dated if day >= today][:days]
    if len(filtered) >= days:
        return filtered
    # Fallback: preserve oldest-first order if provider does not supply enough post-midnight days.
    remaining = [entry for _, entry in dated if entry not in filtered]
    return (filtered + remaining + undated)[:days]


def _weather_entries_google(latitude: float, longitude: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    api_key = _load_google_maps_api_key()
    if not api_key:
        return [], {"ok": False, "reason": "missing_api_key"}
    params = {
        "key": api_key,
        "location.latitude": f"{latitude}",
        "location.longitude": f"{longitude}",
        # Request a wider window and trim by local date so midnight rollover is stable.
        "days": "6",
        "languageCode": "en",
        "unitsSystem": "METRIC",
    }
    url = "https://weather.googleapis.com/v1/forecast/days:lookup"
    resp = requests.get(url, params=params, timeout=20)
    try:
        payload = resp.json()
    except Exception:
        payload = {"raw_text": resp.text}
    capture = {
        "ok": bool(resp.ok),
        "status_code": resp.status_code,
        "url": resp.url,
        "payload": payload,
    }
    if not resp.ok:
        return [], capture

    def _qpf_mm(forecast: dict[str, Any]) -> float | None:
        precip = (forecast or {}).get("precipitation") or {}
        qpf = precip.get("qpf") or {}
        unit = str(qpf.get("unit", "")).upper()
        quantity = qpf.get("quantity")
        if quantity is None:
            return None
        if unit and unit != "MILLIMETERS":
            return None
        try:
            return float(quantity)
        except Exception:
            return None

    out: list[dict[str, Any]] = []
    for day in payload.get("forecastDays", []):
        date_info = day.get("displayDate", {})
        y = int(date_info.get("year", 1970))
        m = int(date_info.get("month", 1))
        d = int(date_info.get("day", 1))
        dt = datetime(y, m, d)
        daytime = day.get("daytimeForecast") or {}
        nighttime = day.get("nighttimeForecast") or {}
        wc = daytime.get("weatherCondition") or {}
        desc = ((wc.get("description") or {}).get("text") or "").strip()
        cond_type = str(wc.get("type", "")).strip()
        if not desc:
            desc = cond_type.replace("_", " ").title() if cond_type else "Unspecified"

        wind = daytime.get("wind") or {}
        speed = (wind.get("speed") or {}).get("value")
        speed_unit = (wind.get("speed") or {}).get("unit", "")
        gust = (wind.get("gust") or {}).get("value")
        gust_unit = (wind.get("gust") or {}).get("unit", "")

        wind_text = ""
        if speed is not None and gust is not None:
            unit = "km/h" if speed_unit == "KILOMETERS_PER_HOUR" and gust_unit == "KILOMETERS_PER_HOUR" else "units"
            wind_text = f"Wind {float(speed):.0f} {unit} gusting to {float(gust):.0f} {unit}"

        day_qpf = _qpf_mm(daytime)
        night_qpf = _qpf_mm(nighttime)
        if day_qpf is None and night_qpf is None:
            precip_mm = None
        else:
            precip_mm = float((day_qpf or 0.0) + (night_qpf or 0.0))

        out.append(
            {
                "date_iso": dt.date().isoformat(),
                "date_label": dt.strftime("%a, %d %b"),
                "icon": _google_weather_icon(cond_type),
                "desc": desc,
                "hi_c": float((day.get("maxTemperature") or {}).get("degrees", 0.0)),
                "lo_c": float((day.get("minTemperature") or {}).get("degrees", 0.0)),
                "precip_mm": precip_mm,
                "wind_text": wind_text,
                "source": "google",
            }
        )
    return out, capture


def _weather_entries_open_meteo(latitude: float, longitude: float, timezone_name: str) -> list[dict[str, Any]]:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        "&daily=temperature_2m_max,temperature_2m_min,weathercode,precipitation_sum"
        f"&timezone={timezone_name}"
    )
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    daily = resp.json()["daily"]
    out: list[dict[str, Any]] = []
    for i in range(min(6, len(daily.get("time", [])))):
        d = datetime.strptime(daily["time"][i], "%Y-%m-%d")
        hi = float(daily["temperature_2m_max"][i])
        lo = float(daily["temperature_2m_min"][i])
        code = int(daily.get("weathercode", [0])[i] or 0)
        icon, desc = OPEN_METEO_CODE_MAP.get(code, ("❓", "Unspecified"))
        rain = float(daily.get("precipitation_sum", [0])[i] or 0)
        out.append(
            {
                "date_iso": d.date().isoformat(),
                "date_label": d.strftime("%a, %d %b"),
                "icon": icon,
                "desc": desc,
                "hi_c": hi,
                "lo_c": lo,
                "precip_mm": rain,
                "source": "open-meteo",
            }
        )
    return out


def _weather_entries(
    latitude: float, longitude: float, timezone_name: str
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    try:
        entries, capture = _weather_entries_google(latitude=latitude, longitude=longitude)
        if entries:
            return _normalize_weather_entries(entries, timezone_name=timezone_name, days=3), "google", capture
    except Exception:
        capture = {"ok": False, "reason": "google_exception"}
    entries = _weather_entries_open_meteo(latitude=latitude, longitude=longitude, timezone_name=timezone_name)
    return _normalize_weather_entries(entries, timezone_name=timezone_name, days=3), "open-meteo", capture


def _weather_markdown(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "Data unavailable"
    lines: list[str] = []
    for e in entries:
        precip = e.get("precip_mm")
        precip_text = f", Precip {precip:.1f} mm" if isinstance(precip, (int, float)) else ""
        wind_text = f", {e['wind_text']}" if e.get("wind_text") else ""
        hi_f = (float(e["hi_c"]) * 9 / 5) + 32
        lo_f = (float(e["lo_c"]) * 9 / 5) + 32
        lines.append(
            f"{e['date_label']}: {e['icon']} {e['desc']}, "
            f"High {e['hi_c']:.1f}C ({hi_f:.1f}F) / Low {e['lo_c']:.1f}C ({lo_f:.1f}F){precip_text}{wind_text}"
        )
    return "\n".join(lines)


def _weather_html(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "<p>Data unavailable</p>"
    items: list[str] = []
    for e in entries:
        precip = e.get("precip_mm")
        precip_text = f", Precip {precip:.1f} mm" if isinstance(precip, (int, float)) else ""
        wind_text = f", {e['wind_text']}" if e.get("wind_text") else ""
        hi_f = (float(e["hi_c"]) * 9 / 5) + 32
        lo_f = (float(e["lo_c"]) * 9 / 5) + 32
        items.append(
            "<li>"
            f"<strong>{escape(e['date_label'])}</strong>: {escape(e['icon'])} "
            f"{escape(e['desc'])}, High {e['hi_c']:.1f}C ({hi_f:.1f}F) / "
            f"Low {e['lo_c']:.1f}C ({lo_f:.1f}F){escape(precip_text)}{escape(wind_text)}"
            "</li>"
        )
    return "<ul>" + "".join(items) + "</ul>"


def _events_by_day(events: list[CalendarEvent], timezone_name: str, days: int) -> str:
    tz = ZoneInfo(timezone_name)
    now = datetime.now(tz)
    bucket: dict[str, list[CalendarEvent]] = {}
    for i in range(days):
        key = (now + timedelta(days=i)).date().isoformat()
        bucket[key] = []
    for event in events:
        key = event.start_local.date().isoformat()
        if key in bucket:
            bucket[key].append(event)

    lines: list[str] = []
    for i in range(days):
        day = now + timedelta(days=i)
        key = day.date().isoformat()
        lines.append(f"- **{day.strftime('%a, %d %B %Y')}**")
        entries = sorted(bucket.get(key, []), key=lambda e: (e.start_local, e.title.lower()))
        if not entries:
            lines.append("  - No appointments")
            continue
        for event in entries:
            calendar_text = ", ".join(event.calendar_names) if getattr(event, "calendar_names", None) else event.calendar_name
            lines.append(
                f"  - {event.start_local.strftime('%H:%M')} - {event.end_local.strftime('%H:%M')} | {event.title} | {calendar_text}"
            )
    return "\n".join(lines)


def _events_by_day_html(events: list[CalendarEvent], timezone_name: str, days: int) -> str:
    tz = ZoneInfo(timezone_name)
    now = datetime.now(tz)
    bucket: dict[str, list[CalendarEvent]] = {}
    for i in range(days):
        key = (now + timedelta(days=i)).date().isoformat()
        bucket[key] = []
    for event in events:
        key = event.start_local.date().isoformat()
        if key in bucket:
            bucket[key].append(event)

    parts: list[str] = []
    for i in range(days):
        day = now + timedelta(days=i)
        key = day.date().isoformat()
        parts.append(f"<h3>{escape(day.strftime('%a, %d %B %Y'))}</h3>")
        entries = sorted(bucket.get(key, []), key=lambda e: (e.start_local, e.title.lower()))
        if not entries:
            parts.append("<p>No appointments</p>")
            continue
        parts.append("<ul>")
        for event in entries:
            calendar_text = ", ".join(event.calendar_names) if getattr(event, "calendar_names", None) else event.calendar_name
            parts.append(
                "<li>"
                f"{escape(event.start_local.strftime('%H:%M'))} - {escape(event.end_local.strftime('%H:%M'))} | "
                f"{escape(event.title)} | {escape(calendar_text)}"
                "</li>"
            )
        parts.append("</ul>")
    return "".join(parts)


def _pick_close_line(state_path: Path, now_local: datetime, source: str = "online") -> str:
    state = _read_json(state_path, {})
    recent = [str(x).strip() for x in state.get("recent_closes", []) if str(x).strip()]

    quote = ""
    normalized_source = (source or "online").strip().lower()
    if normalized_source != "local":
        try:
            resp = requests.get("https://zenquotes.io/api/random", timeout=8)
            if resp.ok:
                payload = resp.json()
                if isinstance(payload, list) and payload:
                    item = payload[0] if isinstance(payload[0], dict) else {}
                    text = str(item.get("q", "")).strip()
                    author = str(item.get("a", "")).strip()
                    if text:
                        quote = f"{text} - {author}" if author else text
        except Exception:
            quote = ""

    if quote and quote not in recent:
        choice = quote
    else:
        pool = [line for line in CLOSE_LINES if line not in set(recent[-5:])]
        if not pool:
            pool = CLOSE_LINES[:]
        choice = random.choice(pool)

    today = now_local.strftime("%Y-%m-%d")
    updated_recent = (recent + [choice])[-15:]
    _write_json(
        state_path,
        {
            "last_day": today,
            "last_close": choice,
            "last_generated_at": now_local.isoformat(),
            "recent_closes": updated_recent,
        },
    )
    return choice


def _resolve_header_image_path(report_cfg: dict[str, Any]) -> Path | None:
    local_header = abs_path("static/local/daily_report.png")
    if local_header.exists():
        return local_header
    configured = str(report_cfg.get("header_image_path", "")).strip()
    if not configured:
        return None
    resolved = abs_path(configured)
    if resolved.exists():
        return resolved
    return None


def generate_daily_report(settings: dict[str, Any]) -> dict[str, Any]:
    tz_name = settings["timezone"]
    report_cfg = settings["daily_report"]
    calendar_cfg = settings["calendar"]
    google_creds_path = settings["google"]["google_creds_path"]

    calendar_service = build_calendar_service(google_creds_path)
    events = fetch_events(
        service=calendar_service,
        timezone=tz_name,
        days_ahead=int(calendar_cfg.get("report_days", 3)),
        include_all=bool(calendar_cfg.get("include_all_calendars", True)),
        calendar_ids=calendar_cfg.get("calendar_ids", []),
    )

    now_local = datetime.now(ZoneInfo(tz_name))
    weather_cfg = report_cfg.get("weather", {})
    weather_entries, weather_source, google_capture = _weather_entries(
        latitude=float(weather_cfg.get("latitude", 45.07)),
        longitude=float(weather_cfg.get("longitude", 7.69)),
        timezone_name=tz_name,
    )
    weather_text = _weather_markdown(weather_entries)
    weather_html = _weather_html(weather_entries)
    appt_text = _events_by_day(events, timezone_name=tz_name, days=int(calendar_cfg.get("report_days", 3)))
    appt_html = _events_by_day_html(events, timezone_name=tz_name, days=int(calendar_cfg.get("report_days", 3)))

    close_state_path = abs_path("data/state/daily_report_state.json")
    close_line = _pick_close_line(
        close_state_path,
        now_local=now_local,
        source=str(report_cfg.get("close_line_source", "online")),
    )
    header_image_path = _resolve_header_image_path(report_cfg)
    header_html = ""
    if header_image_path:
        header_html = (
            '<div style="text-align:left; margin-bottom: 12px;">'
            '<img src="cid:daily_report_header" alt="Daily Report Header" '
            'style="display:block; max-width: 560px; width: 100%; height: auto;">'
            "</div>"
        )

    report = (
        f"**Daily Report - {now_local.strftime('%A, %d %B %Y %H:%M')}**\n\n"
        f"**Weather (3 Days)**\n"
        f"**Source:** {weather_source}\n"
        f"{weather_text}\n\n"
        f"**Appointments (3 Days)**\n{appt_text}\n\n"
        f"*{close_line}*"
    )
    report_html = (
        "<html><body style=\"font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Arial, sans-serif; "
        "line-height: 1.5; color: #202124;\">"
        f"{header_html}"
        f"<h1>Daily Report - {escape(now_local.strftime('%A, %d %B %Y %H:%M'))}</h1>"
        "<h2>Weather (3 Days)</h2>"
        f"<p><strong>Source:</strong> {escape(weather_source)}</p>"
        f"{weather_html}"
        "<h2>Appointments (3 Days)</h2>"
        f"{appt_html}"
        f"<p><em>{escape(close_line)}</em></p>"
        "</body></html>"
    )

    report_path = abs_path(report_cfg["report_path"])
    html_path = abs_path(report_cfg.get("html_path", "data/reports/daily_report.html"))
    json_path = abs_path(report_cfg["json_path"])
    google_weather_path = abs_path("data/google_weather.json")
    _atomic_write(report_path, report)
    _atomic_write(html_path, report_html)
    _copy_reports_to_agent_zero_uploads(report_path, html_path)
    _write_json(google_weather_path, google_capture)
    _write_json(
        json_path,
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_path": str(report_path),
            "html_path": str(html_path),
            "google_weather_path": str(google_weather_path),
            "events_count": len(events),
            "weather_source": weather_source,
            "google_weather_ok": bool(google_capture.get("ok", False)) if isinstance(google_capture, dict) else False,
            "google_weather_status_code": (
                int(google_capture.get("status_code")) if isinstance(google_capture, dict) and google_capture.get("status_code") else None
            ),
            "google_weather_reason": (
                str(google_capture.get("reason")) if isinstance(google_capture, dict) and google_capture.get("reason") else ""
            ),
        },
    )

    return {
        "ok": True,
        "report_path": str(report_path),
        "html_path": str(html_path),
        "events_count": len(events),
        "weather_source": weather_source,
        "google_weather_ok": bool(google_capture.get("ok", False)) if isinstance(google_capture, dict) else False,
        "google_weather_status_code": (
            int(google_capture.get("status_code")) if isinstance(google_capture, dict) and google_capture.get("status_code") else None
        ),
        "google_weather_reason": (
            str(google_capture.get("reason")) if isinstance(google_capture, dict) and google_capture.get("reason") else ""
        ),
    }


def send_daily_report(settings: dict[str, Any], force: bool = False) -> dict[str, Any]:
    report_cfg = settings["daily_report"]
    google_creds_path = settings["google"]["google_creds_path"]

    report_path = abs_path(report_cfg["report_path"])
    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")
    html_path = abs_path(report_cfg.get("html_path", "data/reports/daily_report.html"))
    header_image_path = _resolve_header_image_path(report_cfg)

    report_text = report_path.read_text(encoding="utf-8")
    report_html = html_path.read_text(encoding="utf-8") if html_path.exists() else None
    report_hash = hashlib.sha256(report_text.encode("utf-8")).hexdigest()

    state_path = abs_path(report_cfg["state_path"])
    state = _read_json(state_path, {})
    tz = ZoneInfo(settings["timezone"])
    today = datetime.now(tz).strftime("%Y-%m-%d")
    if not force:
        if state.get("last_sent_date") == today and state.get("last_report_hash") == report_hash:
            return {"ok": True, "skipped": True, "reason": "already sent today"}

    bot_token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not bot_token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

    chat_ids = [str(x) for x in report_cfg.get("telegram_chat_ids", [])]
    emails = [str(x) for x in report_cfg.get("email_recipients", [])]

    inline_images: dict[str, bytes] | None = None
    if report_html and header_image_path:
        inline_images = {"daily_report_header": header_image_path.read_bytes()}

    send_telegram_messages(bot_token=bot_token, chat_ids=chat_ids, text=report_text, parse_mode="Markdown")
    gmail_service = build_gmail_service(google_creds_path)
    send_email_via_gmail(
        gmail_service=gmail_service,
        recipients=emails,
        subject=str(report_cfg.get("subject", "Daily Report")),
        body=report_text,
        html_body=report_html,
        inline_images=inline_images,
    )

    _write_json(
        state_path,
        {
            "last_sent_date": today,
            "last_report_hash": report_hash,
            "last_sent_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"ok": True, "telegram_sent": len(chat_ids), "email_sent": len(emails)}


def _owner_tokens(event: CalendarEvent) -> list[str]:
    calendar_tokens = [event.calendar_name.lower()]
    if getattr(event, "calendar_names", None):
        calendar_tokens = [str(name).lower() for name in event.calendar_names]
    tokens = calendar_tokens
    for piece in re.split(r"[(),;/]", event.title.lower()):
        piece = piece.strip()
        if piece:
            tokens.append(piece)
    if "wm" in event.title.lower():
        tokens.append("wm")
    return tokens


def run_appointment_reminders(settings: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    tz_name = settings["timezone"]
    calendar_cfg = settings["calendar"]
    rem_cfg = settings["reminders"]
    google_creds_path = settings["google"]["google_creds_path"]

    calendar_service = build_calendar_service(google_creds_path)
    events = fetch_events(
        service=calendar_service,
        timezone=tz_name,
        days_ahead=int(calendar_cfg.get("reminder_days", 14)),
        include_all=bool(calendar_cfg.get("include_all_calendars", True)),
        calendar_ids=calendar_cfg.get("calendar_ids", []),
    )

    offsets = [int(x) for x in rem_cfg.get("offsets_minutes", [90, 45, 15])]
    email_offsets = {int(x) for x in rem_cfg.get("email_offsets_minutes", [90])}
    lookback = int(rem_cfg.get("lookback_minutes", 6))
    now = datetime.now(ZoneInfo(tz_name))

    aliases = {str(k).lower(): str(v) for k, v in (rem_cfg.get("owner_aliases", {}) or {}).items()}
    owner_tg = {str(k): str(v) for k, v in (rem_cfg.get("owner_telegram_chat_ids", {}) or {}).items()}
    owner_email = {str(k): str(v) for k, v in (rem_cfg.get("owner_email_recipients", {}) or {}).items()}

    state_path = abs_path(rem_cfg["state_path"])
    state = _read_json(state_path, {"sent": {}})
    sent_map = state.setdefault("sent", {})

    bot_token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    gmail_service = build_gmail_service(google_creds_path)

    total_sent = 0
    due_count = 0
    for event in events:
        for offset in offsets:
            remind_at = event.start_local - timedelta(minutes=offset)
            if not (remind_at <= now < remind_at + timedelta(minutes=lookback)):
                continue
            reminder_key = f"{event.event_id}|{event.start_local.isoformat()}|{offset}"
            if reminder_key in sent_map:
                continue

            owners: set[str] = set()
            for token in _owner_tokens(event):
                mapped = aliases.get(token)
                if mapped:
                    owners.add(mapped)

            tg_ids = set(str(x) for x in rem_cfg.get("always_telegram_chat_ids", []))
            email_ids = set(str(x) for x in rem_cfg.get("always_email_recipients", []))
            for owner in owners:
                if owner in owner_tg:
                    tg_ids.add(owner_tg[owner])
                if owner in owner_email:
                    email_ids.add(owner_email[owner])

            if offset not in email_offsets:
                email_ids.clear()

            msg = (
                f"Reminder: '{event.title}' starts in {offset} minutes "
                f"({event.start_local.strftime('%a %d %b %H:%M')})."
            )
            if dry_run:
                print(msg)
                sent_count = len(tg_ids) + len(email_ids)
            else:
                if tg_ids and not bot_token:
                    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN for reminder sends")
                if tg_ids:
                    send_telegram_messages(bot_token=bot_token, chat_ids=sorted(tg_ids), text=msg)
                if email_ids:
                    send_email_via_gmail(
                        gmail_service=gmail_service,
                        recipients=sorted(email_ids),
                        subject=f"Appointment Reminder ({offset}m)",
                        body=msg,
                    )
                sent_count = len(tg_ids) + len(email_ids)

            due_count += 1
            total_sent += sent_count
            sent_map[reminder_key] = datetime.now(timezone.utc).isoformat()

    if not dry_run:
        _write_json(state_path, state)

    return {"ok": True, "due_count": due_count, "messages_sent": total_sent, "dry_run": dry_run}
