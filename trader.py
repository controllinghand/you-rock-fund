import json
import logging
import math
from datetime import datetime, timezone
from ib_insync import IB, Option, LimitOrder, MarketOrder

from config import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID, ACCOUNT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("trade_log.txt"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

MAX_SPREAD_PCT    = 0.20
MIN_OPEN_INTEREST = 100
MID_WAIT_SECS     = 120
BID_WAIT_SECS     = 120
DRY_RUN           = False   # ← flip to False when ready to go live


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
            # Simulate with screener premium for dry run testing
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

    log.info(f"  📤 Market order: SELL {contracts}x {ticker} PUT")
    order = MarketOrder("SELL", contracts, account=ACCOUNT, tif="DAY")
    trade = ib.placeOrder(contract, order)
    ib.sleep(5)
    if trade.orderStatus.status == "Filled":
        fill = trade.orderStatus.avgFillPrice
        result.update({
            "status": "filled", "fill_price": fill,
            "order_type": "market",
            "premium_collected": round(contracts * fill * 100, 2)
        })
    else:
        log.error(f"  ❌ Could not fill {ticker} — manual review needed")
        result["status"] = "failed"
    return result


def execute_positions(sized_positions: list) -> list:
    log.info("\n" + "=" * 65)
    log.info(f"🚀 YOU ROCK VOLATILITY INCOME FUND — Execution Start")
    log.info(f"   Mode: {'🧪 DRY RUN' if DRY_RUN else '🔴 LIVE'}")
    log.info(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"   Positions: {len(sized_positions)}")
    log.info("=" * 65)

    ib      = connect()
    results = []

    for i, pos in enumerate(sized_positions, 1):
        ticker    = pos["ticker"]
        strike    = pos["strike"]
        expiry    = pos["expiry"]
        contracts = pos["contracts"]
        premium   = pos["premium"]

        log.info(f"\n[{i}/{len(sized_positions)}] {ticker} — "
                 f"{contracts} contracts @ ${strike} strike")

        contract = get_option_contract(ib, ticker, strike, expiry)
        if not contract:
            results.append({"ticker": ticker, "status": "failed_qualify"})
            continue

        mkt = get_market_data(ib, contract, screener_premium=premium)
        if not mkt:
            results.append({"ticker": ticker, "status": "failed_market_data"})
            continue

        if not check_liquidity(mkt, ticker):
            results.append({"ticker": ticker, "status": "skipped_liquidity"})
            continue

        result = place_order_with_escalation(ib, contract, contracts, mkt, ticker)
        results.append(result)

        if i < len(sized_positions):
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

    log.info(f"\n  Total Premium Collected: ${total_premium:,.0f}")
    log.info("=" * 65)

    with open("state.json", "w") as f:
        json.dump({
            "run_date":      datetime.now().isoformat(),
            "positions":     sized_positions,
            "executions":    results,
            "total_premium": total_premium
        }, f, indent=2)
    log.info("💾 Results saved to state.json")

    return results


if __name__ == "__main__":
    from screener import get_top_targets
    from position_sizer import size_all
    targets   = get_top_targets(10)
    positions = size_all(targets)
    execute_positions(positions)
