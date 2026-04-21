"""
Wheel Strategy Manager

detect_assignments() — Friday 4:15PM PST
    Scan IBKR for stock positions created by put assignments.
    Persist to state.json["wheel_holdings"].

run_wheel_check() — Monday 9:55AM PST (runs before CSP pipeline)
    For each held stock:
      - If current_price < assignment_strike * 0.90 → sell at market (stop loss)
      - Else → sell covered call at assignment_strike, nearest Friday expiry
    Writes monday_context to state.json for run_pipeline to consume.
    Returns (freed_capital, skip_tickers).
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from ib_insync import IB, Stock, Option, LimitOrder, MarketOrder

from config import (
    IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID_WHEEL, ACCOUNT, STOP_LOSS_PCT
)

STATE_FILE       = "state.json"
MID_WAIT_SECS    = 120
BID_WAIT_SECS    = 120
MARKET_WAIT_SECS = 60
MARKET_POLL_SECS = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("wheel_log.txt"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ── State helpers ──────────────────────────────────────────────

def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── IBKR helpers ───────────────────────────────────────────────

def _connect() -> IB:
    ib = IB()
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID_WHEEL)
    ib.reqMarketDataType(3)
    log.info(f"✅ Connected to IBKR (clientId={IBKR_CLIENT_ID_WHEEL})")
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
    price = data.last if not _is_nan(data.last) and data.last > 0 else \
            data.close if not _is_nan(data.close) and data.close > 0 else \
            data.bid   if not _is_nan(data.bid)   and data.bid   > 0 else None
    ib.cancelMktData(qualified[0])
    ib.sleep(0.5)
    return round(float(price), 2) if price else None


def _next_friday_expiry() -> str:
    today      = datetime.now().date()
    days_ahead = 4 - today.weekday()   # Monday=0 → days_ahead=4 (this Friday)
    if days_ahead <= 0:
        days_ahead += 7
    return (today + timedelta(days=days_ahead)).strftime("%Y%m%d")


# ── Order helpers ──────────────────────────────────────────────

def _sell_stock_market(ib: IB, ticker: str, shares: int) -> dict:
    contract  = Stock(ticker, "SMART", "USD")
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        log.error(f"  ❌ Could not qualify {ticker} for stop loss sale")
        return {"status": "failed", "proceeds": 0.0, "fill_price": None}

    log.info(f"  📤 STOP LOSS: SELL {shares} shares of {ticker} at market")
    order = MarketOrder("SELL", shares, account=ACCOUNT, tif="DAY")
    trade = ib.placeOrder(qualified[0], order)

    elapsed = 0
    while elapsed < MARKET_WAIT_SECS:
        ib.sleep(MARKET_POLL_SECS)
        elapsed += MARKET_POLL_SECS
        status    = trade.orderStatus.status
        remaining = trade.orderStatus.remaining
        filled    = trade.orderStatus.filled
        if status == "Filled" or (remaining == 0 and filled > 0):
            fill     = trade.orderStatus.avgFillPrice
            proceeds = round(shares * fill, 2)
            log.info(f"  ✅ Stop loss filled: {shares}x {ticker} @ ${fill:.2f} = ${proceeds:,.0f}")
            return {"status": "filled", "fill_price": fill, "proceeds": proceeds}
        log.info(f"  ⏳ Stop loss status: {status} after {elapsed}s")

    log.error(f"  ❌ Stop loss timed out for {ticker} — MANUAL ACTION REQUIRED")
    return {"status": "failed", "proceeds": 0.0, "fill_price": None}


def _sell_cc_with_escalation(ib: IB, contract, shares: int, ticker: str,
                              strike: float, ref_mid: float) -> dict:
    num_contracts = shares // 100
    if num_contracts < 1:
        log.warning(f"  ⚠️  {ticker}: {shares} shares < 100 — cannot sell CC")
        return {"status": "skipped_insufficient_shares", "premium_collected": 0.0,
                "fill_price": None, "order_type": None}

    result = {
        "ticker": ticker, "option_contracts": num_contracts, "shares": shares,
        "strike": strike, "status": "unfilled", "fill_price": None,
        "order_type": None, "premium_collected": 0.0,
        "timestamp": datetime.now().isoformat()
    }

    def try_limit(price: float, label: str, wait: int) -> bool:
        log.info(f"  📤 {label}: SELL {num_contracts}x {ticker} CALL @ ${price:.2f}")
        order = LimitOrder("SELL", num_contracts, price, account=ACCOUNT, tif="DAY")
        trade = ib.placeOrder(contract, order)
        ib.sleep(wait)
        if trade.orderStatus.status == "Filled":
            fill = trade.orderStatus.avgFillPrice
            log.info(f"  ✅ CC filled: {ticker} @ ${fill:.2f}")
            result.update({
                "status": "filled", "fill_price": fill, "order_type": label,
                "premium_collected": round(num_contracts * fill * 100, 2)
            })
            return True
        log.info(f"  ⏳ {label} unfilled — escalating...")
        ib.cancelOrder(trade.order)
        ib.sleep(1)
        return False

    if try_limit(ref_mid, "limit_mid", MID_WAIT_SECS):
        return result
    bid_proxy = round(ref_mid * 0.90, 2)
    if try_limit(bid_proxy, "limit_bid", BID_WAIT_SECS):
        return result

    log.info(f"  📤 Market order: SELL {num_contracts}x {ticker} CALL")
    order = MarketOrder("SELL", num_contracts, account=ACCOUNT, tif="DAY")
    trade = ib.placeOrder(contract, order)

    elapsed = 0
    while elapsed < MARKET_WAIT_SECS:
        ib.sleep(MARKET_POLL_SECS)
        elapsed += MARKET_POLL_SECS
        status    = trade.orderStatus.status
        remaining = trade.orderStatus.remaining
        filled    = trade.orderStatus.filled
        if status == "Filled" or (remaining == 0 and filled > 0):
            fill = trade.orderStatus.avgFillPrice
            log.info(f"  ✅ CC market filled: {ticker} @ ${fill:.2f} in {elapsed}s")
            result.update({
                "status": "filled", "fill_price": fill, "order_type": "market",
                "premium_collected": round(filled * fill * 100, 2)
            })
            return result
        if status == "PartiallyFilled" and filled > 0:
            log.info(f"  ⏳ Partial CC: {filled}/{num_contracts} after {elapsed}s")
        else:
            log.info(f"  ⏳ CC market status: {status} after {elapsed}s")

    final_qty = trade.orderStatus.filled
    if final_qty > 0:
        fill = trade.orderStatus.avgFillPrice
        log.warning(f"  ⚠️  CC partial fill accepted: {final_qty}/{num_contracts} @ ${fill:.2f}")
        result.update({
            "status": "partial_fill", "fill_price": fill, "order_type": "market",
            "premium_collected": round(final_qty * fill * 100, 2)
        })
    else:
        log.error(f"  ❌ CC order failed for {ticker}")
        result["status"] = "failed"
    return result


# ── Public API ─────────────────────────────────────────────────

def detect_assignments():
    """
    Friday 4:15PM PST — scan IBKR for stock positions and reconcile
    against known wheel_holdings. New assignments are added with their
    CSP strike looked up from state.json executions.
    """
    log.info("\n" + "=" * 65)
    log.info(f"🔍 FRIDAY ASSIGNMENT DETECTION — "
             f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 65)

    state             = _load_state()
    existing_holdings = {h["ticker"]: h for h in state.get("wheel_holdings", [])}

    # Build a strike lookup from last week's CSP executions + sized positions
    strike_lookup = {}
    for p in state.get("positions", []):
        strike_lookup[p["ticker"]] = p["strike"]

    ib = _connect()
    try:
        ibkr_positions = ib.positions(account=ACCOUNT)
        stock_positions = {
            p.contract.symbol: int(p.position)
            for p in ibkr_positions
            if p.contract.secType == "STK" and int(p.position) > 0
        }
    finally:
        ib.disconnect()

    log.info(f"📊 Found {len(stock_positions)} stock position(s) in IBKR")

    updated = []
    for ticker, shares in stock_positions.items():
        if ticker in existing_holdings:
            h          = existing_holdings[ticker]
            h["shares"] = shares
            h["last_checked"] = datetime.now().isoformat()
            log.info(f"  ✅ {ticker}: {shares} shares (existing — updated count)")
        else:
            assignment_strike = strike_lookup.get(ticker)
            if assignment_strike is None:
                log.warning(f"  ⚠️  {ticker}: CSP strike not found in state — "
                             f"set assignment_strike manually in state.json")
                assignment_strike = 0.0
            stop_loss_price = round(assignment_strike * (1 - STOP_LOSS_PCT), 2)
            h = {
                "ticker":               ticker,
                "shares":               shares,
                "assignment_strike":    assignment_strike,
                "assignment_date":      datetime.now().date().isoformat(),
                "stop_loss_price":      stop_loss_price,
                "cc_expiry":            None,
                "cc_strike":            assignment_strike,
                "cc_status":            "pending",
                "cc_premium_collected": 0.0,
                "current_price":        None,
                "last_checked":         datetime.now().isoformat(),
                "stop_loss_alert":      False,
            }
            log.info(f"  🆕 NEW ASSIGNMENT: {ticker}  {shares} shares  "
                     f"strike ${assignment_strike:.2f}  stop ${stop_loss_price:.2f}")
        updated.append(h)

    for ticker, h in existing_holdings.items():
        if ticker not in stock_positions:
            log.info(f"  📤 {ticker}: no longer held (assigned away or previously sold)")

    state["wheel_holdings"] = updated
    _save_state(state)
    log.info(f"\n💾 Saved {len(updated)} wheel holding(s) to state.json")
    log.info("=" * 65)


def run_wheel_check() -> tuple[float, list]:
    """
    Monday 9:55AM PST — evaluate each held stock position:
      - below stop loss  → sell shares at market, free capital, skip in CSP
      - above stop loss  → sell covered call at assignment_strike, nearest Friday

    Writes monday_context to state.json for run_pipeline to consume.
    Returns (freed_capital, skip_tickers).
    """
    log.info("\n" + "=" * 65)
    log.info(f"🔄 MONDAY WHEEL CHECK — "
             f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 65)

    state    = _load_state()
    holdings = state.get("wheel_holdings", [])

    empty_context = {
        "skip_tickers": [], "freed_capital": 0.0,
        "cc_premium": 0.0, "stop_loss_realized_pnl": 0.0,
        "updated": datetime.now().isoformat()
    }

    if not holdings:
        log.info("📭 No wheel holdings — nothing to do")
        state["monday_context"] = empty_context
        _save_state(state)
        return 0.0, []

    ib             = _connect()
    expiry         = _next_friday_expiry()
    freed_capital  = 0.0
    skip_tickers   = []
    cc_premium     = 0.0
    stop_loss_pnl  = 0.0

    try:
        for h in holdings:
            ticker            = h["ticker"]
            shares            = h["shares"]
            assignment_strike = h["assignment_strike"]
            stop_loss_price   = h["stop_loss_price"]

            log.info(f"\n  [{ticker}]  {shares} shares  "
                     f"strike ${assignment_strike:.2f}  stop ${stop_loss_price:.2f}")

            if shares <= 0:
                log.info(f"  ⏭️  {ticker}: 0 shares — skipping")
                continue

            current_price = _get_stock_price(ib, ticker)
            if current_price is None:
                log.warning(f"  ⚠️  {ticker}: could not get price — skipping this week")
                continue

            h["current_price"] = current_price
            h["last_checked"]  = datetime.now().isoformat()
            log.info(f"  📈 Current: ${current_price:.2f}  "
                     f"({'🔴 BELOW' if current_price < stop_loss_price else '🟢 above'} stop)")

            # ── Stop loss ─────────────────────────────────────
            if current_price < stop_loss_price:
                log.warning(f"  🛑 STOP LOSS TRIGGERED — selling {shares} shares")
                result = _sell_stock_market(ib, ticker, shares)
                if result["status"] == "filled":
                    proceeds    = result["proceeds"]
                    realized    = round(proceeds - (assignment_strike * shares), 2)
                    freed_capital   += proceeds
                    stop_loss_pnl   += realized
                    skip_tickers.append(ticker)
                    h["cc_status"] = "stop_loss_exit"
                    h["shares"]    = 0
                    log.info(f"  📊 Realized P&L: ${realized:,.0f}  "
                             f"Proceeds added to pool: ${proceeds:,.0f}")
                else:
                    log.error(f"  ❌ Stop loss FAILED for {ticker} — MANUAL ACTION REQUIRED")

            # ── Sell covered call ─────────────────────────────
            else:
                log.info(f"  ☎️  Selling covered call @ ${assignment_strike:.2f}  expiry {expiry}")
                cc_contract = Option(ticker, expiry, assignment_strike, "C", "SMART", currency="USD")
                try:
                    qualified = ib.qualifyContracts(cc_contract)
                except Exception as e:
                    log.error(f"  ❌ Could not qualify CC for {ticker}: {e}")
                    continue

                if not qualified:
                    log.warning(f"  ⚠️  No CC contract: {ticker} ${assignment_strike} {expiry}")
                    continue

                # Get CC mid price
                cc_data = ib.reqMktData(qualified[0], snapshot=False)
                ib.sleep(4)
                cc_bid = cc_data.bid
                cc_ask = cc_data.ask
                ib.cancelMktData(qualified[0])
                ib.sleep(0.5)

                if _is_nan(cc_bid) or _is_nan(cc_ask) or cc_bid <= 0 or cc_ask <= 0:
                    ref_mid = 0.50
                    log.warning(f"  ⚠️  No CC market data — using ${ref_mid:.2f} as mid reference")
                else:
                    ref_mid = round((cc_bid + cc_ask) / 2, 2)
                    log.info(f"  CC market — Bid: ${cc_bid:.2f}  Ask: ${cc_ask:.2f}  "
                             f"Mid: ${ref_mid:.2f}")

                cc_result = _sell_cc_with_escalation(
                    ib, qualified[0], shares, ticker, assignment_strike, ref_mid
                )
                if cc_result["status"] in ("filled", "partial_fill"):
                    prem = cc_result["premium_collected"]
                    cc_premium              += prem
                    h["cc_expiry"]           = expiry
                    h["cc_strike"]           = assignment_strike
                    h["cc_status"]           = "open"
                    h["cc_premium_collected"] = prem
                    log.info(f"  💰 CC premium collected: ${prem:,.0f}")
                else:
                    h["cc_status"] = "failed"
                    log.warning(f"  ⚠️  {ticker} CC sell failed — no covered call this week")

    finally:
        ib.disconnect()

    # ── Persist context for run_pipeline ─────────────────────
    state["wheel_holdings"] = holdings
    state["monday_context"] = {
        "skip_tickers":          skip_tickers,
        "freed_capital":         freed_capital,
        "cc_premium":            cc_premium,
        "stop_loss_realized_pnl": stop_loss_pnl,
        "updated":               datetime.now().isoformat()
    }
    _save_state(state)

    log.info("\n" + "=" * 65)
    log.info("📊 WHEEL CHECK SUMMARY")
    log.info(f"   Stop loss exits:   {len(skip_tickers)}  {skip_tickers or ''}")
    log.info(f"   Freed capital:     ${freed_capital:,.0f}")
    log.info(f"   Stop loss P&L:     ${stop_loss_pnl:,.0f}")
    log.info(f"   CC premium earned: ${cc_premium:,.0f}")
    log.info("=" * 65)

    return freed_capital, skip_tickers


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "detect":
        detect_assignments()
    else:
        freed, skip = run_wheel_check()
        print(f"\nFreed: ${freed:,.0f}  Skip: {skip}")
