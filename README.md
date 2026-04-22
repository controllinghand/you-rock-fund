# You Rock Volatility Income Fund (YRVI)

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

3. **Wheel Manager** — Monday 9:55 AM:
   - Detects stocks assigned from Friday's expiry
   - Stock above 90% of assignment strike → sell covered call at strike, nearest Friday
   - Stock below 90% of assignment strike → sell shares at market (stop loss)
   - Freed capital flows back into that week's CSP pool

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
| Stop loss | Sell shares if price drops 10% below assignment strike |
| Earnings protection | Skip tickers with earnings within 7 days |
| Auto-replacement | Failed position → automatically try next ranked ticker |

## Getting Started

New to IBKR? See the **[IBKR Account Setup Guide](IBKR_SETUP_GUIDE.md)** for a complete walkthrough — from creating your account to paper trading your first week.

## Prerequisites

- Python 3.13+
- [IB Gateway](https://www.interactivebrokers.com/en/trading/ibgateway-stable.php) running locally (set up via `setup_ibc.sh`)
- Access to the You Rock Club screener API (Render)

### IB Gateway vs TWS port numbers

| Application | Paper trading | Live trading |
|---|---|---|
| **IB Gateway** (this system) | **4002** | **4001** |
| TWS | 7497 | 7496 |

IB Gateway uses different ports than TWS. `IBKR_PORT=4002` is the correct default for paper trading via IB Gateway.

## Installation

```bash
git clone https://github.com/controllinghand/you-rock-fund.git
cd you-rock-fund
```

Copy the template and fill in your credentials:

```bash
cp .env.template .env
```

Edit `.env` with your values:

```env
IBKR_HOST=127.0.0.1
IBKR_PORT=4002          # IB Gateway: 4002 = paper, 4001 = live
IBKR_CLIENT_ID=1
ACCOUNT=YOUR_IBKR_ACCOUNT_ID
IBKR_USERNAME=your_ibkr_username
IBKR_PASSWORD=your_ibkr_password
RENDER_URL=https://yourockclub-ledger-sync.onrender.com/api/targets/csp
RENDER_SECRET=get_from_fund_operator   # contact Sean for this value
```

Fund parameters (capital, position targets, schedule) are constants in `config.py`.

## IB Gateway Auto-Login (Mac Mini)

IB Gateway is managed by IBC and launchd — it starts automatically at login and re-authenticates without manual intervention.

**One-time setup (run once per machine):**
```bash
bash setup_ibc.sh
```

`setup_ibc.sh` handles everything automatically:
- Installs Homebrew, Python 3.13, git, and Node.js if missing
- Creates the Python virtual environment and installs all dependencies
- Downloads and installs IB Gateway if not already present
- Downloads IBC, generates `~/IBC/config.ini` from your `.env`
- Installs the `com.yourockfund.ibgateway` launchd service so IB Gateway starts on every login

> **Note:** IBKR's offline installer may include the version number in the install path,
> e.g. `~/Applications/IB Gateway 10.37/IB Gateway 10.37.app`. `setup_ibc.sh`
> handles both the fixed path and any versioned path automatically.

**IB Gateway service management:**
```bash
# Status
launchctl list com.yourockfund.ibgateway

# Restart
launchctl kickstart -k gui/$(id -u) com.yourockfund.ibgateway

# Logs
tail -f ~/IBC/Logs/ibgateway_stdout.log
tail -f ~/IBC/Logs/ibgateway_stderr.log
```

## Mac Startup (after any reboot)

**Double-click `YRVI Startup` on your Desktop** to run the pre-flight check. It opens a Terminal window, verifies IB Gateway is running, ensures the scheduler is alive, tests the IBKR API connection, and prints a full GO/NO-GO table.

> `setup_ibc.sh` builds the app automatically — it converts the You Rock Club logo into a proper `.icns` icon, assembles the `.app` bundle, and places it on your Desktop. No manual steps needed.

Or run directly from the terminal:
```bash
bash ~/you_rock_fund/startup.sh
```

The scheduler is managed by macOS **launchd** — it starts automatically at login and restarts itself if it ever crashes. No manual `nohup` needed.

**Scheduler management:**
```bash
# Status
launchctl list com.yourockfund.scheduler

# Stop
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.yourockfund.scheduler.plist

# Start / reload after plist changes
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.yourockfund.scheduler.plist

# Logs
tail -f ~/you_rock_fund/scheduler_stdout.log
tail -f ~/you_rock_fund/scheduler_stderr.log
```

## Running Manually

**Run full pipeline once immediately** (screener → size → execute):
```bash
source venv/bin/activate
python trader.py
```

**Manual wheel operations:**
```bash
python wheel_manager.py detect   # run assignment detection now
python wheel_manager.py check    # run wheel check (stop loss + CCs) now
python risk_manager.py           # run daily risk monitor now
```

**Dry run** — set `DRY_RUN = True` in `trader.py` to simulate without placing orders.

## Monitoring

```bash
tail -f trade_log.txt           # CSP execution details and order fills
tail -f wheel_log.txt           # Wheel check: stop loss exits, covered calls
tail -f risk_log.txt            # Daily risk monitor and P&L snapshots
tail -f scheduler_stdout.log    # Scheduler stdout (launchd-managed)
tail -f scheduler_stderr.log    # Scheduler errors (launchd-managed)
cat state.json                  # Full system state: positions, wheel holdings, P&L
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
startup.sh                         — Startup & pre-flight check script
com.yourockfund.scheduler.plist    — launchd service definition (auto-start)
.env.template                      — Environment variable template
```

The `com.yourockfund.scheduler.plist` must be present in both the project folder (for git) and `~/Library/LaunchAgents/` (for launchd). `startup.sh` keeps them in sync automatically.

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

### Minimum Requirements
| Component | Spec | Notes |
|-----------|------|-------|
| Computer | Mac Mini M4 | M5 coming ~mid 2026 |
| RAM | 16GB | Base config is fine |
| Storage | 256GB SSD | Base config is fine |
| OS | macOS Sequoia | Required for launchd |
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
