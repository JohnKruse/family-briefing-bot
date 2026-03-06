#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${COMMON_ENV_PYTHON:-$HOME/common_env/bin/python}"
AGENT_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$AGENT_DIR" "$PROJECT_ROOT/logs"

render_template() {
  local src="$1"
  local dst="$2"
  sed -e "s|__PROJECT__|$PROJECT_ROOT|g" -e "s|__PYTHON__|$PYTHON_BIN|g" "$src" > "$dst"
}

install_job() {
  local label="$1"
  local template="$2"
  local plist="$AGENT_DIR/$label.plist"

  render_template "$template" "$plist"
  launchctl bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
  launchctl enable "gui/$(id -u)/$label"
  echo "Installed $label"
}

install_job "com.kruser.scheduling.compose" "$PROJECT_ROOT/launchd/templates/com.kruser.scheduling.compose.plist.template"
install_job "com.kruser.scheduling.send" "$PROJECT_ROOT/launchd/templates/com.kruser.scheduling.send.plist.template"
install_job "com.kruser.scheduling.reminders" "$PROJECT_ROOT/launchd/templates/com.kruser.scheduling.reminders.plist.template"

echo "Done. Use launchd/status.sh to inspect jobs and logs."
