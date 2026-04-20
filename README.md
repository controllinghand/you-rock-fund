# You Rock Volatility Income Fund (YRVI)

An automated Python algorithmic options trading system that generates weekly income by selling cash-secured puts (CSPs) on high-volatility, high-quality stocks through Interactive Brokers.

## How It Works

Each week the system runs a two-stage cycle:

| Day | Time (PST) | Action |
|-----|-----------|--------|
| Saturday | 6:00 PM | Screener preview — logs top 5 targets, no trades |
| Monday | 10:00 AM | Full pipeline — screen → size → execute |

**Pipeline:**
1. **Screener** — fetches CSP candidates from the Render API, applies hard filters (delta ≤ 0.21, buffer ≥ 5%, DTE ≥ 4), and scores survivors by buffer + premium + IV
2. **Position Sizer** — allocates $250K across up to 5 positions at ~$50K each
3. **Trader** — connects to IBKR, qualifies each contract, checks liquidity, and executes with limit-mid → limit-bid → market escalation

## Prerequisites

- Python 3.13+
- [Interactive Brokers TWS or IB Gateway](https://www.interactivebrokers.com/en/trading/tws.php) running locally
- Access to the You Rock Club screener API (Render)

## Installation

```bash
git clone https://github.com/controllinghand/you-rock-fund.git
cd you-rock-fund

python3.13 -m venv venv
source venv/bin/activate

pip install ib_insync apscheduler requests pandas numpy python-dotenv python-dateutil tzlocal nest_asyncio
```

## Configuration

Copy the template and fill in your values:

```bash
cp .env.template .env
```

Edit `.env`:

```env
IBKR_HOST=127.0.0.1
IBKR_PORT=7497          # 7497 = paper trading, 7496 = live trading
IBKR_CLIENT_ID=1
ACCOUNT=YOUR_IBKR_ACCOUNT_ID
RENDER_URL=https://yourockclub-ledger-sync.onrender.com/api/targets/csp
RENDER_SECRET=YOUR_RENDER_SECRET_KEY
```

Fund parameters (capital, position targets, schedule) are constants in `config.py`.

## Running

**Start the scheduler** (runs indefinitely — Saturday preview + Monday execution):
```bash
source venv/bin/activate
python scheduler.py
```

**Run once immediately** (screener → size → execute):
```bash
python trader.py
```

**Background daemon:**
```bash
nohup python scheduler.py > nohup.out 2>&1 &
```

**Dry run** — set `DRY_RUN = True` in `trader.py` to simulate without placing orders.

## Monitoring

```bash
tail -f trade_log.txt       # Per-trade execution details and order fills
tail -f scheduler_log.txt   # Scheduler heartbeat and pipeline logs
cat state.json              # Last run: positions sized, fills, premiums collected
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
- Days to expiry ≥ 4

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
config.py          — Fund parameters and env var loading
screener.py        — Render API fetch, filters, scoring
position_sizer.py  — Capital allocation logic
trader.py          — IBKR execution engine
scheduler.py       — APScheduler orchestration
.env.template      — Environment variable template
```
