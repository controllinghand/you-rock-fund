# You Rock Volatility Income Fund (YRVI)

![Version](https://img.shields.io/badge/version-1.0.0--beta-blue)

An automated Python algorithmic options trading system that generates weekly income through the complete wheel strategy — selling cash-secured puts (CSPs), managing assignments with covered calls (CCs), and enforcing automatic stop losses — all running 24/7 on a Mac Mini with zero manual intervention.

## How It Works

**Full weekly schedule:**

| Day | Time (PST) | Action |
|-----|-----------|--------|
| Saturday | 6:00 PM | Screener preview — logs top 5 targets, no trades |
| Monday | 9:50 AM | Discord preview — posts this week's sized positions |
| Monday | 9:55 AM | Wheel check — stop losses + sell covered calls on assigned stocks |
| Monday | 10:00 AM | CSP execution — screen → size → execute 5 positions |
| Tuesday–Thursday | 9:00 AM | Daily risk monitor — checks stop loss thresholds, logs P&L |
| Friday | 4:15 PM | Assignment detection — checks for newly assigned positions |

**Pipeline:**

1. **Screener** — fetches candidates from the Render API, applies hard filters (delta ≤ 0.21, buffer ≥ 5%, DTE ≥ 3), and scores survivors by buffer + premium + IV

2. **Position Sizer** — allocates $250K across up to 5 positions (~$50K each, last position gets remainder up to $70K max)

3. **Wheel Manager** — Monday 9:55 AM (four-step logic per holding):
   - **Step 1 — Screener check:** if ticker no longer passes screener filters → sell shares at market and free capital
   - **Step 2 — Option chain:** query IBKR for CALL options on the nearest Friday, strike ≥ assigned strike; collect delta for each candidate
   - **Step 3 — Decision:** sell the highest-delta (≥ 0.20) covered call found. If no strike with delta ≥ 0.20 exists → sell shares at market
   - **Step 4 — Accounting:** freed capital (from any sales) returns to the CSP pool; sold tickers are skipped in that week's screener

4. **Trader** — connects to IBKR, qualifies contracts, checks liquidity (spread ≤ 20%, OI ≥ 100), executes with limit-mid → limit-bid → market escalation; automatically replaces failed positions with the next ranked ticker

5. **Risk Manager** — daily Tue–Thu monitor checks all wheel holdings against the 10% stop loss threshold, logs unrealized P&L, and sends alerts

6. **Discord Poster** — (optional) posts weekly results, YTD stats, Monday previews, and Friday assignment alerts to a Discord channel automatically

## Strategy Overview

### The Wheel Strategy

```
Week 1:  Sell CSP on TICKER at $50 strike → collect $500 premium
           ↓ expires worthless → keep $500, repeat
           ↓ or assigned 100 shares at $50
Week 2:  Sell CC on 100 shares at $50 strike → collect $300 premium
           ↓ expires worthless → keep $300, repeat
           ↓ or shares called away at $50 → back to selling CSPs
```

Each cycle generates income whether the option expires or gets exercised.

### Risk Management

| Control | Rule |
|---------|------|
| Delta filter | Only sell puts with delta ≤ 0.21 (~20Δ) |
| Buffer requirement | Strike must be ≥ 5% below current price |
| Liquidity check | Spread ≤ 20%, Open Interest ≥ 100 |
| Screener exit | Sell shares if ticker drops from screener filters |
| Delta exit | Sell shares if no CC strike with delta ≥ 0.20 available |
| Earnings protection | Skip tickers with earnings within 7 days |
| Auto-replacement | Failed position → automatically try next ranked ticker |

## Getting Started

New to IBKR? See the **[IBKR Account Setup Guide](IBKR_SETUP_GUIDE.md)** for a complete walkthrough — from creating your account to paper trading your first week.

## Prerequisites

- [Rancher Desktop](https://rancherdesktop.io) or Docker Desktop (dockerd/moby engine)
- Access to the You Rock Club screener API (Render)

### IB Gateway port reference

| Mode | Port (inside Docker network) |
|---|---|
| Paper trading | 4004 |
| Live trading | 4003 |

These are the ports the Python containers use to reach IB Gateway inside the Compose network. They differ from the standalone IB Gateway defaults (4002/4001) used in the legacy launchd setup.

## Installation

```bash
git clone https://github.com/controllinghand/you_rock_fund.git you_rock_fund
cd you_rock_fund
bash setup_docker.sh
```

`setup_docker.sh` validates your config, builds all four containers (`ib_gateway`, `api`, `scheduler`, `web`), starts the stack, and installs a login item so containers restart automatically after a reboot.

See **[CONTAINERIZATION.md](CONTAINERIZATION.md)** for the full setup guide — secrets, credentials, 2FA recovery, and troubleshooting.

## Mac Startup (after any reboot)

**Double-click `YRVI Startup` on your Desktop** to run the pre-flight check. It verifies the Docker containers are running and prints a full GO/NO-GO status table.

Or from the terminal:
```bash
bash ~/you_rock_fund/startup.sh
```

**Container management:**
```bash
# Status
docker compose --env-file .env.compose ps

# Logs
docker compose --env-file .env.compose logs -f scheduler
docker compose --env-file .env.compose logs -f ib_gateway

# Restart scheduler
docker compose --env-file .env.compose restart scheduler
```

## Running Manually

**Run full pipeline once immediately** (screener → size → execute):
```bash
docker compose --env-file .env.compose exec scheduler python - <<'PY'
import scheduler
scheduler.run_pipeline()
PY
```

**Manual wheel operations:**
```bash
docker compose --env-file .env.compose exec scheduler python wheel_manager.py detect
docker compose --env-file .env.compose exec scheduler python wheel_manager.py check
docker compose --env-file .env.compose exec scheduler python risk_manager.py
```

**Dry run** — set `dry_run: true` via the dashboard settings or the API:
```bash
curl -sS -X POST http://127.0.0.1:3000/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"dry_run":true}'
```

## Monitoring

**Live container logs:**
```bash
docker compose --env-file .env.compose logs -f scheduler   # execution, wheel, risk jobs
docker compose --env-file .env.compose logs -f api         # dashboard API requests
docker compose --env-file .env.compose logs -f ib_gateway  # IB Gateway login status
```

**Persisted log files** (enable bind-mount override in [CONTAINERIZATION.md](CONTAINERIZATION.md) for local file access):
```bash
tail -f docker/data/trade_log.txt    # CSP execution details and order fills
tail -f docker/data/wheel_log.txt    # Wheel check: stop loss exits, covered calls
tail -f docker/data/risk_log.txt     # Daily risk monitor and P&L snapshots
cat docker/data/state.json           # Full system state: positions, wheel holdings, P&L
```

## Screener Scoring

```
Score = 0.50 × buffer_pct × (1.5 if buffer ≥ 10%)
      + 0.35 × premium_pct × (1.1 if in buyzone)
      + 0.15 × (iv_atm / 10)
```

Hard filters applied before scoring:
- `wheel_fit == "Wheel-ready"`
- Delta ≤ 0.21
- Buffer ≥ 5%
- Days to expiry ≥ 3 (Mon→Fri = 3 UTC calendar days)

## Capital Allocation

| Parameter | Default |
|-----------|---------|
| Total fund budget | $250,000 |
| Target per position | $50,000 |
| Max per position | $70,000 |
| Max positions | 5 |

The last position absorbs remaining capital up to `MAX_PER_POSITION`.

## Order Execution

Each position escalates through three stages (120 seconds each):
1. **Limit @ mid** — tries for best price
2. **Limit @ bid** — accepts bid to ensure fill
3. **Market order** — last resort

Liquidity checks: spread ≤ 20%, open interest ≥ 100.

## File Structure

```
config.py                          — Fund parameters and env var loading
screener.py                        — Render API fetch, filters, scoring
position_sizer.py                  — Capital allocation logic
trader.py                          — IBKR CSP execution engine
wheel_manager.py                   — Assignment detection, stop loss, covered calls
risk_manager.py                    — Daily price monitoring and P&L tracking
scheduler.py                       — APScheduler orchestration (5 jobs)
api.py                             — FastAPI dashboard backend
startup.sh                         — Startup & pre-flight check (Docker-aware)
setup_docker.sh                    — One-command Docker setup
docker-compose.yml                 — Container stack definition
docker/                            — Dockerfiles, entrypoint, secrets, preflight
CONTAINERIZATION.md                — Full Docker setup and operations guide
.env.compose.example               — Compose environment variable template
```

## 🔔 Optional: Discord Notifications

YRVI can post trade results to a Discord channel automatically. This is entirely optional — if no webhook is configured, the system runs silently as normal.

### What gets posted

| Event | When | Content |
|-------|------|---------|
| Pre-execution preview | Monday 9:50AM | Sized positions with strikes, contracts, estimated premium |
| Weekly results | Monday ~10:30AM | CSP/CC/stop-loss P&L, week yield %, YTD stats |
| Assignment alert | Friday 4:15PM | Newly assigned stocks with stop-loss prices |

Results are color-coded: 🟢 green (≥1% yield), 🟡 yellow (0.5–1%), 🔴 red (<0.5%).

YTD stats track total premium collected, weeks traded, avg weekly yield, best/worst week, and progress toward the $100K annual target. Stored locally in `ytd_tracker.json`.

### Setup

1. In Discord, go to your channel → **Edit Channel → Integrations → Webhooks → New Webhook**
2. Copy the webhook URL
3. Add it to your `.env` file:
   ```env
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/yyy
   ```
4. Restart the scheduler — Discord posts will begin automatically

No code changes needed. If `DISCORD_WEBHOOK_URL` is absent or blank, all Discord calls are silently skipped.

---

## 🛒 Hardware & Shopping List

A dedicated Mac Mini is the recommended setup for set-and-forget automated trading.

**Supported hardware:**
- ✅ Supported: Mac Mini M4 (Apple Silicon/ARM)
- ✅ Supported: Intel Mac (x86_64)
- ✅ Supported: Any Mac running macOS Sequoia or later

### Minimum Requirements
| Component | Spec | Notes |
|-----------|------|-------|
| Computer | Mac Mini M4 | M5 coming ~mid 2026 |
| RAM | 16GB | Base config is fine |
| Storage | 256GB SSD | Base config is fine |
| OS | macOS (Intel/ARM), Windows | Docker-based; macOS Sequoia for native launchd (legacy) |
| Network | Ethernet (recommended) | More reliable than WiFi |

### Shopping List
- **Mac Mini M4 (16GB/256GB)** — $599 retail, often $469-499 on sale
  - Amazon: https://www.amazon.com/dp/B0DLBTPDCS
  - Apple Store: https://www.apple.com/shop/buy-mac/mac-mini
  - Costco (sometimes cheaper): search "Mac Mini M4" on costco.com
  - MicroCenter: ~$399 in store (best price if one is nearby)
- **Ethernet cable** — ~$10 (if needed)
- **IBKR Account** — Free (paper trading available)
  https://www.interactivebrokers.com

> 💡 **Pro Tip:** Check Amazon weekly — the M4 Mac Mini regularly goes on sale for $469-499. Also check MicroCenter if you have one nearby — they often have it for $399!

> **Note:** M5 Mac Mini expected ~mid 2026 (WWDC June) at the same $599 price — worth waiting if you can!

### Optional but recommended
- **UPS Battery Backup** — ~$50-100 (protects against power outages)
- **Monitor** (only needed for initial setup, can SSH after)

### Why Mac Mini?
- Runs 24/7 silently (~6W power draw)
- Auto-restarts after power outage
- IB Gateway + YRVI use <1GB RAM total
- Pays for itself in first week of trading ($3,500+ weekly target)

### Total Setup Cost
| Item | Cost |
|------|------|
| Mac Mini M4 | ~$499 |
| UPS backup | ~$75 |
| Ethernet cable | ~$10 |
| **Total** | **~$584 one time** |

vs $3,500+/week potential income = ROI in first week! 💰

---

---

## Legacy / Manual Setup (macOS launchd)

> The Docker setup above is the recommended install. This section documents the original macOS-only launchd approach for reference or if Docker is not available.

**Prerequisites (legacy):** Python 3.13+, macOS Sequoia, IB Gateway.

**One-time setup:**
```bash
cp .env.template .env     # fill in IBKR credentials and RENDER_SECRET
bash setup_ibc.sh
```

`setup_ibc.sh` installs Homebrew, Python 3.13, IB Gateway, IBC, and the launchd scheduler service.

**IB Gateway service management:**
```bash
launchctl list com.yourockfund.ibgateway
launchctl kickstart -k gui/$(id -u) com.yourockfund.ibgateway
tail -f ~/IBC/Logs/ibgateway_stdout.log
```

**Scheduler management:**
```bash
launchctl list com.yourockfund.scheduler
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.yourockfund.scheduler.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.yourockfund.scheduler.plist
tail -f ~/you_rock_fund/scheduler_stdout.log
```

**Monitoring (legacy):**
```bash
tail -f trade_log.txt        # CSP execution details
tail -f wheel_log.txt        # Wheel check and covered calls
tail -f risk_log.txt         # Daily risk monitor
cat state.json               # Full system state
```

---

## Version History

### v1.0.0-beta (April 2026)
- Docker containerization (replaces launchd)
- Cross-platform: Mac Intel/ARM + Windows
- Secrets management via Docker secrets
- Auto-start via Docker login plist
- nginx serving React dashboard
- Socket-based health checks
- Scheduler heartbeat monitoring

### v0.1.0-beta (April 2026)
- Initial automated trading system
- Wheel strategy (CSP + CC)
- IB Gateway auto-login via IBC
- Zero-touch Mac reboot via launchd
- Discord auto-posting
- Web dashboard (React + FastAPI)
- YRVI logo and desktop app
- Friend install blueprint (Mac Mini)
