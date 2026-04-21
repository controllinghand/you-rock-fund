#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  YRVI Trading System — Startup & Pre-flight Check
#  Run after any reboot, or double-click "YRVI Startup" on Desktop
# ─────────────────────────────────────────────────────────────

PROJ="/Users/seanleegreer/you_rock_fund"
PYTHON="$PROJ/venv/bin/python3"
PLIST_SRC="$PROJ/com.yourockfund.scheduler.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.yourockfund.scheduler.plist"
LABEL="com.yourockfund.scheduler"
GW_LABEL="com.yourockfund.ibgateway"
IBC_LOG="$HOME/IBC/Logs/ibgateway_stderr.log"

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

# Ensure plist is in LaunchAgents
if [ ! -f "$PLIST_DEST" ]; then
    warn "Plist not in LaunchAgents — copying..."
    cp "$PLIST_SRC" "$PLIST_DEST"
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

# DRY_RUN
DRY=$(grep "^DRY_RUN" trader.py | grep -o "True\|False" | head -1)
if [ "$DRY" = "False" ]; then
    pass "DRY_RUN = False  (live orders enabled)"
elif [ "$DRY" = "True" ]; then
    warn "DRY_RUN = True  — no real orders will be placed"
else
    warn "Could not determine DRY_RUN state in trader.py"
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
    if [ "$P" -eq 0 ]; then
        fail "0 positions sized — pipeline would abort Monday"
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

if   [ "$FAIL" -eq 0 ] && [ "$WARN" -eq 0 ]; then
    echo ""
    printf "  ${BOLD}${GREEN}🟢  GO — All systems ready for Monday 10:00 AM PST${NC}\n"
elif [ "$FAIL" -eq 0 ]; then
    echo ""
    printf "  ${BOLD}${YELLOW}🟡  GO with warnings — review items above before Monday${NC}\n"
else
    echo ""
    printf "  ${BOLD}${RED}🔴  NO-GO — resolve %d critical issue(s) before Monday${NC}\n" "$FAIL"
fi
echo ""
