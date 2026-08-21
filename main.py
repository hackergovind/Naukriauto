import asyncio
import sys
from src.config import Config, logger
from src.scheduler import SchedulerManager
from src.bot import TelegramBot

async def main():
    logger.info("Initializing Naukri Auto Profile Updater Bot...")

    # Validate config
    errors = Config.validate()
    if errors:
        for err in errors:
            logger.warning("Config validation notice: {}", err)
        logger.info("Please set environment variables in .env file before running.")

    if not Config.TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN is required to run the bot. Exiting.")
        sys.exit(1)

    # Initialize Scheduler
    scheduler_mgr = SchedulerManager()
    scheduler_mgr.start()

    # Initialize Telegram Bot
    bot = TelegramBot(scheduler_mgr)

    logger.info("Starting Telegram Bot polling loop...")
    async with bot.app:
        await bot.app.start()
        await bot.app.updater.start_polling(drop_pending_updates=True)
        logger.info("Naukri Auto Bot is now LIVE and listening for commands!")

        # Keep running
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

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process terminated by user.")
