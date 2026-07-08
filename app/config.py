from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


def _bool_env(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    # Flash is the default because Pro may have 0 free-tier quota on some accounts.
    # Use GEMINI_MODEL=gemini-2.5-pro only if your Google API account has quota/billing for it.
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_fallback_models: tuple[str, ...] = tuple(
        m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-2.5-flash,gemini-1.5-flash").split(",") if m.strip()
    )
    gemini_temperature: float = float(os.getenv("GEMINI_TEMPERATURE", "0.2"))
    # Set to -1 to disable thinking budget. Some Gemini SDK/model combinations may ignore this.
    gemini_thinking_budget: int = int(os.getenv("GEMINI_THINKING_BUDGET", "4096"))

    imap_host: str = os.getenv("IMAP_HOST", "imap.gmail.com")
    imap_port: int = int(os.getenv("IMAP_PORT", "993"))
    imap_user: str = os.getenv("IMAP_USER", "")
    imap_password: str = os.getenv("IMAP_PASSWORD", "")
    imap_folder: str = os.getenv("IMAP_FOLDER", "INBOX")
    lbc_email_filter: str = os.getenv("LBC_EMAIL_FILTER", "leboncoin")
    max_email_age_days: int = int(os.getenv("MAX_EMAIL_AGE_DAYS", "3"))
    max_listing_links_per_email: int = int(os.getenv("MAX_LISTING_LINKS_PER_EMAIL", "25"))

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    max_total_eur: int = int(os.getenv("MAX_TOTAL_EUR", "120"))
    min_buy_ready_score: int = int(os.getenv("MIN_BUY_READY_SCORE", "88"))
    min_confidence: float = float(os.getenv("MIN_CONFIDENCE", "0.72"))
    daily_purchase_limit_eur: int = int(os.getenv("DAILY_PURCHASE_LIMIT_EUR", "250"))

    purchase_mode: str = os.getenv("PURCHASE_MODE", "guided")
    fetch_listing_details: bool = _bool_env("FETCH_LISTING_DETAILS", "true")
    playwright_user_data_dir: Path = Path(os.getenv("PLAYWRIGHT_USER_DATA_DIR", ".browser-profile"))
    db_path: Path = Path(os.getenv("DB_PATH", "deals.sqlite3"))


def get_settings() -> Settings:
    return Settings()
