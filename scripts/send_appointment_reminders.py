#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scheduling_asst.config import load_settings
from scheduling_asst.jobs import run_appointment_reminders


def main() -> int:
    parser = argparse.ArgumentParser(description="Send appointment reminders")
    parser.add_argument("--settings", default="", help="Optional settings path")
    parser.add_argument("--dry-run", action="store_true", help="Compute reminders but do not send")
    args = parser.parse_args()

    settings = load_settings(args.settings or None)
    result = run_appointment_reminders(settings, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
