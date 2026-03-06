#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scheduling_asst.config import load_settings
from scheduling_asst.jobs import generate_daily_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate daily report")
    parser.add_argument("--settings", default="", help="Optional settings path")
    args = parser.parse_args()

    settings = load_settings(args.settings or None)
    result = generate_daily_report(settings)
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
