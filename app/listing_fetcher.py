from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from .config import Settings
from .models import ListingInput

PRICE_RE = re.compile(r"(?<!\d)(\d{1,5}(?:[\s.,]\d{3})?)(?:\s?€|\s?EUR)", re.IGNORECASE)

NON_DEAL_PAGE_MARKERS = [
    "votre annonce",
    "votre annonce est en ligne",
    "nouveau message pour",
    "messages",
    "mes annonces",
    "mon compte",
    "se connecter",
    "captcha",
    "robot",
]

LAPTOP_HINTS = [
    "ordinateur", "pc portable", "laptop", "macbook", "thinkpad", "latitude", "vostro", "elitebook",
    "probook", "ideapad", "vivobook", "zenbook", "core i", "ryzen", "ssd", "ram", "écran", "ecran"
]


@dataclass
class FetchedListing:
    ok: bool
    should_ignore: bool
    reason: str
    title: Optional[str] = None
    description: Optional[str] = None
    price_eur: Optional[float] = None
    location: Optional[str] = None
    final_url: Optional[str] = None
    body_text: str = ""


def _extract_price(text: str) -> Optional[float]:
    match = PRICE_RE.search(text.replace("\xa0", " "))
    if not match:
        return None
    value = match.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def _compact_text(text: str, limit: int = 5000) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:limit]


def _looks_like_non_deal_page(text: str, final_url: str) -> Optional[str]:
    low = text.lower()
    url = final_url.lower()
    if "messagerie" in url or "/messages" in url or "/account" in url:
        return "Link opened an account/messages page, not a public listing."
    if "captcha" in low or "robot" in low:
        return "Leboncoin showed a robot/CAPTCHA page."
    if "votre annonce" in low or "nouveau message pour" in low:
        return "Own-listing or seller-message notification page."
    if "se connecter" in low and "mot de passe" in low:
        return "Login page, not a public listing page."
    return None


def _has_laptop_signal(text: str) -> bool:
    low = text.lower()
    return any(hint in low for hint in LAPTOP_HINTS)


async def fetch_listing_details(listing: ListingInput, settings: Settings) -> FetchedListing:
    """
    Opens the exact Leboncoin link from the saved-search email and extracts visible listing text.

    This uses a normal visible browser profile and does not bypass login, CAPTCHA, or platform protections.
    If the link is not a public listing, it returns should_ignore=True.
    """
    settings.playwright_user_data_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(settings.playwright_user_data_dir),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = await browser.new_page()
        try:
            await page.goto(listing.url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(2500)
            final_url = page.url
            title = await page.title()
            body = await page.locator("body").inner_text(timeout=8000)
            body_compact = _compact_text(body)
        except PlaywrightTimeoutError:
            await browser.close()
            return FetchedListing(ok=False, should_ignore=False, reason="Timed out opening listing URL.")
        except Exception as exc:
            await browser.close()
            return FetchedListing(ok=False, should_ignore=False, reason=f"Could not fetch listing page: {exc}")

        await browser.close()

    ignore_reason = _looks_like_non_deal_page(body_compact, final_url)
    if ignore_reason:
        return FetchedListing(
            ok=True,
            should_ignore=True,
            reason=ignore_reason,
            title=title,
            final_url=final_url,
            body_text=body_compact,
        )

    if not _has_laptop_signal(body_compact):
        return FetchedListing(
            ok=True,
            should_ignore=True,
            reason="Fetched page does not look like a laptop/computer listing.",
            title=title,
            final_url=final_url,
            body_text=body_compact,
        )

    price = _extract_price(body_compact) or listing.price_eur
    description = body_compact

    return FetchedListing(
        ok=True,
        should_ignore=False,
        reason="Fetched public listing details.",
        title=title or listing.title,
        description=description,
        price_eur=price,
        final_url=final_url,
        body_text=body_compact,
    )


def enrich_listing_from_fetch(listing: ListingInput, fetched: FetchedListing) -> ListingInput:
    if not fetched.ok or fetched.should_ignore:
        return listing

    title = fetched.title or listing.title
    description = fetched.description or listing.description
    url = fetched.final_url or listing.url
    price = fetched.price_eur if fetched.price_eur is not None else listing.price_eur

    return listing.model_copy(
        update={
            "title": title,
            "url": url,
            "price_eur": price,
            "description": description[:2500],
            "raw_text": (
                "Fetched Leboncoin listing page:\n"
                + description[:6000]
                + "\n\nOriginal email text:\n"
                + listing.raw_text[:2000]
            ),
        }
    )
