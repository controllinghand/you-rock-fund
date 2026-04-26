"""YRVI Management Dashboard — FastAPI backend."""
import json
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

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

def _get_ibkr_data(settings: dict) -> dict:
    now = time.time()
    if _ibkr_cache["data"] and (now - _ibkr_cache["ts"]) < IBKR_CACHE_TTL:
        return _ibkr_cache["data"]

    result = {"connected": False, "account_value": None, "buying_power": None, "account": None}
    try:
        from ib_insync import IB
        port = settings.get("ibkr_port", 4002)
        host = os.environ.get("IBKR_HOST", "127.0.0.1")
        account_env = os.environ.get("ACCOUNT", "")

        ib = IB()
        ib.connect(host, port, clientId=IBKR_API_CLIENT_ID, timeout=5, readonly=True)
        accts = ib.managedAccounts()
        acct = account_env or (accts[0] if accts else "")
        if acct:
            result["account"] = acct
            for item in ib.accountSummary(acct):
                if item.currency == "USD":
                    if item.tag == "NetLiquidation":
                        result["account_value"] = round(float(item.value), 2)
                    elif item.tag == "BuyingPower":
                        result["buying_power"] = round(float(item.value), 2)
            result["connected"] = True
        ib.disconnect()
    except Exception as e:
        print(f"[api] IBKR: {e}")

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

def _next_execution() -> str:
    now = datetime.now(PST)
    days = (7 - now.weekday()) % 7  # Monday = 0
    if days == 0 and (now.hour > 10 or (now.hour == 10 and now.minute >= 1)):
        days = 7
    target = (now + timedelta(days=days)).replace(hour=10, minute=0, second=0, microsecond=0)
    return target.isoformat()

# ── Endpoints ─────────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    settings = load_settings()
    ibkr = _get_ibkr_data(settings)
    port = settings.get("ibkr_port", 4002)
    return {
        "gateway_running": _gateway_running(port),
        "scheduler_pid":   _scheduler_pid(),
        "ibkr_connected":  ibkr["connected"],
        "account_value":   ibkr["account_value"],
        "buying_power":    ibkr["buying_power"],
        "account":         ibkr["account"],
        "next_execution":  _next_execution(),
        "trading_mode":    settings.get("trading_mode", "paper"),
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

    return {
        "positions":      enriched,
        "wheel_holdings": state.get("wheel_holdings", []),
        "weekly_pnl":     state.get("weekly_pnl", {}),
        "run_date":       state.get("run_date"),
        "monday_context": state.get("monday_context", {}),
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

        n = settings.get("num_positions", 5)
        budget = settings.get("fund_budget", 250_000)

        targets = get_top_targets(n * 2)
        positions = size_all(targets[:n], budget=budget)

        total_premium = sum(p.get("premium_total", 0) for p in positions)
        total_capital = sum(p.get("capital_used", 0) for p in positions)

        return {
            "positions":     positions,
            "raw_targets":   targets[:n],
            "total_premium": total_premium,
            "total_capital": total_capital,
            "blended_yield": round(total_premium / total_capital * 100 if total_capital else 0, 3),
            "budget":        budget,
            "run_at":        datetime.now(PST).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

    current = load_settings()
    current["trading_mode"] = body.mode
    current["ibkr_port"]    = 4001 if body.mode == "live" else 4002
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
