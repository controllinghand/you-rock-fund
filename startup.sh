#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  YRVI Trading System — Startup & Pre-flight Check
#  Run after any reboot, or double-click "YRVI Startup" on Desktop
# ─────────────────────────────────────────────────────────────

PROJ=$(cd "$(dirname "$0")" && pwd)
PYTHON="$PROJ/venv/bin/python3"
NODE="$(command -v node 2>/dev/null)"
NPM="$(command -v npm 2>/dev/null)"
PLIST_SRC="$PROJ/com.yourockfund.scheduler.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.yourockfund.scheduler.plist"
LABEL="com.yourockfund.scheduler"
GW_LABEL="com.yourockfund.ibgateway"
IBC_LOG="$HOME/IBC/Logs/ibgateway_stderr.log"
API_PLIST_SRC="$PROJ/com.yourockfund.api.plist"
API_PLIST_DEST="$HOME/Library/LaunchAgents/com.yourockfund.api.plist"
API_LABEL="com.yourockfund.api"

# ANSI colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

PASS=0; FAIL=0; WARN=0

pass() { printf "  ${GREEN}✅${NC}  %s\n" "$1"; ((PASS++)) || true; }
fail() { printf "  ${RED}❌${NC}  %s\n" "$1"; ((FAIL++)) || true; }
warn() { printf "  ${YELLOW}⚠️${NC}   %s\n" "$1"; ((WARN++)) || true; }

section() {
    echo ""
    printf "${BOLD}${BLUE}%s${NC}\n" "$1"
    printf '%0.s─' {1..52}; echo ""
}

# ── Banner ────────────────────────────────────────────────────
echo ""
printf "${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║    YOU ROCK VOLATILITY INCOME FUND               ║"
echo "║    System Startup & Pre-flight Check             ║"
echo "╚══════════════════════════════════════════════════╝"
printf "${NC}"
echo "  $(date '+%A %Y-%m-%d  %H:%M:%S %Z')"

# ═════════════════════════════════════════════════════════════
section "1 / 4   IB Gateway  (via IBC launchd service)"
# ═════════════════════════════════════════════════════════════

ibkr_port_open() {
    lsof -i :4002 > /dev/null 2>&1 || lsof -i :4001 > /dev/null 2>&1
}

GW_PID=$(launchctl list "$GW_LABEL" 2>/dev/null | grep '"PID"' | grep -o '[0-9]*' || true)

if [ -n "$GW_PID" ] && ibkr_port_open; then
    pass "IB Gateway running  (PID $GW_PID, API port open)"

elif [ -n "$GW_PID" ]; then
    # Process alive but port not open yet — likely still loading
    warn "IB Gateway running (PID $GW_PID) but API port not open yet — waiting..."
    for i in $(seq 1 30); do sleep 1; ibkr_port_open && break; printf "."; done
    echo ""
    if ibkr_port_open; then
        pass "IB Gateway API port now open"
    else
        warn "API port still closed — IB Gateway may be logging in (allow ~60 s)"
    fi

elif launchctl list "$GW_LABEL" > /dev/null 2>&1; then
    # Registered but not running — restart it
    warn "IB Gateway service registered but not running — restarting..."
    launchctl kickstart -k "gui/$(id -u)/$GW_LABEL" > /dev/null 2>&1 || true
    printf "      ⏳ Waiting up to 45 seconds for IB Gateway to launch"
    for i in $(seq 1 45); do
        sleep 1; printf "."
        GW_PID=$(launchctl list "$GW_LABEL" 2>/dev/null | grep '"PID"' | grep -o '[0-9]*' || true)
        [ -n "$GW_PID" ] && ibkr_port_open && break
    done
    echo ""
    GW_PID=$(launchctl list "$GW_LABEL" 2>/dev/null | grep '"PID"' | grep -o '[0-9]*' || true)
    if [ -n "$GW_PID" ]; then
        pass "IB Gateway restarted  (PID $GW_PID)"
    else
        fail "IB Gateway failed to restart"
        [ -f "$IBC_LOG" ] && warn "Last log line: $(tail -1 "$IBC_LOG" 2>/dev/null)"
        warn "Run:  tail -f $IBC_LOG"
    fi

else
    fail "IBC launchd service not installed (com.yourockfund.ibgateway)"
    warn "Run setup once:  bash $PROJ/setup_ibc.sh"
fi

# ═════════════════════════════════════════════════════════════
section "2 / 4   YRVI Scheduler (launchd)"
# ═════════════════════════════════════════════════════════════

# Kill any old nohup scheduler that predates launchd management
OLD_NOHUP=$(pgrep -f "python.*scheduler.py" 2>/dev/null | \
            while read pid; do
                # Exclude if it's the launchd-managed one (parent = launchd PID 1)
                ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
                [ "$ppid" = "1" ] || echo "$pid"
            done)
if [ -n "$OLD_NOHUP" ]; then
    warn "Found non-launchd scheduler process(es): $OLD_NOHUP — stopping them..."
    echo "$OLD_NOHUP" | xargs kill 2>/dev/null || true
    sleep 1
fi

# Ensure plist is in LaunchAgents (substitute __PROJ__ and __HOME__ placeholders)
if [ ! -f "$PLIST_DEST" ]; then
    warn "Plist not in LaunchAgents — installing..."
    sed -e "s|__PROJ__|$PROJ|g" -e "s|__HOME__|$HOME|g" "$PLIST_SRC" > "$PLIST_DEST"
fi

# Check and start via launchd
SCHED_PID=$(launchctl list "$LABEL" 2>/dev/null | grep '"PID"' | grep -o '[0-9]*' || true)

if [ -n "$SCHED_PID" ]; then
    pass "Scheduler running via launchd  (PID $SCHED_PID)"
elif launchctl list "$LABEL" > /dev/null 2>&1; then
    # Registered but not running (crashed or clean exit) — kick it
    warn "Scheduler registered but not running — restarting..."
    launchctl kickstart -k "gui/$(id -u)/$LABEL" > /dev/null 2>&1 || true
    sleep 3
    SCHED_PID=$(launchctl list "$LABEL" 2>/dev/null | grep '"PID"' | grep -o '[0-9]*' || true)
    if [ -n "$SCHED_PID" ]; then
        pass "Scheduler restarted  (PID $SCHED_PID)"
    else
        fail "Scheduler failed to restart — check scheduler_stderr.log"
    fi
else
    # Not registered at all — bootstrap it
    warn "Scheduler not loaded — bootstrapping via launchd..."
    launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST" 2>/dev/null || \
        launchctl load "$PLIST_DEST" 2>/dev/null
    sleep 3
    SCHED_PID=$(launchctl list "$LABEL" 2>/dev/null | grep '"PID"' | grep -o '[0-9]*' || true)
    if [ -n "$SCHED_PID" ]; then
        pass "Scheduler bootstrapped  (PID $SCHED_PID)"
    else
        fail "Could not bootstrap scheduler"
        fail "Manual fix: launchctl bootstrap gui/\$(id -u) $PLIST_DEST"
    fi
fi

# ═════════════════════════════════════════════════════════════
section "3 / 4   IBKR Connection  (127.0.0.1:\$IBKR_PORT)"
# ═════════════════════════════════════════════════════════════

# Read port from .env so this section stays in sync with config automatically
IBKR_PORT_VAL=$("$PYTHON" -c "
import os; from dotenv import load_dotenv; load_dotenv()
print(os.environ.get('IBKR_PORT', '4002'))
" 2>/dev/null)
IBKR_PORT_VAL="${IBKR_PORT_VAL:-4002}"

IBKR_OUT=$("$PYTHON" -c "
import sys
sys.path.insert(0, '$PROJ')
from ib_insync import IB
ib = IB()
try:
    ib.connect('127.0.0.1', $IBKR_PORT_VAL, clientId=98, timeout=8)
    accts = ib.managedAccounts()
    print('OK account=' + (accts[0] if accts else 'unknown'))
    ib.disconnect()
except Exception as e:
    print('FAIL ' + str(e))
" 2>/dev/null)

if echo "$IBKR_OUT" | grep -q "^OK"; then
    ACCT=$(echo "$IBKR_OUT" | sed 's/.*account=//')
    pass "Connected  (account: $ACCT)"
else
    ERR=$(echo "$IBKR_OUT" | sed 's/^FAIL //')
    fail "Connection failed: $ERR"
    warn "IB Gateway paper=4002 live=4001 | check IB Gateway is running and API is enabled"
fi

# ═════════════════════════════════════════════════════════════
section "4 / 4   Pre-flight Checks"
# ═════════════════════════════════════════════════════════════

cd "$PROJ"

# .env populated
ALL_ENV_OK=true
for KEY in IBKR_HOST IBKR_PORT IBKR_CLIENT_ID ACCOUNT RENDER_URL RENDER_SECRET; do
    VAL=$("$PYTHON" -c "
import os; from dotenv import load_dotenv; load_dotenv()
print(os.environ.get('$KEY', ''))
" 2>/dev/null)
    if [ -z "$VAL" ]; then
        fail ".env key missing: $KEY"
        ALL_ENV_OK=false
    fi
done
[ "$ALL_ENV_OK" = "true" ] && pass ".env — all 6 keys populated"

# DRY_RUN (read from settings.json via config.get_settings)
DRY=$("$PYTHON" -c "
from config import get_settings
s = get_settings()
print(s.get('dry_run', False))
" 2>/dev/null)
if [ "$DRY" = "False" ]; then
    pass "DRY_RUN = False  (live orders enabled)"
elif [ "$DRY" = "True" ]; then
    warn "DRY_RUN = True  — no real orders will be placed"
else
    warn "Could not determine DRY_RUN state (settings.json missing?)"
fi

# MIN_DAYS_TO_EXPIRY
DTE=$(grep "^MIN_DAYS_TO_EXPIRY" screener.py | grep -o '[0-9]*' | head -1)
if [ "$DTE" = "3" ]; then
    pass "MIN_DAYS_TO_EXPIRY = 3  (correct for Monday execution)"
else
    warn "MIN_DAYS_TO_EXPIRY = ${DTE:-unknown}  (expected 3 — Mon→Fri = 3 DTE)"
fi

# Screener + position sizer
printf "  🔄  Fetching screener targets...\r"
SCREEN_OUT=$("$PYTHON" -c "
import sys, os
sys.path.insert(0, '$PROJ')
os.chdir('$PROJ')
from screener import get_top_targets
from position_sizer import size_all
try:
    targets   = get_top_targets(10)
    positions = size_all(targets)
    cap  = sum(p['capital_used']  for p in positions)
    prem = sum(p['premium_total'] for p in positions)
    yld  = (prem / cap * 100) if cap > 0 else 0
    print(f'OK t={len(targets)} p={len(positions)} cap={cap:.0f} prem={prem:.0f} yld={yld:.2f}')
except Exception as e:
    print('FAIL ' + str(e))
" 2>/dev/null)

if echo "$SCREEN_OUT" | grep -q "^OK"; then
    T=$(echo    "$SCREEN_OUT" | grep -o 't=[0-9]*'    | cut -d= -f2)
    P=$(echo    "$SCREEN_OUT" | grep -o ' p=[0-9]*'   | tr -d ' ' | cut -d= -f2)
    CAP=$(echo  "$SCREEN_OUT" | grep -o 'cap=[0-9]*'  | cut -d= -f2)
    PREM=$(echo "$SCREEN_OUT" | grep -o 'prem=[0-9]*' | cut -d= -f2)
    YLD=$(echo  "$SCREEN_OUT" | grep -o 'yld=[0-9.]*' | cut -d= -f2)
    CAPF=$("$PYTHON" -c "print(f'\${int(\"$CAP\"):,}')" 2>/dev/null || echo "\$$CAP")
    PREMF=$("$PYTHON" -c "print(f'\${int(\"$PREM\"):,}')" 2>/dev/null || echo "\$$PREM")
    pass "Screener: $T targets → $P positions  $CAPF deployed  $PREMF premium  ${YLD}% yield"
    DOW=$(date +%u)   # 1=Mon … 7=Sun
    if [ "$P" -eq 0 ]; then
        if [ "$DOW" -le 2 ]; then
            # Mon/Tue — trades are imminent, 0 positions is critical
            fail "0 positions sized — pipeline would abort Monday"
        elif [ "$DOW" -le 5 ]; then
            # Wed/Thu/Fri — screener resets Saturday; mid-week zeros are normal
            warn "0 positions now (mid-week) — new targets load Saturday 6 PM"
        else
            # Sat/Sun — Saturday screener should have run; worth flagging
            warn "0 positions — screener preview may not have run yet"
        fi
    elif [ "$P" -lt 5 ]; then
        warn "Only $P / 5 positions sized — auto-replacement will fill remaining"
    fi
else
    ERR=$(echo "$SCREEN_OUT" | sed 's/^FAIL //')
    fail "Screener/sizer error: $ERR"
fi

# ═════════════════════════════════════════════════════════════
# GO / NO-GO
# ═════════════════════════════════════════════════════════════

echo ""
echo "══════════════════════════════════════════════════════"
printf "  Checks: ${GREEN}%d passed${NC}  " "$PASS"
printf "${YELLOW}%d warning(s)${NC}  "     "$WARN"
printf "${RED}%d failed${NC}\n"             "$FAIL"
echo "══════════════════════════════════════════════════════"

DOW_FINAL=$(date +%u)   # 1=Mon … 7=Sun
case "$DOW_FINAL" in
    1|2) DAY_CTX="Monday trading is imminent" ;;
    3)   DAY_CTX="next trade Monday 10:00 AM PST" ;;
    4)   DAY_CTX="next trade Monday 10:00 AM PST" ;;
    5)   DAY_CTX="next trade Monday 10:00 AM PST" ;;
    6)   DAY_CTX="screener preview runs tonight 6:00 PM PST" ;;
    7)   DAY_CTX="screener ran yesterday — targets ready for Monday" ;;
    *)   DAY_CTX="next trade Monday 10:00 AM PST" ;;
esac

if   [ "$FAIL" -eq 0 ] && [ "$WARN" -eq 0 ]; then
    echo ""
    printf "  ${BOLD}${GREEN}🟢  GO — All systems ready  (%s)${NC}\n" "$DAY_CTX"
elif [ "$FAIL" -eq 0 ]; then
    echo ""
    printf "  ${BOLD}${YELLOW}🟡  GO with warnings — review items above  (%s)${NC}\n" "$DAY_CTX"
else
    echo ""
    printf "  ${BOLD}${RED}🔴  NO-GO — resolve %d critical issue(s)  (%s)${NC}\n" "$FAIL" "$DAY_CTX"
fi

# ═════════════════════════════════════════════════════════════
section "5 / 5   YRVI Dashboard API  (launchd)"
# ═════════════════════════════════════════════════════════════

# Kill any stale nohup API process that predates launchd management
OLD_NOHUP_API=$(pgrep -f "python.*uvicorn.*api:app" 2>/dev/null | \
    while read pid; do
        ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
        [ "$ppid" = "1" ] || echo "$pid"
    done)
if [ -n "$OLD_NOHUP_API" ]; then
    warn "Found non-launchd API process(es): $OLD_NOHUP_API — stopping them..."
    echo "$OLD_NOHUP_API" | xargs kill 2>/dev/null || true
    sleep 1
fi

# Ensure plist is installed in LaunchAgents
if [ ! -f "$API_PLIST_DEST" ]; then
    warn "API plist not in LaunchAgents — installing..."
    sed -e "s|__PROJ__|$PROJ|g" -e "s|__HOME__|$HOME|g" "$API_PLIST_SRC" > "$API_PLIST_DEST"
fi

API_PID=$(launchctl list "$API_LABEL" 2>/dev/null | grep '"PID"' | grep -o '[0-9]*' || true)

if [ -n "$API_PID" ]; then
    pass "Dashboard API running via launchd  (PID $API_PID, port 8000)"
elif launchctl list "$API_LABEL" > /dev/null 2>&1; then
    warn "API service registered but not running — restarting..."
    launchctl kickstart -k "gui/$(id -u)/$API_LABEL" > /dev/null 2>&1 || true
    sleep 3
    API_PID=$(launchctl list "$API_LABEL" 2>/dev/null | grep '"PID"' | grep -o '[0-9]*' || true)
    if [ -n "$API_PID" ]; then
        pass "Dashboard API restarted  (PID $API_PID)"
    else
        fail "Dashboard API failed to restart — check api_stderr.log"
    fi
else
    warn "API service not loaded — bootstrapping via launchd..."
    launchctl bootstrap "gui/$(id -u)" "$API_PLIST_DEST" 2>/dev/null || \
        launchctl load "$API_PLIST_DEST" 2>/dev/null
    sleep 3
    API_PID=$(launchctl list "$API_LABEL" 2>/dev/null | grep '"PID"' | grep -o '[0-9]*' || true)
    if [ -n "$API_PID" ]; then
        pass "Dashboard API bootstrapped  (PID $API_PID)"
    else
        fail "Could not bootstrap API — manual fix:"
        fail "  launchctl bootstrap gui/\$(id -u) $API_PLIST_DEST"
    fi
fi

# React frontend (npm start — not daemonized via launchd, start on demand)
APP_PID=$(lsof -ti :3000 2>/dev/null | head -1)
if [ -n "$APP_PID" ]; then
    pass "React dashboard running  (port 3000, PID $APP_PID)"
elif [ -n "$NPM" ]; then
    APP_DIR="$PROJ/yrvi-app"
    if [ -d "$APP_DIR/node_modules" ]; then
        warn "React app not running — starting in background..."
        cd "$APP_DIR"
        nohup npm start > "$APP_DIR/app_stdout.log" 2> "$APP_DIR/app_stderr.log" &
        sleep 4
        APP_PID=$(lsof -ti :3000 2>/dev/null | head -1)
        if [ -n "$APP_PID" ]; then
            pass "React app started  (port 3000, PID $APP_PID)"
        else
            warn "React app may still be compiling — check $APP_DIR/app_stderr.log"
        fi
    else
        warn "node_modules not found — run: cd yrvi-app && npm install"
    fi
else
    warn "npm not found — install Node.js to run the dashboard"
fi

echo ""
printf "  ${BOLD}${BLUE}🌐  YRVI Dashboard: http://localhost:3000${NC}\n"
echo ""
