from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, async_playwright

from .config import Settings
from .models import DealRecord


@dataclass
class SellerMessageResult:
    ok: bool
    message: str


async def _first_visible(page: Page, selectors: Iterable[str], timeout_ms: int = 1500) -> Optional[Locator]:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=timeout_ms)
            return locator
        except PlaywrightTimeoutError:
            continue
    return None


async def send_seller_message(record: DealRecord, settings: Settings) -> SellerMessageResult:
    """
    Sends the suggested seller message through the visible Leboncoin website after the user clicks Ask seller.

    Requirements:
    - The user must already be logged into Leboncoin in the Playwright browser profile.
    - This does not bypass CAPTCHA, 2FA, login checks, or platform protections.
    - If the page changes or a check appears, it stops and reports the issue.
    """
    message = record.evaluation.seller_message_fr
    if not message:
        return SellerMessageResult(False, "No seller message was generated for this listing.")

    settings.playwright_user_data_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(settings.playwright_user_data_dir),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = await browser.new_page()
        await page.goto(record.listing.url, wait_until="domcontentloaded")

        await page.wait_for_timeout(2500)

        # If Leboncoin asks for login or CAPTCHA, stop. Do not bypass it.
        body_text = (await page.locator("body").inner_text(timeout=5000)).lower()
        if "captcha" in body_text or "robot" in body_text:
            await browser.close()
            return SellerMessageResult(False, "Leboncoin showed a CAPTCHA/robot check. Open manually; automation stopped.")
        if "se connecter" in body_text and "mot de passe" in body_text:
            await browser.close()
            return SellerMessageResult(False, "Leboncoin asks you to log in. Open once manually in the bot browser profile and log in.")

        contact_button = await _first_visible(
            page,
            [
                "text=Envoyer un message",
                "text=Contacter",
                "text=Message",
                "button:has-text('Message')",
                "button:has-text('Contacter')",
                "a:has-text('Message')",
                "a:has-text('Contacter')",
                "[data-qa-id*='contact']",
                "[data-test-id*='contact']",
            ],
        )
        if contact_button:
            await contact_button.click(timeout=5000)
            await page.wait_for_timeout(1500)

        input_box = await _first_visible(
            page,
            [
                "textarea",
                "[contenteditable='true']",
                "input[placeholder*='message' i]",
                "textarea[placeholder*='message' i]",
                "[role='textbox']",
            ],
        )
        if not input_box:
            await browser.close()
            return SellerMessageResult(False, "Could not find the Leboncoin message input box. Open the listing manually.")

        await input_box.fill(message)
        await page.wait_for_timeout(700)

        send_button = await _first_visible(
            page,
            [
                "button:has-text('Envoyer')",
                "button:has-text('Send')",
                "[aria-label*='Envoyer' i]",
                "[data-qa-id*='send']",
                "[data-test-id*='send']",
            ],
        )
        if not send_button:
            await browser.close()
            return SellerMessageResult(False, "Message filled, but send button was not found. Please send manually.")

        await send_button.click(timeout=5000)
        await page.wait_for_timeout(2000)

        await browser.close()
        return SellerMessageResult(True, "Seller message sent through Leboncoin.")


def send_seller_message_sync(record: DealRecord, settings: Settings) -> SellerMessageResult:
    return asyncio.run(send_seller_message(record, settings))
