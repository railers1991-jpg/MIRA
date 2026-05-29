#!/usr/bin/env bash
#
# MIRA one-line installer.
#
#   curl -fsSL https://raw.githubusercontent.com/railers1991-jpg/mira/main/install.sh | bash
#
# Sets up everything: the Python brain (venv + deps), the native macOS app
# (built and copied to /Applications), a login-time launchd agent for the
# brain, and your Anthropic API key. Re-running updates an existing install.
#
# Environment overrides:
#   MIRA_REF=<branch|tag>   which git ref to install     (default: main)
#   MIRA_HOME=<dir>         source checkout location     (default: ~/.mira/src)
#   MIRA_NO_APP=1           skip building the .app (brain only)
#   MIRA_NO_LAUNCHD=1       skip the login-time agent
#   ANTHROPIC_API_KEY=...   provide the key non-interactively
#
set -euo pipefail

REPO_URL="https://github.com/railers1991-jpg/mira.git"
MIRA_REF="${MIRA_REF:-main}"
MIRA_HOME="${MIRA_HOME:-$HOME/.mira/src}"
DATA_DIR="$HOME/.mira"
ENV_FILE="$DATA_DIR/env"
APP_DEST="/Applications/MIRA.app"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
info() { printf '\033[36m›\033[0m %s\n' "$1"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '\033[33m!\033[0m %s\n' "$1"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

ask() {
    # Read a line from the controlling terminal even when this script is
    # piped through `bash` (stdin is the script, not the keyboard).
    local prompt="$1" __var="$2" reply=""
    if [[ -e /dev/tty ]]; then
        printf '%s' "$prompt" > /dev/tty
        IFS= read -r reply < /dev/tty || true
    fi
    printf -v "$__var" '%s' "$reply"
}

# ---- preflight -------------------------------------------------------------

bold "MIRA installer"

[[ "$(uname -s)" == "Darwin" ]] || die "MIRA runs on macOS only."

ARCH="$(uname -m)"
info "macOS $(sw_vers -productVersion) on $ARCH"

if ! xcode-select -p >/dev/null 2>&1; then
    warn "Xcode Command Line Tools are required. Launching the installer…"
    xcode-select --install || true
    die "Re-run this script once the Command Line Tools finish installing."
fi
ok "Xcode Command Line Tools present"

PYTHON_BIN="$(command -v python3 || true)"
[[ -n "$PYTHON_BIN" ]] || die "python3 not found. Install Python 3.11+ (e.g. 'brew install python@3.12')."
PY_VER="$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
case "$PY_VER" in
    3.1[1-9]|3.[2-9][0-9]) ok "Python $PY_VER" ;;
    *) die "Python 3.11+ required, found $PY_VER." ;;
esac

command -v git >/dev/null 2>&1 || die "git not found."
command -v swift >/dev/null 2>&1 || warn "swift not found — the .app build may fail (set MIRA_NO_APP=1 to skip)."

# ---- fetch source ----------------------------------------------------------

mkdir -p "$DATA_DIR"
if [[ -d "$MIRA_HOME/.git" ]]; then
    info "Updating existing checkout at $MIRA_HOME"
    git -C "$MIRA_HOME" fetch --depth 1 origin "$MIRA_REF"
    git -C "$MIRA_HOME" checkout -q "$MIRA_REF"
    git -C "$MIRA_HOME" reset --hard -q "origin/$MIRA_REF" 2>/dev/null \
        || git -C "$MIRA_HOME" reset --hard -q "$MIRA_REF"
else
    info "Cloning $REPO_URL ($MIRA_REF) → $MIRA_HOME"
    rm -rf "$MIRA_HOME"
    git clone --depth 1 --branch "$MIRA_REF" "$REPO_URL" "$MIRA_HOME" 2>/dev/null \
        || git clone "$REPO_URL" "$MIRA_HOME"
    git -C "$MIRA_HOME" checkout -q "$MIRA_REF" 2>/dev/null || true
fi
ok "Source ready"

# ---- brain -----------------------------------------------------------------

info "Setting up the brain (Python venv + dependencies)…"
cd "$MIRA_HOME/brain"
[[ -d .venv ]] || "$PYTHON_BIN" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -e .
deactivate
ok "Brain installed"

# ---- API key ---------------------------------------------------------------

have_key=""
[[ -f "$ENV_FILE" ]] && grep -q '^ANTHROPIC_API_KEY=' "$ENV_FILE" && have_key="yes"

if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    touch "$ENV_FILE"; chmod 600 "$ENV_FILE"
    grep -v '^ANTHROPIC_API_KEY=' "$ENV_FILE" > "$ENV_FILE.tmp" 2>/dev/null || true
    mv -f "$ENV_FILE.tmp" "$ENV_FILE" 2>/dev/null || true
    echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" >> "$ENV_FILE"
    ok "Saved API key to $ENV_FILE"
elif [[ -n "$have_key" ]]; then
    ok "Existing API key found in $ENV_FILE"
else
    ask "Paste your Anthropic API key (or leave blank to add later): " KEY_INPUT
    touch "$ENV_FILE"; chmod 600 "$ENV_FILE"
    if [[ -n "${KEY_INPUT:-}" ]]; then
        echo "ANTHROPIC_API_KEY=$KEY_INPUT" >> "$ENV_FILE"
        ok "Saved API key to $ENV_FILE"
    else
        warn "No key set. MIRA will run local-only (Ollama) until you add one to $ENV_FILE."
    fi
fi

# ---- app -------------------------------------------------------------------

if [[ "${MIRA_NO_APP:-}" != "1" ]] && command -v swift >/dev/null 2>&1; then
    info "Building MIRA.app (this can take a minute)…"
    if CONFIG=release "$MIRA_HOME/scripts/build-app.sh" >/tmp/mira-build.log 2>&1; then
        rm -rf "$APP_DEST"
        cp -R "$MIRA_HOME/mac-app/MIRA.app" "$APP_DEST"
        # Re-sign in place so TCC prompts attach to the installed bundle.
        codesign --deep --force --sign - "$APP_DEST" >/dev/null 2>&1 || true
        xattr -dr com.apple.quarantine "$APP_DEST" 2>/dev/null || true
        ok "Installed $APP_DEST"
    else
        warn "App build failed — see /tmp/mira-build.log. Brain still installed."
    fi
else
    warn "Skipping .app build (MIRA_NO_APP=1 or swift missing)."
fi

# ---- launchd ---------------------------------------------------------------

if [[ "${MIRA_NO_LAUNCHD:-}" != "1" ]]; then
    info "Registering the brain as a login agent…"
    "$MIRA_HOME/scripts/install-launchd.sh" >/tmp/mira-launchd.log 2>&1 \
        && ok "Brain will start automatically at login" \
        || warn "launchd registration failed — see /tmp/mira-launchd.log"
fi

# ---- done ------------------------------------------------------------------

echo
bold "MIRA is installed 🎉"
echo
echo "  Brain:  http://127.0.0.1:7842   (curl localhost:7842/health)"
[[ -d "$APP_DEST" ]] && echo "  App:    $APP_DEST"
echo "  Data:   $DATA_DIR"
echo "  Config: $ENV_FILE   (API key, MCP servers in mcp.json)"
echo
if [[ -d "$APP_DEST" ]]; then
    info "Opening MIRA — grant Microphone, Speech Recognition, Accessibility & Screen Recording when asked."
    open "$APP_DEST" || true
fi
echo "Toggle the chat panel anywhere with ⌥⇧Space · dictate anywhere with ⌃⌥V."
