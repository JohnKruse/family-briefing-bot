#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scheduling_asst.config import load_settings


def _api_key() -> str:
    for key in ("GOOGLE_MAPS_KEY", "GOOGLE_MAPS_API_KEY", "GOOGLE_API_KEY", "MAPS_API_KEY"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture raw Google Weather API sample JSON")
    parser.add_argument("--settings", default="", help="Optional settings path")
    parser.add_argument("--out", default="", help="Optional explicit output path")
    args = parser.parse_args()

    settings = load_settings(args.settings or None)
    weather_cfg = settings.get("daily_report", {}).get("weather", {})
    lat = float(weather_cfg.get("latitude", 45.07))
    lon = float(weather_cfg.get("longitude", 7.69))

    key = _api_key()
    if not key:
        raise RuntimeError("Missing GOOGLE_MAPS_KEY/GOOGLE_MAPS_API_KEY/GOOGLE_API_KEY/MAPS_API_KEY")

    params = {
        "key": key,
        "location.latitude": f"{lat}",
        "location.longitude": f"{lon}",
        "days": "3",
        "languageCode": "en",
        "unitsSystem": "METRIC",
    }
    resp = requests.get("https://weather.googleapis.com/v1/forecast/days:lookup", params=params, timeout=20)

    if args.out:
        out_path = Path(args.out).expanduser().resolve()
    else:
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        out_path = Path(f"/tmp/google_weather_sample_{stamp}.json")

    try:
        payload = resp.json()
    except Exception:
        payload = {"raw_text": resp.text}

    wrapped = {
        "status_code": resp.status_code,
        "url": resp.url,
        "payload": payload,
    }
    out_path.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    selected = []
    if isinstance(payload, dict):
        for day in payload.get("forecastDays", [])[:3]:
            wc = (day.get("daytimeForecast") or {}).get("weatherCondition") or {}
            desc = ((wc.get("description") or {}).get("text") or "").strip()
            typ = str(wc.get("type", "")).strip()
            selected.append({"type": typ, "description_text": desc})

    print(
        json.dumps(
            {
                "out": str(out_path),
                "status_code": resp.status_code,
                "weather_fields_preview": selected,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
