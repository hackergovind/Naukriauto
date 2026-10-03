import argparse
import asyncio
import sys
from src.config import Config, logger
from src.scheduler import SchedulerManager


async def run_bot(scheduler_mgr: SchedulerManager):
    """Full mode: scheduler (09:00 + 12:30) + Telegram bot. Needs TELEGRAM_BOT_TOKEN."""
    from src.bot import TelegramBot

    if not Config.TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN is required for bot mode. "
                        "Use CLI mode instead: python main.py --update-now")
        sys.exit(1)

    scheduler_mgr.start()
    bot = TelegramBot(scheduler_mgr)

    logger.info("Starting Telegram Bot polling loop...")
    async with bot.app:
        await bot.app.start()
        await bot.app.updater.start_polling(drop_pending_updates=True)
        logger.info("Naukri Auto Bot is now LIVE and listening for commands!")

        stop_signal = asyncio.Event()
        try:
            await stop_signal.wait()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Received exit signal. Shutting down...")
        finally:
            await bot.app.updater.stop()
            await bot.app.stop()
            scheduler_mgr.scheduler.shutdown()
            logger.info("Bot and scheduler stopped cleanly.")


async def run_scheduler_only(scheduler_mgr: SchedulerManager):
    """Server mode: scheduler only, no Telegram. Ideal for basic CLI servers."""
    scheduler_mgr.start()
    logger.info("Scheduler-only mode. Updates at: {} ({}). Press Ctrl+C to stop.",
                ",".join(Config.get_schedule_times()), Config.get_timezone_name())
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler...")
    finally:
        scheduler_mgr.scheduler.shutdown()


async def run_oneshot(action: str):
    """One-shot CLI actions for cron: --update-now, --headline, --check."""
    from src.naukri_client import NaukriClient

    client = NaukriClient()
    if action == "headline":
        res = await client.get_current_headline()
        if res["success"]:
            print(f"Current headline: {res['headline']}")
        else:
            print(f"FAILED: {res['message']}")
            sys.exit(2)
    elif action == "update-now":
        res = await client.update_profile_headline()
        if res["success"]:
            print("Headline updated successfully!")
            print(f"Old: {res['old_headline']}")
            print(f"New: {res['new_headline']}")
        else:
            print(f"UPDATE FAILED: {res['message']}")
            sys.exit(2)
    elif action == "check":
        errors = Config.validate()
        print(f"Schedule: {','.join(Config.get_schedule_times())} ({Config.get_timezone_name()})")
        print(f"Email set: {bool(Config.NAUKRI_EMAIL)}")
        print(f"Password set: {bool(Config.NAUKRI_PASSWORD)}")
        print(f"Telegram token set: {bool(Config.TELEGRAM_BOT_TOKEN)}")
        state = client.get_headline_state()
        print(f"Base headline set: {bool(state['base'])}" + (f" ({state['base'][:60]})" if state['base'] else " — run --set-headline or /set_headline first"))
        if errors:
            print("Config issues: " + "; ".join(errors))


async def main():
    parser = argparse.ArgumentParser(description="Naukri Auto Profile Updater (email+password, CLI-server ready)")
    parser.add_argument("--update-now", action="store_true", help="Update headline once (dot toggle) and exit. Use in cron.")
    parser.add_argument("--headline", action="store_true", help="Print current headline and exit.")
    parser.add_argument("--check", action="store_true", help="Validate .env config and exit.")
    parser.add_argument("--no-bot", action="store_true", help="Run scheduler only, no Telegram polling.")
    parser.add_argument("--set-headline", metavar="TEXT", default=None, help="One-time: save base headline, e.g. --set-headline \"Java Developer\"")
    args = parser.parse_args()

    logger.info("Initializing Naukri Auto Profile Updater...")

    errors = Config.validate()
    if errors:
        for err in errors:
            logger.warning("Config validation notice: {}", err)

    scheduler_mgr = SchedulerManager()

    if args.update_now:
        await run_oneshot("update-now")
    elif args.headline:
        await run_oneshot("headline")
    elif args.check:
        await run_oneshot("check")
    elif args.set_headline:
        from src.naukri_client import NaukriClient
        print("Saved base headline:", NaukriClient().set_base_headline(args.set_headline))
    elif args.no_bot:
        await run_scheduler_only(scheduler_mgr)
    else:
        await run_bot(scheduler_mgr)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process terminated by user.")
