"""
Wheel Strategy Manager

detect_assignments() — Friday 4:15PM PST
    Scan IBKR for stock positions created by put assignments.
    Persist to state.json["wheel_holdings"].

run_wheel_check() — Monday 9:55AM PST (runs before CSP pipeline)
    For each held stock, four-step evaluation:
      Step 1  Screener check: if ticker dropped from screener → sell at market
      Step 2  Option chain: find highest call strike >= assigned_strike
              where abs(delta) >= 0.20 (the "20-delta CC")
      Step 3  Decision: sell CC if viable strike found; else sell at market
      Step 4  Persist monday_context + wheel_activity to state.json

    Returns (freed_capital, skip_tickers) for run_pipeline to consume.
"""
import json
import logging
from datetime import datetime, timedelta
from ib_insync import IB, Stock, Option, LimitOrder, MarketOrder

from config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID_WHEEL, ACCOUNT
from screener import get_all_candidates

STATE_FILE       = "state.json"
MID_WAIT_SECS    = 120
BID_WAIT_SECS    = 120
MARKET_WAIT_SECS = 60
MARKET_POLL_SECS = 5
CC_DELTA_MIN     = 0.20   # minimum call delta required to sell a covered call
MAX_CC_STRIKES   = 25     # max option strikes to evaluate per holding

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("wheel_log.txt"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ── State ──────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── IBKR ───────────────────────────────────────────────────────

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


def _next_friday_expiry() -> str:
    today      = datetime.now().date()
    days_ahead = 4 - today.weekday()   # Monday=0 → days_ahead=4 (this Friday)
    if days_ahead <= 0:
        days_ahead += 7
    return (today + timedelta(days=days_ahead)).strftime("%Y%m%d")


# ── Option chain ───────────────────────────────────────────────

def _find_cc_strike(ib: IB, ticker: str, expiry: str,
                    assigned_strike: float) -> tuple | None:
    """
    Scan the IBKR call option chain for the highest strike >= assigned_strike
    on expiry where abs(delta) >= CC_DELTA_MIN.

    Call delta decreases monotonically as strike increases (more OTM → lower
    delta), so the highest qualifying strike is the closest to CC_DELTA_MIN
    from above — the "20-delta covered call."

    All market data streams are opened simultaneously and read after a single
    sleep, making this O(1) in wall-clock time regardless of how many strikes
    are checked.

    Returns (strike, delta, mid_price) or None if no viable strike found.
    """
    stock = Stock(ticker, "SMART", "USD")
    q_stock = ib.qualifyContracts(stock)
    if not q_stock:
        log.warning(f"  ⚠️  {ticker}: cannot qualify stock for option chain lookup")
        return None

    chains = ib.reqSecDefOptParams(ticker, "", "STK", q_stock[0].conId)
    if not chains:
        log.warning(f"  ⚠️  {ticker}: IBKR returned no option chain data")
        return None

    all_strikes: set[float] = set()
    for chain in chains:
        if expiry in chain.expirations:
            all_strikes.update(chain.strikes)

    if not all_strikes:
        log.warning(f"  ⚠️  {ticker}: expiry {expiry} not listed in option chain")
        return None

    candidates = sorted(s for s in all_strikes if s >= assigned_strike)
    if not candidates:
        log.warning(f"  ⚠️  {ticker}: no strikes >= ${assigned_strike:.2f}")
        return None

    candidates = candidates[:MAX_CC_STRIKES]
    log.info(f"  📊 {ticker}: scanning {len(candidates)} call strike(s) "
             f"[${candidates[0]:.2f}–${candidates[-1]:.2f}] on {expiry}")

    # Qualify all option contracts up front
    q_pairs: list[tuple[float, object]] = []
    for strike in candidates:
        opt = Option(ticker, expiry, strike, "C", "SMART", currency="USD")
        try:
            q = ib.qualifyContracts(opt)
            if q:
                q_pairs.append((strike, q[0]))
        except Exception:
            continue

    if not q_pairs:
        log.warning(f"  ⚠️  {ticker}: no call contracts qualified on {expiry}")
        return None

    # Open all market data streams simultaneously — one sleep covers all
    streams: dict[float, tuple[object, object]] = {}
    for strike, contract in q_pairs:
        data = ib.reqMktData(contract, genericTickList="13", snapshot=False)
        streams[strike] = (contract, data)

    ib.sleep(5)

    # Read delta and mid from each stream, then cancel
    results: list[tuple[float, float, float | None]] = []
    for strike, (contract, data) in streams.items():
        ib.cancelMktData(contract)

        delta = None
        for attr in ("modelGreeks", "lastGreeks"):
            g = getattr(data, attr, None)
            if g is not None:
                d = getattr(g, "delta", None)
                if d is not None and not _is_nan(d):
                    delta = d
                    break

        if delta is None:
            continue

        bid = data.bid
        ask = data.ask
        mid = round((bid + ask) / 2, 2) \
              if (not _is_nan(bid) and not _is_nan(ask) and bid > 0 and ask > 0) \
              else None
        results.append((strike, abs(delta), mid))

    ib.sleep(0.5)

    if not results:
        log.warning(f"  ⚠️  {ticker}: no delta data returned for any call strike")
        return None

    results.sort(key=lambda x: x[0])  # ascending by strike

    log.info(f"  {'Strike':>8}  {'Delta':>7}  {'Mid':>8}")
    for strike, delta, mid in results:
        flag    = "✅" if delta >= CC_DELTA_MIN else "❌"
        mid_str = f"${mid:.2f}" if mid else "?"
        log.info(f"  ${strike:>7.2f}  {delta:>6.3f}  {mid_str:>8}  {flag}")

    # Highest qualifying strike (delta closest to CC_DELTA_MIN from above)
    viable = [(s, d, m) for s, d, m in results if d >= CC_DELTA_MIN]
    if not viable:
        log.info(f"  ❌ No call strike with delta ≥ {CC_DELTA_MIN:.2f} available")
        return None

    return viable[-1]   # (strike, delta, mid)


# ── Orders ─────────────────────────────────────────────────────

def _sell_stock_market(ib: IB, ticker: str, shares: int, reason: str) -> dict:
    contract  = Stock(ticker, "SMART", "USD")
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        log.error(f"  ❌ Cannot qualify {ticker} for sale")
        return {"status": "failed", "proceeds": 0.0, "fill_price": None}

    log.info(f"  📤 SELL {shares} shares {ticker} at market  [{reason}]")
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
            log.info(f"  ✅ Sold: {shares}x {ticker} @ ${fill:.2f} = ${proceeds:,.0f}")
            return {"status": "filled", "fill_price": fill, "proceeds": proceeds}
        log.info(f"  ⏳ Sell status: {status} after {elapsed}s")

    log.error(f"  ❌ Share sale timed out for {ticker} — MANUAL ACTION REQUIRED")
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
        log.info(f"  📤 {label}: SELL {num_contracts}x {ticker} CALL "
                 f"${strike:.2f} @ ${price:.2f}")
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

    log.info(f"  📤 Market order: SELL {num_contracts}x {ticker} CALL ${strike:.2f}")
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
    against known wheel_holdings. New assignments are added with the
    assigned strike looked up from that week's state.json positions.
    """
    log.info("\n" + "=" * 65)
    log.info(f"🔍 FRIDAY ASSIGNMENT DETECTION — "
             f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 65)

    state             = _load_state()
    existing_holdings = {h["ticker"]: h for h in state.get("wheel_holdings", [])}
    strike_lookup     = {p["ticker"]: p["strike"] for p in state.get("positions", [])}

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
            h           = existing_holdings[ticker]
            h["shares"] = shares
            h["last_checked"] = datetime.now().isoformat()
            log.info(f"  ✅ {ticker}: {shares} shares (existing — updated count)")
        else:
            assigned_strike = strike_lookup.get(ticker, 0.0)
            if assigned_strike == 0.0:
                log.warning(f"  ⚠️  {ticker}: strike not found in state — "
                             f"set assigned_strike manually in state.json")
            h = {
                "ticker":             ticker,
                "shares":             shares,
                "assigned_strike":    assigned_strike,
                "assignment_date":    datetime.now().date().isoformat(),
                "current_cc_strike":  None,
                "current_cc_expiry":  None,
                "current_cc_premium": 0.0,
                "weeks_held":         0,
                "cc_status":          "pending",
                "current_price":      None,
                "last_checked":       datetime.now().isoformat(),
            }
            log.info(f"  🆕 NEW ASSIGNMENT: {ticker}  {shares} shares  "
                     f"@ ${assigned_strike:.2f}")
        updated.append(h)

    for ticker in existing_holdings:
        if ticker not in stock_positions:
            log.info(f"  📤 {ticker}: no longer held (called away or sold)")

    state["wheel_holdings"] = updated
    _save_state(state)
    log.info(f"\n💾 Saved {len(updated)} wheel holding(s) to state.json")
    log.info("=" * 65)


def run_wheel_check() -> tuple[float, list]:
    """
    Monday 9:55AM PST — four-step evaluation for each held stock:

      Step 1  Screener check — if ticker no longer passes screener filters,
              sell all shares at market and free capital.
      Step 2  Option chain — query IBKR for call strikes >= assigned_strike
              on the nearest Friday; collect delta for each.
      Step 3  Decision — sell the highest-delta (≥ 0.20) call as a covered
              call. If no such strike exists, sell shares at market.
      Step 4  Persist monday_context and wheel_activity to state.json.

    Returns (freed_capital, skip_tickers) consumed by run_pipeline.
    """
    log.info("\n" + "=" * 65)
    log.info(f"🔄 MONDAY WHEEL CHECK — "
             f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 65)

    state    = _load_state()
    holdings = state.get("wheel_holdings", [])

    empty_context = {
        "skip_tickers": [], "freed_capital": 0.0, "cc_premium": 0.0,
        "shares_sold_pnl": 0.0, "wheel_activity": [],
        "updated": datetime.now().isoformat()
    }

    if not holdings:
        log.info("📭 No wheel holdings — nothing to do")
        state["monday_context"] = empty_context
        _save_state(state)
        return 0.0, []

    # Screener candidates (Step 1 prerequisite)
    log.info("\n📡 Fetching screener candidates...")
    screener_tickers = get_all_candidates()
    if screener_tickers:
        log.info(f"  ✅ {len(screener_tickers)} ticker(s) pass screener filters")
    else:
        log.warning("  ⚠️  Screener returned 0 tickers — API may be down")
        log.warning("  Skipping screener check; will attempt CCs for all holdings")

    expiry          = _next_friday_expiry()
    freed_capital   = 0.0
    skip_tickers    = []
    cc_premium      = 0.0
    shares_sold_pnl = 0.0
    wheel_activity  = []

    ib = _connect()

    try:
        for h in holdings:
            ticker          = h["ticker"]
            shares          = h.get("shares", 0)
            assigned_strike = h.get("assigned_strike", 0.0)
            weeks_held      = h.get("weeks_held", 0) + 1
            h["weeks_held"] = weeks_held
            h["last_checked"] = datetime.now().isoformat()

            log.info(f"\n  ── {ticker}  {shares} shares  "
                     f"@ ${assigned_strike:.2f}  week {weeks_held} ──")

            if shares <= 0:
                log.info(f"  ⏭️  {ticker}: 0 shares — skipping")
                continue

            # ── Step 1: Screener check ────────────────────────
            if screener_tickers and ticker not in screener_tickers:
                log.warning(f"  🚫 {ticker}: dropped from screener — selling shares")
                result = _sell_stock_market(ib, ticker, shares, "dropped_screener")
                if result["status"] == "filled":
                    proceeds = result["proceeds"]
                    realized = round(proceeds - (assigned_strike * shares), 2)
                    freed_capital   += proceeds
                    shares_sold_pnl += realized
                    skip_tickers.append(ticker)
                    h["shares"]    = 0
                    h["cc_status"] = "sold_dropped_screener"
                    wheel_activity.append({
                        "ticker":       ticker,
                        "action":       "sold_dropped_screener",
                        "shares":       shares,
                        "fill_price":   result["fill_price"],
                        "proceeds":     proceeds,
                        "realized_pnl": realized,
                    })
                    log.info(f"  📊 P&L: ${realized:,.0f}  Freed: ${proceeds:,.0f}")
                else:
                    log.error(f"  ❌ Sale FAILED for {ticker} — MANUAL ACTION REQUIRED")
                continue

            log.info(f"  ✅ {ticker} on screener — querying option chain")

            # ── Step 2: Find best CC strike ───────────────────
            cc_info = _find_cc_strike(ib, ticker, expiry, assigned_strike)

            # ── Step 3: Decision ──────────────────────────────
            if cc_info is None:
                log.warning(f"  ❌ {ticker}: no call strike with delta ≥ "
                             f"{CC_DELTA_MIN:.2f} — selling shares")
                result = _sell_stock_market(ib, ticker, shares, "no_viable_cc")
                if result["status"] == "filled":
                    proceeds = result["proceeds"]
                    realized = round(proceeds - (assigned_strike * shares), 2)
                    freed_capital   += proceeds
                    shares_sold_pnl += realized
                    skip_tickers.append(ticker)
                    h["shares"]    = 0
                    h["cc_status"] = "sold_no_viable_cc"
                    wheel_activity.append({
                        "ticker":       ticker,
                        "action":       "sold_no_viable_cc",
                        "shares":       shares,
                        "fill_price":   result["fill_price"],
                        "proceeds":     proceeds,
                        "realized_pnl": realized,
                    })
                    log.info(f"  📊 P&L: ${realized:,.0f}  Freed: ${proceeds:,.0f}")
                else:
                    log.error(f"  ❌ Sale FAILED for {ticker} — MANUAL ACTION REQUIRED")
                continue

            cc_strike, cc_delta, cc_mid = cc_info
            mid_display = f"${cc_mid:.2f}" if cc_mid else "?"
            log.info(f"  🎯 Selling CC: ${cc_strike:.2f} strike  "
                     f"delta={cc_delta:.3f}  mid={mid_display}")

            cc_opt = Option(ticker, expiry, cc_strike, "C", "SMART", currency="USD")
            try:
                qualified = ib.qualifyContracts(cc_opt)
            except Exception as e:
                log.error(f"  ❌ Cannot qualify CC for {ticker}: {e}")
                h["cc_status"] = "failed"
                continue

            if not qualified:
                log.warning(f"  ⚠️  {ticker}: CC contract did not qualify")
                h["cc_status"] = "failed"
                continue

            ref_mid      = cc_mid if (cc_mid and cc_mid > 0) else 0.50
            order_result = _sell_cc_with_escalation(
                ib, qualified[0], shares, ticker, cc_strike, ref_mid
            )

            if order_result["status"] in ("filled", "partial_fill"):
                prem = order_result["premium_collected"]
                cc_premium             += prem
                h["current_cc_strike"]  = cc_strike
                h["current_cc_expiry"]  = expiry
                h["current_cc_premium"] = prem
                h["cc_status"]          = "open"
                wheel_activity.append({
                    "ticker":     ticker,
                    "action":     "cc_opened",
                    "cc_strike":  cc_strike,
                    "cc_delta":   round(cc_delta, 3),
                    "cc_premium": prem,
                    "cc_expiry":  expiry,
                })
                log.info(f"  💰 CC premium: ${prem:,.0f}")
            else:
                h["cc_status"] = "failed"
                wheel_activity.append({
                    "ticker": ticker, "action": "cc_failed", "cc_strike": cc_strike
                })
                log.warning(f"  ⚠️  {ticker}: CC order failed — no CC this week")

    finally:
        ib.disconnect()

    # ── Step 4: Persist to state.json ────────────────────────
    state["wheel_holdings"] = holdings
    state["monday_context"] = {
        "skip_tickers":    skip_tickers,
        "freed_capital":   freed_capital,
        "cc_premium":      cc_premium,
        "shares_sold_pnl": shares_sold_pnl,
        "wheel_activity":  wheel_activity,
        "updated":         datetime.now().isoformat()
    }
    _save_state(state)

    exits   = [a for a in wheel_activity if "sold" in a["action"]]
    ccs     = [a for a in wheel_activity if a["action"] == "cc_opened"]
    cc_summ = "  ".join(
        f"{a['ticker']} ${a['cc_strike']:.0f} δ{a['cc_delta']:.2f}" for a in ccs
    )

    log.info("\n" + "=" * 65)
    log.info("📊 WHEEL CHECK SUMMARY")
    log.info(f"   Shares sold:      {len(exits)}  "
             f"{[a['ticker'] for a in exits] or ''}")
    log.info(f"   CCs opened:       {len(ccs)}  {cc_summ or ''}")
    log.info(f"   Freed capital:    ${freed_capital:,.0f}")
    log.info(f"   Shares sold P&L:  ${shares_sold_pnl:,.0f}")
    log.info(f"   CC premium:       ${cc_premium:,.0f}")
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
