"""
Risk Manager — daily monitor (Tuesday–Thursday 9AM PST)

run_daily_monitor():
  - Connects to IBKR and fetches current price for each wheel holding
  - Compares price to stop_loss_price (assignment_strike * 0.90)
  - Logs stop loss alerts — actual sells happen Monday morning only
  - Updates state.json with current prices, alert flags, and running P&L
"""
import json
import logging
from datetime import datetime, timezone

from ib_insync import IB, Stock

from config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID_RISK, ACCOUNT, STOP_LOSS_PCT

STATE_FILE = "state.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("risk_log.txt"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _connect() -> IB:
    ib = IB()
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID_RISK)
    ib.reqMarketDataType(3)
    log.info(f"✅ Connected to IBKR (clientId={IBKR_CLIENT_ID_RISK})")
    return ib


def _is_nan(val) -> bool:
    try:
        return val != val
    except Exception:
        return True


def _get_stock_price(ib: IB, ticker: str) -> float | None:
    contract  = Stock(ticker, "SMART", "USD")
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        log.warning(f"  ⚠️  Could not qualify stock: {ticker}")
        return None
    data  = ib.reqMktData(qualified[0], snapshot=False)
    ib.sleep(4)
    price = data.last  if not _is_nan(data.last)  and data.last  > 0 else \
            data.close if not _is_nan(data.close) and data.close > 0 else \
            data.bid   if not _is_nan(data.bid)   and data.bid   > 0 else None
    ib.cancelMktData(qualified[0])
    ib.sleep(0.5)
    return round(float(price), 2) if price else None


def _build_weekly_pnl(state: dict) -> dict:
    executions = state.get("executions", [])
    holdings   = state.get("wheel_holdings", [])
    context    = state.get("monday_context", {})

    csp_premium = sum(
        e.get("premium_collected", 0) for e in executions
        if e.get("status") in ("filled", "partial_fill", "dry_run")
    )
    cc_premium       = context.get("cc_premium", 0.0)
    stop_loss_pnl    = context.get("stop_loss_realized_pnl", 0.0)

    # Unrealized P&L: (current_price - assignment_strike) * shares for active holdings
    unrealized = 0.0
    for h in holdings:
        if h.get("shares", 0) > 0 and h.get("current_price") and h.get("assignment_strike"):
            unrealized += (h["current_price"] - h["assignment_strike"]) * h["shares"]
    unrealized = round(unrealized, 2)

    total_realized = round(csp_premium + cc_premium + stop_loss_pnl, 2)

    return {
        "week_start":             state.get("run_date", "")[:10],
        "csp_premium":            round(csp_premium, 2),
        "cc_premium":             round(cc_premium, 2),
        "stop_loss_realized_pnl": round(stop_loss_pnl, 2),
        "total_realized":         total_realized,
        "unrealized_stock_pnl":   unrealized,
        "grand_total":            round(total_realized + unrealized, 2),
        "last_updated":           datetime.now().isoformat()
    }


# ── Public API ─────────────────────────────────────────────────

def run_daily_monitor():
    """
    Tuesday–Thursday 9AM PST.
    Fetches live prices for all wheel holdings, logs stop loss alerts,
    and updates state.json with current prices and weekly P&L snapshot.
    """
    now = datetime.now()
    log.info("\n" + "=" * 65)
    log.info(f"📊 DAILY RISK MONITOR — {now.strftime('%A %Y-%m-%d %H:%M:%S')}")
    log.info("=" * 65)

    state    = _load_state()
    holdings = state.get("wheel_holdings", [])

    if not holdings:
        log.info("📭 No wheel holdings to monitor")
        pnl = _build_weekly_pnl(state)
        state["weekly_pnl"] = pnl
        _save_state(state)
        _log_pnl_summary(pnl)
        return

    ib = _connect()
    alerts = []

    try:
        log.info(f"\n  Monitoring {len(holdings)} wheel holding(s):")
        log.info(f"  {'Ticker':<8} {'Shares':>6}  {'Strike':>8}  "
                 f"{'Stop':>8}  {'Current':>8}  {'Buffer':>8}  {'Unreal P&L':>12}  Status")
        log.info("  " + "-" * 75)

        for h in holdings:
            ticker            = h["ticker"]
            shares            = h.get("shares", 0)
            assignment_strike = h.get("assignment_strike", 0.0)
            stop_loss_price   = h.get("stop_loss_price", 0.0)
            cc_status         = h.get("cc_status", "unknown")

            if shares <= 0:
                log.info(f"  {ticker:<8}  (exited)")
                continue

            current_price = _get_stock_price(ib, ticker)
            if current_price is None:
                log.warning(f"  {ticker:<8}  ⚠️  price unavailable")
                continue

            h["current_price"] = current_price
            h["last_checked"]  = now.isoformat()

            buffer_pct  = ((current_price - stop_loss_price) / current_price) * 100
            unrealized  = round((current_price - assignment_strike) * shares, 2)
            at_risk     = current_price < stop_loss_price

            if at_risk:
                h["stop_loss_alert"] = True
                alerts.append(ticker)
                status_icon = "🚨 STOP ALERT"
            elif buffer_pct < 3:
                status_icon = "⚠️  approaching"
            else:
                h["stop_loss_alert"] = False
                status_icon = "✅ safe"

            log.info(f"  {ticker:<8} {shares:>6}  ${assignment_strike:>7.2f}  "
                     f"${stop_loss_price:>7.2f}  ${current_price:>7.2f}  "
                     f"{buffer_pct:>7.1f}%  ${unrealized:>10,.0f}  {status_icon}  "
                     f"[CC: {cc_status}]")

    finally:
        ib.disconnect()

    # ── Stop loss alerts ──────────────────────────────────────
    if alerts:
        log.warning("\n" + "!" * 65)
        log.warning(f"  🚨 STOP LOSS ALERT: {alerts}")
        log.warning(f"  These positions are below stop loss price.")
        log.warning(f"  They will be sold next Monday 9:55AM PST.")
        log.warning("!" * 65)
    else:
        log.info(f"\n  ✅ All {len(holdings)} holding(s) above stop loss threshold")

    # ── Update state ──────────────────────────────────────────
    state["wheel_holdings"] = holdings
    pnl = _build_weekly_pnl(state)
    state["weekly_pnl"] = pnl
    _save_state(state)
    _log_pnl_summary(pnl)


def _log_pnl_summary(pnl: dict):
    log.info("\n" + "=" * 65)
    log.info("💰 WEEKLY P&L SNAPSHOT")
    log.info(f"   Week of:              {pnl.get('week_start', 'N/A')}")
    log.info(f"   CSP premium:         ${pnl.get('csp_premium', 0):>10,.0f}")
    log.info(f"   CC premium:          ${pnl.get('cc_premium', 0):>10,.0f}")
    log.info(f"   Stop loss P&L:       ${pnl.get('stop_loss_realized_pnl', 0):>10,.0f}")
    log.info(f"   ─────────────────────────────")
    log.info(f"   Total realized:      ${pnl.get('total_realized', 0):>10,.0f}")
    log.info(f"   Unrealized stock:    ${pnl.get('unrealized_stock_pnl', 0):>10,.0f}")
    log.info(f"   Grand total:         ${pnl.get('grand_total', 0):>10,.0f}")
    log.info("=" * 65)


if __name__ == "__main__":
    run_daily_monitor()
