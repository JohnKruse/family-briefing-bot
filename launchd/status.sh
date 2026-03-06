#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for label in com.familybriefing.scheduling.compose com.familybriefing.scheduling.send com.familybriefing.scheduling.reminders; do
  echo "=== $label ==="
  launchctl print "gui/$(id -u)/$label" 2>/dev/null | sed -n '1,40p' || echo "not loaded"
  echo
done

echo "=== recent logs ==="
for f in "$PROJECT_ROOT"/logs/*.log; do
  [ -f "$f" ] || continue
  echo "--- $f ---"
  tail -n 20 "$f"
  echo
done
