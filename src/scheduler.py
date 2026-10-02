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

    async def notify_users(self, message: str):
        """Send text notification to authorized Telegram users."""
        if not self.bot_app:
            return
        
        for user_id in Config.ALLOWED_TELEGRAM_USER_IDS:
            try:
                await self.bot_app.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error("Failed to send Telegram notification to user {}: {}", user_id, e)

    async def execute_daily_update(self, is_manual: bool = False) -> dict:
        """Execute the headline update workflow and report status."""
        schedule_label = ",".join(Config.get_schedule_times())
        trigger_type = "Manual Trigger" if is_manual else f"Daily Schedule ({schedule_label})"
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
                f"🕒 *Time:* `{self.last_run_status['timestamp']}`\n"
                f"⚡ *Trigger:* `{trigger_type}`\n\n"
                f"📝 *Old Headline:*\n`{result['old_headline']}`\n\n"
                f"✨ *New Headline:*\n`{result['new_headline']}`\n\n"
                f"🚀 *Status:* Headline timestamp refreshed on Naukri."
            )
        else:
            msg = (
                f"❌ *Naukri Profile Update Failed!*\n\n"
                f"🕒 *Time:* `{self.last_run_status['timestamp']}`\n"
                f"⚡ *Trigger:* `{trigger_type}`\n\n"
                f"⚠️ *Error:* {result['message']}\n"
                f"Please check your credentials in `.env` if needed."
            )

        await self.notify_users(msg)
        return result

    def start(self):
        """Register daily cron jobs (supports multiple times) and start scheduler."""
        times = Config.get_schedule_times()
        # Keep DAILY_UPDATE_TIME in sync with first time for backward compat
        if times:
            Config.DAILY_UPDATE_TIME = times[0]

        for time_str in times:
            hour, minute = [int(x) for x in time_str.split(":")]
            trigger = CronTrigger(hour=hour, minute=minute, timezone=self.tz)
            job_id = f"{self.job_id}_{time_str.replace(':', '')}"

            self.scheduler.add_job(
                self.execute_daily_update,
                trigger=trigger,
                id=job_id,
                replace_existing=True
            )
        # Keep legacy single job id alias pointing at first time (for reschedule compat)
        self.scheduler.start()
        logger.info(
            "Scheduler active. Daily updates scheduled for {} ({})",
            ", ".join(times), Config.TIMEZONE
        )

    def get_next_run_time(self) -> str:
        """Get the formatted next scheduled run time (earliest of all jobs)."""
        jobs = self.scheduler.get_jobs()
        upcoming = [j.next_run_time for j in jobs if j.next_run_time]
        if upcoming:
            nxt = min(upcoming)
            return nxt.strftime("%Y-%m-%d %I:%M %p %Z")
        # Fallback to legacy single-job lookup
        job = self.scheduler.get_job(self.job_id)
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%d %I:%M %p %Z")
        return "Not scheduled"

    def get_all_next_runs(self) -> str:
        """Comma-separated next run per configured time."""
        parts = []
        for job in self.scheduler.get_jobs():
            if job.next_run_time:
                parts.append(job.next_run_time.strftime("%I:%M %p"))
        return ", ".join(parts) if parts else self.get_next_run_time()

    def update_schedule_time(self, time_str: str) -> bool:
        """Update daily scheduled time. Accepts single HH:MM or comma list HH:MM,HH:MM."""
        try:
            # Normalize: allow "09:00" or "09:00,12:30"
            candidates = [t.strip() for t in time_str.split(",") if t.strip()]
            if not candidates:
                return False
            validated: list[str] = []
            for cand in candidates:
                hour, minute = [int(x) for x in cand.split(":")]
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    return False
                validated.append(f"{hour:02d}:{minute:02d}")
            # Remove existing daily jobs and re-add
            for job in list(self.scheduler.get_jobs()):
                if job.id.startswith(self.job_id):
                    self.scheduler.remove_job(job.id)
            for vt in validated:
                hour, minute = [int(x) for x in vt.split(":")]
                trigger = CronTrigger(hour=hour, minute=minute, timezone=self.tz)
                self.scheduler.add_job(
                    self.execute_daily_update,
                    trigger=trigger,
                    id=f"{self.job_id}_{vt.replace(':', '')}",
                    replace_existing=True,
                )
            Config.DAILY_UPDATE_TIMES_RAW = ",".join(validated)
            Config.DAILY_UPDATE_TIME = validated[0]
            logger.info("Updated daily schedule to {}", ",".join(validated))
            return True
        except Exception as e:
            logger.error("Failed to update schedule time: {}", e)
            return False