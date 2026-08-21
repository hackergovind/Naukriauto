import asyncio
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
from src.config import Config, logger
from src.scheduler import SchedulerManager

class TelegramBot:
    def __init__(self, scheduler_mgr: SchedulerManager):
        self.scheduler_mgr = scheduler_mgr
        self.app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        self.scheduler_mgr.set_bot_app(self.app)
        self._register_handlers()

    def _is_user_authorized(self, user_id: int) -> bool:
        """Check if user is authorized to use the bot."""
        if not Config.ALLOWED_TELEGRAM_USER_IDS:
            return True
        return user_id in Config.ALLOWED_TELEGRAM_USER_IDS

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
            await update.message.reply_text(
                f"⛔ *Unauthorized Access*\n\nYour Telegram User ID is `{user_id}`.\n"
                "Please add this ID to `ALLOWED_TELEGRAM_USER_IDS` in your `.env` configuration.",
                parse_mode="Markdown"
            )
            return

        text = (
            "🤖 *Welcome to Naukri Auto Profile Bot!*\n\n"
            "This bot automatically keeps your Naukri profile active by toggling a dot in your headline "
            "every morning at *9:00 AM IST*, boosting your visibility to recruiters.\n\n"
            f"🎯 *Configured Account:* `{self._mask_email(Config.NAUKRI_EMAIL)}`\n"
            f"⏰ *Daily Schedule:* `{Config.DAILY_UPDATE_TIME}` ({Config.TIMEZONE})\n\n"
            "Choose an action below to get started:"
        )
        await update.message.reply_text(text, reply_markup=self._get_main_keyboard(), parse_mode="Markdown")

    async def update_now_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            return

        target_msg = update.message or (update.callback_query.message if update.callback_query else None)
        if not target_msg:
            return

        status_msg = await target_msg.reply_text("🔄 *Updating Naukri profile headline...*", parse_mode="Markdown")

        try:
            result = await self.scheduler_mgr.execute_daily_update(is_manual=True)
            if not result["success"]:
                await status_msg.edit_text(f"❌ *Update failed:*\n{result['message']}", parse_mode="Markdown")
            else:
                await status_msg.edit_text("✅ *Profile headline updated successfully!*", parse_mode="Markdown")
        except Exception as e:
            logger.error("Manual update error: {}", e)
            await status_msg.edit_text(f"❌ *Unexpected error:* {str(e)}")

    async def status_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            return

        next_run = self.scheduler_mgr.get_next_run_time()
        last_run = self.scheduler_mgr.last_run_status
        last_run_str = (
            f"`{last_run['timestamp']}` (" + ("✅ Success" if last_run["success"] else "❌ Failed") + ")"
            if last_run["timestamp"] else "None yet"
        )

        status_text = (
            "📊 *Naukri Bot Status*\n\n"
            f"👤 *Account:* `{self._mask_email(Config.NAUKRI_EMAIL)}`\n"
            f"🟢 *Scheduler State:* `Running`\n"
            f"⏰ *Daily Update Time:* `{Config.DAILY_UPDATE_TIME}` ({Config.TIMEZONE})\n"
            f"📅 *Next Scheduled Run:* `{next_run}`\n"
            f"🕒 *Last Execution:* {last_run_str}\n\n"
            "Use /update_now to trigger an immediate update."
        )
        target_msg = update.message or (update.callback_query.message if update.callback_query else None)
        if target_msg:
            await target_msg.reply_text(status_text, reply_markup=self._get_main_keyboard(), parse_mode="Markdown")

    async def headline_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            return

        target_msg = update.message or (update.callback_query.message if update.callback_query else None)
        if not target_msg:
            return

        status_msg = await target_msg.reply_text("🔍 *Fetching current headline from Naukri...*", parse_mode="Markdown")

        client = self.scheduler_mgr.client
        res = await client.get_current_headline()
        if res["success"]:
            await status_msg.edit_text(
                f"📝 *Current Resume Headline:*\n\n`{res['headline']}`",
                parse_mode="Markdown"
            )
        else:
            await status_msg.edit_text(f"⚠️ *Could not fetch headline:* {res['message']}")

    async def set_cookie_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            return

        if not context.args or len(context.args) == 0:
            help_msg = (
                "🔑 *How to Set Session Cookie:*\n\n"
                "1. Open Naukri on your browser and login.\n"
                "2. Press `F12` (Developer Tools) ➔ Go to **Network** tab ➔ Refresh.\n"
                "3. Click any request to `naukri.com` and copy the **`Cookie`** header value.\n"
                "4. Send it here like this:\n"
                "`/set_cookie <your_cookie_string>`\n\n"
                "💡 *This keeps your bot connected 24/7 without needing passwords.*"
            )
            await update.message.reply_text(help_msg, parse_mode="Markdown")
            return

        raw_cookie = " ".join(context.args).strip()
        client = self.scheduler_mgr.client
        saved = client.save_raw_cookie_string(raw_cookie)
        if saved:
            status_msg = await update.message.reply_text("⏳ *Validating session cookie with Naukri...*", parse_mode="Markdown")
            res = await client.get_current_headline()
            if res["success"]:
                await status_msg.edit_text(
                    f"✅ *Session Cookie Saved & Verified!*\n\n"
                    f"📝 *Detected Headline:* `{res['headline']}`\n\n"
                    "Daily automatic updates are now active!",
                    parse_mode="Markdown"
                )
            else:
                await status_msg.edit_text("✅ *Session Cookie Saved!* You can now run `/update_now`.", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ *Failed to parse cookie string.* Please make sure it is in `key=value;` format.", parse_mode="Markdown")

    async def set_time_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            return

        if not context.args or len(context.args) == 0:
            await update.message.reply_text(
                "⚠️ *Usage:* `/set_time HH:MM` (e.g. `/set_time 09:00` or `/set_time 14:30`)",
                parse_mode="Markdown"
            )
            return

        time_val = context.args[0].strip()
        success = self.scheduler_mgr.update_schedule_time(time_val)
        if success:
            await update.message.reply_text(
                f"✅ *Daily update schedule updated to:* `{Config.DAILY_UPDATE_TIME}` ({Config.TIMEZONE})\n"
                f"📅 *Next Run:* `{self.scheduler_mgr.get_next_run_time()}`",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "❌ *Invalid time format.* Please use 24-hr format like `09:00` or `18:30`.",
                parse_mode="Markdown"
            )

    async def logs_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            return

        target_msg = update.message or (update.callback_query.message if update.callback_query else None)
        if not target_msg:
            return

        log_file = Config.LOG_FILE_PATH
        if not log_file.exists():
            await target_msg.reply_text("📜 *No logs recorded yet.*", parse_mode="Markdown")
            return

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                last_lines = "".join(lines[-20:])
                if len(last_lines) > 3800:
                    last_lines = last_lines[-3800:]

            await target_msg.reply_text(
                f"📜 *Recent Logs (Last 20 entries):*\n```\n{last_lines}\n```",
                parse_mode="Markdown"
            )
        except Exception as e:
            await target_msg.reply_text(f"⚠️ *Failed to read logs:* {e}")

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_user_authorized(user_id):
            return

        target_msg = update.message or (update.callback_query.message if update.callback_query else None)
        if not target_msg:
            return

        help_text = (
            "🤖 *Naukri Auto Bot Commands*\n\n"
            "🔹 `/start` - Open main dashboard & control panel\n"
            "🔹 `/update_now` - Trigger immediate headline update\n"
            "🔹 `/status` - View scheduler status & next run time\n"
            "🔹 `/headline` - Fetch current headline from Naukri\n"
            "🔹 `/set_cookie <cookie>` - Set browser session cookies\n"
            "🔹 `/set_time <HH:MM>` - Change daily schedule time (24-hr format)\n"
            "🔹 `/logs` - Show recent application logs\n"
            "🔹 `/help` - Show this help message\n\n"
            "💡 *How it works:*\n"
            "Every day at 9:00 AM IST, the bot securely communicates with Naukri, "
            "toggles a trailing `.` on your headline, and saves it. This marks your profile as "
            "freshly updated without altering your text meaning, boosting recruiter visibility."
        )
        await target_msg.reply_text(help_text, reply_markup=self._get_main_keyboard(), parse_mode="Markdown")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        if not self._is_user_authorized(user_id):
            await query.message.reply_text("⛔ Unauthorized.")
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
                "🔑 *To set your session cookie:*\nSend `/set_cookie <your_browser_cookies>` in chat.",
                parse_mode="Markdown"
            )
        elif data == "btn_next_run":
            next_run = self.scheduler_mgr.get_next_run_time()
            await query.message.reply_text(
                f"⏰ *Next Scheduled Update:* `{next_run}`",
                parse_mode="Markdown"
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
        self.app.add_handler(CommandHandler("set_cookie", self.set_cookie_cmd))
        self.app.add_handler(CommandHandler("set_time", self.set_time_cmd))
        self.app.add_handler(CommandHandler("logs", self.logs_cmd))
        self.app.add_handler(CommandHandler("help", self.help_cmd))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))