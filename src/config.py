import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Config:
    # Naukri Credentials
    NAUKRI_EMAIL: str = os.getenv("NAUKRI_EMAIL", "").strip()
    NAUKRI_PASSWORD: str = os.getenv("NAUKRI_PASSWORD", "").strip()

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    _allowed_users_raw = os.getenv("ALLOWED_TELEGRAM_USER_IDS", "").strip()
    ALLOWED_TELEGRAM_USER_IDS: list[int] = [
        int(uid.strip()) for uid in _allowed_users_raw.split(",") if uid.strip().isdigit()
    ]

    # Scheduling
    DAILY_UPDATE_TIME: str = os.getenv("DAILY_UPDATE_TIME", "09:00").strip()
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata").strip()

    # File Paths
    SESSION_FILE_PATH: Path = BASE_DIR / "data" / "session.json"
    LOG_FILE_PATH: Path = BASE_DIR / "data" / "app.log"
    DATA_DIR: Path = BASE_DIR / "data"

    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration parameters."""
        errors = []
        if not cls.NAUKRI_EMAIL:
            errors.append("NAUKRI_EMAIL is not set in environment or .env file.")
        if not cls.NAUKRI_PASSWORD:
            errors.append("NAUKRI_PASSWORD is not set in environment or .env file.")
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is not set in environment or .env file.")
        return errors

# Ensure data directory exists safely
try:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# Configure Loguru logger
logger.remove()
logger.add(sys.stdout, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
try:
    logger.add(Config.LOG_FILE_PATH, rotation="5 MB", retention="3 days", level="DEBUG", encoding="utf-8")
except Exception:
    pass