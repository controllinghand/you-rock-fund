#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Docker Setup — You Rock Volatility Income Fund
#  Containerized branch: Docker replaces launchd/IBC
#
#  Run once after a fresh install or when setting up on a new machine:
#    bash setup_docker.sh
#
#  What it does:
#    1. Checks Docker is running (install Rancher Desktop first)
#    2. Runs docker/preflight.sh to validate secrets and config
#    3. Builds and starts all 4 containers (ib_gateway, api, scheduler, web)
#    4. Installs com.yourockfund.docker launchd service so containers
#       start automatically on every login / reboot
#    5. Installs YRVI Startup.app on the Desktop
# ─────────────────────────────────────────────────────────────

set -euo pipefail

PROJ=$(cd "$(dirname "$0")" && pwd)
DOCKER_PLIST_SRC="$PROJ/com.yourockfund.docker.plist"
DOCKER_PLIST_DEST="$HOME/Library/LaunchAgents/com.yourockfund.docker.plist"
DOCKER_LABEL="com.yourockfund.docker"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { printf "  ${GREEN}✅${NC}  %s\n" "$1"; }
fail() { printf "  ${RED}❌${NC}  %s\n" "$1"; exit 1; }
warn() { printf "  ${YELLOW}⚠️${NC}   %s\n" "$1"; }
info() { printf "  ${BLUE}ℹ️${NC}   %s\n" "$1"; }

echo ""
printf "${BOLD}${BLUE}"
echo "╔══════════════════════════════════════════════════╗"
echo "║    Docker Setup — YRVI Fund                      ║"
echo "╚══════════════════════════════════════════════════╝"
printf "${NC}"
echo ""

# ── Step 1: Check Docker is running ──────────────────────────
echo "${BOLD}Step 1 / 5   Check Docker${NC}"
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
echo "       Preferences → Application →"
echo "         ✅  Automatically start at login"
echo "         ✅  Start in background"
echo "       This ensures Docker is running before YRVI containers"
echo "       restart after a reboot."
echo ""

# ── Step 2: Validate secrets and config ───────────────────────
echo ""
echo "${BOLD}Step 2 / 5   Validate secrets and config${NC}"
echo "──────────────────────────────────────────────────────"

cd "$PROJ"

if [ ! -f ".env.compose" ]; then
    fail ".env.compose not found — copy .env.compose.example to .env.compose and fill in credentials"
fi

sh docker/preflight.sh || fail "Preflight check failed — fix the issues above and retry"
ok "Secrets and config OK"

# ── Step 3: Build and start containers ───────────────────────
echo ""
echo "${BOLD}Step 3 / 5   Build and start all 4 containers${NC}"
echo "──────────────────────────────────────────────────────"

info "Building images and starting ib_gateway, api, scheduler, web..."
docker compose --env-file .env.compose up -d --build

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

# ── Step 4: Install Docker auto-start on login ────────────────
echo ""
echo "${BOLD}Step 4 / 5   Install Docker auto-start on login${NC}"
echo "──────────────────────────────────────────────────────"

mkdir -p "$HOME/Library/LaunchAgents"

launchctl bootout "gui/$(id -u)/$DOCKER_LABEL" 2>/dev/null || true
launchctl unload "$DOCKER_PLIST_DEST" 2>/dev/null || true

sed -e "s|__PROJ__|$PROJ|g" "$DOCKER_PLIST_SRC" > "$DOCKER_PLIST_DEST"

launchctl bootstrap "gui/$(id -u)" "$DOCKER_PLIST_DEST" 2>/dev/null || \
    launchctl load "$DOCKER_PLIST_DEST" 2>/dev/null || true

ok "com.yourockfund.docker installed — containers will auto-start on every login"

# ── Step 5: Install app to /Applications ─────────────────────
echo ""
echo "${BOLD}Step 5 / 5   Install Desktop app${NC}"
echo "──────────────────────────────────────────────────────"

APP_DEST="/Applications/YRVI Startup.app"

rm -rf "$APP_DEST"
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

ok "YRVI Startup app installed on Desktop"

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
echo "  Pre-flight check anytime:"
echo "    bash startup.sh"
echo ""
