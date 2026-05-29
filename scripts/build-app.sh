#!/usr/bin/env bash
# Build MIRA.app from the Swift sources.
#
# Primary path: SwiftPM (`swift build`). On some toolchains (e.g. beta
# macOS where the Command Line Tools' PackageDescription is out of sync with
# its libPackageDescription) the *manifest* fails to link with errors like:
#   Undefined symbols: PackageDescription.Package.__allocating_init(...)
# In that case we fall back to compiling the sources directly with `swiftc`,
# which doesn't touch PackageDescription at all.
#
# Either way the app is built in Swift 5 language mode: the code uses
# @MainActor/actor patterns written before Swift 6 strict concurrency.
set -euo pipefail

cd "$(dirname "$0")/../mac-app"

CONFIG="${CONFIG:-release}"
APP="$(pwd)/MIRA.app"
SWIFT5_SPM=(-Xswiftc -swift-version -Xswiftc 5)
BIN=""

build_with_spm() {
    swift build -c "$CONFIG" "${SWIFT5_SPM[@]}" 2>&1 || return 1
    local bin
    bin="$(swift build -c "$CONFIG" "${SWIFT5_SPM[@]}" --show-bin-path 2>/dev/null)/MIRA"
    [[ -x "$bin" ]] || return 1
    BIN="$bin"
}

build_with_swiftc() {
    echo "→ SwiftPM unavailable/broken; compiling directly with swiftc…"
    local sdk arch out opt
    sdk="$(xcrun --show-sdk-path --sdk macosx)"
    arch="$(uname -m)"
    out="$(pwd)/.build/direct/MIRA"
    opt="-Onone"
    [[ "$CONFIG" == "release" ]] && opt="-O"
    mkdir -p "$(dirname "$out")"
    # @main (SwiftUI App) needs -parse-as-library. Frameworks (AppKit,
    # SwiftUI, Speech, ScreenCaptureKit, Carbon, …) autolink via `import`.
    # shellcheck disable=SC2046
    swiftc -parse-as-library -swift-version 5 "$opt" \
        -target "${arch}-apple-macosx14.0" \
        -sdk "$sdk" \
        $(find Sources/MIRA -name '*.swift') \
        -o "$out"
    BIN="$out"
}

build_with_spm || build_with_swiftc

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/MIRA"
cp Sources/MIRA/Info.plist "$APP/Contents/Info.plist"

# Ad-hoc sign so TCC prompts work; users can re-sign with a real identity later.
codesign --deep --force --sign - "$APP" >/dev/null 2>&1 || true

echo "Built: $APP"
echo "Run with: open '$APP'"
