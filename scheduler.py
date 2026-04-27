import json
import logging
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from config import NUM_POSITIONS, TOTAL_FUND_BUDGET

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("scheduler_log.txt"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

PST        = ZoneInfo("America/Los_Angeles")
STATE_FILE = "state.json"
SETTINGS_FILE = "settings.json"


def _new_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


def _load_settings() -> dict:
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def _parse_exec_time(settings: dict) -> tuple:
    """Return (hour, minute) PST for configured Monday execution time."""
    try:
        h, m = map(int, settings.get("execution_time", "10:00").split(":"))
        return h, m
    except Exception:
        return 10, 0

def _offset_time(hour: int, minute: int, delta_minutes: int) -> tuple:
    """Subtract delta_minutes from (hour, minute), return new (hour, minute)."""
    total = hour * 60 + minute - delta_minutes
    return total // 60, total % 60


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# ── Saturday 6PM — screener preview ───────────────────────────

def run_screener_preview():
    loop = _new_loop()
    now  = datetime.now(PST)
    log.info("\n" + "=" * 65)
    log.info(f"📋 SATURDAY PREVIEW — {now.strftime('%A %Y-%m-%d %H:%M %Z')}")
    log.info("=" * 65)
    try:
        from screener import get_top_targets
        from position_sizer import size_all

        targets   = get_top_targets(10)
        positions = size_all(targets)
        exec_time = _load_settings().get("execution_time", "10:00")
        log.info(f"\n📋 {len(positions)} positions queued for Monday {exec_time} PST")

        from discord_poster import is_plan_enabled, post_weekly_plan
        if is_plan_enabled():
            post_weekly_plan(positions)
            log.info("✅ Weekly plan posted to Discord")
    except Exception as e:
        log.error(f"❌ Preview error: {e}", exc_info=True)
    finally:
        loop.close()


# ── Friday 4:15PM — assignment detection ──────────────────────

def run_assignment_detection():
    loop = _new_loop()
    now  = datetime.now(PST)
    log.info("\n" + "=" * 65)
    log.info(f"🔍 FRIDAY ASSIGNMENT DETECTION — {now.strftime('%A %Y-%m-%d %H:%M %Z')}")
    log.info("=" * 65)
    try:
        from wheel_manager import detect_assignments
        state_before  = _load_state()
        known_tickers = {h["ticker"] for h in state_before.get("wheel_holdings", [])}

        detect_assignments()

        from discord_poster import is_enabled, post_assignment_alert
        if is_enabled():
            state_after  = _load_state()
            today        = now.date().isoformat()
            new_ones     = [h for h in state_after.get("wheel_holdings", [])
                            if h["ticker"] not in known_tickers
                            and h.get("assignment_date") == today]
            post_assignment_alert(new_ones)
    except Exception as e:
        log.error(f"❌ Assignment detection error: {e}", exc_info=True)
    finally:
        loop.close()


# ── Monday 9:50AM — Discord pre-execution preview ─────────────

def run_discord_preview():
    from discord_poster import is_enabled, post_preview
    if not is_enabled():
        return
    loop = _new_loop()
    log.info("📋 Discord preview — sizing positions...")
    try:
        from screener import get_top_targets
        from position_sizer import size_all
        state        = _load_state()
        context      = state.get("monday_context", {})
        skip_tickers = set(context.get("skip_tickers", []))
        freed        = context.get("freed_capital", 0.0)
        targets      = get_top_targets(10)
        filtered     = [t for t in targets if t["ticker"] not in skip_tickers]
        budget       = TOTAL_FUND_BUDGET + freed
        positions    = size_all(filtered, budget=budget)
        post_preview(positions, budget)
        log.info("✅ Discord preview posted")
    except Exception as e:
        log.error(f"❌ Discord preview error: {e}", exc_info=True)
    finally:
        loop.close()


# ── Monday 9:55AM — wheel check (runs before CSP pipeline) ────

def run_wheel_check_job():
    loop = _new_loop()
    now  = datetime.now(PST)
    log.info("\n" + "=" * 65)
    log.info(f"🔄 MONDAY WHEEL CHECK — {now.strftime('%A %Y-%m-%d %H:%M %Z')}")
    log.info("=" * 65)
    try:
        from wheel_manager import run_wheel_check
        freed, skip = run_wheel_check()
        log.info(f"✅ Wheel check done — freed ${freed:,.0f}  skip {skip or 'none'}")
    except Exception as e:
        log.error(f"❌ Wheel check error: {e}", exc_info=True)
    finally:
        loop.close()


# ── Monday 10AM — CSP execution pipeline ──────────────────────

def run_pipeline():
    loop = _new_loop()
    now  = datetime.now(PST)
    log.info("\n" + "=" * 65)
    log.info(f"⏰ MONDAY EXECUTION — {now.strftime('%A %Y-%m-%d %H:%M %Z')}")
    log.info("=" * 65)
    try:
        from screener import get_top_targets
        from position_sizer import size_all
        from trader import execute_positions

        # Read context left by wheel_check (9:55AM)
        state         = _load_state()
        context       = state.get("monday_context", {})
        skip_tickers  = set(context.get("skip_tickers", []))
        freed_capital = context.get("freed_capital", 0.0)

        if skip_tickers:
            log.info(f"  🚫 Skipping tickers (wheel exits): {skip_tickers}")
        if freed_capital > 0:
            log.info(f"  💰 Freed capital added to pool: ${freed_capital:,.0f}")

        all_targets = get_top_targets(10)
        if not all_targets:
            log.error("❌ No targets returned — aborting"); return

        # Filter out stop-loss tickers so they don't re-enter as CSPs this week
        filtered_targets = [t for t in all_targets if t["ticker"] not in skip_tickers]
        if len(filtered_targets) < len(all_targets):
            log.info(f"  Filtered {len(all_targets) - len(filtered_targets)} ticker(s) "
                     f"from screener results")

        effective_budget = TOTAL_FUND_BUDGET + freed_capital
        positions = size_all(filtered_targets, budget=effective_budget)
        if not positions:
            log.error("❌ No positions sized — aborting"); return

        results = execute_positions(positions, extra_targets=filtered_targets)

        # ── Build weekly P&L ──────────────────────────────────
        filled          = [r for r in results if r.get("status") in ("filled", "dry_run", "partial_fill")]
        csp_premium     = sum(r.get("premium_collected", 0) for r in results)
        cc_premium      = context.get("cc_premium", 0.0)
        shares_sold_pnl = context.get("shares_sold_pnl", 0.0)
        total_realized  = round(csp_premium + cc_premium + shares_sold_pnl, 2)

        state = _load_state()   # reload — execute_positions merges but may have written it
        state["weekly_pnl"] = {
            "week_start":       now.strftime("%Y-%m-%d"),
            "csp_premium":      round(csp_premium, 2),
            "cc_premium":       round(cc_premium, 2),
            "shares_sold_pnl":  round(shares_sold_pnl, 2),
            "total_realized":   total_realized,
            "last_updated":     datetime.now().isoformat()
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

        from discord_poster import is_enabled, post_weekly_results
        if is_enabled():
            post_weekly_results(_load_state(), fund_budget=effective_budget)

        log.info(f"\n✅ Done — {len(filled)}/{NUM_POSITIONS} CSP fills  |  "
                 f"CSP ${csp_premium:,.0f}  CC ${cc_premium:,.0f}  "
                 f"Shares sold P&L ${shares_sold_pnl:,.0f}  "
                 f"Total realized ${total_realized:,.0f}")

    except Exception as e:
        log.error(f"❌ Pipeline error: {e}", exc_info=True)
    finally:
        loop.close()


# ── Tuesday–Thursday 9AM — daily risk monitor ─────────────────

def run_risk_monitor():
    loop = _new_loop()
    now  = datetime.now(PST)
    log.info("\n" + "=" * 65)
    log.info(f"📊 DAILY RISK MONITOR — {now.strftime('%A %Y-%m-%d %H:%M %Z')}")
    log.info("=" * 65)
    try:
        from risk_manager import run_daily_monitor
        run_daily_monitor()
    except Exception as e:
        log.error(f"❌ Risk monitor error: {e}", exc_info=True)
    finally:
        loop.close()


# ── Scheduler main ─────────────────────────────────────────────

def main():
    settings = _load_settings()
    exec_h, exec_m = _parse_exec_time(settings)
    prev_h, prev_m = _offset_time(exec_h, exec_m, 10)   # Discord preview: exec − 10 min
    wheel_h, wheel_m = _offset_time(exec_h, exec_m, 5)  # Wheel check:     exec − 5 min

    def fmt(h, m):
        ampm = "AM" if h < 12 else "PM"
        h12  = h % 12 or 12
        return f"{h12}:{m:02d} {ampm} PST"

    scheduler = BlockingScheduler(timezone=PST)

    scheduler.add_job(
        run_screener_preview,
        trigger="cron", day_of_week="sat", hour=18, minute=0,
        id="saturday_preview", name="Saturday Screener Preview"
    )
    scheduler.add_job(
        run_assignment_detection,
        trigger="cron", day_of_week="fri", hour=16, minute=15,
        id="friday_assignment", name="Friday Assignment Detection"
    )
    scheduler.add_job(
        run_discord_preview,
        trigger="cron", day_of_week="mon", hour=prev_h, minute=prev_m,
        id="monday_discord_preview", name="Monday Discord Preview"
    )
    scheduler.add_job(
        run_wheel_check_job,
        trigger="cron", day_of_week="mon", hour=wheel_h, minute=wheel_m,
        id="monday_wheel_check", name="Monday Wheel Check"
    )
    scheduler.add_job(
        run_pipeline,
        trigger="cron", day_of_week="mon", hour=exec_h, minute=exec_m,
        id="monday_execution", name="Monday CSP Execution"
    )
    scheduler.add_job(
        run_risk_monitor,
        trigger="cron", day_of_week="tue,wed,thu", hour=9, minute=0,
        id="daily_risk_monitor", name="Daily Risk Monitor"
    )

    log.info("\n" + "=" * 65)
    log.info("🗓️  YOU ROCK FUND SCHEDULER — Running")
    log.info(f"   Current time : {datetime.now(PST).strftime('%A %Y-%m-%d %H:%M %Z')}")
    log.info("   • Friday     4:15 PM PST  — assignment detection")
    log.info("   • Saturday   6:00 PM PST  — screener preview")
    log.info(f"   • Monday    {fmt(prev_h, prev_m):>11}  — Discord preview (if webhook set)")
    log.info(f"   • Monday    {fmt(wheel_h, wheel_m):>11}  — wheel check (stop loss + CCs)")
    log.info(f"   • Monday    {fmt(exec_h, exec_m):>11}  — CSP execution  ← configured")
    log.info("   • Tue–Thu    9:00 AM PST  — daily risk monitor")
    log.info("   Press Ctrl+C to stop")
    log.info("=" * 65 + "\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("\n⛔ Scheduler stopped")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
