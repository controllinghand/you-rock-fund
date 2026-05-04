#!/bin/bash
# yrvi-register-url-scheme.sh — one-time setup to register yrvi:// on macOS
#
# Run once from the repo root after cloning:
#   bash scripts/yrvi-register-url-scheme.sh
#
# Creates ~/Applications/YRVIUpgrade.app, registers the yrvi:// URL scheme
# with Launch Services, and bakes the current repo path into the app handler.

REPO_ROOT="$(pwd)"
APP_DIR="$HOME/Applications/YRVIUpgrade.app"
CONTENTS="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS/MacOS"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

echo "Registering yrvi:// URL scheme..."
echo "Repo root: $REPO_ROOT"

mkdir -p "$MACOS_DIR"

# ── Info.plist ────────────────────────────────────────────────
cat > "$CONTENTS/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.yourockfund.yrvi-upgrade</string>
    <key>CFBundleName</key>
    <string>YRVIUpgrade</string>
    <key>CFBundleExecutable</key>
    <string>YRVIUpgrade</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleURLTypes</key>
    <array>
        <dict>
            <key>CFBundleURLName</key>
            <string>YRVI Upgrade</string>
            <key>CFBundleURLSchemes</key>
            <array>
                <string>yrvi</string>
            </array>
        </dict>
    </array>
    <key>LSBackgroundOnly</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
</dict>
</plist>
PLIST

# ── App handler — repo root baked in at registration time ─────
cat > "$MACOS_DIR/YRVIUpgrade" << HANDLER
#!/bin/bash
open -a Terminal "$REPO_ROOT/scripts/yrvi-upgrade.command"
HANDLER

chmod +x "$MACOS_DIR/YRVIUpgrade"

# ── Register with Launch Services ────────────────────────────
if [ ! -f "$LSREGISTER" ]; then
    echo "Error: lsregister not found at expected path — registration skipped"
    echo "App bundle created at $APP_DIR"
    exit 1
fi

"$LSREGISTER" -f "$APP_DIR"

echo "URL scheme registered — yrvi://upgrade is ready"
