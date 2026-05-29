#!/usr/bin/env bash
# Install MIRA brain as a per-user launchd agent so it starts at login
# and restarts on crash. Idempotent — re-running updates the plist.
set -euo pipefail

LABEL="com.mira.brain"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
ENV_FILE="$HOME/.mira/env"
BRAIN_DIR="$(cd "$(dirname "$0")/../brain" && pwd)"
LOG_DIR="$HOME/.mira/logs"

mkdir -p "$(dirname "$PLIST")" "$LOG_DIR" "$(dirname "$ENV_FILE")"

# Ensure the venv is up to date before we hand off to launchd.
cd "$BRAIN_DIR"
if [[ ! -d .venv ]]; then
    python3 -m venv .venv
fi
.venv/bin/pip install -q -e .

PYTHON_BIN="$BRAIN_DIR/.venv/bin/python"

# Source the user's env file at launch so ANTHROPIC_API_KEY etc. are present.
WRAPPER="$BRAIN_DIR/.venv/bin/mira-brain-launchd"
cat > "$WRAPPER" <<EOF
#!/usr/bin/env bash
set -a
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
set +a
exec "$BRAIN_DIR/.venv/bin/mira-brain"
EOF
chmod +x "$WRAPPER"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${WRAPPER}</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>${LOG_DIR}/brain.out.log</string>
    <key>StandardErrorPath</key><string>${LOG_DIR}/brain.err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key><string>1</string>
    </dict>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "Installed ${LABEL}"
echo "Logs: $LOG_DIR"
echo "Env (put ANTHROPIC_API_KEY=... here): $ENV_FILE"
echo
echo "Manage with:"
echo "  launchctl list | grep mira      # status"
echo "  launchctl unload '$PLIST'       # stop"
echo "  launchctl load   '$PLIST'       # start"
