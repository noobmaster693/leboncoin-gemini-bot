from __future__ import annotations

import argparse
from email import message_from_bytes
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.email_watcher import listings_from_email_message
from app.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Leboncoin .eml parsing without Gmail/IMAP.")
    parser.add_argument("eml_path", help="Path to a downloaded .eml file")
    args = parser.parse_args()

    settings = get_settings()
    path = Path(args.eml_path)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    msg = message_from_bytes(path.read_bytes())
    listings = listings_from_email_message(
        msg,
        max_age_days=settings.max_email_age_days,
        max_links=settings.max_listing_links_per_email,
    )

    print(f"Subject: {msg.get('Subject', '')}")
    print(f"Parsed listing links: {len(listings)}")
    for item in listings:
        print(f"- {item.listing_id} | {item.title} | {item.url}")


if __name__ == "__main__":
    main()
