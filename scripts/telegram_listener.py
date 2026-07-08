from __future__ import annotations

from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.storage import DealStore
from app.telegram_callbacks import TelegramCallbackHandler


def main() -> None:
    settings = get_settings()
    store = DealStore(settings.db_path)
    handler = TelegramCallbackHandler(settings, store)

    if not handler.enabled():
        raise SystemExit("Telegram is not configured. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env.")

    print("Telegram button listener started. Press Ctrl+C to stop.")
    while True:
        try:
            count = handler.poll_once(timeout=5)
            if count:
                print(f"Handled {count} Telegram button click(s).")
        except KeyboardInterrupt:
            print("Telegram listener stopped by user.")
            break
        except Exception:
            print("Telegram listener error:")
            traceback.print_exc()
            time.sleep(5)


if __name__ == "__main__":
    main()
