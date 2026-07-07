from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .config import Settings
from .models import DealEvaluation, Decision, ListingInput


@dataclass
class SafetyDecision:
    allowed_for_buy_alert: bool
    reasons: List[str]


def apply_hard_safety_rules(listing: ListingInput, evaluation: DealEvaluation, settings: Settings) -> SafetyDecision:
    reasons: list[str] = []

    if evaluation.decision != Decision.buy_ready:
        reasons.append(f"AI decision is {evaluation.decision.value}, not buy_ready.")

    if evaluation.deal_score < settings.min_buy_ready_score:
        reasons.append(f"Deal score {evaluation.deal_score} is below threshold {settings.min_buy_ready_score}.")

    if evaluation.confidence < settings.min_confidence:
        reasons.append(f"Confidence {evaluation.confidence:.2f} is below threshold {settings.min_confidence:.2f}.")

    estimated_total = evaluation.estimated_total_cost_eur or listing.price_eur
    if estimated_total is None:
        reasons.append("No reliable total cost estimate.")
    elif estimated_total > settings.max_total_eur:
        reasons.append(f"Estimated total cost {estimated_total:.2f}€ exceeds max {settings.max_total_eur}€.")

    joined_flags = " ".join(evaluation.red_flags).lower()
    forbidden_terms = ["liquid", "eau", "water", "corrosion", "bios", "icloud", "mdm", "stolen", "volé"]
    for term in forbidden_terms:
        if term in joined_flags:
            reasons.append(f"Forbidden red flag detected: {term}")
            break

    return SafetyDecision(allowed_for_buy_alert=not reasons, reasons=reasons)
