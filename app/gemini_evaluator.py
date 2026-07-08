from __future__ import annotations

import json
from typing import Any

from google import genai
from pydantic import ValidationError

from .config import Settings
from .models import DealEvaluation, ListingInput


SYSTEM_RULES = """
You are a strict deal evaluator for buying broken laptops on Leboncoin in France.
Goal: find profitable broken-laptop flips while avoiding risky purchases.

Use only information in the listing. Do not invent specs or prices.

Take extra care before marking a listing buy_ready. Think through:
- exact model/spec uncertainty
- likely repair cost
- likely resale value
- hidden damage risk
- whether the seller description is enough to buy without questions

Decision rules:
- buy_ready: only if model/specs/damage/price are clear enough and risk is acceptable.
- ask_seller: if it could be good but key info is missing.
- skip: if price is too high, model unknown, damage is too risky, or red flags appear.

Very risky / usually skip:
- liquid damage, water, corrosion
- no power / does not turn on, unless price is extremely low and parts value is obvious
- BIOS password, iCloud/MDM/activation lock, stolen suspicion
- seller refuses photos/testing or description is too vague
- cracked motherboard, burnt smell, charging IC issue

Often acceptable when price is low:
- broken screen but boots externally
- missing SSD/RAM
- dead battery
- keyboard/trackpad damage
- damaged case or hinges if the model has parts value

Always require the final buyer to confirm total price, delivery fee, seller, listing ID, and availability before payment.
Output strict JSON matching the schema.
""".strip()


def _build_prompt(listing: ListingInput) -> str:
    return f"""
{SYSTEM_RULES}

Analyze this Leboncoin listing for broken-laptop resale/repair flipping.

Listing:
- ID: {listing.listing_id}
- Title: {listing.title}
- URL: {listing.url}
- Price EUR: {listing.price_eur}
- Location: {listing.location}
- Seller: {listing.seller_name}
- Description: {listing.description}
- Raw email/listing text: {listing.raw_text[:6000]}
- Image URLs, if any: {listing.image_urls}

Return a DealEvaluation JSON object.
""".strip()


class GeminiDealEvaluator:
    def __init__(self, settings: Settings):
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is missing. Add it to .env.")
        self.settings = settings
        self.client = genai.Client(api_key=settings.gemini_api_key)

    def _make_config(self, include_thinking: bool = True) -> dict[str, Any]:
        config: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_schema": DealEvaluation.model_json_schema(),
            "temperature": self.settings.gemini_temperature,
        }
        if include_thinking and self.settings.gemini_thinking_budget >= 0:
            config["thinking_config"] = {"thinking_budget": self.settings.gemini_thinking_budget}
        return config

    def evaluate(self, listing: ListingInput) -> DealEvaluation:
        prompt = _build_prompt(listing)

        try:
            response = self.client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=self._make_config(include_thinking=True),
            )
        except Exception as exc:
            # Some SDK/model combinations do not accept thinking_config.
            if "thinking" not in str(exc).lower() and "extra" not in str(exc).lower():
                raise
            response = self.client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=self._make_config(include_thinking=False),
            )

        text = getattr(response, "text", "") or ""
        try:
            return DealEvaluation.model_validate_json(text)
        except ValidationError as exc:
            # Fallback for cases where SDK returns JSON with surrounding text.
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return DealEvaluation.model_validate_json(text[start : end + 1])
            raise RuntimeError(f"Gemini returned invalid evaluation JSON: {text}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Gemini returned invalid JSON: {text}") from exc
