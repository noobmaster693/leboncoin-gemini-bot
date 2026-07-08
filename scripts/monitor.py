from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
import os
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.email_watcher import LeboncoinEmailWatcher
from app.gemini_evaluator import GeminiDealEvaluator
from app.listing_fetcher import enrich_listing_from_fetch, fetch_listing_details
from app.models import DealRecord, ListingInput
from app.notifier import Notifier
from app.rules import apply_hard_safety_rules
from app.storage import DealStore


async def enrich_if_enabled(listing: ListingInput, settings) -> tuple[ListingInput | None, str]:
    if not settings.fetch_listing_details:
        return listing, "Listing-page fetch disabled."

    fetched = await fetch_listing_details(listing, settings)
    if fetched.should_ignore:
        return None, fetched.reason
    if not fetched.ok:
        return listing, fetched.reason
    return enrich_listing_from_fetch(listing, fetched), fetched.reason


def scan_once() -> int:
    settings = get_settings()
    store = DealStore(settings.db_path)
    watcher = LeboncoinEmailWatcher(settings)
    evaluator = GeminiDealEvaluator(settings)
    notifier = Notifier(settings)

    listings = watcher.fetch_unseen_listings(max_results=20)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Found {len(listings)} unseen Leboncoin email listing(s).")

    processed = 0
    for listing in listings:
        try:
            if store.exists(listing.listing_id):
                print(f"Skipping existing listing {listing.listing_id}")
                continue

            enriched_listing, fetch_reason = asyncio.run(enrich_if_enabled(listing, settings))
            if enriched_listing is None:
                print(f"Ignoring non-deal email/link: {listing.title} | {fetch_reason}")
                continue

            listing = enriched_listing
            print(f"Evaluating: {listing.title} | {listing.price_eur}€ | {fetch_reason}")
            evaluation = evaluator.evaluate(listing)
            record = DealRecord(listing=listing, evaluation=evaluation)
            safety = apply_hard_safety_rules(listing, evaluation, settings)
            store.save(record)
            notifier.send_deal_alert(record, safety)
            processed += 1
        except Exception:
            print(f"Error while processing listing {listing.listing_id} | {listing.title}")
            traceback.print_exc()
            print("Continuing with next listing...")
            continue

    return processed


def main() -> None:
    interval_seconds = int(os.getenv("MONITOR_INTERVAL_SECONDS", "60"))
    print("Leboncoin Gemini Bot monitor started.")
    print(f"Checking every {interval_seconds} seconds. Press Ctrl+C to stop.")

    while True:
        try:
            scan_once()
        except KeyboardInterrupt:
            print("Monitor stopped by user.")
            break
        except Exception:
            print("Error during scan:")
            traceback.print_exc()

        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
