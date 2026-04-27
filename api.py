"""YRVI Management Dashboard — FastAPI backend."""
import asyncio
import json
import os
import re
import subprocess
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

try:
    import nest_asyncio
    nest_asyncio.apply()
except (ValueError, ImportError):
    # uvloop doesn't support nest_asyncio; the per-thread loop setup below handles ib_insync instead
    pass

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "state.json"
YTD_FILE = BASE_DIR / "ytd_tracker.json"
SETTINGS_FILE = BASE_DIR / "settings.json"
SETTINGS_DEFAULT_FILE = BASE_DIR / "settings_default.json"
IBC_CONFIG_FILE = BASE_DIR / "ibc_config.ini"

LIVE_PLACEHOLDERS = {
    "IBKR_USERNAME_LIVE": "your_live_ibkr_username",
    "IBKR_PASSWORD_LIVE": "your_live_ibkr_password",
    "ACCOUNT_LIVE": "your_live_account_number (starts with U)",
}

PST = ZoneInfo("America/Los_Angeles")
ANNUAL_TARGET = 100_000
IBKR_API_CLIENT_ID = 10  # dedicated client ID — never conflicts with trader (1), wheel (2), risk (3)

app = FastAPI(title="YRVI Dashboard API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── File helpers ──────────────────────────────────────────────

def load_settings() -> dict:
    defaults: dict = {}
    if SETTINGS_DEFAULT_FILE.exists():
        try:
            defaults = json.loads(SETTINGS_DEFAULT_FILE.read_text())
        except Exception:
            pass
    if SETTINGS_FILE.exists():
        try:
            user = json.loads(SETTINGS_FILE.read_text())
            return {**defaults, **user}
        except Exception:
            pass
    return defaults

def save_settings(data: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))

def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}

def load_ytd() -> dict:
    try:
        return json.loads(YTD_FILE.read_text())
    except Exception:
        return {"weeks": [], "total_premium": 0.0, "weeks_traded": 0,
                "best_week": None, "worst_week": None}

# ── IBKR helpers ──────────────────────────────────────────────

_ibkr_cache: dict = {"data": None, "ts": 0.0}
IBKR_CACHE_TTL = 30.0

_ACCT_TAGS = (
    "NetLiquidation,SettledCash,UnrealizedPnL,"
    "RealizedPnL,MaintenanceMargin,ExcessLiquidity,BuyingPower"
)
_TAG_KEY = {
    "NetLiquidation":   "account_value",
    "BuyingPower":      "buying_power",
    "SettledCash":      "settled_cash",
    "UnrealizedPnL":    "unrealized_pnl",
    "RealizedPnL":      "realized_pnl",
    "MaintenanceMargin":"maintenance_margin",
    "ExcessLiquidity":  "excess_liquidity",
}

def _safe_float(val, ndigits: int = 2):
    """Convert IBKR values to float, returning None for NaN / sentinel values."""
    try:
        f = float(val)
        if f != f or abs(f) > 1e15:   # NaN or IBKR's 1e308 "unavailable" sentinel
            return None
        return round(f, ndigits)
    except (TypeError, ValueError):
        return None

def _live_ready() -> dict:
    missing = []
    for var, placeholder in LIVE_PLACEHOLDERS.items():
        val = os.environ.get(var, "")
        if not val or val == placeholder:
            missing.append(var)
    account_live = os.environ.get("ACCOUNT_LIVE", "")
    placeholder_account = LIVE_PLACEHOLDERS["ACCOUNT_LIVE"]
    masked = (account_live[0] + "****") if (account_live and account_live != placeholder_account) else ""
    return {"ready": len(missing) == 0, "missing": missing, "account_masked": masked}

def _update_ibc_config(username: str, password: str, mode: str, port: int) -> None:
    if not IBC_CONFIG_FILE.exists():
        return
    content = IBC_CONFIG_FILE.read_text()
    content = re.sub(r'^IbLoginId=.*$', f'IbLoginId={username}', content, flags=re.MULTILINE)
    content = re.sub(r'^IbPassword=.*$', f'IbPassword={password}', content, flags=re.MULTILINE)
    content = re.sub(r'^TradingMode=.*$', f'TradingMode={mode}', content, flags=re.MULTILINE)
    content = re.sub(r'^ForceTwsApiPort=.*$', f'ForceTwsApiPort={port}', content, flags=re.MULTILINE)
    IBC_CONFIG_FILE.write_text(content)

def _restart_ibgateway() -> None:
    uid = os.getuid()
    subprocess.run(
        ["launchctl", "kickstart", "-k", f"gui/{uid}/com.yourockfund.ibgateway"],
        capture_output=True, text=True, timeout=10,
    )

@app.post("/api/restart-scheduler")
def restart_scheduler():
    uid = os.getuid()
    service = "com.yourockfund.scheduler"
    errors: list[str] = []

    # 1. Try kickstart -k (kills running instance then relaunches)
    r = subprocess.run(
        ["launchctl", "kickstart", "-k", f"gui/{uid}/{service}"],
        capture_output=True, text=True, timeout=10,
    )
    print(f"[api] kickstart stdout: {r.stdout!r}  stderr: {r.stderr!r}  rc={r.returncode}")
    if r.returncode != 0:
        errors.append(f"kickstart rc={r.returncode}: {r.stderr.strip() or r.stdout.strip()}")

        # 2. Fallback: stop then start
        r2 = subprocess.run(["launchctl", "stop", service], capture_output=True, text=True, timeout=10)
        print(f"[api] stop rc={r2.returncode} stderr={r2.stderr!r}")
        time.sleep(1)
        r3 = subprocess.run(["launchctl", "start", service], capture_output=True, text=True, timeout=10)
        print(f"[api] start rc={r3.returncode} stderr={r3.stderr!r}")
        if r3.returncode != 0:
            errors.append(f"stop/start rc={r3.returncode}: {r3.stderr.strip() or r3.stdout.strip()}")

    time.sleep(2)
    pid = _scheduler_pid()
    if pid is None:
        detail = "Scheduler did not start. " + " | ".join(errors) if errors else "Scheduler did not start — check scheduler_log.txt"
        raise HTTPException(status_code=500, detail=detail)
    return {"success": True, "pid": pid, "errors": errors}

def _get_ibkr_data(settings: dict) -> dict:
    now = time.time()
    if _ibkr_cache["data"] and (now - _ibkr_cache["ts"]) < IBKR_CACHE_TTL:
        return _ibkr_cache["data"]

    result = {
        "connected":          False,
        "account_value":      None,   # NetLiquidation
        "buying_power":       None,
        "settled_cash":       None,
        "unrealized_pnl":     None,
        "realized_pnl":       None,
        "maintenance_margin": None,
        "excess_liquidity":   None,
        "account":            None,
        "portfolio":          [],
        "error":              None,
    }
    port = settings.get("ibkr_port", 4002)
    host = os.environ.get("IBKR_HOST", "127.0.0.1")
    account_env = settings.get("account") or os.environ.get("ACCOUNT", "")
    print(f"[api] IBKR connect attempt → {host}:{port} clientId={IBKR_API_CLIENT_ID}")

    # FastAPI sync endpoints run in anyio thread-pool workers. In Python 3.12+
    # those threads have no event loop set, which causes ib_insync's sync API to
    # raise RuntimeError("no current event loop"). Create one for this thread.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    from ib_insync import IB
    ib = IB()
    try:
        ib.connect(host, port, clientId=IBKR_API_CLIENT_ID, timeout=5, readonly=True)
        accts = ib.managedAccounts()
        acct = account_env or (accts[0] if accts else "")
        print(f"[api] IBKR connected — accounts: {accts}")
        if acct:
            result["account"] = acct

            # Account summary — collect all tags then extract by name
            summary_dict = {item.tag: item.value for item in ib.accountSummary(acct)}
            print(f"[api] accountSummary tags: {list(summary_dict.keys())}")
            result["account_value"]      = _safe_float(summary_dict.get("NetLiquidation",  0))
            result["buying_power"]       = _safe_float(summary_dict.get("BuyingPower",     0))
            result["settled_cash"]       = _safe_float(summary_dict.get("TotalCashValue",  0))
            result["unrealized_pnl"]     = _safe_float(summary_dict.get("UnrealizedPnL",   0))
            result["realized_pnl"]       = _safe_float(summary_dict.get("RealizedPnL",     0))
            result["maintenance_margin"] = _safe_float(summary_dict.get("MaintMarginReq",  0))
            result["excess_liquidity"]   = _safe_float(summary_dict.get("ExcessLiquidity", 0))

            # Portfolio items with live market prices
            ib.reqAccountUpdates(True, acct)
            ib.sleep(2)   # allow updatePortfolio events to populate the cache
            raw_portfolio = ib.portfolio(acct)

            portfolio = []
            for item in raw_portfolio:
                c = item.contract
                is_opt = c.secType == "OPT"
                portfolio.append({
                    "symbol":       c.symbol,
                    "secType":      c.secType,
                    "right":        c.right if is_opt else None,
                    "strike":       _safe_float(c.strike, 4) if is_opt else None,
                    "expiry":       c.lastTradeDateOrContractMonth if is_opt else None,
                    "position":     _safe_float(item.position, 0),
                    "avgCost":      _safe_float(item.averageCost, 4),
                    "marketPrice":  _safe_float(item.marketPrice, 4),
                    "marketValue":  _safe_float(item.marketValue, 2),
                    "unrealizedPNL":_safe_float(item.unrealizedPNL, 2),
                    "realizedPNL":  _safe_float(item.realizedPNL, 2),
                })

            # Sort: stocks first, then options; alphabetical within each group
            portfolio.sort(key=lambda x: (0 if x["secType"] == "STK" else 1, x["symbol"]))
            result["portfolio"] = portfolio
            result["connected"] = True
        print(f"[api] IBKR net_liq={result['account_value']} "
              f"unrealized_pnl={result['unrealized_pnl']} "
              f"portfolio_items={len(result['portfolio'])}")
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"[api] IBKR connection failed — {msg}")
        traceback.print_exc()
        result["error"] = msg
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

    _ibkr_cache["data"] = result
    _ibkr_cache["ts"] = now
    return result

def _scheduler_pid() -> Optional[int]:
    try:
        r = subprocess.run(["pgrep", "-f", "python.*scheduler.py"],
                           capture_output=True, text=True)
        pids = [p.strip() for p in r.stdout.strip().split("\n") if p.strip()]
        return int(pids[0]) if pids else None
    except Exception:
        return None

def _gateway_running(port: int) -> bool:
    try:
        r = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
        return bool(r.stdout.strip())
    except Exception:
        return False

def _parse_exec_time(settings: dict) -> tuple:
    try:
        h, m = map(int, settings.get("execution_time", "10:00").split(":"))
        return h, m
    except Exception:
        return 10, 0

def _next_execution() -> str:
    settings = load_settings()
    exec_h, exec_m = _parse_exec_time(settings)
    now = datetime.now(PST)
    days = (7 - now.weekday()) % 7  # Monday = 0
    if days == 0 and (now.hour > exec_h or (now.hour == exec_h and now.minute >= exec_m)):
        days = 7
    target = (now + timedelta(days=days)).replace(hour=exec_h, minute=exec_m, second=0, microsecond=0)
    return target.isoformat()

# ── Endpoints ─────────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    settings = load_settings()
    ibkr = _get_ibkr_data(settings)
    port = settings.get("ibkr_port", 4002)
    state = load_state()
    wheel_count = sum(
        1 for h in state.get("wheel_holdings", []) if h.get("shares", 0) > 0
    )
    return {
        "gateway_running":    _gateway_running(port),
        "scheduler_pid":      _scheduler_pid(),
        "ibkr_connected":     ibkr["connected"],
        "ibkr_error":         ibkr.get("error"),
        "account_value":      ibkr["account_value"],
        "buying_power":       ibkr["buying_power"],
        "unrealized_pnl":     ibkr.get("unrealized_pnl"),
        "net_liquidation":    ibkr.get("account_value"),
        "account":            ibkr["account"],
        "next_execution":     _next_execution(),
        "trading_mode":       settings.get("trading_mode", "paper"),
        "execution_time":     settings.get("execution_time", "10:00"),
        "wheel_count":        wheel_count,
    }

@app.get("/api/positions")
def get_positions():
    state = load_state()
    positions = state.get("positions", [])
    executions = state.get("executions", [])
    exec_map = {e.get("ticker"): e for e in executions if "ticker" in e}

    enriched = []
    for p in positions:
        ex = exec_map.get(p["ticker"], {})
        enriched.append({
            **p,
            "status":            ex.get("status", "unknown"),
            "fill_price":        ex.get("fill_price"),
            "order_type":        ex.get("order_type"),
            "premium_collected": ex.get("premium_collected", 0),
            "simulated":         ex.get("simulated", False),
            "exec_timestamp":    ex.get("timestamp"),
        })

    settings = load_settings()
    ibkr = _get_ibkr_data(settings)
    acct = ibkr.get("account_value")

    return {
        "positions":      enriched,
        "csp_positions":  enriched,
        "wheel_holdings": state.get("wheel_holdings", []),
        "weekly_pnl":     state.get("weekly_pnl", {}),
        "run_date":       state.get("run_date"),
        "monday_context": state.get("monday_context", {}),
        "portfolio":      ibkr.get("portfolio", []),
        "account_summary": {
            "net_liquidation":    acct,
            "settled_cash":       ibkr.get("settled_cash"),
            "unrealized_pnl":     ibkr.get("unrealized_pnl"),
            "realized_pnl":       ibkr.get("realized_pnl"),
            "maintenance_margin": ibkr.get("maintenance_margin"),
            "excess_liquidity":   ibkr.get("excess_liquidity"),
            "buying_power":       ibkr.get("buying_power"),
        } if ibkr.get("connected") else None,
    }

@app.get("/api/performance")
def get_performance():
    settings = load_settings()
    ytd = load_ytd()
    budget = settings.get("fund_budget", 250_000)

    weeks = ytd.get("weeks", [])
    total = ytd.get("total_premium", 0.0)
    weeks_traded = ytd.get("weeks_traded", 0)
    avg_yield = (total / weeks_traded / budget * 100) if weeks_traded and budget else 0.0
    progress_pct = (total / ANNUAL_TARGET * 100) if ANNUAL_TARGET else 0.0

    return {
        "weeks":         weeks,
        "total_premium": total,
        "weeks_traded":  weeks_traded,
        "avg_yield_pct": round(avg_yield, 3),
        "best_week":     ytd.get("best_week"),
        "worst_week":    ytd.get("worst_week"),
        "annual_target": ANNUAL_TARGET,
        "progress_pct":  round(progress_pct, 1),
    }

@app.get("/api/screener")
def run_screener():
    """Run screener + position sizer. Takes ~10 seconds."""
    settings = load_settings()
    try:
        import importlib
        import sys
        for mod_name in ["config", "screener", "position_sizer"]:
            if mod_name in sys.modules:
                importlib.reload(sys.modules[mod_name])

        from screener import get_top_targets
        from position_sizer import size_all

        n      = settings.get("num_positions", 5)
        budget = settings.get("fund_budget", 250_000)

        # Deduct capital reserved for active wheel holdings
        state          = load_state()
        wheel_holdings = state.get("wheel_holdings", [])
        active_holdings = [h for h in wheel_holdings if h.get("shares", 0) > 0]
        reserved_capital   = round(sum(
            h["shares"] * h.get("assigned_strike", 0.0) for h in active_holdings
        ), 2)
        active_wheel_count = len(active_holdings)
        adjusted_budget    = budget - reserved_capital
        target_fills       = max(1, n - active_wheel_count)

        targets   = get_top_targets(n * 2)
        positions = size_all(targets, budget=adjusted_budget, num_positions=target_fills)

        total_premium = sum(p.get("premium_total", 0) for p in positions)
        total_capital = sum(p.get("capital_used", 0) for p in positions)

        return {
            "positions":          positions,
            "raw_targets":        targets,
            "total_premium":      total_premium,
            "total_capital":      total_capital,
            "blended_yield":      round(total_premium / total_capital * 100 if total_capital else 0, 3),
            "budget":             adjusted_budget,
            "total_budget":       budget,
            "reserved_capital":   reserved_capital,
            "active_wheel_count": active_wheel_count,
            "wheel_holdings":     wheel_holdings,
            "run_at":             datetime.now(PST).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/live-ready")
def get_live_ready():
    return _live_ready()

@app.get("/api/settings")
def get_settings_endpoint():
    return load_settings()

class SettingsUpdate(BaseModel):
    fund_budget:              Optional[float] = None
    num_positions:            Optional[int]   = None
    min_position_size:        Optional[float] = None
    max_position_size:        Optional[float] = None
    max_delta:                Optional[float] = None
    min_buffer_pct:           Optional[float] = None
    earnings_filter_days:     Optional[int]   = None
    dry_run:                  Optional[bool]  = None
    ibkr_port:                Optional[int]   = None
    discord_webhook_enabled:  Optional[bool]  = None
    trading_mode:             Optional[str]   = None
    execution_time:           Optional[str]   = None

@app.post("/api/settings")
def update_settings(body: SettingsUpdate):
    current = load_settings()
    updates = {k: v for k, v in body.dict().items() if v is not None}
    current.update(updates)
    save_settings(current)
    return current

class TradingModeRequest(BaseModel):
    mode: str
    confirmation: str

@app.post("/api/trading-mode")
def set_trading_mode(body: TradingModeRequest):
    if body.confirmation != "CONFIRM":
        raise HTTPException(status_code=400, detail="confirmation must be exactly 'CONFIRM'")
    if body.mode not in ("paper", "live"):
        raise HTTPException(status_code=400, detail="mode must be 'paper' or 'live'")

    if body.mode == "live":
        ready = _live_ready()
        if not ready["ready"]:
            missing_str = ", ".join(ready["missing"])
            raise HTTPException(
                status_code=400,
                detail=f"Live credentials not configured. Add these to your .env file and restart YRVI: {missing_str}",
            )

    current = load_settings()
    current["trading_mode"] = body.mode
    current["ibkr_port"]    = 4001 if body.mode == "live" else 4002

    if body.mode == "live":
        current["account"] = os.environ.get("ACCOUNT_LIVE", "")
        _update_ibc_config(
            username=os.environ.get("IBKR_USERNAME_LIVE", ""),
            password=os.environ.get("IBKR_PASSWORD_LIVE", ""),
            mode="live",
            port=4001,
        )
        _restart_ibgateway()

    save_settings(current)

    # Bust cache so next /api/status re-checks IBKR
    _ibkr_cache["data"] = None
    _ibkr_cache["ts"]   = 0.0

    try:
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
        if webhook_url and current.get("discord_webhook_enabled", True):
            import requests as req
            req.post(webhook_url, json={
                "content": f"⚠️ YRVI trading mode switched to **{body.mode.upper()}** via web dashboard"
            }, timeout=5)
    except Exception:
        pass

    return {"success": True, "trading_mode": body.mode, "ibkr_port": current["ibkr_port"]}

@app.get("/api/trade-history")
def get_trade_history():
    state = load_state()
    ytd = load_ytd()

    positions = state.get("positions", [])
    executions = state.get("executions", [])
    pos_map = {p["ticker"]: p for p in positions}

    enriched = []
    for ex in executions:
        t = ex.get("ticker", "")
        pos = pos_map.get(t, {})
        enriched.append({
            **ex,
            "screener_premium": pos.get("premium"),
            "strike":           pos.get("strike"),
            "buffer_pct":       pos.get("buffer_pct"),
            "delta":            pos.get("delta"),
            "capital_used":     pos.get("capital_used"),
        })

    return {
        "current_week": {
            "run_date":   state.get("run_date"),
            "executions": enriched,
            "weekly_pnl": state.get("weekly_pnl", {}),
        },
        "weekly_summaries": ytd.get("weeks", []),
        "total_premium":    ytd.get("total_premium", 0),
    }

@app.post("/api/discord-test")
def test_discord():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        raise HTTPException(status_code=400, detail="DISCORD_WEBHOOK_URL not set in .env")
    try:
        import requests as req
        r = req.post(webhook_url, json={"content": "🔔 YRVI Dashboard — test notification"}, timeout=5)
        r.raise_for_status()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
