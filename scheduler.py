import logging
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from config import NUM_POSITIONS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("scheduler_log.txt"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

PST = ZoneInfo("America/Los_Angeles")


def run_pipeline():
    """Monday 10AM PST — full execution"""
    # ── Fix: create event loop for this thread ────────────────
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    now = datetime.now(PST)
    log.info("\n" + "=" * 65)
    log.info(f"⏰ MONDAY EXECUTION — {now.strftime('%A %Y-%m-%d %H:%M %Z')}")
    log.info("=" * 65)
    try:
        from screener import get_top_targets
        from position_sizer import size_all
        from trader import execute_positions

        all_targets = get_top_targets(10)
        if not all_targets:
            log.error("❌ No targets — aborting"); return

        positions = size_all(all_targets)
        if not positions:
            log.error("❌ No positions sized — aborting"); return

        results      = execute_positions(positions, extra_targets=all_targets)
        filled = [r for r in results if r.get("status") in ("filled", "dry_run", "partial_fill")]
        total  = sum(r.get("premium_collected", 0) for r in results)
        log.info(f"\n✅ Done — {len(filled)}/{NUM_POSITIONS} positions  |  Premium: ${total:,.0f}")

    except Exception as e:
        log.error(f"❌ Pipeline error: {e}", exc_info=True)
    finally:
        loop.close()


def run_screener_preview():
    """Saturday 6PM PST — preview only, no trades"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    now = datetime.now(PST)
    log.info("\n" + "=" * 65)
    log.info(f"📋 SATURDAY PREVIEW — {now.strftime('%A %Y-%m-%d %H:%M %Z')}")
    log.info("=" * 65)
    try:
        from screener import get_top_targets
        from position_sizer import size_all

        targets   = get_top_targets(10)
        positions = size_all(targets)
        log.info(f"\n📋 {len(positions)} positions queued for Monday 10AM")

    except Exception as e:
        log.error(f"❌ Preview error: {e}", exc_info=True)
    finally:
        loop.close()


def main():
    scheduler = BlockingScheduler(timezone=PST)

    scheduler.add_job(
        run_screener_preview,
        trigger="cron",
        day_of_week="sat",
        hour=18,
        minute=0,
        id="saturday_preview",
        name="Saturday Screener Preview"
    )

    scheduler.add_job(
        run_pipeline,
        trigger="cron",
        day_of_week="mon",
        hour=10,
        minute=0,
        id="monday_execution",
        name="Monday Trade Execution"
    )

    log.info("\n" + "=" * 65)
    log.info("🗓️  YOU ROCK FUND SCHEDULER — Running")
    log.info(f"   Current time : {datetime.now(PST).strftime('%A %Y-%m-%d %H:%M %Z')}")
    log.info("   • Saturday  6:00 PM PST — screener preview")
    log.info("   • Monday   10:00 AM PST — execute trades")
    log.info("   Press Ctrl+C to stop")
    log.info("=" * 65 + "\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("\n⛔ Scheduler stopped")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
