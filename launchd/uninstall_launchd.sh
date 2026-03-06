#!/usr/bin/env bash
set -euo pipefail

for label in com.kruser.scheduling.compose com.kruser.scheduling.send com.kruser.scheduling.reminders; do
  launchctl bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
  rm -f "$HOME/Library/LaunchAgents/$label.plist"
  echo "Removed $label"
done
