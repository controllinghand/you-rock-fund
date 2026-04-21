#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  IBC + IB Gateway Auto-Login — One-Time Setup
#  You Rock Volatility Income Fund — Mac Mini
#
#  Run once after a fresh install or credential change:
#    bash setup_ibc.sh
#
#  What it does:
#    1. Verifies IB Gateway is installed
#    2. Downloads IBC (Interactive Brokers Controller) if absent
#    3. Generates ~/IBC/config.ini from .env credentials
#    4. Configures ~/IBC/StartGateway.sh with correct paths
#    5. Installs and loads the launchd plist so IB Gateway
#       starts automatically on every login / reboot
# ─────────────────────────────────────────────────────────────

set -euo pipefail

PROJ="/Users/seanleegreer/you_rock_fund"
IBC_DIR="$HOME/IBC"
IBC_LOG_DIR="$IBC_DIR/Logs"
IBC_VERSION="3.18.0"
IBC_ZIP_URL="https://github.com/IbcAlpha/IBC/releases/download/${IBC_VERSION}/IBCMacos-${IBC_VERSION}.zip"
IBC_ZIP="/tmp/IBCMacos-${IBC_VERSION}.zip"

PLIST_SRC="$PROJ/com.yourockfund.ibgateway.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.yourockfund.ibgateway.plist"
GATEWAY_LABEL="com.yourockfund.ibgateway"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { printf "  ${GREEN}✅${NC}  %s\n" "$1"; }
fail() { printf "  ${RED}❌${NC}  %s\n" "$1"; exit 1; }
warn() { printf "  ${YELLOW}⚠️${NC}   %s\n" "$1"; }
info() { printf "  ${BLUE}ℹ️${NC}   %s\n" "$1"; }

echo ""
printf "${BOLD}${BLUE}"
echo "╔══════════════════════════════════════════════════╗"
echo "║    IBC + IB Gateway Setup — YRVI Fund            ║"
echo "╚══════════════════════════════════════════════════╝"
printf "${NC}"
echo ""

# ── Step 1: Load .env ─────────────────────────────────────────
echo "${BOLD}Step 1 / 5   Load credentials from .env${NC}"
echo "──────────────────────────────────────────────────────"

ENV_FILE="$PROJ/.env"
[ -f "$ENV_FILE" ] || fail ".env not found at $ENV_FILE"

# Parse .env (skip comments and blanks)
get_env() {
    grep "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'"
}

IBKR_USERNAME=$(get_env "IBKR_USERNAME")
IBKR_PASSWORD=$(get_env "IBKR_PASSWORD")
IBKR_PORT=$(get_env "IBKR_PORT")

if [ -z "$IBKR_USERNAME" ] || [ -z "$IBKR_PASSWORD" ]; then
    echo ""
    warn "IBKR_USERNAME or IBKR_PASSWORD not found in .env"
    warn "Add these two lines to your .env file:"
    echo ""
    echo "    IBKR_USERNAME=your_ibkr_login_id"
    echo "    IBKR_PASSWORD=your_ibkr_password"
    echo ""
    fail "Re-run setup_ibc.sh after updating .env"
fi

[ -z "$IBKR_PORT" ] && IBKR_PORT="7497"
TRADING_MODE="paper"
[ "$IBKR_PORT" = "7496" ] && TRADING_MODE="live"
ok "Credentials loaded  (port=$IBKR_PORT  mode=$TRADING_MODE)"

# ── Step 2: Verify IB Gateway installation ────────────────────
echo ""
echo "${BOLD}Step 2 / 5   Locate IB Gateway${NC}"
echo "──────────────────────────────────────────────────────"

# Search common install locations
GATEWAY_APP=""
GATEWAY_VERSION=""

find_gateway() {
    # Fixed paths (no version suffix)
    local candidates=(
        "$HOME/Applications/IB Gateway/IB Gateway.app"
        "/Applications/IB Gateway.app"
        "$HOME/Applications/IBKR Desktop/IBKR Desktop.app"
        "/Applications/IBKR Desktop.app"
    )
    for c in "${candidates[@]}"; do
        [ -d "$c" ] && echo "$c" && return 0
    done

    # Versioned install dirs: "IB Gateway 10.37/IB Gateway 10.37.app" etc.
    local versioned
    versioned=$(find "$HOME/Applications" -maxdepth 2 -name "*.app" -path "*Gateway*" 2>/dev/null \
                | sort -V | tail -1)
    [ -n "$versioned" ] && echo "$versioned" && return 0

    versioned=$(find "/Applications" -maxdepth 2 -name "*.app" -path "*Gateway*" 2>/dev/null \
                | sort -V | tail -1)
    [ -n "$versioned" ] && echo "$versioned" && return 0

    # Offline installer layout: ~/Jts/ibgateway/<version>/*.app
    local jts_gw
    jts_gw=$(find "$HOME/Jts/ibgateway" -maxdepth 2 -name "*.app" 2>/dev/null | head -1)
    [ -n "$jts_gw" ] && echo "$jts_gw" && return 0

    return 1
}

GATEWAY_APP=$(find_gateway 2>/dev/null) || true

if [ -z "$GATEWAY_APP" ]; then
    echo ""
    warn "IB Gateway not found. Install it first:"
    echo ""
    echo "  1. Go to:  https://www.interactivebrokers.com/en/trading/ibgateway-stable.php"
    echo "  2. Download the macOS offline installer"
    echo "  3. Run the installer — default path: ~/Applications/IB Gateway/"
    echo "  4. Re-run this script"
    echo ""
    fail "IB Gateway not installed"
fi
ok "IB Gateway: $GATEWAY_APP"

# Detect version number from the install directory
GATEWAY_DIR=$(dirname "$GATEWAY_APP")
GATEWAY_VERSION=$(ls "$GATEWAY_DIR" 2>/dev/null | grep -E '^[0-9]+$' | sort -n | tail -1 || true)
[ -z "$GATEWAY_VERSION" ] && GATEWAY_VERSION=$(ls "$HOME/Jts/ibgateway" 2>/dev/null | grep -E '^[0-9]+$' | sort -n | tail -1 || true)
[ -z "$GATEWAY_VERSION" ] && GATEWAY_VERSION="1028"   # sensible default
ok "Version dir: $GATEWAY_VERSION"

# Config path where IB Gateway writes its settings
GATEWAY_CONF="$HOME/Jts/ibgateway/$GATEWAY_VERSION"

# ── Step 3: Install IBC ───────────────────────────────────────
echo ""
echo "${BOLD}Step 3 / 5   Install IBC $IBC_VERSION${NC}"
echo "──────────────────────────────────────────────────────"

if [ -f "$IBC_DIR/IBCMacos.sh" ] || [ -f "$IBC_DIR/StartGateway.sh" ]; then
    ok "IBC already installed at $IBC_DIR"
else
    info "Downloading IBC $IBC_VERSION..."
    curl -fsSL "$IBC_ZIP_URL" -o "$IBC_ZIP" || \
        fail "Download failed — check internet connection and IBC_ZIP_URL in setup_ibc.sh"
    mkdir -p "$IBC_DIR"
    unzip -q "$IBC_ZIP" -d "$IBC_DIR"
    rm -f "$IBC_ZIP"
    chmod +x "$IBC_DIR"/*.sh 2>/dev/null || true
    ok "IBC $IBC_VERSION installed to $IBC_DIR"
fi
mkdir -p "$IBC_LOG_DIR"

# ── Step 4: Generate config.ini ───────────────────────────────
echo ""
echo "${BOLD}Step 4 / 5   Generate ~/IBC/config.ini${NC}"
echo "──────────────────────────────────────────────────────"

CONFIG_DEST="$IBC_DIR/config.ini"

# Start from repo template, substitute placeholders
sed \
    -e "s/PLACEHOLDER_USERNAME/$IBKR_USERNAME/" \
    -e "s/PLACEHOLDER_PASSWORD/$IBKR_PASSWORD/" \
    -e "s/PLACEHOLDER_TRADING_MODE/$TRADING_MODE/" \
    -e "s/PLACEHOLDER_PORT/$IBKR_PORT/" \
    "$PROJ/ibc_config.ini" > "$CONFIG_DEST"

chmod 600 "$CONFIG_DEST"   # credentials file — owner-read only
ok "config.ini written (mode 600)"

# ── Configure StartGateway.sh ─────────────────────────────────
STARTGW="$IBC_DIR/StartGateway.sh"

if [ ! -f "$STARTGW" ]; then
    # IBC ships a sample — copy and configure it
    STARTGW_SAMPLE=$(find "$IBC_DIR" -name "StartGateway.sh.sample" 2>/dev/null | head -1 || true)
    [ -z "$STARTGW_SAMPLE" ] && fail "IBC installation missing StartGateway.sh — re-run setup"
    cp "$STARTGW_SAMPLE" "$STARTGW"
fi

# Patch key variables in StartGateway.sh
patch_var() {
    local var="$1" val="$2" file="$3"
    # Handle both quoted and unquoted assignments
    if grep -qE "^${var}=" "$file"; then
        sed -i '' "s|^${var}=.*|${var}=\"${val}\"|" "$file"
    else
        echo "${var}=\"${val}\"" >> "$file"
    fi
}

patch_var "TWS_MAJOR_VRSN" "$GATEWAY_VERSION" "$STARTGW"
patch_var "IBC_PATH"        "$IBC_DIR"          "$STARTGW"
patch_var "GATEWAY_PATH"    "$(dirname "$GATEWAY_APP")" "$STARTGW"
patch_var "TWS_CONFIG_PATH" "$GATEWAY_CONF"     "$STARTGW"
patch_var "LOG_PATH"        "$IBC_LOG_DIR"      "$STARTGW"
patch_var "TRADING_MODE"    "$TRADING_MODE"     "$STARTGW"
patch_var "JAVA_PATH"       ""                  "$STARTGW"

chmod +x "$STARTGW"
ok "StartGateway.sh configured"

# ── Step 5: Install and load launchd plist ────────────────────
echo ""
echo "${BOLD}Step 5 / 5   Install launchd service${NC}"
echo "──────────────────────────────────────────────────────"

# Unload existing service if present (ignore errors)
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/$GATEWAY_LABEL" 2>/dev/null || true

cp "$PLIST_SRC" "$PLIST_DEST"
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST" 2>/dev/null || \
    launchctl load "$PLIST_DEST" 2>/dev/null || true

sleep 3
GW_PID=$(launchctl list "$GATEWAY_LABEL" 2>/dev/null | grep '"PID"' | grep -o '[0-9]*' || true)
if [ -n "$GW_PID" ]; then
    ok "launchd service loaded and IB Gateway starting  (PID $GW_PID)"
else
    warn "Service registered but IB Gateway not yet running (may still be loading)"
    info "Check: launchctl list $GATEWAY_LABEL"
    info "Logs:  tail -f $IBC_LOG_DIR/ibgateway_stderr.log"
fi

# ── Summary ───────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
printf "${BOLD}${GREEN}  Setup complete.${NC}\n"
echo "══════════════════════════════════════════════════════"
echo ""
echo "  IB Gateway will now auto-start on every login."
echo ""
echo "  Monitor:"
echo "    tail -f $IBC_LOG_DIR/ibgateway_stdout.log"
echo "    tail -f $IBC_LOG_DIR/ibgateway_stderr.log"
echo ""
echo "  Test API connection:"
echo "    bash startup.sh"
echo ""
echo "  Manual restart:"
echo "    launchctl kickstart -k gui/\$(id -u)/$GATEWAY_LABEL"
echo ""
