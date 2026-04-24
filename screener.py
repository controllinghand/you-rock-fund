import requests
from datetime import datetime, timezone
from config import RENDER_URL as URL, RENDER_SECRET as SECRET

PARAMS = {
    "secret": SECRET,
    "iv_min_atm": 0.40,
    "market_cap_min": 10000000000,
    "min_star_rating": 0,
    "expiry_days": 7,
    "min_target_premium_pct": 0.01,
    "earnings_days_hide": 7,
    "earnings_recent_hide": 0,
    "hide_red": True
}

# ── Hard filters ──────────────────────────────────────────────
MAX_DELTA           = 0.21
MIN_BUFFER_PCT      = 0.05
MIN_BUFFER_PRIORITY = 0.10
MIN_DAYS_TO_EXPIRY  = 3   # Mon→Fri = 3 UTC calendar days; 4 fails Monday execution

def score_target(row: dict) -> float:
    premium_pct  = row.get("put_20d_premium_pct", 0)
    buffer_pct   = row["_buffer_pct"]
    iv_atm       = row.get("iv_atm", 0)
    buyzone      = 1.10 if row.get("buyzone_flag") else 1.0

    buffer_bonus = 1.5 if buffer_pct >= MIN_BUFFER_PRIORITY else 1.0

    return (
        (0.50 * buffer_pct * buffer_bonus) +
        (0.35 * premium_pct * buyzone) +
        (0.15 * (iv_atm / 10))
    )

def get_top_targets(n=5):
    print(f"\n📡 Fetching CSP targets from Render API...")
    response = requests.get(URL, params=PARAMS, timeout=60)
    response.raise_for_status()

    data = response.json()
    rows = data.get("rows", [])
    print(f"✅ {len(rows)} candidates returned")

    # ── Filter 1: wheel-ready ─────────────────────────────────
    rows = [r for r in rows if r.get("wheel_fit") == "Wheel-ready"]
    print(f"🔧 {len(rows)} wheel-ready candidates")

    # ── Filter 2: must expire at least 4 days out ─────────────
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    def days_to_expiry(r):
        try:
            exp = datetime.strptime(r["expiry"], "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
            return (exp - today).days
        except:
            return 99
    before = len(rows)
    rows = [r for r in rows if days_to_expiry(r) >= MIN_DAYS_TO_EXPIRY]
    print(f"📅 {len(rows)} passed expiry filter (removed {before - len(rows)} expiring too soon)")

    # ── Filter 3: delta ≤ 0.21 ────────────────────────────────
    before = len(rows)
    rows = [r for r in rows if abs(r.get("put_20d_delta", -1)) <= MAX_DELTA]
    print(f"📐 {len(rows)} passed delta filter (removed {before - len(rows)})")

    # ── Filter 4: buffer ≥ 5% ─────────────────────────────────
    before = len(rows)
    for r in rows:
        r["_buffer_pct"] = (r["latest_price"] - r["put_20d_strike"]) / r["latest_price"]
    rows = [r for r in rows if r["_buffer_pct"] >= MIN_BUFFER_PCT]
    print(f"🛡️  {len(rows)} passed buffer filter (removed {before - len(rows)})")

    # ── Score ─────────────────────────────────────────────────
    for r in rows:
        r["_score"] = score_target(r)

    rows.sort(key=lambda r: r["_score"], reverse=True)
    top = rows[:n]

    print(f"\n🎯 Top {n} CSP Targets — {datetime.today().strftime('%Y-%m-%d')}")
    print(f"   Scoring: 50% Buffer (1.5x ≥10%) | 35% Premium (1.1x buyzone) | 15% IV")
    print("=" * 65)

    for i, r in enumerate(top, 1):
        premium_pct = r.get("put_20d_premium_pct", 0) * 100
        buffer_pct  = r["_buffer_pct"] * 100
        score       = r["_score"] * 100
        buf_icon    = "✅" if buffer_pct >= 10 else "⚠️"
        fire        = "🔥" if r["_buffer_pct"] >= MIN_BUFFER_PRIORITY else "  "
        bz          = "✅" if r.get("buyzone_flag") else "❌"
        dte         = days_to_expiry(r)
        print(f"\n#{i} {fire} {r['ticker']} — {r.get('sector', 'N/A')}  [score: {score:.3f}]")
        print(f"   Price:       ${r['latest_price']:.2f}")
        print(f"   Strike:      ${r['put_20d_strike']:.2f}")
        print(f"   Buffer:      {buffer_pct:.2f}%  {buf_icon}")
        print(f"   Premium:     ${r['put_20d_premium']:.2f}  ({premium_pct:.2f}%)")
        print(f"   Delta:       {r['put_20d_delta']:.3f}")
        print(f"   IV ATM:      {r['iv_atm']:.3f}")
        print(f"   Expiry:      {r['expiry']}  ({dte} days)")
        print(f"   Earnings:    {r.get('days_to_earnings', '?')} days away")
        print(f"   Buyzone:     {bz}")

    print("\n" + "=" * 65)
    return top

def get_all_candidates() -> dict[str, dict]:
    """
    Returns a dict of ticker → metadata for tickers that pass all screener filters.
    Metadata keys: days_to_earnings (int|None), earnings_date (str|None).
    No printing — designed for programmatic use by wheel_manager and risk_manager.
    Returns an empty dict on API error so callers handle gracefully.
    """
    try:
        response = requests.get(URL, params=PARAMS, timeout=60)
        response.raise_for_status()
        rows = response.json().get("rows", [])
    except Exception as e:
        print(f"⚠️  get_all_candidates: API error — {e}")
        return {}

    rows = [r for r in rows if r.get("wheel_fit") == "Wheel-ready"]

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    def _dte(r):
        try:
            exp = datetime.strptime(r["expiry"], "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
            return (exp - today).days
        except Exception:
            return 99

    rows = [r for r in rows if _dte(r) >= MIN_DAYS_TO_EXPIRY]
    rows = [r for r in rows if abs(r.get("put_20d_delta", -1)) <= MAX_DELTA]

    for r in rows:
        r["_buffer_pct"] = (r["latest_price"] - r["put_20d_strike"]) / r["latest_price"]
    rows = [r for r in rows if r["_buffer_pct"] >= MIN_BUFFER_PCT]

    return {
        r["ticker"]: {
            "days_to_earnings": r.get("days_to_earnings"),
            "earnings_date":    r.get("earnings_date"),
        }
        for r in rows
    }


if __name__ == "__main__":
    get_top_targets(5)
