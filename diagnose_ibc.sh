#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  IBC / IB Gateway Diagnostics — You Rock Volatility Income Fund
#
#  Run when IB Gateway isn't starting or connecting:
#    bash diagnose_ibc.sh
#
#  Prints a full picture of the IBC installation, launchd
#  registration, and log tail — then summarises what's broken.
# ─────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()      { printf "  ${GREEN}✅${NC}  %s\n" "$1";  ISSUES_OK+=("$1"); }
fail()    { printf "  ${RED}❌${NC}  %s\n" "$1";    ISSUES_FAIL+=("$1"); }
warn()    { printf "  ${YELLOW}⚠️${NC}   %s\n" "$1"; ISSUES_WARN+=("$1"); }
section() { echo ""; printf "${BOLD}${BLUE}── %s ${NC}\n" "$1"; echo "────────────────────────────────────────────────────"; }

ISSUES_OK=()
ISSUES_FAIL=()
ISSUES_WARN=()

echo ""
printf "${BOLD}${BLUE}"
echo "╔══════════════════════════════════════════════════╗"
echo "║    IBC + IB Gateway Diagnostics — YRVI Fund     ║"
echo "╚══════════════════════════════════════════════════╝"
printf "${NC}"

# ── 1. System Info ────────────────────────────────────────────
section "1 / 7   System Info"

ARCH=$(uname -m)
echo "  Architecture : $ARCH"
echo "  macOS        : $(sw_vers -productVersion) (build $(sw_vers -buildVersion))"
echo "  User         : $(whoami)"
echo "  Home         : $HOME"
echo "  Shell        : $SHELL"

# ── 2. IB Gateway ─────────────────────────────────────────────
section "2 / 7   IB Gateway"

gw_filter() { grep -i "gateway" | grep -v "/\." | grep -iv "uninstall" | sort -V | tail -1; }

GATEWAY_APP=""
GATEWAY_APP=$(find "$HOME/Applications" -maxdepth 3 -name "*.app" 2>/dev/null | gw_filter) || true
if [ -z "$GATEWAY_APP" ]; then
    GATEWAY_APP=$(find "/Applications" -maxdepth 3 -name "*.app" 2>/dev/null | gw_filter) || true
fi
if [ -z "$GATEWAY_APP" ]; then
    GATEWAY_APP=$(find "$HOME/Applications" -maxdepth 3 -name "*.app" 2>/dev/null \
        | grep -i "ibkr" | grep -v "/\." | grep -iv "uninstall" | sort -V | tail -1) || true
fi
if [ -z "$GATEWAY_APP" ]; then
    GATEWAY_APP=$(find "$HOME/Jts/ibgateway" -maxdepth 3 -name "*.app" 2>/dev/null \
        | grep -v "/\." | sort -V | tail -1) || true
fi

if [ -n "$GATEWAY_APP" ]; then
    ok "IB Gateway found"
    echo "  Path    : $GATEWAY_APP"

    # Version from parent dir
    GATEWAY_DIR=$(dirname "$GATEWAY_APP")
    GATEWAY_PARENT=$(basename "$GATEWAY_DIR")
    if echo "$GATEWAY_PARENT" | grep -qE '[0-9]+\.[0-9]+'; then
        GW_VER=$(echo "$GATEWAY_PARENT" | grep -oE '[0-9]+\.[0-9]+' | tail -1)
    elif echo "$GATEWAY_PARENT" | grep -qE '^[0-9]{4}$'; then
        GW_VER=$(echo "$GATEWAY_PARENT" | sed 's/\([0-9][0-9]\)\([0-9][0-9]\)/\1.\2/')
    else
        GW_VER="unknown"
    fi
    echo "  Version : $GW_VER"

    # Binary architecture
    GW_BIN="$GATEWAY_APP/Contents/MacOS/ibgateway"
    if [ -f "$GW_BIN" ]; then
        GW_ARCH=$(file "$GW_BIN" | grep -oE 'arm64|x86_64' | head -1)
        echo "  Binary  : $GW_ARCH"
        if [ "$ARCH" = "arm64" ] && [ "$GW_ARCH" = "x86_64" ]; then
            warn "x86_64 binary on Apple Silicon — runs via Rosetta 2 (may cause issues)"
        else
            ok "Binary architecture matches system ($GW_ARCH)"
        fi
    else
        fail "ibgateway binary not found at $GW_BIN"
    fi
else
    fail "IB Gateway not found in ~/Applications, /Applications, or ~/Jts/ibgateway"
fi

# ── 3. IBC Installation ───────────────────────────────────────
section "3 / 7   IBC Installation"

IBC_DIR="$HOME/IBC"

if [ -d "$IBC_DIR" ]; then
    ok "~/IBC directory exists"
else
    fail "~/IBC directory does not exist — run setup_ibc.sh"
fi

if [ -f "$IBC_DIR/IBC.sh" ]; then
    ok "IBC.sh present"
else
    fail "IBC.sh not found in ~/IBC"
fi

if [ -f "$IBC_DIR/gatewaystartmacos.sh" ]; then
    ok "gatewaystartmacos.sh present"
else
    fail "gatewaystartmacos.sh not found in ~/IBC"
fi

echo ""
echo "  IBC script permissions:"
ls -la "$IBC_DIR"/*.sh 2>/dev/null | sed 's/^/    /' || echo "    (no .sh files found)"

# Check executability
NON_EXEC=$(find "$IBC_DIR" -maxdepth 1 -name "*.sh" ! -perm -u+x 2>/dev/null)
if [ -z "$NON_EXEC" ] && ls "$IBC_DIR"/*.sh &>/dev/null; then
    ok "All IBC .sh scripts are executable"
else
    [ -n "$NON_EXEC" ] && fail "Non-executable scripts found:$(echo "$NON_EXEC" | sed 's/^/ /')"
fi

if [ -f "$IBC_DIR/config.ini" ]; then
    ok "config.ini present"
    echo ""
    echo "  config.ini contents (passwords masked):"
    sed 's/\(IbPassword=\).*/\1[MASKED]/' "$IBC_DIR/config.ini" | sed 's/^/    /'
else
    fail "config.ini not found in ~/IBC — run setup_ibc.sh"
fi

# ── 4. launchd Plist ──────────────────────────────────────────
section "4 / 7   launchd Plist"

PLIST="$HOME/Library/LaunchAgents/com.yourockfund.ibgateway.plist"

if [ -f "$PLIST" ]; then
    ok "com.yourockfund.ibgateway.plist installed"
    echo ""
    echo "  Plist contents:"
    cat "$PLIST" | sed 's/^/    /'
else
    fail "Plist not found at $PLIST — run setup_ibc.sh"
fi

echo ""
echo "  launchctl list com.yourockfund.ibgateway:"
LAUNCHCTL_OUT=$(launchctl list com.yourockfund.ibgateway 2>&1)
echo "$LAUNCHCTL_OUT" | sed 's/^/    /'

if echo "$LAUNCHCTL_OUT" | grep -q '"PID"'; then
    GW_PID=$(echo "$LAUNCHCTL_OUT" | grep '"PID"' | grep -o '[0-9]*')
    ok "IB Gateway service running  (PID $GW_PID)"
elif echo "$LAUNCHCTL_OUT" | grep -q '"Label"'; then
    LAST_EXIT=$(echo "$LAUNCHCTL_OUT" | grep '"LastExitStatus"' | grep -o '[0-9]*')
    if [ "$LAST_EXIT" = "0" ] || [ -z "$LAST_EXIT" ]; then
        warn "Service registered but not running (LastExitStatus=$LAST_EXIT)"
    else
        fail "Service registered but crashed (LastExitStatus=$LAST_EXIT)"
    fi
else
    fail "Service not registered with launchd — run setup_ibc.sh"
fi

# ── 5. IBC Logs ───────────────────────────────────────────────
section "5 / 7   IBC Logs"

STDOUT_LOG="$HOME/IBC/Logs/ibgateway_stdout.log"
STDERR_LOG="$HOME/IBC/Logs/ibgateway_stderr.log"

if [ -f "$STDOUT_LOG" ]; then
    ok "stdout log exists"
    echo ""
    echo "  Last 20 lines of ibgateway_stdout.log:"
    tail -20 "$STDOUT_LOG" | sed 's/^/    /'
else
    warn "No stdout log at $STDOUT_LOG (IBC may never have run)"
fi

if [ -f "$STDERR_LOG" ]; then
    ok "stderr log exists"
    echo ""
    echo "  Last 20 lines of ibgateway_stderr.log:"
    tail -20 "$STDERR_LOG" | sed 's/^/    /'
else
    warn "No stderr log at $STDERR_LOG (IBC may never have run)"
fi

# ── 6. Manual Start Command ───────────────────────────────────
section "6 / 7   Manual Start Command"

STARTGW="$HOME/IBC/gatewaystartmacos.sh"
echo "  To start IB Gateway manually (outside launchd), run:"
echo ""
if [ -f "$STARTGW" ]; then
    echo "    bash $STARTGW -inline"
    echo ""
    echo "  Or to test IBC directly:"
    echo "    bash $HOME/IBC/IBC.sh $HOME/IBC/config.ini"
else
    echo "    (cannot determine — gatewaystartmacos.sh not found)"
fi
echo ""
echo "  To reload the launchd service:"
echo "    launchctl bootout gui/\$(id -u) $PLIST"
echo "    launchctl bootstrap gui/\$(id -u) $PLIST"
echo ""
echo "  To kickstart (kill + restart) the service:"
echo "    launchctl kickstart -k gui/\$(id -u)/com.yourockfund.ibgateway"

# ── 7. Summary ────────────────────────────────────────────────
section "7 / 7   Summary"

for msg in "${ISSUES_OK[@]}";   do printf "  ${GREEN}✅${NC}  %s\n" "$msg"; done
for msg in "${ISSUES_WARN[@]}"; do printf "  ${YELLOW}⚠️${NC}   %s\n" "$msg"; done
for msg in "${ISSUES_FAIL[@]}"; do printf "  ${RED}❌${NC}  %s\n" "$msg"; done

echo ""
if [ ${#ISSUES_FAIL[@]} -eq 0 ] && [ ${#ISSUES_WARN[@]} -eq 0 ]; then
    printf "${GREEN}${BOLD}  All checks passed.${NC}\n"
elif [ ${#ISSUES_FAIL[@]} -eq 0 ]; then
    printf "${YELLOW}${BOLD}  Warnings found — review above.${NC}\n"
else
    printf "${RED}${BOLD}  ${#ISSUES_FAIL[@]} issue(s) found — fix the ❌ items above, then re-run setup_ibc.sh.${NC}\n"
fi
echo ""
