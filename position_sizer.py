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
        "ticker":           target["ticker"],
        "strike":           strike,
        "premium":          target["put_20d_premium"],
        "expiry":           target["expiry"],
        "contracts":        contracts,
        "capital_used":     capital_used,
        "premium_total":    premium_total,
        "yield_pct":        yield_pct,
        "delta":            target["put_20d_delta"],
        "iv_atm":           target["iv_atm"],
        "sector":           target.get("sector", ""),
        "latest_price":     target["latest_price"],
        "buffer_pct":       target["_buffer_pct"] * 100,
        "buyzone":          target.get("buyzone_flag", False),
        "days_to_earnings": target.get("days_to_earnings"),
    }

def size_all(targets: list, budget: float = None) -> list:
    remaining_budget = budget if budget is not None else TOTAL_FUND_BUDGET
    effective_budget = remaining_budget

    # Pass 1: size positions #2–#5 at TARGET from targets[1:]
    rest_sized   = []
    target_index = 1
    while len(rest_sized) < NUM_POSITIONS - 1 and target_index < len(targets):
        result = size_position(targets[target_index], remaining_budget, is_last=False)
        if result:
            rest_sized.append(result)
            remaining_budget -= result["capital_used"]
        target_index += 1

    # Pass 2: allocate remainder to #1 (highest-scored), capped at MAX_PER_POSITION
    top_sized = []
    if targets:
        result = size_position(targets[0], remaining_budget, is_last=True)
        if result:
            top_sized.append(result)
            remaining_budget -= result["capital_used"]

    sized = top_sized + rest_sized

    print("\n💼 Position Sizing Summary")
    print(f"   Fund Budget: ${effective_budget:,.0f}  |  Target: ${TARGET_PER_POSITION:,.0f}/pos (#2–5)  |  Max #1: ${MAX_PER_POSITION:,.0f}")
    print("=" * 65)

    total_capital = 0
    total_premium = 0

    for i, p in enumerate(sized, 1):
        bz       = "✅" if p["buyzone"] else "❌"
        last_tag = " ← remainder (max $70K)" if i == 1 else ""
        over     = " ⚡" if p["capital_used"] > TARGET_PER_POSITION else ""
        print(f"\n  #{i} {p['ticker']}  (Buyzone: {bz}){last_tag}")
        print(f"    Strike:      ${p['strike']:.2f}")
        print(f"    Contracts:   {p['contracts']}")
        print(f"    Capital:     ${p['capital_used']:,.0f}{over}")
        print(f"    Premium:     ${p['premium_total']:,.0f}  ({p['yield_pct']:.2f}%)")
        print(f"    Buffer:      {p['buffer_pct']:.2f}%")
        total_capital += p["capital_used"]
        total_premium += p["premium_total"]

    leftover = effective_budget - total_capital
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
