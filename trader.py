import json
import logging
import math
from datetime import datetime, timezone
from ib_insync import IB, Option, LimitOrder, MarketOrder

from config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID, ACCOUNT, NUM_POSITIONS, TOTAL_FUND_BUDGET

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("trade_log.txt"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

MAX_SPREAD_PCT      = 0.20
MIN_OPEN_INTEREST   = 100
MID_WAIT_SECS       = 120
BID_WAIT_SECS       = 120
MARKET_WAIT_SECS    = 60    # total polling window for market orders
MARKET_POLL_SECS    = 5     # check every N seconds
DRY_RUN             = False


def connect() -> IB:
    ib = IB()
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
    # Request delayed data globally — works without market data subscription
    ib.reqMarketDataType(3)  # 1=live, 2=frozen, 3=delayed, 4=delayed-frozen
    log.info(f"✅ Connected to IBKR — Account: {ib.managedAccounts()}")
    log.info(f"   Market data type: DELAYED (type 3)")
    return ib


def parse_expiry(expiry_str: str) -> str:
    dt = datetime.strptime(expiry_str, "%a, %d %b %Y %H:%M:%S %Z")
    return dt.strftime("%Y%m%d")


def get_option_contract(ib: IB, ticker: str, strike: float, expiry_str: str):
    expiry   = parse_expiry(expiry_str)
    contract = Option(ticker, expiry, strike, "P", "SMART", currency="USD")
    try:
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            log.warning(f"⚠️  Could not qualify: {ticker} {strike}P {expiry}")
            return None
        log.info(f"✅ Qualified: {ticker} {strike}P {expiry}")
        return qualified[0]
    except Exception as e:
        log.error(f"Error qualifying {ticker}: {e}")
        return None


def is_nan(val) -> bool:
    try:
        return val != val  # nan != nan is True
    except:
        return True


def get_market_data(ib: IB, contract, screener_premium: float) -> dict | None:
    """
    Request delayed market data (type 3 — no subscription needed).
    Falls back to screener premium if market is closed.
    """
    ticker = ib.reqMktData(contract, genericTickList="101", snapshot=False)
    ib.sleep(4)

    bid = ticker.bid
    ask = ticker.ask
    oi  = ticker.putOpenInterest or ticker.callOpenInterest or 0

    ib.cancelMktData(contract)
    ib.sleep(0.5)

    # Market is closed or no delayed data available
    if is_nan(bid) or is_nan(ask) or bid <= 0 or ask <= 0:
        log.warning(f"  ⏰ No market data for {contract.symbol} — market likely closed")
        if DRY_RUN:
            simulated_bid = round(screener_premium * 0.90, 2)
            simulated_ask = round(screener_premium * 1.10, 2)
            simulated_mid = screener_premium
            log.info(f"  🧪 Simulating: Bid ${simulated_bid}  Ask ${simulated_ask}  "
                     f"Mid ${simulated_mid}  (from screener)")
            return {
                "bid": simulated_bid,
                "ask": simulated_ask,
                "mid": simulated_mid,
                "spread_pct": 0.20,
                "open_interest": 999,
                "simulated": True
            }
        return None

    mid        = round((bid + ask) / 2, 2)
    spread     = ask - bid
    spread_pct = spread / mid if mid > 0 else 999

    log.info(f"  {contract.symbol} — Bid: ${bid:.2f}  Ask: ${ask:.2f}  "
             f"Mid: ${mid:.2f}  Spread: {spread_pct*100:.1f}%  OI: {oi}")

    return {
        "bid": bid, "ask": ask, "mid": mid,
        "spread_pct": spread_pct,
        "open_interest": oi,
        "simulated": False
    }


def check_liquidity(mkt: dict, ticker: str) -> bool:
    if mkt.get("simulated"):
        return True  # skip liquidity check on simulated data
    if mkt["spread_pct"] > MAX_SPREAD_PCT:
        log.warning(f"⚠️  {ticker} spread too wide: {mkt['spread_pct']*100:.1f}% — skipping")
        return False
    if mkt["open_interest"] < MIN_OPEN_INTEREST:
        log.warning(f"⚠️  {ticker} OI too low: {mkt['open_interest']} — skipping")
        return False
    return True


def place_order_with_escalation(ib: IB, contract, contracts: int,
                                 mkt: dict, ticker: str) -> dict:
    result = {
        "ticker": ticker, "contracts": contracts,
        "status": "unfilled", "fill_price": None,
        "order_type": None, "premium_collected": 0,
        "simulated": mkt.get("simulated", False),
        "timestamp": datetime.now().isoformat()
    }

    if DRY_RUN:
        tag = " (simulated data)" if mkt.get("simulated") else " (live data)"
        log.info(f"  🧪 DRY RUN{tag} — would sell {contracts}x {ticker} "
                 f"put @ mid ${mkt['mid']:.2f}")
        result.update({
            "status": "dry_run",
            "fill_price": mkt["mid"],
            "order_type": "limit_mid",
            "premium_collected": round(contracts * mkt["mid"] * 100, 2)
        })
        return result

    def try_limit(price: float, label: str, wait: int) -> bool:
        log.info(f"  📤 {label}: SELL {contracts}x {ticker} PUT @ ${price:.2f}")
        order = LimitOrder("SELL", contracts, price, account=ACCOUNT, tif="DAY")
        trade = ib.placeOrder(contract, order)
        ib.sleep(wait)
        if trade.orderStatus.status == "Filled":
            fill = trade.orderStatus.avgFillPrice
            log.info(f"  ✅ Filled {ticker} @ ${fill:.2f}")
            result.update({
                "status": "filled", "fill_price": fill,
                "order_type": label,
                "premium_collected": round(contracts * fill * 100, 2)
            })
            return True
        log.info(f"  ⏳ {label} unfilled — escalating...")
        ib.cancelOrder(trade.order)
        ib.sleep(1)
        return False

    if try_limit(mkt["mid"], "limit_mid", MID_WAIT_SECS): return result
    if try_limit(mkt["bid"], "limit_bid", BID_WAIT_SECS): return result

    # Market order with polling loop — options can partially fill across multiple exchanges
    log.info(f"  📤 Market order: SELL {contracts}x {ticker} PUT")
    order = MarketOrder("SELL", contracts, account=ACCOUNT, tif="DAY")
    trade = ib.placeOrder(contract, order)

    elapsed = 0
    while elapsed < MARKET_WAIT_SECS:
        ib.sleep(MARKET_POLL_SECS)
        elapsed += MARKET_POLL_SECS
        status      = trade.orderStatus.status
        filled_qty  = trade.orderStatus.filled
        remaining   = trade.orderStatus.remaining

        if status == "Filled" or (remaining == 0 and filled_qty > 0):
            fill = trade.orderStatus.avgFillPrice
            log.info(f"  ✅ Market order filled {ticker} @ ${fill:.2f} "
                     f"({filled_qty} contracts in {elapsed}s)")
            result.update({
                "status": "filled",
                "fill_price": fill,
                "order_type": "market",
                "premium_collected": round(filled_qty * fill * 100, 2)
            })
            return result

        if status == "PartiallyFilled" and filled_qty > 0:
            log.info(f"  ⏳ Partial: {filled_qty}/{contracts} filled after {elapsed}s — waiting...")
        else:
            log.info(f"  ⏳ Market status: {status} after {elapsed}s — waiting...")

    # Accept whatever partial fill arrived before timeout
    final_qty = trade.orderStatus.filled
    if final_qty > 0:
        fill = trade.orderStatus.avgFillPrice
        log.warning(f"  ⚠️  Partial fill accepted: {final_qty}/{contracts} @ ${fill:.2f}")
        result.update({
            "status": "partial_fill",
            "fill_price": fill,
            "order_type": "market",
            "premium_collected": round(final_qty * fill * 100, 2)
        })
    else:
        log.error(f"  ❌ Could not fill {ticker} — manual review needed")
        result["status"] = "failed"

    return result


def execute_positions(sized_positions: list, extra_targets: list = None) -> list:
    """
    Execute up to NUM_POSITIONS fills. If a candidate fails qualification,
    market data, or liquidity, the next-ranked screener target is sized and
    attempted automatically until the fill target is met or candidates are
    exhausted.

    extra_targets: full ranked screener list (raw dicts from screener).
    """
    from position_sizer import size_position

    log.info("\n" + "=" * 65)
    log.info(f"🚀 YOU ROCK VOLATILITY INCOME FUND — Execution Start")
    log.info(f"   Mode: {'🧪 DRY RUN' if DRY_RUN else '🔴 LIVE'}")
    log.info(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"   Primary candidates: {len(sized_positions)}  |  "
             f"Fallback pool: {len(extra_targets or [])}")
    log.info("=" * 65)

    ib              = connect()
    results         = []
    filled_count    = 0
    capital_deployed = 0
    attempted       = set()

    # Work through pre-sized primaries first, then size extras on demand
    primary    = list(sized_positions)
    extras     = list(extra_targets or [])
    extra_ptr  = 0

    def next_candidate():
        nonlocal extra_ptr
        while primary:
            p = primary.pop(0)
            if p["ticker"] not in attempted:
                return p
        while extra_ptr < len(extras):
            raw = extras[extra_ptr]
            extra_ptr += 1
            if raw["ticker"] in attempted:
                continue
            is_last  = (filled_count == NUM_POSITIONS - 1)
            remaining = TOTAL_FUND_BUDGET - capital_deployed
            p = size_position(raw, remaining, is_last=is_last)
            if p:
                log.info(f"  🔄 Fallback candidate: {p['ticker']} "
                         f"({p['contracts']}x @ ${p['strike']:.2f})")
                return p
        return None

    slot = 0
    while filled_count < NUM_POSITIONS:
        pos = next_candidate()
        if pos is None:
            log.warning(f"⚠️  No more candidates — {filled_count}/{NUM_POSITIONS} positions filled")
            break

        slot    += 1
        ticker   = pos["ticker"]
        attempted.add(ticker)
        strike   = pos["strike"]
        expiry   = pos["expiry"]
        contracts = pos["contracts"]
        premium  = pos["premium"]

        log.info(f"\n[attempt {slot}  fill {filled_count + 1}/{NUM_POSITIONS}] "
                 f"{ticker} — {contracts} contracts @ ${strike:.2f} strike")

        contract = get_option_contract(ib, ticker, strike, expiry)
        if not contract:
            log.info(f"  🔄 {ticker} — qualify failed, trying next candidate")
            results.append({"ticker": ticker, "status": "failed_qualify"})
            continue

        mkt = get_market_data(ib, contract, screener_premium=premium)
        if not mkt:
            log.info(f"  🔄 {ticker} — no market data, trying next candidate")
            results.append({"ticker": ticker, "status": "failed_market_data"})
            continue

        if not check_liquidity(mkt, ticker):
            log.info(f"  🔄 {ticker} — failed liquidity, trying next candidate")
            results.append({"ticker": ticker, "status": "skipped_liquidity"})
            continue

        result = place_order_with_escalation(ib, contract, contracts, mkt, ticker)
        results.append(result)

        if result["status"] in ("filled", "dry_run", "partial_fill"):
            filled_count     += 1
            capital_deployed += pos["capital_used"]
        else:
            log.info(f"  🔄 {ticker} — order failed, trying next candidate")

        if filled_count < NUM_POSITIONS:
            ib.sleep(3)

    ib.disconnect()

    # ── Summary ───────────────────────────────────────────────
    log.info("\n" + "=" * 65)
    log.info("📊 EXECUTION SUMMARY")
    log.info("=" * 65)

    total_premium = 0
    for r in results:
        status  = r.get("status", "unknown")
        fill    = r.get("fill_price")
        prem    = r.get("premium_collected", 0)
        otype   = r.get("order_type", "")
        sim_tag = " [simulated]" if r.get("simulated") else ""
        total_premium += prem
        fill_str = f"@ ${fill:.2f} via {otype} — ${prem:,.0f}{sim_tag}" if fill else ""
        log.info(f"  {r['ticker']:6s}  {status:20s}  {fill_str}")

    log.info(f"\n  Fills: {filled_count}/{NUM_POSITIONS}  |  "
             f"Total Premium: ${total_premium:,.0f}")
    log.info("=" * 65)

    with open("state.json", "w") as f:
        json.dump({
            "run_date":      datetime.now().isoformat(),
            "positions":     sized_positions,
            "executions":    results,
            "filled_count":  filled_count,
            "total_premium": total_premium
        }, f, indent=2)
    log.info("💾 Results saved to state.json")

    return results


if __name__ == "__main__":
    from screener import get_top_targets
    from position_sizer import size_all
    all_targets = get_top_targets(10)
    positions   = size_all(all_targets)
    execute_positions(positions, extra_targets=all_targets)
