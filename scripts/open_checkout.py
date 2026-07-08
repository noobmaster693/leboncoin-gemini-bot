from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.purchase_assistant import run_guided_checkout
from app.storage import DealStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("listing_id")
    parser.add_argument("--approved-max-total", type=float, required=True)
    args = parser.parse_args()

    settings = get_settings()
    store = DealStore(settings.db_path)
    record = store.get(args.listing_id)
    if not record:
        raise SystemExit(f"Listing not found: {args.listing_id}")

    run_guided_checkout(record, args.approved_max_total, settings)


if __name__ == "__main__":
    main()
