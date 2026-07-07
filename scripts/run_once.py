from __future__ import annotations

from app.config import get_settings
from app.email_watcher import LeboncoinEmailWatcher
from app.gemini_evaluator import GeminiDealEvaluator
from app.models import DealRecord
from app.notifier import Notifier
from app.rules import apply_hard_safety_rules
from app.storage import DealStore


def main() -> None:
    settings = get_settings()
    store = DealStore(settings.db_path)
    watcher = LeboncoinEmailWatcher(settings)
    evaluator = GeminiDealEvaluator(settings)
    notifier = Notifier(settings)

    listings = watcher.fetch_unseen_listings(max_results=10)
    print(f"Found {len(listings)} unseen Leboncoin email listings.")

    for listing in listings:
        if store.exists(listing.listing_id):
            print(f"Skipping existing listing {listing.listing_id}")
            continue
        evaluation = evaluator.evaluate(listing)
        record = DealRecord(listing=listing, evaluation=evaluation)
        safety = apply_hard_safety_rules(listing, evaluation, settings)
        store.save(record)
        notifier.send_deal_alert(record, safety)


if __name__ == "__main__":
    main()
