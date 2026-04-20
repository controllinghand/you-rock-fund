import math
from config import (
    TARGET_PER_POSITION,
    MAX_PER_POSITION,
    TOTAL_FUND_BUDGET,
    NUM_POSITIONS
)

def size_position(target: dict, available_capital: float, is_last: bool = False) -> dict | None:
    strike            = target["put_20d_strike"]
    cash_per_contract = strike * 100

    if cash_per_contract > MAX_PER_POSITION:
        print(f"  ⚠️  {target['ticker']} skipped — 1 contract = ${cash_per_contract:,.0f} (exceeds ${MAX_PER_POSITION:,.0f} max)")
        return None

    if cash_per_contract > available_capital:
        print(f"  ⚠️  {target['ticker']} skipped — insufficient remaining capital (${available_capital:,.0f})")
        return None

    if is_last:
        # Last position: maximize contracts up to MAX_PER_POSITION
        budget    = min(available_capital, MAX_PER_POSITION)
        contracts = math.floor(budget / cash_per_contract)
    else:
        # Normal positions: closest to TARGET without exceeding it
        contracts = math.floor(TARGET_PER_POSITION / cash_per_contract)
        if contracts < 1:
            contracts = 1

    capital_used  = contracts * cash_per_contract
    premium_total = contracts * target["put_20d_premium"] * 100
    yield_pct     = target["put_20d_premium_pct"] * 100

    return {
        "ticker":        target["ticker"],
        "strike":        strike,
        "premium":       target["put_20d_premium"],
        "expiry":        target["expiry"],
        "contracts":     contracts,
        "capital_used":  capital_used,
        "premium_total": premium_total,
        "yield_pct":     yield_pct,
        "delta":         target["put_20d_delta"],
        "iv_atm":        target["iv_atm"],
        "sector":        target.get("sector", ""),
        "latest_price":  target["latest_price"],
        "buffer_pct":    target["_buffer_pct"] * 100,
        "buyzone":       target.get("buyzone_flag", False),
    }

def size_all(targets: list) -> list:
    sized            = []
    remaining_budget = TOTAL_FUND_BUDGET
    target_index     = 0

    while len(sized) < NUM_POSITIONS and target_index < len(targets):
        target  = targets[target_index]
        is_last = (len(sized) == NUM_POSITIONS - 1)
        result  = size_position(target, remaining_budget, is_last=is_last)

        if result:
            sized.append(result)
            remaining_budget -= result["capital_used"]

        target_index += 1

    print("\n💼 Position Sizing Summary")
    print(f"   Fund Budget: ${TOTAL_FUND_BUDGET:,.0f}  |  Target: ${TARGET_PER_POSITION:,.0f}/pos  |  Max last pos: ${MAX_PER_POSITION:,.0f}")
    print("=" * 65)

    total_capital = 0
    total_premium = 0

    for i, p in enumerate(sized, 1):
        bz       = "✅" if p["buyzone"] else "❌"
        last_tag = " ← remainder (max $70K)" if i == len(sized) else ""
        over     = " ⚡" if p["capital_used"] > TARGET_PER_POSITION else ""
        print(f"\n  #{i} {p['ticker']}  (Buyzone: {bz}){last_tag}")
        print(f"    Strike:      ${p['strike']:.2f}")
        print(f"    Contracts:   {p['contracts']}")
        print(f"    Capital:     ${p['capital_used']:,.0f}{over}")
        print(f"    Premium:     ${p['premium_total']:,.0f}  ({p['yield_pct']:.2f}%)")
        print(f"    Buffer:      {p['buffer_pct']:.2f}%")
        total_capital += p["capital_used"]
        total_premium += p["premium_total"]

    leftover = TOTAL_FUND_BUDGET - total_capital
    print("\n" + "=" * 65)
    print(f"  Positions Filled:       {len(sized)} / {NUM_POSITIONS}")
    print(f"  Total Capital Deployed: ${total_capital:,.0f}")
    print(f"  Undeployed Cash:        ${leftover:,.0f}")
    print(f"  Total Premium Income:   ${total_premium:,.0f}")
    if total_capital > 0:
        print(f"  Blended Weekly Yield:   {(total_premium/total_capital)*100:.2f}%")
    print("=" * 65)

    return sized

if __name__ == "__main__":
    from screener import get_top_targets
    targets = get_top_targets(10)
    size_all(targets)
