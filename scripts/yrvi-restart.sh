#!/bin/bash

LOCKFILE="$HOME/.yrvi_restart.lock"
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
#  Container Restart — You Rock Volatility Income Fund
#
#  Usage:
#    ./scripts/yrvi-restart.sh <container> --paper|--live [--dry-run] [--keep-secrets]
#
#  Valid containers: ib_gateway  api  scheduler  web
#
#  What it does:
#    1. Verifies the docker compose stack is running
#    2. Re-injects secrets from macOS Keychain → docker/secrets/
#    3. Restarts the named container
#    4. Polls health status every 3s until healthy or 60s timeout
#    5. Wipes secret files unless --keep-secrets passed
# ─────────────────────────────────────────────────────────────

set -euo pipefail

# ── Flag parsing ───────────────────────────────────────────────

VALID_CONTAINERS="ib_gateway api scheduler web"

usage() {
    echo ""
    echo "  Usage: yrvi-restart.sh <container> --paper|--live [--dry-run] [--keep-secrets]"
    echo ""
    echo "    <container>      one of: ib_gateway  api  scheduler  web"
    echo "    --paper          paper trading mode (IBKR paper account)"
    echo "    --live           live trading mode  (IBKR live account)"
    echo "    --dry-run        print what would happen; make no changes"
    echo "    --keep-secrets   skip deletion of plaintext secret files after restart"
    echo ""
}

CONTAINER=""
TRADING_MODE=""
DRY_RUN=false
KEEP_SECRETS=false

for arg in "$@"; do
    case "$arg" in
        --paper)        TRADING_MODE="paper" ;;
        --live)         TRADING_MODE="live"  ;;
        --dry-run)      DRY_RUN=true         ;;
        --keep-secrets) KEEP_SECRETS=true    ;;
        --help|-h) usage; exit 0 ;;
        --*) printf "Unknown flag: %s\n" "$arg" >&2; usage; exit 1 ;;
        *)
            if [ -z "$CONTAINER" ]; then
                CONTAINER="$arg"
            else
                printf "Unexpected argument: %s\n" "$arg" >&2; usage; exit 1
            fi
            ;;
    esac
done

if [ -z "$CONTAINER" ]; then
    printf "Error: container name is required\n" >&2; usage; exit 1
fi

VALID=false
for c in $VALID_CONTAINERS; do
    [ "$c" = "$CONTAINER" ] && VALID=true && break
done
if [ "$VALID" = false ]; then
    printf "Error: '%s' is not a valid container\nValid names: %s\n" "$CONTAINER" "$VALID_CONTAINERS" >&2
    usage; exit 1
fi

if [ -z "$TRADING_MODE" ]; then
    printf "Error: --paper or --live is required\n" >&2; usage; exit 1
fi

# ── Globals ────────────────────────────────────────────────────

PROJ=$(cd "$(dirname "$0")/.." && pwd)

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { printf "  ${GREEN}✅${NC}  %s\n" "$1"; }
fail() { printf "  ${RED}❌${NC}  %s\n" "$1" >&2; exit 1; }
warn() { printf "  ${YELLOW}⚠️${NC}   %s\n" "$1"; }
info() { printf "  ${BLUE}ℹ️${NC}   %s\n" "$1"; }

MODE_LABEL="paper"
[ "$TRADING_MODE" = "live" ] && MODE_LABEL="LIVE"
DRY_LABEL=""
[ "$DRY_RUN" = true ] && DRY_LABEL=" [dry run]"

echo ""
printf "${BOLD}${BLUE}"
echo "╔══════════════════════════════════════════════════╗"
printf "║    Container Restart — YRVI  (%-17s)  ║\n" "$CONTAINER"
echo "╚══════════════════════════════════════════════════╝"
printf "${NC}"
echo ""
info "Mode: $MODE_LABEL$DRY_LABEL"
echo ""

# ── Safety checks ──────────────────────────────────────────────

cd "$PROJ"
if [ ! -f ".env.compose" ]; then
    fail "Must be run from repo root — .env.compose not found in $PROJ"
fi

if [ "$TRADING_MODE" = "live" ] && [ "${YRVI_ENV:-}" != "live" ]; then
    printf "  ${RED}❌${NC}  --live requires YRVI_ENV=live in your environment\n" >&2
    printf "  ${BLUE}ℹ️${NC}   Set it and retry:\n" >&2
    printf "         export YRVI_ENV=live\n" >&2
    printf "         ./scripts/yrvi-restart.sh %s --live\n" "$CONTAINER" >&2
    exit 1
fi

if [ "$DRY_RUN" = true ]; then
    info "DRY RUN — no changes will be made"
    echo ""
fi

# ── Step 1: Verify stack is running ────────────────────────────
echo "${BOLD}Step 1 / 4   Verify stack is running${NC}"
echo "──────────────────────────────────────────────────────"

RUNNING=$(docker compose --env-file .env.compose ps --status running 2>/dev/null \
    | grep -cE "running|Up" || true)

if [ "$RUNNING" -eq 0 ]; then
    printf "  ${RED}❌${NC}  Docker compose stack is not running\n" >&2
    info "Start it first:  bash setup_docker.sh --${TRADING_MODE}"
    exit 1
fi

CONTAINER_ID=$(docker compose --env-file .env.compose ps -q "$CONTAINER" 2>/dev/null | head -1 || true)
if [ -z "$CONTAINER_ID" ]; then
    fail "'$CONTAINER' is not in the running stack ($RUNNING other container(s) running)"
fi

ok "$RUNNING container(s) running — $CONTAINER found (id: ${CONTAINER_ID:0:12})"

# ── Step 2: Inject secrets from macOS Keychain ─────────────────
echo ""
echo "${BOLD}Step 2 / 4   Inject secrets from macOS Keychain${NC}"
echo "──────────────────────────────────────────────────────"

mkdir -p docker/secrets

# Create empty placeholder files for optional secrets (only if absent — never overwrite)
for _placeholder in \
    docker/secrets/discord_webhook_url \
    docker/secrets/discord_webhook_weekly_plan \
    docker/secrets/anthropic_api_key \
    docker/secrets/ibkr_password_live; do
    if [ ! -f "$_placeholder" ]; then
        if [ "$DRY_RUN" = true ]; then
            info "Would create placeholder: $_placeholder"
        else
            touch "$_placeholder"
        fi
    fi
done
unset _placeholder

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

WRITTEN_SECRET_FILES=()

# fetch_secret SERVICE FILE LABEL
#   Retrieves secret from Keychain only — exits if missing, never prompts.
fetch_secret() {
    local service="$1"
    local file="$2"
    local label="$3"

    local value
    value=$(security find-generic-password -s "$service" -w 2>/dev/null || true)

    if [ -z "$value" ]; then
        printf "  ${RED}❌${NC}  '%s' not found in Keychain (service: %s)\n" "$label" "$service" >&2
        printf "  ${BLUE}ℹ️${NC}   Run setup_docker.sh first to store secrets:\n" >&2
        printf "         bash setup_docker.sh --%s\n" "$TRADING_MODE" >&2
        exit 1
    fi

    if [ "$DRY_RUN" = true ]; then
        ok "[dry run] Would write '$label' → $file"
        return
    fi

    printf '%s' "$value" > "$file"
    chmod 600 "$file"
    WRITTEN_SECRET_FILES+=("$file")
    ok "Retrieved '$label' from Keychain"
}

info "macOS may prompt you to allow Keychain access — click Allow."
echo ""

fetch_secret "$KC_TWS"    "$TWS_SECRET_FILE"            "$TWS_LABEL"
fetch_secret "$KC_RENDER" "docker/secrets/render_secret" "Render screener API secret"

[ "$DRY_RUN" = false ] && ok "Secret files written to docker/secrets/"

# ── Step 3: Restart container ──────────────────────────────────
echo ""
echo "${BOLD}Step 3 / 4   Restart container${NC}"
echo "──────────────────────────────────────────────────────"

if [ "$DRY_RUN" = true ]; then
    info "Would run: docker restart $CONTAINER_ID  (service: $CONTAINER)"
else
    info "Restarting $CONTAINER..."
    docker restart "$CONTAINER_ID" >/dev/null
    ok "$CONTAINER restarted"
fi

# ── Step 4: Wait for healthy ───────────────────────────────────
echo ""
echo "${BOLD}Step 4 / 4   Wait for container to become healthy${NC}"
echo "──────────────────────────────────────────────────────"

if [ "$DRY_RUN" = true ]; then
    info "Would poll docker inspect health every 3s (timeout 60s)"
else
    TIMEOUT=60
    ELAPSED=0
    FINAL_STATUS=""

    while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
        HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_ID" 2>/dev/null || echo "error")
        STATUS=$(docker inspect --format='{{.State.Status}}'        "$CONTAINER_ID" 2>/dev/null || echo "error")

        if [ "$STATUS" = "exited" ] || [ "$STATUS" = "dead" ]; then
            FINAL_STATUS="$STATUS"; break
        fi

        if [ "$HEALTH" = "healthy" ]; then
            FINAL_STATUS="healthy"; break
        elif [ "$HEALTH" = "unhealthy" ]; then
            FINAL_STATUS="unhealthy"; break
        elif [ -z "$HEALTH" ] && [ "$STATUS" = "running" ]; then
            # Container has no healthcheck configured — running is sufficient
            FINAL_STATUS="running (no healthcheck)"; break
        fi

        ELAPSED=$(( ELAPSED + 3 ))
        printf "  waiting... %ds / %ds  (health: %s, status: %s)\r" \
            "$ELAPSED" "$TIMEOUT" "${HEALTH:-none}" "$STATUS"
        sleep 3
    done
    echo ""

    if [ -z "$FINAL_STATUS" ]; then
        printf "  ${RED}❌${NC}  %s did not become healthy within %ds\n" "$CONTAINER" "$TIMEOUT" >&2
        info "Check logs: docker compose --env-file .env.compose logs --tail=50 $CONTAINER"
        # Wipe secrets even on failure to avoid leaving them on disk
        if [ "$KEEP_SECRETS" = false ] && [ ${#WRITTEN_SECRET_FILES[@]} -gt 0 ]; then
            for f in "${WRITTEN_SECRET_FILES[@]}"; do rm -f "$f"; done
        fi
        exit 1
    elif [ "$FINAL_STATUS" = "unhealthy" ] || \
         [ "$FINAL_STATUS" = "exited" ]    || \
         [ "$FINAL_STATUS" = "dead" ]; then
        printf "  ${RED}❌${NC}  %s status is '%s'\n" "$CONTAINER" "$FINAL_STATUS" >&2
        info "Check logs: docker compose --env-file .env.compose logs --tail=50 $CONTAINER"
        if [ "$KEEP_SECRETS" = false ] && [ ${#WRITTEN_SECRET_FILES[@]} -gt 0 ]; then
            for f in "${WRITTEN_SECRET_FILES[@]}"; do rm -f "$f"; done
        fi
        exit 1
    else
        ok "$CONTAINER is $FINAL_STATUS"
    fi

    # ── Wipe plaintext secret files ─────────────────────────────
    if [ "$KEEP_SECRETS" = true ]; then
        warn "--keep-secrets: secret files left on disk in docker/secrets/"
        warn "Delete manually when done: rm docker/secrets/*"
    else
        if [ ${#WRITTEN_SECRET_FILES[@]} -gt 0 ]; then
            for f in "${WRITTEN_SECRET_FILES[@]}"; do rm -f "$f"; done
        fi
        ok "Secret files wiped — passwords remain safely in macOS Keychain"
    fi
fi

# ── Summary ────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
if [ "$DRY_RUN" = true ]; then
    printf "${BOLD}${YELLOW}  Dry run complete — no changes made.${NC}\n"
else
    printf "${BOLD}${GREEN}  $CONTAINER restarted successfully.${NC}\n"
fi
echo "══════════════════════════════════════════════════════"
echo ""
if [ "$DRY_RUN" = false ]; then
    info "Logs:   docker compose --env-file .env.compose logs --tail=50 $CONTAINER"
    info "Status: docker compose --env-file .env.compose ps"
    echo ""
fi
