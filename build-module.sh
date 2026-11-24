#!/usr/bin/env bash
# build-module.sh — Build module.apk containing Google Play Billing Library
# 博客：https://blog.caowo.de/
# 发卡网（仅提供 GPT 代充）：https://faka.cdkey.si/
#
# Requirements: curl, unzip, Java 11+, Android SDK build-tools (d8)
#
# If you don't have Android SDK build-tools:
#   brew install android-commandlinetools   (macOS)
#   sdkmanager "build-tools;34.0.0"
#
# Usage:
#   ./build-module.sh              # builds module.apk in current directory
#   ./build-module.sh --push       # also pushes to MuMu device via adb

set -euo pipefail

BILLING_VERSION="7.1.1"
BILLING_URL="https://repo1.maven.org/maven2/com/android/billingclient/billing/${BILLING_VERSION}/billing-${BILLING_VERSION}.aar"

TMPDIR_BUILD="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_BUILD"' EXIT

log()  { echo "[*] $*"; }
ok()   { echo "[+] $*"; }
die()  { echo "[-] $*" >&2; exit 1; }

# --- Find d8 ---
find_d8() {
    command -v d8 2>/dev/null && return
    # Android SDK
    local sdk="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
    if [ -d "$sdk/build-tools" ]; then
        local latest
        latest=$(ls -1 "$sdk/build-tools/" | sort -V | tail -1)
        local d8_path="$sdk/build-tools/$latest/d8"
        [ -x "$d8_path" ] && { echo "$d8_path"; return; }
    fi
    return 1
}

D8="$(find_d8)" || die "d8 not found. Install Android SDK build-tools: sdkmanager 'build-tools;34.0.0'"
log "Using d8: $D8"

# --- Download billing AAR ---
log "Downloading billing library v${BILLING_VERSION}..."
curl -fsSL "$BILLING_URL" -o "$TMPDIR_BUILD/billing.aar" || die "Failed to download billing AAR"
ok "Downloaded billing.aar"

# --- Extract classes.jar ---
log "Extracting classes.jar..."
unzip -q -o "$TMPDIR_BUILD/billing.aar" "classes.jar" -d "$TMPDIR_BUILD/" || die "Failed to extract classes.jar"
ok "Extracted classes.jar"

# --- Convert to DEX ---
log "Converting to DEX..."
"$D8" --output "$TMPDIR_BUILD/dex/" "$TMPDIR_BUILD/classes.jar" 2>/dev/null || \
"$D8" --min-api 21 --output "$TMPDIR_BUILD/dex/" "$TMPDIR_BUILD/classes.jar"
ok "Converted to classes.dex"

# --- Package as minimal APK ---
# A valid APK is just a zip with classes.dex and AndroidManifest.xml
log "Packaging module.apk..."
mkdir -p "$TMPDIR_BUILD/apk"
cp "$TMPDIR_BUILD/dex/classes.dex" "$TMPDIR_BUILD/apk/"

# Minimal binary AndroidManifest.xml (just enough for DexClassLoader)
# We use a plain-text manifest since DexClassLoader doesn't parse it
cat > "$TMPDIR_BUILD/apk/AndroidManifest.xml" << 'MANIFEST'
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.helper.billing">
    <application />
</manifest>
MANIFEST

cd "$TMPDIR_BUILD/apk"
zip -q module.apk classes.dex AndroidManifest.xml
cd - >/dev/null

cp "$TMPDIR_BUILD/apk/module.apk" ./module.apk
ok "Built module.apk ($(wc -c < module.apk | tr -d ' ') bytes)"

# --- Optional: push to device ---
if [[ "${1:-}" == "--push" ]]; then
    ADB="${ADB_PATH:-adb}"
    DEVICE="${2:-}"
    if [ -z "$DEVICE" ]; then
        # Auto-detect MuMu
        for port in 16384 16416 16448 16480; do
            if "$ADB" connect "127.0.0.1:$port" 2>/dev/null | grep -q "connected"; then
                DEVICE="127.0.0.1:$port"
                break
            fi
        done
    fi
    [ -z "$DEVICE" ] && die "No device found. Start MuMu or specify device: $0 --push 127.0.0.1:16416"
    log "Pushing to $DEVICE..."
    "$ADB" -s "$DEVICE" push module.apk /data/local/tmp/module.apk
    ok "Pushed to /data/local/tmp/module.apk"
fi

echo ""
ok "Done! Push to device with:"
echo "  adb push module.apk /data/local/tmp/module.apk"
