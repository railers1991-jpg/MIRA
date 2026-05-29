#!/usr/bin/env bash
# Remove MIRA: the login agent, the installed app, and (optionally) all data.
set -euo pipefail

LABEL="com.mira.brain"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
APP_DEST="/Applications/MIRA.app"
DATA_DIR="$HOME/.mira"

echo "Stopping and removing the login agent…"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"

echo "Removing $APP_DEST…"
rm -rf "$APP_DEST"

if [[ "${1:-}" == "--purge" ]]; then
    echo "Purging all data at $DATA_DIR (memory, sessions, skills, config)…"
    rm -rf "$DATA_DIR"
else
    echo "Keeping your data at $DATA_DIR (run with --purge to delete it)."
fi

echo "MIRA uninstalled."
