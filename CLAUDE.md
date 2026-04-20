# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An automated Python algorithmic options trading system for the **You Rock Volatility Income Fund**. It generates weekly income by selling cash-secured puts (CSP) on high-volatility stocks through Interactive Brokers.

**Weekly flow:** Render API screener → position sizer → IBKR order execution, scheduled Saturday preview + Monday 10 AM PST execution.

## Running the System

```bash
source venv/bin/activate

# Start scheduler (production — runs indefinitely, Saturday preview + Monday execution)
python scheduler.py

# Run full pipeline once immediately (screener → sizer → trader)
python trader.py

# Run screener only
python screener.py

# Background daemon
nohup python scheduler.py > nohup.out 2>&1 &
```

**Monitor execution:**
```bash
tail -f trade_log.txt        # Per-trade execution details
tail -f scheduler_log.txt    # Scheduler system logs
cat state.json               # Last run: positions, fills, premiums collected
```

## Architecture

```
config.py          → All fund parameters, IBKR credentials, schedule, API keys
screener.py        → Fetches CSP candidates from Render API, filters + scores them
position_sizer.py  → Allocates capital across up to 5 positions
trader.py          → IBKR connection, contract qualification, order escalation, execution
scheduler.py       → APScheduler orchestration (Saturday preview, Monday execution)
state.json         → Persisted last-run output (positions, premiums, fills)
trade_log.txt      → Appended execution log
```

### Key Execution Details (trader.py)

- **Order escalation:** limit @ mid → limit @ bid → market (120s per stage)
- **Liquidity check:** max spread 20%, min open interest 100
- **Market data:** 4-second wait after request; falls back to screener premium if market closed
- **DRY_RUN flag:** set `DRY_RUN = True` in `trader.py` to simulate without placing orders

### Screener Scoring (screener.py)

Score = 50% buffer (1.5× boost if ≥10%) + 35% premium (1.1× boost if in buyzone) + 15% IV ATM

Filters: "Wheel-ready" status, ≥4 DTE, delta ≤ 0.21, buffer ≥ 5%

### Capital Allocation (position_sizer.py)

- Up to 5 positions, `TARGET_PER_POSITION` = $50K, `MAX_PER_POSITION` = $70K
- Last position uses remaining budget up to the max cap
- Skips if a single contract exceeds `MAX_PER_POSITION`

## Key Configuration (config.py)

```python
IBKR_PORT = 7497        # 7497 = paper trading, 7496 = live trading
TOTAL_FUND_BUDGET = 250_000
TARGET_PER_POSITION = 50_000
NUM_POSITIONS = 5
STOP_LOSS_PCT = 0.10    # 10% below strike
EXECUTE_HOUR_PST = 10   # Monday 10 AM PST
```

**IBKR TWS or Gateway must be running** on `127.0.0.1:7497` (paper) or `:7496` (live) before running any trading code.

## Dependencies

Python 3.13 + venv. Key packages: `ib_insync`, `apscheduler`, `requests`, `pandas`, `numpy`, `nest_asyncio`.

No requirements.txt — install with:
```bash
pip install ib_insync apscheduler requests pandas numpy python-dateutil tzlocal nest_asyncio
```

## No Test/Lint Framework

This is pure operational code. Validate changes by inspecting `state.json` and `trade_log.txt` after a dry-run execution.
