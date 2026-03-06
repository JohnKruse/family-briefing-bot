#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scheduling_asst.config import load_settings
from scheduling_asst.jobs import send_daily_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Send daily report")
    parser.add_argument("--settings", default="", help="Optional settings path")
    parser.add_argument("--force", action="store_true", help="Force send even if already sent today")
    args = parser.parse_args()

    settings = load_settings(args.settings or None)
    result = send_daily_report(settings, force=args.force)
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
