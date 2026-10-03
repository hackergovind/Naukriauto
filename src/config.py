import json
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

# Load .env file from project root. Decode BOM in-memory only (never rewrite
# the user's .env file on import — mutating secrets files is unsafe).
BASE_DIR = Path(__file__).resolve().parent.parent
env_file = BASE_DIR / ".env"

load_dotenv(env_file, encoding="utf-8-sig")

class Config:
    # Naukri Credentials & Cookie Session
    NAUKRI_EMAIL: str = os.getenv("NAUKRI_EMAIL", "").strip()
    NAUKRI_PASSWORD: str = os.getenv("NAUKRI_PASSWORD", "").strip()
    NAUKRI_COOKIES: str = os.getenv("NAUKRI_COOKIES", "").strip()

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    _allowed_users_raw = os.getenv("ALLOWED_TELEGRAM_USER_IDS", "").strip()
    ALLOWED_TELEGRAM_USER_IDS: list[int] = [
        int(uid.strip()) for uid in _allowed_users_raw.split(",") if uid.strip().isdigit()
    ]

    # Scheduling - supports single time (DAILY_UPDATE_TIME=09:00)
    # or multiple times comma-separated (DAILY_UPDATE_TIMES=09:00,12:30)
    DAILY_UPDATE_TIME: str = os.getenv("DAILY_UPDATE_TIME", "09:00").strip()
    DAILY_UPDATE_TIMES_RAW: str = os.getenv("DAILY_UPDATE_TIMES", "").strip()
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata").strip()

    @classmethod
    def get_schedule_times(cls) -> list[str]:
        """Return list of HH:MM schedule times (supports 09:00 + 12:30)."""
        raw = cls.DAILY_UPDATE_TIMES_RAW or cls.DAILY_UPDATE_TIME or "09:00"
        times: list[str] = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                h, m = part.split(":")
                hi, mi = int(h), int(m)
                if 0 <= hi <= 23 and 0 <= mi <= 59:
                    times.append(f"{hi:02d}:{mi:02d}")
            except ValueError:
                continue
        # Deduplicate preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for t in times:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        return unique or ["09:00"]

    # Headline tracking (Naukri has no lightweight read API without a browser,
    # so we track the dot-toggle state locally; seeded once from your real headline)
    BASE_HEADLINE: str = os.getenv("BASE_HEADLINE", "").strip()
    HEADLINE_STATE_PATH: Path = BASE_DIR / "data" / "headline_state.json"
    SESSION_FILE_PATH: Path = BASE_DIR / "data" / "session.json"
    LOG_FILE_PATH: Path = BASE_DIR / "data" / "app.log"
    DATA_DIR: Path = BASE_DIR / "data"

    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration parameters."""
        errors = []
        if not cls.NAUKRI_EMAIL and not cls.NAUKRI_COOKIES:
            errors.append("Neither NAUKRI_EMAIL nor NAUKRI_COOKIES is set.")
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is not set.")
        if not cls.ALLOWED_TELEGRAM_USER_IDS:
            errors.append(
                "ALLOWED_TELEGRAM_USER_IDS is empty — the bot denies ALL users "
                "until at least one Telegram user ID is allowlisted. "
                "Get your ID from @userinfobot and set it in .env."
            )
        return errors

    @classmethod
    def get_timezone_name(cls) -> str:
        """Validated timezone name, falling back to Asia/Kolkata (never crash on bad env)."""
        tz = (cls.TIMEZONE or "").strip() or "Asia/Kolkata"
        try:
            import pytz
            pytz.timezone(tz)
            return tz
        except Exception:
            return "Asia/Kolkata"


# --- secret redaction (never log bearer tokens / passwords / cookies) ---
# Each entry: (pattern, replacement). Patterns WITH a capture group keep the
# prefix via \1; patterns without one are replaced wholesale.
_REDACT_PATTERNS = [
    (re.compile(r"nauk_at=[^;\s\"']+", re.IGNORECASE), "nauk_at=***REDACTED***"),
    (re.compile(r"(authorization['\"\s:=]+Bearer\s+)\S+", re.IGNORECASE), r"\1***REDACTED***"),
    (re.compile(r"(password['\"\s:=]+)\S+", re.IGNORECASE), r"\1***REDACTED***"),
]


def redact_secrets(text: str) -> str:
    """Mask bearer tokens, cookies and passwords in log/message text."""
    if not text:
        return text
    redacted = text
    for pat, repl in _REDACT_PATTERNS:
        try:
            redacted = pat.sub(repl, redacted)
        except Exception:
            continue
    token = Config.TELEGRAM_BOT_TOKEN
    if token and len(token) > 8 and token in redacted:
        redacted = redacted.replace(token, "***REDACTED-TOKEN***")
    pwd = Config.NAUKRI_PASSWORD
    if pwd and len(pwd) > 2 and pwd in redacted:
        redacted = redacted.replace(pwd, "***REDACTED***")
    email = Config.NAUKRI_EMAIL
    if email and len(email) > 3 and email in redacted:
        redacted = redacted.replace(email, "***REDACTED-EMAIL***")
    return redacted


def _redacting_filter(record):
    record["message"] = redact_secrets(record["message"])
    return True


def write_secure_json(path: Path, payload: dict) -> None:
    """Write JSON state with owner-only permissions (0o600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass

# Ensure data directory exists safely (owner-only on POSIX)
try:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(Config.DATA_DIR, 0o700)
    except Exception:
        pass
except Exception:
    pass

# Configure Loguru logger (redact secrets; file log at INFO — never DEBUG,
# so session tokens / response bodies can't land in app.log or /logs output)
logger.remove()
logger.add(sys.stdout, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>", filter=_redacting_filter)
try:
    logger.add(Config.LOG_FILE_PATH, rotation="5 MB", retention="3 days", level="INFO", encoding="utf-8", filter=_redacting_filter)
    try:
        os.chmod(Config.LOG_FILE_PATH, 0o600)
    except Exception:
        pass
except Exception:
    pass