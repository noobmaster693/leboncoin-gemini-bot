from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .config import get_settings
from .gemini_evaluator import GeminiDealEvaluator
from .models import DealRecord, ListingInput
from .notifier import Notifier
from .purchase_assistant import preflight_purchase_checks
from .rules import apply_hard_safety_rules
from .storage import DealStore

app = FastAPI(title="Leboncoin Gemini Deal Bot")
settings = get_settings()
store = DealStore(settings.db_path)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/listings")
def listings(limit: int = 25):
    return [record.model_dump() for record in store.list_recent(limit)]


@app.post("/evaluate")
def evaluate_listing(listing: ListingInput):
    evaluator = GeminiDealEvaluator(settings)
    evaluation = evaluator.evaluate(listing)
    record = DealRecord(listing=listing, evaluation=evaluation)
    safety = apply_hard_safety_rules(listing, evaluation, settings)
    store.save(record)
    Notifier(settings).send_deal_alert(record, safety)
    return {"record": record.model_dump(), "safety": safety.__dict__}


@app.post("/confirm-purchase/{listing_id}")
def confirm_purchase(listing_id: str, approved_max_total_eur: float):
    record = store.get(listing_id)
    if not record:
        raise HTTPException(status_code=404, detail="Listing not found")
    check = preflight_purchase_checks(record, approved_max_total_eur, settings)
    if not check.ok:
        raise HTTPException(status_code=400, detail=check.reason)
    store.update_status(listing_id, "purchase_confirmed")
    return {
        "ok": True,
        "message": "Preflight checks passed. Run scripts/open_checkout.py with this listing_id to open guided checkout.",
        "listing_id": listing_id,
    }
