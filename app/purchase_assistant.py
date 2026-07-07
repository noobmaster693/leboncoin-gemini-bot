from __future__ import annotations

import asyncio
from dataclasses import dataclass

from playwright.async_api import async_playwright

from .config import Settings
from .models import DealRecord


@dataclass
class PurchaseCheckResult:
    ok: bool
    reason: str


def preflight_purchase_checks(record: DealRecord, approved_max_total_eur: float, settings: Settings) -> PurchaseCheckResult:
    ev = record.evaluation
    listing = record.listing

    estimated_total = ev.estimated_total_cost_eur or listing.price_eur
    if estimated_total is None:
        return PurchaseCheckResult(False, "No reliable estimated total cost.")
    if estimated_total > approved_max_total_eur:
        return PurchaseCheckResult(False, f"Estimated total {estimated_total}€ exceeds approved max {approved_max_total_eur}€.")
    if estimated_total > settings.max_total_eur:
        return PurchaseCheckResult(False, f"Estimated total {estimated_total}€ exceeds global max {settings.max_total_eur}€.")
    if ev.decision.value != "buy_ready":
        return PurchaseCheckResult(False, f"Deal is not buy_ready: {ev.decision.value}")
    return PurchaseCheckResult(True, "Preflight checks passed.")


async def open_guided_checkout(record: DealRecord, approved_max_total_eur: float, settings: Settings) -> None:
    """
    Opens a visible browser at the listing after your confirmation.

    This function intentionally avoids bypassing CAPTCHA, 2FA, or anti-bot protections.
    It does not silently pay. It gives you a controlled place to add tested selectors later.
    """
    check = preflight_purchase_checks(record, approved_max_total_eur, settings)
    if not check.ok:
        raise RuntimeError(check.reason)

    settings.playwright_user_data_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(settings.playwright_user_data_dir),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = await browser.new_page()
        await page.goto(record.listing.url, wait_until="domcontentloaded")
        print("Opened listing in visible browser.")
        print("Do not bypass CAPTCHA/2FA. Verify price, seller, delivery, and listing status before paying.")
        print("Press Ctrl+C in this terminal when finished.")
        while True:
            await asyncio.sleep(5)


def run_guided_checkout(record: DealRecord, approved_max_total_eur: float, settings: Settings) -> None:
    asyncio.run(open_guided_checkout(record, approved_max_total_eur, settings))
