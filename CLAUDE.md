# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An automated Python algorithmic options trading system for the **You Rock Volatility Income Fund**. It generates weekly income by selling cash-secured puts (CSPs) and, after assignment, selling covered calls (the wheel strategy) through Interactive Brokers.

## Running the System

```bash
source venv/bin/activate

# Start scheduler (production — runs indefinitely)
python scheduler.py

# Run full pipeline once immediately (screener → sizer → trader)
python trader.py

# Manual wheel operations
python wheel_manager.py detect   # run assignment detection now
python wheel_manager.py check    # run wheel check (stop loss + CC) now

# Run daily risk monitor now
python risk_manager.py

# Background daemon
nohup python scheduler.py > nohup.out 2>&1 &
```

**Monitor execution:**
```bash
tail -f trade_log.txt        # CSP execution details
tail -f wheel_log.txt        # Wheel check and assignment logs
tail -f risk_log.txt         # Daily risk monitor logs
tail -f scheduler_log.txt    # Scheduler heartbeat
cat state.json               # Full system state (see schema below)
```

## Weekly Schedule

| Day/Time (PST) | Job | Module |
|---|---|---|
| Friday 4:15PM | Assignment detection | `wheel_manager.detect_assignments()` |
| Saturday 6:00PM | Screener preview | `screener` + `position_sizer` |
| Monday 9:55AM | Wheel check: stop loss sells + covered calls | `wheel_manager.run_wheel_check()` |
| Monday 10:00AM | CSP pipeline: screen → size → execute | `trader.execute_positions()` |
| Tue–Thu 9:00AM | Daily risk monitor | `risk_manager.run_daily_monitor()` |

## Architecture

```
config.py          → All fund parameters, IBKR credentials, API keys
screener.py        → Fetches CSP candidates from Render API, filters + scores them
position_sizer.py  → Allocates capital across up to 5 positions (accepts budget override)
trader.py          → IBKR CSP execution: qualify → liquidity check → limit/market escalation
wheel_manager.py   → Assignment detection, stop loss sells, covered call execution
risk_manager.py    → Daily price checks, stop loss alerts, weekly P&L tracking
scheduler.py       → APScheduler orchestration for all 5 jobs
state.json         → Persisted system state (see schema below)
```

### IBKR Client IDs

Each module connects with a distinct client ID to allow concurrent connections:
- `trader.py` → `IBKR_CLIENT_ID` (=1)
- `wheel_manager.py` → `IBKR_CLIENT_ID_WHEEL` (=2)
- `risk_manager.py` → `IBKR_CLIENT_ID_RISK` (=3)

### state.json Schema

```json
{
  "run_date":      "ISO timestamp of last CSP execution",
  "positions":     [...],        // sized positions from position_sizer
  "executions":    [...],        // CSP order results from trader
  "filled_count":  5,
  "total_premium": 4088,

  "wheel_holdings": [            // stock positions being wheeled
    {
      "ticker":               "OKLO",
      "shares":               800,
      "assignment_strike":    60.00,
      "assignment_date":      "2026-04-25",
      "stop_loss_price":      54.00,
      "cc_expiry":            "20260501",
      "cc_strike":            60.00,
      "cc_status":            "open",  // pending|open|failed|stop_loss_exit
      "cc_premium_collected": 320.0,
      "current_price":        62.50,
      "last_checked":         "ISO timestamp",
      "stop_loss_alert":      false
    }
  ],

  "monday_context": {            // written by wheel_check, read by run_pipeline
    "skip_tickers":          ["OKLO"],
    "freed_capital":         54000.0,
    "cc_premium":            320.0,
    "stop_loss_realized_pnl": -4800.0,
    "updated":               "ISO timestamp"
  },

  "weekly_pnl": {
    "week_start":             "2026-04-27",
    "csp_premium":            4088,
    "cc_premium":             320,
    "stop_loss_realized_pnl": -4800,
    "total_realized":         -392,
    "unrealized_stock_pnl":   2000,
    "grand_total":            1608
  }
}
```

### Monday Data Flow

```
9:55AM wheel_check:
  → get live prices from IBKR
  → stop loss: sell shares at market, add proceeds to freed_capital
  → above stop loss: sell covered call at assignment_strike, nearest Friday
  → write monday_context to state.json

10:00AM run_pipeline:
  → read monday_context (skip_tickers, freed_capital)
  → filter skip_tickers from screener results
  → size_all(targets, budget=TOTAL_FUND_BUDGET + freed_capital)
  → execute CSPs
  → assemble and write weekly_pnl
```

### Order Execution (shared pattern)

All orders — CSPs, covered calls, stop loss sells — use the same escalation:
- Limit @ mid (120s) → limit @ bid proxy (120s) → market with 60s polling loop
- Partial fills accepted and logged

### Key Rules

- Never buy back covered calls
- Stop loss sells happen Monday 9:55AM only (daily monitor just alerts)
- Freed stop-loss capital is added to that week's CSP deployment budget
- Stop-loss tickers are skipped in the same week's CSP screener

## Key Configuration (config.py)

```python
IBKR_PORT           = 4002    # IB Gateway: 4002 = paper, 4001 = live
TOTAL_FUND_BUDGET   = 250_000
TARGET_PER_POSITION = 50_000
MAX_PER_POSITION    = 70_000
NUM_POSITIONS       = 5
STOP_LOSS_PCT       = 0.10    # 10% below assignment strike
```

**IB Gateway must be running** on `127.0.0.1:4002` (paper) or `:4001` (live). These are IB Gateway ports — TWS uses different ports (7497/7496).

## Dependencies

Python 3.13 + venv. Key packages: `ib_insync`, `apscheduler`, `requests`, `pandas`, `numpy`, `python-dotenv`, `nest_asyncio`.

```bash
pip install ib_insync apscheduler requests pandas numpy python-dotenv python-dateutil tzlocal nest_asyncio
```

## No Test/Lint Framework

Pure operational code. Validate changes via `state.json` and log files after a dry-run execution (`DRY_RUN = True` in `trader.py`).
