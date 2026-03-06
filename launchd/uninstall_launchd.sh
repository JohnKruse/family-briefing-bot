#!/usr/bin/env bash
set -euo pipefail

for label in com.familybriefing.scheduling.compose com.familybriefing.scheduling.send com.familybriefing.scheduling.reminders; do
  launchctl bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
  rm -f "$HOME/Library/LaunchAgents/$label.plist"
  echo "Removed $label"
done
