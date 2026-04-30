#!/bin/bash

LOCKFILE="$HOME/.yrvi_setup.lock"
if [ -f "$LOCKFILE" ]; then
    LOCK_AGE=$(( $(date +%s) - $(date -r "$LOCKFILE" +%s) ))
    if [ "$LOCK_AGE" -lt 600 ]; then
        echo "$(date): Another instance is running (lock age: ${LOCK_AGE}s) — exiting"
        exit 0
    else
        echo "$(date): Stale lock found (${LOCK_AGE}s old) — removing and proceeding"
        rm -f "$LOCKFILE"
    fi
fi
touch "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT

# ─────────────────────────────────────────────────────────────
#  Docker Setup — You Rock Volatility Income Fund
#  Containerized branch: Docker replaces launchd/IBC
#
#  Usage:
#    bash setup_docker.sh --paper   # paper trading (IBKR paper account)
#    bash setup_docker.sh --live    # live trading  (IBKR live account)
#
#  What it does:
#    1. Checks Docker is running (install Rancher Desktop first)
#    2. Injects secrets from macOS Keychain → docker/secrets/ files
#    3. Validates .env.compose and config (docker/preflight.sh)
#    4. Builds and starts all 4 containers (ib_gateway, api, scheduler, web)
#       then optionally wipes the plaintext secret files
#    5. Installs com.yourockfund.docker launchd service so containers
#       start automatically on every login / reboot
#    6. Installs YRVI Startup.app in /Applications
# ─────────────────────────────────────────────────────────────

set -euo pipefail

# ── Flag parsing ───────────────────────────────────────────────

usage() {
    echo ""
    echo "  Usage: setup_docker.sh --paper|--live [--keep-secrets]"
    echo ""
    echo "    --paper          use paper trading secrets (IBKR paper account)"
    echo "    --live           use live trading secrets  (IBKR live account)"
    echo "    --keep-secrets   skip deletion of plaintext secret files after launch"
    echo ""
}

TRADING_MODE=""
KEEP_SECRETS=false
for arg in "$@"; do
    case "$arg" in
        --paper)         TRADING_MODE="paper" ;;
        --live)          TRADING_MODE="live"  ;;
        --keep-secrets)  KEEP_SECRETS=true    ;;
        --help|-h) usage; exit 0 ;;
        *) printf "Unknown flag: %s\n" "$arg" >&2; usage; exit 1 ;;
    esac
done

if [ -z "$TRADING_MODE" ]; then
    usage
    exit 1
fi

# ── Globals ────────────────────────────────────────────────────

PROJ=$(cd "$(dirname "$0")" && pwd)
DOCKER_PLIST_SRC="$PROJ/com.yourockfund.docker.plist"
DOCKER_PLIST_DEST="$HOME/Library/LaunchAgents/com.yourockfund.docker.plist"
DOCKER_LABEL="com.yourockfund.docker"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { printf "  ${GREEN}✅${NC}  %s\n" "$1"; }
fail() { printf "  ${RED}❌${NC}  %s\n" "$1" >&2; exit 1; }
warn() { printf "  ${YELLOW}⚠️${NC}   %s\n" "$1"; }
info() { printf "  ${BLUE}ℹ️${NC}   %s\n" "$1"; }

MODE_LABEL="paper"
[ "$TRADING_MODE" = "live" ] && MODE_LABEL="LIVE"

echo ""
printf "${BOLD}${BLUE}"
echo "╔══════════════════════════════════════════════════╗"
printf "║    Docker Setup — YRVI Fund  (%-17s)  ║\n" "$MODE_LABEL"
echo "╚══════════════════════════════════════════════════╝"
printf "${NC}"
echo ""

# ── Step 1: Check Docker is running ──────────────────────────
echo "${BOLD}Step 1 / 6   Check Docker${NC}"
echo "──────────────────────────────────────────────────────"

if ! command -v docker &>/dev/null; then
    fail "docker not found — install Rancher Desktop from https://rancherdesktop.io and retry"
fi

if ! docker info &>/dev/null 2>&1; then
    fail "Docker daemon not running — start Rancher Desktop and retry"
fi

DOCKER_VER=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
ok "Docker running  (server $DOCKER_VER)"

echo ""
warn "Make sure Rancher Desktop is set to auto-start:"
echo "       Preferences → Application → Behavior tab:"
echo "         ✅  Automatically start at login  (under Startup)"
echo "         ✅  Start in the background        (under Background)"
echo "         ☐   Quit when closing window      (leave UNCHECKED)"
echo "       This ensures Docker is running before YRVI containers"
echo "       restart after a reboot."
echo ""

# ── Step 2: Inject secrets from macOS Keychain ───────────────
echo ""
echo "${BOLD}Step 2 / 6   Inject secrets from macOS Keychain${NC}"
echo "──────────────────────────────────────────────────────"

cd "$PROJ"
mkdir -p docker/secrets

# Keychain service names (fixed — do not change without updating Keychain entries)
KC_RENDER="YRVI_RENDER"
if [ "$TRADING_MODE" = "paper" ]; then
    KC_TWS="YRVI_TWS_PAPER"
    TWS_SECRET_FILE="docker/secrets/tws_password_paper"
    TWS_LABEL="IBKR paper trading password"
else
    KC_TWS="YRVI_TWS_LIVE"
    TWS_SECRET_FILE="docker/secrets/tws_password_live"
    TWS_LABEL="IBKR live trading password"
fi

# Files written this run — tracked so we can offer to delete them after launch
WRITTEN_SECRET_FILES=()

echo ""
info "macOS may prompt you to allow access to Keychain — click Allow."
echo ""

# inject_secret SERVICE FILE LABEL
#   Checks Keychain for SERVICE. If found, uses it silently.
#   If not found, prompts the user (with double-entry confirmation)
#   and stores the value in Keychain.
#   Always writes the value to FILE and sets chmod 600.
inject_secret() {
    local service="$1"
    local file="$2"
    local label="$3"
    local value

    value=$(security find-generic-password -s "$service" -w 2>/dev/null || true)

    if [ -n "$value" ]; then
        ok "Retrieved '$label' from Keychain"
    else
        local confirm
        while true; do
            printf "  (you can paste — input is hidden but accepted)\n"
            printf "  Enter %s: " "$label"
            read -rs value </dev/tty
            echo ""

            if [ -z "$value" ]; then
                fail "'$label' cannot be empty"
            fi

            printf "  Confirm %s: " "$label"
            read -rs confirm </dev/tty
            echo ""

            if [ "$value" = "$confirm" ]; then
                local char_count=${#value}
                printf "  ${GREEN}✅${NC}  Password confirmed (%d characters stored).\n" "$char_count"
                break
            else
                printf "  ${RED}❌${NC}  Passwords do not match. Please try again.\n"
            fi
        done

        # -U: add or update if the item already exists
        if ! security add-generic-password -U -s "$service" -a "$USER" -w "$value" 2>/dev/null; then
            fail "Failed to store '$label' in Keychain — check Keychain Access permissions"
        fi
        ok "Stored '$label' in Keychain"
    fi

    printf '%s' "$value" > "$file"
    chmod 600 "$file"
    WRITTEN_SECRET_FILES+=("$file")
}

inject_secret "$KC_TWS"    "$TWS_SECRET_FILE"            "$TWS_LABEL"
inject_secret "$KC_RENDER" "docker/secrets/render_secret" "Render screener API secret"

ok "Secret files written to docker/secrets/"

# ── Step 3: Validate .env.compose and config ─────────────────
echo ""
echo "${BOLD}Step 3 / 6   Validate .env.compose and config${NC}"
echo "──────────────────────────────────────────────────────"

if [ ! -f ".env.compose" ]; then
    fail ".env.compose not found — copy .env.compose.example to .env.compose and fill in credentials"
fi

# Read a value from .env.compose (strips inline comments and CR)
env_value() {
    grep -E "^${1}=" .env.compose 2>/dev/null \
        | head -1 \
        | cut -d'=' -f2- \
        | sed 's/#.*//' \
        | tr -d '\r ' \
        || true
}

is_placeholder() {
    case "$1" in
        ""|your_*|YOUR_*|DUP_*|replace-*|get_from*) return 0 ;;
        *) return 1 ;;
    esac
}

# Mode-specific required vars in .env.compose
if [ "$TRADING_MODE" = "paper" ]; then
    REQUIRED_VARS="ACCOUNT_PAPER TWS_USERID_PAPER"
else
    REQUIRED_VARS="ACCOUNT_LIVE TWS_USERID_LIVE"
fi

MISSING=""
for var in $REQUIRED_VARS; do
    val=$(env_value "$var")
    if is_placeholder "$val"; then
        MISSING="${MISSING}    - ${var}\n"
    fi
done

if [ -n "$MISSING" ]; then
    printf "  ${RED}❌${NC}  Missing or placeholder values in .env.compose:\n"
    printf "$MISSING"
    echo ""
    echo "  Edit .env.compose, fill in the values above, and retry."
    exit 1
fi
ok ".env.compose has required $TRADING_MODE credentials"

# Run the full preflight for paper mode (preflight.sh is paper-centric)
if [ "$TRADING_MODE" = "paper" ]; then
    sh docker/preflight.sh || fail "Preflight check failed — fix the issues above and retry"
fi
ok "Config validated"

# ── Step 4: Build and start containers ───────────────────────
echo ""
echo "${BOLD}Step 4 / 6   Build and start all 4 containers${NC}"
echo "──────────────────────────────────────────────────────"

info "Building images and starting ib_gateway, api, scheduler, web..."

if docker compose --env-file .env.compose up -d --build; then

    # ── Wipe plaintext secret files ───────────────────────────
    if [ "$KEEP_SECRETS" = true ]; then
        warn "--keep-secrets: secret files left on disk in docker/secrets/"
        warn "Delete manually when done: rm docker/secrets/*"
    else
        if [ ${#WRITTEN_SECRET_FILES[@]} -gt 0 ]; then
            for f in "${WRITTEN_SECRET_FILES[@]}"; do
                rm -f "$f"
            done
        fi
        ok "Secret files wiped — passwords remain safely in macOS Keychain"
    fi

    sleep 3
    RUNNING=$(docker compose --env-file .env.compose ps 2>/dev/null \
        | grep -cE "Up|running|healthy" || true)
    if [ "$RUNNING" -ge 4 ]; then
        ok "All $RUNNING containers running"
    elif [ "$RUNNING" -gt 0 ]; then
        warn "$RUNNING / 4 containers running — IB Gateway may still be initializing (allow 60 s)"
        info "Monitor: docker compose --env-file .env.compose logs -f ib_gateway"
    else
        warn "Containers started but status unclear — check:"
        info "  docker compose --env-file .env.compose ps"
    fi

    # ── dry_run safety check ──────────────────────────────────
    info "Checking dry_run safety default..."
    sleep 5
    DRY_RUN=$(curl -sf http://127.0.0.1:8000/api/settings 2>/dev/null \
        | python3 -c \
          "import sys,json; print(json.load(sys.stdin).get('dry_run','?'))" \
          2>/dev/null \
        || echo "?")
    if [ "$DRY_RUN" = "True" ] || [ "$DRY_RUN" = "true" ]; then
        ok "dry_run=true — no IBKR orders will be submitted until you enable trading"
    elif [ "$DRY_RUN" = "False" ] || [ "$DRY_RUN" = "false" ]; then
        warn "dry_run=false — the scheduler WILL submit orders to IBKR when scheduled jobs run"
    else
        info "dry_run not checked yet (API still starting — verify at http://localhost:8000/api/settings)"
    fi

else
    echo ""
    printf "  ${RED}❌${NC}  docker compose up failed.\n"
    warn "Secret files NOT deleted — you may need them to debug the failure."
    info "  docker compose --env-file .env.compose ps"
    info "  docker compose --env-file .env.compose logs"
    exit 1
fi

# ── Step 5: Install Docker auto-start on login ────────────────
echo ""
echo "${BOLD}Step 5 / 6   Install Docker auto-start on login${NC}"
echo "──────────────────────────────────────────────────────"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

sed -e "s|__PROJ__|$PROJ|g" -e "s|__HOME__|$HOME|g" "$DOCKER_PLIST_SRC" > "$DOCKER_PLIST_DEST"

if [ -t 0 ]; then
    launchctl bootstrap "gui/$(id -u)" "$DOCKER_PLIST_DEST" 2>/dev/null || \
        launchctl load "$DOCKER_PLIST_DEST" 2>/dev/null || true
    ok "com.yourockfund.docker installed — containers will auto-start on every login"
else
    ok "com.yourockfund.docker already active (launched by launchd — skipping re-register)"
fi
info "  Reboot log: cat ~/Library/Logs/yrvi-autostart.log"

# ── Step 6: Install Desktop app (macOS only) ─────────────────
echo ""
echo "${BOLD}Step 6 / 6   Install Desktop app${NC}"
echo "──────────────────────────────────────────────────────"

OS=$(uname -s)

if [ "$OS" = "Darwin" ]; then
    APP_DEST="/Applications/YRVI Startup.app"

    if [ -e "$APP_DEST" ]; then
        ok "YRVI Startup app already installed — skipping"
    else
        cp -R "$PROJ/assets/app_template/" "$APP_DEST"
        mkdir -p "$APP_DEST/Contents/Resources"
        cp "$PROJ/assets/YRVI.icns" "$APP_DEST/Contents/Resources/YRVI.icns"
        sed -i '' "s|__PROJ__|$PROJ|g" "$APP_DEST/Contents/MacOS/yrvi_startup"
        chmod +x "$APP_DEST/Contents/MacOS/yrvi_startup"
        xattr -dr com.apple.quarantine "$APP_DEST" 2>/dev/null || true
        defaults write com.apple.dock persistent-apps -array-add \
            "<dict><key>tile-data</key><dict><key>file-data</key><dict>\
<key>_CFURLString</key><string>/Applications/YRVI Startup.app</string>\
<key>_CFURLStringType</key><integer>0</integer></dict></dict></dict>"
        killall Dock 2>/dev/null || true

        ok "YRVI Startup app installed"
    fi
else
    info "Desktop app is macOS only"
    info "  Access dashboard at http://localhost:3000"
fi

# ── Summary ───────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
printf "${BOLD}${GREEN}  Setup complete.${NC}\n"
echo "══════════════════════════════════════════════════════"
echo ""
echo "  Dashboard:  http://localhost:3000"
echo "  API status: http://localhost:8000/api/status"
echo ""
echo "  Wait for IB Gateway to log in (watch for 'Login has completed'):"
echo "    docker compose --env-file .env.compose logs -f ib_gateway"
echo ""
echo "  VNC (if IBKR shows a dialog at first login):"
echo "    1. Set VNC_SERVER_PASSWORD in .env.compose"
echo "    2. docker compose --env-file .env.compose up -d --force-recreate ib_gateway"
echo "    3. Connect a VNC client to localhost:5900"
echo "    macOS: open vnc://localhost:5900 in Finder → Go → Connect to Server"
echo ""
echo "  Pre-flight check anytime:"
echo "    bash startup.sh"
echo ""
echo "  Re-run setup (secrets pulled from Keychain, no prompts):"
echo "    bash setup_docker.sh --$TRADING_MODE"
echo ""

# ─────────────────────────────────────────────────────────────
# KEYCHAIN TEST CHECKLIST
# Run each scenario in order and confirm the expected result.
#
# [ ] First run --paper:
#       prompted for IBKR paper password and Render secret
#       stores both in Keychain under YRVI_TWS_PAPER and YRVI_RENDER
#
# [ ] Passwords visible in Keychain Access app:
#       open Keychain Access → search "YRVI" → two items visible
#
# [ ] Second run --paper:
#       no prompts — both secrets pulled silently from Keychain
#       "Retrieved '...' from Keychain" lines printed
#
# [ ] Containers start successfully with paper credentials:
#       docker compose --env-file .env.compose ps → all 4 Up
#       http://localhost:8000/api/status → ibkr_connected: true
#
# [ ] Secret files deleted after successful launch:
#       answer Y at the deletion prompt
#       ls docker/secrets/ → tws_password_paper and render_secret absent
#
# [ ] Third run --paper:
#       secrets still in Keychain, works without files on disk
#
# [ ] Run --live:
#       prompted separately for live password
#       stored under YRVI_TWS_LIVE (separate from YRVI_TWS_PAPER)
#       render secret reused from existing YRVI_RENDER Keychain entry
#
# [ ] .env.compose missing ACCOUNT_PAPER:
#       exits with "Missing or placeholder values" and lists the var
#       does NOT proceed to build containers
#
# [ ] docker compose up fails (e.g., bad .env.compose port conflict):
#       secret files NOT deleted
#       error message points to: docker compose ... ps / logs
# ─────────────────────────────────────────────────────────────
