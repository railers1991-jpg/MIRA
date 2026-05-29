#!/usr/bin/env bash
# Build MIRA.app bundle from the Swift package.
#
# Why a bundle: `swift run` won't trigger macOS permission prompts
# (microphone, speech) or accept Carbon hotkeys reliably. A proper
# .app with an Info.plist solves both.
set -euo pipefail

cd "$(dirname "$0")/../mac-app"

CONFIG="${CONFIG:-release}"
swift build -c "$CONFIG"

BIN="$(swift build -c "$CONFIG" --show-bin-path)/MIRA"
APP="$(pwd)/MIRA.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/MIRA"
cp Sources/MIRA/Info.plist "$APP/Contents/Info.plist"

# Ad-hoc sign so TCC prompts work; users can re-sign with a real identity later.
codesign --deep --force --sign - "$APP" >/dev/null

echo "Built: $APP"
echo "Run with: open '$APP'"
