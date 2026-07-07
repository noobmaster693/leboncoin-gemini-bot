from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Decision(str, Enum):
    buy_ready = "buy_ready"
    ask_seller = "ask_seller"
    skip = "skip"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    unknown = "unknown"


class ListingInput(BaseModel):
    listing_id: str = Field(description="Stable ID from URL/email when available.")
    source: str = "leboncoin_email"
    title: str
    url: str
    price_eur: Optional[float] = None
    location: Optional[str] = None
    seller_name: Optional[str] = None
    description: str = ""
    email_subject: Optional[str] = None
    raw_text: str = ""
    image_urls: List[str] = Field(default_factory=list)
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DealEvaluation(BaseModel):
    decision: Decision = Field(description="buy_ready, ask_seller, or skip")
    deal_score: int = Field(ge=0, le=100, description="Overall deal score for broken-laptop flipping.")
    confidence: float = Field(ge=0, le=1, description="Confidence based only on listing info.")
    risk_level: RiskLevel

    model_guess: str = Field(description="Likely laptop model/specs, or 'unknown'.")
    cpu_guess: str = Field(description="Likely CPU, generation, or 'unknown'.")
    condition_summary: str = Field(description="Concise summary of damage/condition.")
    reason: str = Field(description="Why this decision was made.")

    red_flags: List[str] = Field(default_factory=list)
    missing_info: List[str] = Field(default_factory=list)
    required_checks_before_buying: List[str] = Field(default_factory=list)

    estimated_working_resale_eur: Optional[float] = None
    estimated_repair_cost_eur: Optional[float] = None
    estimated_total_cost_eur: Optional[float] = None
    max_buy_price_eur: Optional[float] = Field(default=None, description="Maximum total cost the buyer should accept.")
    expected_profit_eur: Optional[float] = None

    seller_message_fr: Optional[str] = Field(
        default=None,
        description="Short French message to ask seller only if decision is ask_seller."
    )


class DealRecord(BaseModel):
    listing: ListingInput
    evaluation: DealEvaluation
    status: str = "new"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
