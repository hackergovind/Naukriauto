import asyncio
from datetime import datetime
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from src.config import Config, logger
from src.naukri_client import NaukriClient

class SchedulerManager:
    def __init__(self, bot_app=None):
        self.tz = pytz.timezone(Config.TIMEZONE)
        self.scheduler = AsyncIOScheduler(timezone=self.tz)
        self.client = NaukriClient()
        self.bot_app = bot_app
        self.job_id = "daily_naukri_update"
        self.last_run_status = {"timestamp": None, "success": None, "message": "No run yet"}

    def set_bot_app(self, bot_app):
        self.bot_app = bot_app

    async def notify_users(self, message: str, photo_path: str = None):
        """Send notification to all allowed telegram users."""
        if not self.bot_app:
            return
        
        for user_id in Config.ALLOWED_TELEGRAM_USER_IDS:
            try:
                if photo_path and photo_path.endswith(".png"):
                    with open(photo_path, "rb") as f:
                        await self.bot_app.bot.send_photo(
                            chat_id=user_id,
                            photo=f,
                            caption=message,
                            parse_mode="Markdown"
                        )
                else:
                    await self.bot_app.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode="Markdown"
                    )
            except Exception as e:
                logger.error("Failed to send Telegram notification to user {}: {}", user_id, e)

    async def execute_daily_update(self, is_manual: bool = False) -> dict:
        """Execute the headline update workflow and report status."""
        trigger_type = "Manual Trigger" if is_manual else "Scheduled Daily Update (09:00 AM)"
        logger.info("Starting Naukri profile update job ({})", trigger_type)
        
        start_time = datetime.now(self.tz)
        result = await self.client.update_profile_headline()

        self.last_run_status = {
            "timestamp": start_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "success": result["success"],
            "message": result["message"]
        }

        if result["success"]:
            msg = (
                f"✅ *Naukri Profile Updated Successfully!*\n\n"
                f"🕒 *Time:* {self.last_run_status['timestamp']}\n"
                f"⚡ *Trigger:* {trigger_type}\n\n"
                f"📝 *Old Headline:*\n{result['old_headline']}\n\n"
                f"✨ *New Headline:*\n{result['new_headline']}\n\n"
                f"🚀 Your profile timestamp has been refreshed for recruiters."
            )
        else:
            msg = (
                f"❌ *Naukri Profile Update Failed!*\n\n"
                f"🕒 *Time:* {self.last_run_status['timestamp']}\n"
                f"⚡ *Trigger:* {trigger_type}\n\n"
                f"⚠️ *Error:* {result['message']}\n"
                f"Check logs or update credentials in .env if needed."
            )

        await self.notify_users(msg, result.get("screenshot_path"))
        return result

    def start(self):
        """Register the daily cron job and start scheduler."""
        hour, minute = [int(x) for x in Config.DAILY_UPDATE_TIME.split(":")]
        trigger = CronTrigger(hour=hour, minute=minute, timezone=self.tz)
        
        self.scheduler.add_job(
            self.execute_daily_update,
            trigger=trigger,
            id=self.job_id,
            replace_existing=True
        )
        self.scheduler.start()
        logger.info(
            "Scheduler started. Daily update scheduled for {}:{:02d} ({})",
            hour, minute, Config.TIMEZONE
        )

    def get_next_run_time(self) -> str:
        """Get the formatted next scheduled run time."""
        job = self.scheduler.get_job(self.job_id)
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%d %I:%M %p %Z")
        return "Not scheduled"

    def update_schedule_time(self, time_str: str) -> bool:
        """Update daily scheduled time (Format HH:MM)."""
        try:
            hour, minute = [int(x) for x in time_str.split(":")]
            trigger = CronTrigger(hour=hour, minute=minute, timezone=self.tz)
            self.scheduler.reschedule_job(self.job_id, trigger=trigger)
            Config.DAILY_UPDATE_TIME = f"{hour:02d}:{minute:02d}"
            logger.info("Updated daily schedule to {}:{:02d}", hour, minute)
            return True
        except Exception as e:
            logger.error("Failed to update schedule time: {}", e)
            return False
