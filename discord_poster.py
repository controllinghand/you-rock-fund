"""
Optional Discord notification plugin for YRVI.
Only active when DISCORD_WEBHOOK_URL is set in .env — silently no-ops otherwise.
"""
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL   = os.getenv("DISCORD_WEBHOOK_URL")
YTD_FILE      = "ytd_tracker.json"
PST           = ZoneInfo("America/Los_Angeles")
ANNUAL_TARGET = 100_000

COLOR_GREEN  = 0x2ECC71   # yield ≥ 1%
COLOR_YELLOW = 0xF1C40F   # yield 0.5–1%
COLOR_RED    = 0xE74C3C   # yield < 0.5%
COLOR_BLUE   = 0x3498DB   # preview
COLOR_PURPLE = 0x9B59B6   # assignment alert


def is_enabled() -> bool:
    return bool(WEBHOOK_URL)


def _post(payload: dict) -> bool:
    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[discord] post failed: {e}")
        return False


def _load_ytd() -> dict:
    try:
        with open(YTD_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"weeks": [], "total_premium": 0.0, "weeks_traded": 0,
                "best_week": None, "worst_week": None}


def _save_ytd(ytd: dict):
    with open(YTD_FILE, "w") as f:
        json.dump(ytd, f, indent=2)


def _update_ytd(week_start: str, total_realized: float, fund_budget: float) -> dict:
    ytd = _load_ytd()
    if not any(w["week_start"] == week_start for w in ytd["weeks"]):
        ytd["weeks"].append({
            "week_start": week_start,
            "realized":   total_realized,
            "yield_pct":  round(total_realized / fund_budget * 100, 3) if fund_budget else 0,
        })
        ytd["total_premium"] = round(sum(w["realized"] for w in ytd["weeks"]), 2)
        ytd["weeks_traded"]  = len(ytd["weeks"])
        by_realized       = sorted(ytd["weeks"], key=lambda w: w["realized"])
        ytd["worst_week"]  = by_realized[0]
        ytd["best_week"]   = by_realized[-1]
        _save_ytd(ytd)
    return ytd


def _yield_color(yield_pct: float) -> int:
    if yield_pct >= 1.0:
        return COLOR_GREEN
    elif yield_pct >= 0.5:
        return COLOR_YELLOW
    return COLOR_RED


def _yield_emoji(yield_pct: float) -> str:
    if yield_pct >= 1.0:
        return "🟢"
    elif yield_pct >= 0.5:
        return "🟡"
    return "🔴"


def post_weekly_results(state: dict, fund_budget: float = 250_000):
    """Post rich embed after Monday CSP execution completes."""
    if not WEBHOOK_URL:
        return

    pnl            = state.get("weekly_pnl", {})
    week_start     = pnl.get("week_start", datetime.now(PST).strftime("%Y-%m-%d"))
    csp_premium    = pnl.get("csp_premium", 0.0)
    cc_premium     = pnl.get("cc_premium", 0.0)
    stop_loss_pnl  = pnl.get("stop_loss_realized_pnl", 0.0)
    total_realized = pnl.get("total_realized", 0.0)

    yield_pct = total_realized / fund_budget * 100 if fund_budget else 0
    ytd       = _update_ytd(week_start, total_realized, fund_budget)

    avg_yield    = (ytd["total_premium"] / ytd["weeks_traded"] / fund_budget * 100) \
                   if ytd["weeks_traded"] and fund_budget else 0
    progress_pct = ytd["total_premium"] / ANNUAL_TARGET * 100

    fields = [
        {"name": "CSP Premium",    "value": f"${csp_premium:,.0f}",    "inline": True},
        {"name": "CC Premium",     "value": f"${cc_premium:,.0f}",     "inline": True},
        {"name": "Stop Loss P&L",  "value": f"${stop_loss_pnl:,.0f}",  "inline": True},
        {"name": "Week Yield",     "value": f"{yield_pct:.2f}%",       "inline": True},
        {"name": "Total Realized", "value": f"${total_realized:,.0f}", "inline": True},
        {"name": "​",         "value": "​",                  "inline": True},
    ]

    best  = ytd.get("best_week")
    worst = ytd.get("worst_week")
    ytd_lines = [
        f"**Total Premium:** ${ytd['total_premium']:,.0f}",
        f"**Weeks Traded:** {ytd['weeks_traded']}",
        f"**Avg Yield/Week:** {avg_yield:.2f}%",
        f"**Progress:** {progress_pct:.1f}% toward ${ANNUAL_TARGET:,} annual target",
    ]
    if best:
        ytd_lines.append(f"**Best Week:** ${best['realized']:,.0f} ({best['yield_pct']:.2f}%)")
    if worst and best and worst["week_start"] != best["week_start"]:
        ytd_lines.append(f"**Worst Week:** ${worst['realized']:,.0f} ({worst['yield_pct']:.2f}%)")
    fields.append({"name": "📊 YTD Stats", "value": "\n".join(ytd_lines), "inline": False})

    holdings = [h for h in state.get("wheel_holdings", []) if h.get("shares", 0) > 0]
    if holdings:
        lines = [
            f"• **{h['ticker']}** {h['shares']} shares "
            f"@ ${h['assignment_strike']:.2f} — CC {h.get('cc_status', '?')}"
            for h in holdings
        ]
        fields.append({"name": "🔄 Wheel Holdings", "value": "\n".join(lines), "inline": False})

    _post({"embeds": [{
        "title":     f"{_yield_emoji(yield_pct)} YRVI Week of {week_start} — "
                     f"${total_realized:,.0f} realized ({yield_pct:.2f}%)",
        "color":     _yield_color(yield_pct),
        "fields":    fields,
        "footer":    {"text": "You Rock Volatility Income Fund"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }]})


def post_preview(positions: list, budget: float):
    """Post 9:50AM Monday pre-execution preview."""
    if not WEBHOOK_URL:
        return

    now       = datetime.now(PST)
    lines     = []
    est_total = 0.0
    for i, p in enumerate(positions[:5], 1):
        prem       = p.get("premium_total", 0)
        est_total += prem
        bz         = " ✅" if p.get("buyzone") else ""
        lines.append(
            f"{i}. **{p['ticker']}** ${p['strike']:.0f} put · "
            f"{p['contracts']}x · exp {p.get('expiry', '?')} · "
            f"~${prem:,.0f} prem ({p.get('yield_pct', 0):.2f}%){bz}"
        )

    _post({"embeds": [{
        "title":       f"📋 YRVI Preview — {now.strftime('%A %b %d')} (executing in ~10 min)",
        "description": "\n".join(lines) if lines else "No positions sized.",
        "color":       COLOR_BLUE,
        "fields": [
            {"name": "Budget",            "value": f"${budget:,.0f}",     "inline": True},
            {"name": "Positions",         "value": str(len(positions)),   "inline": True},
            {"name": "Est. Total Prem.",  "value": f"~${est_total:,.0f}", "inline": True},
        ],
        "footer":    {"text": "You Rock Volatility Income Fund"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }]})


def post_assignment_alert(new_assignments: list):
    """Post Friday alert for newly detected stock assignments."""
    if not WEBHOOK_URL or not new_assignments:
        return

    lines = [
        f"• **{a['ticker']}** — {a['shares']} shares "
        f"@ ${a['assignment_strike']:.2f} (stop ${a['stop_loss_price']:.2f})"
        for a in new_assignments
    ]

    _post({"embeds": [{
        "title":       f"📬 YRVI — {len(new_assignments)} Assignment(s) Detected",
        "description": "\n".join(lines),
        "color":       COLOR_PURPLE,
        "fields": [{
            "name":   "Next Step",
            "value":  "Wheel check runs Monday 9:55AM — stop loss check + covered calls",
            "inline": False,
        }],
        "footer":    {"text": "You Rock Volatility Income Fund"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }]})
