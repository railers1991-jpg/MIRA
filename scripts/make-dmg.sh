#!/usr/bin/env bash
# Build MIRA.app and package it into a distributable MIRA.dmg with a
# drag-to-/Applications layout. Used by the release workflow and locally.
set -euo pipefail

cd "$(dirname "$0")/.."

CONFIG="${CONFIG:-release}"
VERSION="${MIRA_VERSION:-$(date +%Y.%m.%d)}"
APP="mac-app/MIRA.app"
DMG="dist/MIRA-${VERSION}.dmg"
STAGE="$(mktemp -d)"

# 1. Build the app bundle.
CONFIG="$CONFIG" scripts/build-app.sh

# 2. Stage app + an /Applications symlink for drag-install.
mkdir -p dist
cp -R "$APP" "$STAGE/MIRA.app"
ln -s /Applications "$STAGE/Applications"

# 3. Create a compressed DMG.
rm -f "$DMG"
hdiutil create \
    -volname "MIRA" \
    -srcfolder "$STAGE" \
    -ov -format UDZO \
    "$DMG"

rm -rf "$STAGE"
echo "Built: $DMG"
