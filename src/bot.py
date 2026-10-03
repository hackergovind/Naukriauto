import asyncio
import html as _html
import re
import time
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from src.config import Config, logger, redact_secrets
from src.scheduler import SchedulerManager

# Security limits (anti-abuse / anti-DoS)
UPDATE_COOLDOWN_SEC = 90
MAX_COOKIE_LEN = 8192
MAX_HEADLINE_LEN = 500
MAX_TIME_LEN = 32
_TIME_RE = re.compile(r"^\d{2}:\d{2}(,\d{2}:\d{2})*$")

class TelegramBot:
    def __init__(self, scheduler_mgr: SchedulerManager):
        self.scheduler_mgr = scheduler_mgr
        self.app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        self.scheduler_mgr.set_bot_app(self.app)
        self._last_update: dict[int, float] = {}
        self._register_handlers()

    def _is_user_authorized(self, user_id: int) -> bool:
        """Fail-closed: deny ALL users until allowlist is configured."""
        if not Config.ALLOWED_TELEGRAM_USER_IDS:
            return False
        return user_id in Config.ALLOWED_TELEGRAM_USER_IDS

    async def _deny(self, update: Update) -> None:
        """Generic denial — no user_id echo, no setup instructions (anti-enumeration)."""
        try:
            user_id = update.effective_user.id if update.effective_user else "unknown"
        except Exception:
            user_id = "unknown"
        logger.warning("Denied unauthorized Telegram access from user_id={}", user_id)
        target = update.message or (update.callback_query.message if update.callback_query else None)
        if target is not None:
            try:
                await target.reply_text("⛔ Unauthorized.")
            except Exception:
                pass

    @staticmethod
    def _esc(text: object) -> str:
        return _html.escape(str(text), quote=False)

    def _get_main_keyboard(self) -> InlineKeyboardMarkup:
        keyboard = [
            [
                InlineKeyboardButton("⚡ Update Profile Now", callback_data="btn_update_now"),
                InlineKeyboardButton("📊 Status & Health", callback_data="btn_status"),
            ],
            [
                InlineKeyboardButton("📝 View Headline", callback_data="btn_headline"),
                InlineKeyboardButton("⏰ Next Scheduled Run", callback_data="btn_next_run"),
            ],
            [
                InlineKeyboardButton("🔑 Set Session Cookie", callback_data="btn_cookie_help"),
                InlineKeyboardButton("📜 Recent Logs", callback_data="btn_logs"),
            ],
            [
                InlineKeyboardButton("❓ Help & Commands", callback_data="btn_help"),
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    def _mask_email(self, email: str) -> str:
        if "@" not in email:
            return email[:4] + "***" if email else "Not Set"
        parts = email.split("@")
        name = parts[0]
        domain = parts[1]
        masked_name = name[0] + "***" + (name[-1] if len(name) > 1 else "")
        return f"{masked_name}@{domain}"

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            await self._deny(update)
            return

        text = (
            "🤖 <b>Welcome to Naukri Auto Profile Bot!</b>\n\n"
            "This bot automatically keeps your Naukri profile active by toggling a dot in your headline "
            "every day at <b>9:00 AM &amp; 12:30 PM IST</b>, boosting your visibility to recruiters.\n\n"
            f"🎯 <b>Configured Account:</b> <code>{self._esc(self._mask_email(Config.NAUKRI_EMAIL))}</code>\n"
            f"⏰ <b>Daily Schedules:</b> <code>{self._esc(','.join(Config.get_schedule_times()))}</code> ({self._esc(Config.get_timezone_name())})\n\n"
            "Choose an action below to get started:"
        )
        await update.message.reply_text(text, reply_markup=self._get_main_keyboard(), parse_mode="HTML")

    async def update_now_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            await self._deny(update)
            return

        # Per-user cooldown: prevents Naukri 429 / account lockout from spam
        now = time.monotonic()
        last = self._last_update.get(user_id, 0.0)
        if now - last < UPDATE_COOLDOWN_SEC:
            wait = int(UPDATE_COOLDOWN_SEC - (now - last))
            target = update.message or (update.callback_query.message if update.callback_query else None)
            if target is not None:
                await target.reply_text(f"⏳ Please wait {wait}s before triggering another update.")
            return
        self._last_update[user_id] = now

        target_msg = update.message or (update.callback_query.message if update.callback_query else None)
        if not target_msg:
            return

        status_msg = await target_msg.reply_text("🔄 <b>Updating Naukri profile headline...</b>", parse_mode="HTML")

        try:
            result = await self.scheduler_mgr.execute_daily_update(is_manual=True)
            if not result["success"]:
                await status_msg.edit_text("❌ <b>Update failed.</b> Check server logs for details.", parse_mode="HTML")
            else:
                await status_msg.edit_text("✅ <b>Profile headline updated successfully!</b>", parse_mode="HTML")
        except Exception as e:
            logger.error("Manual update error: {}", redact_secrets(str(e)))
            await status_msg.edit_text("❌ <b>Unexpected error.</b> Check server logs for details.", parse_mode="HTML")

    async def status_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            await self._deny(update)
            return

        next_run = self.scheduler_mgr.get_next_run_time()
        last_run = self.scheduler_mgr.last_run_status
        last_run_str = (
            f"<code>{self._esc(last_run['timestamp'])}</code> (" + ("✅ Success" if last_run["success"] else "❌ Failed") + ")"
            if last_run["timestamp"] else "None yet"
        )

        status_text = (
            "📊 <b>Naukri Bot Status</b>\n\n"
            f"👤 <b>Account:</b> <code>{self._esc(self._mask_email(Config.NAUKRI_EMAIL))}</code>\n"
            "🟢 <b>Scheduler State:</b> <code>Running</code>\n"
            f"⏰ <b>Daily Update Times:</b> <code>{self._esc(','.join(Config.get_schedule_times()))}</code> ({self._esc(Config.get_timezone_name())})\n"
            f"📅 <b>Next Scheduled Run:</b> <code>{self._esc(next_run)}</code>\n"
            f"🕒 <b>Last Execution:</b> {last_run_str}\n\n"
            "Use /update_now to trigger an immediate update."
        )
        target_msg = update.message or (update.callback_query.message if update.callback_query else None)
        if target_msg:
            await target_msg.reply_text(status_text, reply_markup=self._get_main_keyboard(), parse_mode="HTML")

    async def headline_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            await self._deny(update)
            return

        target_msg = update.message or (update.callback_query.message if update.callback_query else None)
        if not target_msg:
            return

        status_msg = await target_msg.reply_text("🔍 <b>Fetching current headline from Naukri...</b>", parse_mode="HTML")

        client = self.scheduler_mgr.client
        res = await client.get_current_headline()
        if res["success"]:
            await status_msg.edit_text(
                f"📝 <b>Current Resume Headline:</b>\n\n<code>{self._esc(res['headline'])}</code>",
                parse_mode="HTML"
            )
        else:
            await status_msg.edit_text("⚠️ <b>Could not fetch headline.</b> Check server logs for details.", parse_mode="HTML")

    async def set_headline_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """One-time seed of the tracked base headline (email+password mode)."""
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            await self._deny(update)
            return

        if not context.args:
            await update.message.reply_text(
                "📝 <b>Usage:</b> <code>/set_headline &lt;your current headline&gt;</code>\n\n"
                "Copy it exactly from <code>naukri.com/mnjuser/profile</code>.\n"
                "One-time setup — the bot then toggles <code>.</code> at 09:00 &amp; 12:30 automatically.",
                parse_mode="HTML",
            )
            return

        text = " ".join(context.args).strip()
        if len(text) > MAX_HEADLINE_LEN:
            await update.message.reply_text(
                f"❌ <b>Headline too long</b> ({len(text)} chars, max {MAX_HEADLINE_LEN}).",
                parse_mode="HTML",
            )
            return
        try:
            base = self.scheduler_mgr.client.set_base_headline(text)
            await update.message.reply_text(
                f"✅ <b>Base headline saved:</b>\n<code>{self._esc(base)}</code>\n\nNow run /update_now to test the dot toggle.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("set_headline failed: {}", redact_secrets(str(e)))
            await update.message.reply_text("❌ <b>Failed to save headline.</b> Check server logs.", parse_mode="HTML")

    async def set_cookie_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            await self._deny(update)
            return

        if not context.args or len(context.args) == 0:
            help_msg = (
                "🔑 <b>How to Set Session Cookie:</b>\n\n"
                "1. Open Naukri on your browser and login.\n"
                "2. Press <code>F12</code> (Developer Tools) ➔ Go to <b>Network</b> tab ➔ Refresh.\n"
                "3. Click any request to <code>naukri.com</code> and copy the <b><code>Cookie</code></b> header value.\n"
                "4. Send it here like this:\n"
                "<code>/set_cookie &lt;your_cookie_string&gt;</code>\n\n"
                "⚠️ <b>Security:</b> delete your message after sending — cookies are bearer credentials.\n"
                "💡 <i>This keeps your bot connected 24/7 without needing passwords.</i>"
            )
            await update.message.reply_text(help_msg, parse_mode="HTML")
            return

        raw_cookie = " ".join(context.args).strip()
        if len(raw_cookie) > MAX_COOKIE_LEN:
            logger.warning("Rejected oversized /set_cookie ({} chars) from user_id={}", len(raw_cookie), user_id)
            await update.message.reply_text(
                f"❌ <b>Cookie string too long</b> ({len(raw_cookie)} chars, max {MAX_COOKIE_LEN}).",
                parse_mode="HTML",
            )
            return
        client = self.scheduler_mgr.client
        saved = client.save_raw_cookie_string(raw_cookie)
        logger.info("Session cookie overwritten via /set_cookie by user_id={}", user_id)
        try:
            await update.message.delete()
        except Exception:
            pass
        if saved:
            status_msg = await update.message.reply_text("⏳ <b>Validating session cookie with Naukri...</b>", parse_mode="HTML")
            res = await client.get_current_headline()
            if res["success"]:
                await status_msg.edit_text(
                    "✅ <b>Session Cookie Saved &amp; Verified!</b>\n\n"
                    f"📝 <b>Detected Headline:</b> <code>{self._esc(res['headline'])}</code>\n\n"
                    "Daily automatic updates are now active!\n"
                    "⚠️ Please delete your /set_cookie message from chat history.",
                    parse_mode="HTML"
                )
            else:
                await status_msg.edit_text("✅ <b>Session Cookie Saved!</b> You can now run /update_now.\n⚠️ Please delete your /set_cookie message from chat history.", parse_mode="HTML")
        else:
            await update.message.reply_text("❌ <b>Failed to parse cookie string.</b> Please make sure it is in <code>key=value;</code> format.", parse_mode="HTML")

    async def set_time_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            await self._deny(update)
            return

        if not context.args or len(context.args) == 0:
            await update.message.reply_text(
                "⚠️ <b>Usage:</b> <code>/set_time HH:MM</code> (e.g. <code>/set_time 09:00</code>)\n"
                "For two daily runs: <code>/set_time 09:00,12:30</code>",
                parse_mode="HTML"
            )
            return

        time_val = ",".join(context.args).replace(" ", "").strip()
        if len(time_val) > MAX_TIME_LEN or not _TIME_RE.match(time_val):
            await update.message.reply_text(
                "❌ <b>Invalid time format.</b> Please use 24-hr format like <code>09:00</code> or <code>18:30</code>.",
                parse_mode="HTML"
            )
            return
        success = self.scheduler_mgr.update_schedule_time(time_val)
        if success:
            logger.info("Schedule changed via /set_time by user_id={} to {}", user_id, time_val)
            await update.message.reply_text(
                f"✅ <b>Daily update schedule updated to:</b> <code>{self._esc(','.join(Config.get_schedule_times()))}</code> ({self._esc(Config.get_timezone_name())})\n"
                f"📅 <b>Next Run:</b> <code>{self._esc(self.scheduler_mgr.get_next_run_time())}</code>",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                "❌ <b>Invalid time format.</b> Please use 24-hr format like <code>09:00</code> or <code>18:30</code>.",
                parse_mode="HTML"
            )

    async def logs_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            await self._deny(update)
            return

        target_msg = update.message or (update.callback_query.message if update.callback_query else None)
        if not target_msg:
            return

        log_file = Config.LOG_FILE_PATH
        if not log_file.exists():
            await target_msg.reply_text("📜 <b>No logs recorded yet.</b>", parse_mode="HTML")
            return

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                last_lines = "".join(lines[-20:])
                last_lines = redact_secrets(last_lines)
                if len(last_lines) > 3000:
                    last_lines = last_lines[-3000:]

            await target_msg.reply_text(
                f"📜 <b>Recent Logs (Last 20 entries):</b>\n<pre>{self._esc(last_lines)}</pre>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error("logs_cmd failed: {}", redact_secrets(str(e)))
            await target_msg.reply_text("⚠️ <b>Failed to read logs.</b> Check server logs.", parse_mode="HTML")

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            await self._deny(update)
            return

        target_msg = update.message or (update.callback_query.message if update.callback_query else None)
        if not target_msg:
            return

        help_text = (
            "🤖 <b>Naukri Auto Bot Commands</b>\n\n"
            "🔹 /start - Open main dashboard &amp; control panel\n"
            "🔹 /update_now - Trigger immediate headline update\n"
            "🔹 /status - View scheduler status &amp; next run time\n"
            "🔹 /headline - Show tracked headline + profile freshness\n"
            "🔹 /set_headline &lt;text&gt; - One-time: set your base headline (email mode)\n"
            "🔹 /set_cookie &lt;cookie&gt; - Set browser session cookies (fallback)\n"
            "🔹 /set_time &lt;HH:MM&gt; - Change daily schedule time (24-hr format)\n"
            "🔹 /logs - Show recent application logs\n"
            "🔹 /help - Show this help message\n\n"
            "💡 <b>How it works:</b>\n"
            "Every day at 9:00 AM &amp; 12:30 PM IST, the bot logs in with your email+password, "
            "toggles a trailing <code>.</code> on your headline, and saves it. This marks your profile as "
            "freshly updated without altering your text meaning, boosting recruiter visibility."
        )
        await target_msg.reply_text(help_text, reply_markup=self._get_main_keyboard(), parse_mode="HTML")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        if not self._is_user_authorized(user_id):
            await self._deny(update)
            return

        data = query.data
        if data == "btn_update_now":
            await self.update_now_cmd(update, context)
        elif data == "btn_status":
            await self.status_cmd(update, context)
        elif data == "btn_headline":
            await self.headline_cmd(update, context)
        elif data == "btn_cookie_help":
            await query.message.reply_text(
                "🔑 <b>To set your session cookie:</b>\nSend <code>/set_cookie &lt;your_browser_cookies&gt;</code> in chat, then delete the message.",
                parse_mode="HTML"
            )
        elif data == "btn_next_run":
            next_run = self.scheduler_mgr.get_next_run_time()
            await query.message.reply_text(
                f"⏰ <b>Next Scheduled Update:</b> <code>{self._esc(next_run)}</code>",
                parse_mode="HTML"
            )
        elif data == "btn_logs":
            await self.logs_cmd(update, context)
        elif data == "btn_help":
            await self.help_cmd(update, context)

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_cmd))
        self.app.add_handler(CommandHandler("update", self.update_now_cmd))
        self.app.add_handler(CommandHandler("update_now", self.update_now_cmd))
        self.app.add_handler(CommandHandler("status", self.status_cmd))
        self.app.add_handler(CommandHandler("headline", self.headline_cmd))
        self.app.add_handler(CommandHandler("set_headline", self.set_headline_cmd))
        self.app.add_handler(CommandHandler("set_cookie", self.set_cookie_cmd))
        self.app.add_handler(CommandHandler("set_time", self.set_time_cmd))
        self.app.add_handler(CommandHandler("logs", self.logs_cmd))
        self.app.add_handler(CommandHandler("help", self.help_cmd))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))