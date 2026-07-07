from __future__ import annotations

from app.config import get_settings
from app.gemini_evaluator import GeminiDealEvaluator
from app.models import ListingInput


def main() -> None:
    listing = ListingInput(
        listing_id="sample-001",
        title="Dell Vostro 3510 i5 écran cassé",
        url="https://www.leboncoin.fr/ad/ordinateurs/sample-001",
        price_eur=80,
        location="Paris",
        description="Dell Vostro 15 3510 i5-1135G7. Ecran cassé mais fonctionne sur HDMI. Chargeur inclus. SSD retiré.",
        raw_text="Dell Vostro 15 3510 i5-1135G7. Ecran cassé mais fonctionne sur HDMI. Chargeur inclus. SSD retiré. Prix 80€.",
    )
    evaluator = GeminiDealEvaluator(get_settings())
    print(evaluator.evaluate(listing).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
