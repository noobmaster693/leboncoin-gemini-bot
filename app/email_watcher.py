from __future__ import annotations

from datetime import datetime, timezone, timedelta
import email
from email.message import Message
from email.utils import parsedate_to_datetime
import hashlib
import html as html_lib
import imaplib
import quopri
import re
from typing import List, Optional
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from .config import Settings
from .models import ListingInput

URL_RE = re.compile(r"https?://[^\s\"'<>]+")
PRICE_RE = re.compile(r"(?<!\d)(\d{1,5}(?:[\s.,]\d{3})?)(?:\s?€|\s?EUR)", re.IGNORECASE)
VI_LISTING_RE = re.compile(r"/vi/\d+\.htm", re.IGNORECASE)
RAW_VI_URL_RE = re.compile(r"https?://www\.leboncoin\.fr/vi/\d+\.htm", re.IGNORECASE)
BACKGROUND_IMAGE_RE = re.compile(r"background-image:\s*url\(([^)]+)\)", re.IGNORECASE)

IGNORE_SUBJECT_KEYWORDS = [
    "suppression de vos annonces",
    "supprime",
    "mot de passe",
    "connexion",
    "sécurité",
    "securite",
    "paiement",
    "facture",
    "newsletter",
    "conditions générales",
    # Own-account / seller-side notifications, not buyer deal alerts.
    "votre annonce",
    "votre annonce est en ligne",
    "est en ligne",
    "annonce a été publiée",
    "annonce a ete publiee",
    "nouveau message pour",
    "nouveaux messages pour",
    "message pour votre annonce",
    "vous avez reçu un message",
    "vous avez recu un message",
    "livraison est en ligne",
]

LISTING_HINT_KEYWORDS = [
    "nouvelle annonce",
    "nouvelles annonces",
    "recherche sauvegardée",
    "recherche sauvegardee",
    "alerte",
    "ordinateur",
    "pc portable",
    "laptop",
    "macbook",
    "thinkpad",
    "latitude",
    "vostro",
]

TRACKING_OR_ACCOUNT_URL_MARKERS = [
    "unsubscribe",
    "preferences",
    "account",
    "messagerie",
    "auth",
    "login",
    "aide",
    "assistance",
    "legal",
    "cgu",
]


def _normalize_url(url: str) -> str:
    cleaned = html_lib.unescape(url.strip()).rstrip(").,;]")
    parsed = urlparse(cleaned)

    # Some email systems wrap links. If the wrapper contains a real leboncoin URL in a query parameter,
    # unwrap it so the rest of the bot can evaluate the real destination.
    query = parse_qs(parsed.query)
    for key in ["url", "u", "target", "redirect", "redirect_url", "r"]:
        for value in query.get(key, []):
            decoded = unquote(value)
            if "leboncoin" in decoded.lower() and decoded.startswith("http"):
                return decoded.rstrip(").,;]")
    return cleaned


def _decode_part(part: Message) -> Optional[str]:
    payload = part.get_payload(decode=True)
    if not payload:
        return None
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _html_parts(msg: Message) -> list[str]:
    parts = msg.walk() if msg.is_multipart() else [msg]
    html_parts: list[str] = []
    for part in parts:
        if part.get_content_type() != "text/html":
            continue
        decoded = _decode_part(part)
        if decoded:
            html_parts.append(decoded)
    return html_parts


def _message_to_text(msg: Message) -> str:
    chunks: list[str] = []
    parts = msg.walk() if msg.is_multipart() else [msg]

    for part in parts:
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        decoded = _decode_part(part)
        if not decoded:
            continue
        if content_type == "text/html":
            soup = BeautifulSoup(decoded, "html.parser")
            visible_text = soup.get_text(" ", strip=True)
            hrefs = []
            for tag in soup.find_all(["a", "area"]):
                href = tag.get("href")
                if href:
                    hrefs.append(_normalize_url(href))
            decoded = visible_text + "\n" + "\n".join(hrefs)
        chunks.append(decoded)
    return "\n".join(chunks)


def _extract_urls(text: str) -> list[str]:
    urls = []
    for match in URL_RE.findall(text):
        cleaned = _normalize_url(match)
        if "leboncoin" in cleaned.lower():
            urls.append(cleaned)
    return list(dict.fromkeys(urls))


def _extract_raw_listing_urls(raw: bytes) -> list[str]:
    """Last-resort extraction from the raw RFC822 bytes.

    This handles Gmail/IMAP edge cases where the parsed HTML body loses hrefs, plus
    Leboncoin's quoted-printable line wrapping.
    """
    variants = []
    for blob in [raw, quopri.decodestring(raw)]:
        text = blob.decode("utf-8", errors="replace")
        text = text.replace("=\r\n", "").replace("=\n", "")
        text = html_lib.unescape(text)
        variants.append(text)

    urls: list[str] = []
    for text in variants:
        for match in RAW_VI_URL_RE.findall(text):
            urls.append(_normalize_url(match))
        for match in URL_RE.findall(text):
            cleaned = _normalize_url(match)
            if "leboncoin" in cleaned.lower() and _is_probable_listing_url(cleaned):
                urls.append(cleaned)
    return list(dict.fromkeys(urls))


def _is_probable_listing_url(url: str) -> bool:
    low = url.lower()
    if any(marker in low for marker in TRACKING_OR_ACCOUNT_URL_MARKERS):
        return False
    return any(marker in low for marker in ["/ad/", "/offre/", "/vi/", "ordinateurs", "informatique"]) or bool(VI_LISTING_RE.search(low))


def _extract_price(text: str) -> Optional[float]:
    match = PRICE_RE.search(text.replace("\xa0", " "))
    if not match:
        return None
    value = match.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def _listing_id_from_url_or_text(url: str, text: str) -> str:
    parsed = urlparse(url)
    candidates = re.findall(r"\d{8,}", parsed.path + " " + parsed.query)
    if candidates:
        return candidates[-1]
    return hashlib.sha256((url + text[:500]).encode("utf-8")).hexdigest()[:16]


def _email_datetime(msg: Message) -> Optional[datetime]:
    date_header = msg.get("Date")
    if not date_header:
        return None
    try:
        dt = parsedate_to_datetime(date_header)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _is_too_old(msg: Message, max_age_days: int) -> bool:
    if max_age_days <= 0:
        return False
    dt = _email_datetime(msg)
    if not dt:
        return False
    return dt < datetime.now(timezone.utc) - timedelta(days=max_age_days)


def _is_own_account_or_message_email(combined: str) -> bool:
    return any(keyword in combined for keyword in IGNORE_SUBJECT_KEYWORDS)


def _looks_like_listing_email(subject: str, text: str, urls: list[str]) -> bool:
    combined = f"{subject}\n{text[:3000]}".lower()

    # Hard reject before AI: these are not deal alerts, even if they contain a Leboncoin URL or price.
    if _is_own_account_or_message_email(combined):
        return False

    direct_urls = [u for u in urls if _is_probable_listing_url(u)]
    has_listing_url = bool(direct_urls)
    has_hint = any(keyword in combined for keyword in LISTING_HINT_KEYWORDS)
    has_price = _extract_price(text) is not None

    # Require at least a listing-ish URL or a listing alert hint with price.
    return has_listing_url or (has_hint and has_price)


def _extract_card_image_url(card) -> Optional[str]:
    for tag in card.find_all(style=True):
        style = tag.get("style") or ""
        match = BACKGROUND_IMAGE_RE.search(style)
        if match:
            return html_lib.unescape(match.group(1).strip("'\""))
    img = card.find("img")
    if img and img.get("src"):
        return html_lib.unescape(img.get("src"))
    return None


def _extract_listing_cards_from_html(msg: Message, subject: str, email_dt: Optional[datetime], max_links: int) -> list[ListingInput]:
    listings: list[ListingInput] = []
    seen_ids: set[str] = set()

    for html in _html_parts(msg):
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            url = _normalize_url(a["href"])
            if _is_probable_listing_url(url):
                links.append((a, url))

        for a, url in links:
            listing_id = _listing_id_from_url_or_text(url, "")
            if listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)

            card = a.find_parent("table") or a.find_parent("tr") or a
            card_text = card.get_text(" ", strip=True)
            span_texts = [s.get_text(" ", strip=True) for s in card.find_all("span")]
            span_texts = [s for s in span_texts if s]

            title = span_texts[0] if span_texts else (a.get_text(" ", strip=True) or subject)
            price = None
            location = None
            for text in span_texts[1:]:
                if price is None and _extract_price(text) is not None:
                    price = _extract_price(text)
                    continue
                if location is None and _extract_price(text) is None:
                    location = text

            if price is None:
                price = _extract_price(card_text)

            image_url = _extract_card_image_url(card)
            raw_text = f"Leboncoin saved-search email card:\nTitle: {title}\nPrice: {price if price is not None else 'unknown'}€\nLocation: {location or 'unknown'}\nCard text: {card_text}\nEmail subject: {subject}"

            listings.append(
                ListingInput(
                    listing_id=listing_id,
                    title=title,
                    url=url,
                    price_eur=price,
                    location=location,
                    description=card_text[:2000],
                    email_subject=subject,
                    raw_text=raw_text,
                    image_urls=[image_url] if image_url else [],
                    first_seen_at=email_dt or datetime.now(timezone.utc),
                )
            )
            if len(listings) >= max_links:
                break
        if len(listings) >= max_links:
            break

    return listings


def _build_listing_inputs_from_urls(
    *,
    subject: str,
    text: str,
    urls: list[str],
    email_dt: Optional[datetime],
    max_links: int,
) -> list[ListingInput]:
    direct_urls = [u for u in urls if _is_probable_listing_url(u)]
    candidate_urls = direct_urls[:max_links] if direct_urls else urls[:1]
    price = _extract_price(text)

    listings: list[ListingInput] = []
    for index, url in enumerate(candidate_urls, start=1):
        listing_id = _listing_id_from_url_or_text(url, text)
        title = subject or "Leboncoin listing"
        if len(candidate_urls) > 1:
            title = f"{title} | listing {index}/{len(candidate_urls)}"

        listings.append(
            ListingInput(
                listing_id=listing_id,
                title=title,
                url=url,
                price_eur=price,
                description=text[:2000],
                email_subject=subject,
                raw_text=text,
                first_seen_at=email_dt or datetime.now(timezone.utc),
            )
        )
    return listings


def listings_from_email_message(msg: Message, max_age_days: int = 3, max_links: int = 25) -> list[ListingInput]:
    if _is_too_old(msg, max_age_days):
        return []

    subject = email.header.make_header(email.header.decode_header(msg.get("Subject", ""))).__str__()
    text = _message_to_text(msg)
    urls = _extract_urls(text)
    if not urls:
        return []

    if not _looks_like_listing_email(subject, text, urls):
        return []

    # Prefer card-level parsing. This avoids opening the website for every card and gives each listing
    # its own title, price, location, and image from the email itself.
    card_listings = _extract_listing_cards_from_html(msg, subject, _email_datetime(msg), max_links)
    if card_listings:
        return card_listings

    return _build_listing_inputs_from_urls(
        subject=subject,
        text=text,
        urls=urls,
        email_dt=_email_datetime(msg),
        max_links=max_links,
    )


def listings_from_raw_email(raw: bytes, max_age_days: int = 3, max_links: int = 25) -> list[ListingInput]:
    msg = email.message_from_bytes(raw)
    parsed = listings_from_email_message(msg, max_age_days=max_age_days, max_links=max_links)
    if parsed:
        return parsed

    subject = email.header.make_header(email.header.decode_header(msg.get("Subject", ""))).__str__()
    text = _message_to_text(msg)
    raw_urls = _extract_raw_listing_urls(raw)
    if not raw_urls:
        return []

    return _build_listing_inputs_from_urls(
        subject=subject,
        text=text or raw.decode("utf-8", errors="replace")[:3000],
        urls=raw_urls,
        email_dt=_email_datetime(msg),
        max_links=max_links,
    )


def listing_from_email_message(msg: Message, max_age_days: int = 3) -> Optional[ListingInput]:
    # Backward-compatible helper for older imports/tests.
    listings = listings_from_email_message(msg, max_age_days=max_age_days, max_links=1)
    return listings[0] if listings else None


class LeboncoinEmailWatcher:
    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch_unseen_listings(self, max_results: int = 10) -> List[ListingInput]:
        if not self.settings.imap_user or not self.settings.imap_password:
            raise ValueError("IMAP_USER/IMAP_PASSWORD missing. Add them to .env.")

        listings: list[ListingInput] = []
        with imaplib.IMAP4_SSL(self.settings.imap_host, self.settings.imap_port) as imap:
            imap.login(self.settings.imap_user, self.settings.imap_password)
            imap.select(self.settings.imap_folder)

            since_date = (datetime.now(timezone.utc) - timedelta(days=self.settings.max_email_age_days)).strftime("%d-%b-%Y")
            criteria = f'(UNSEEN FROM "{self.settings.lbc_email_filter}" SINCE "{since_date}")'
            status, data = imap.search(None, criteria)
            if status != "OK":
                return []

            ids = data[0].split()[-max_results:]
            for msg_id in ids:
                # BODY.PEEK[] prevents the act of fetching from marking the email as read.
                status, msg_data = imap.fetch(msg_id, "(BODY.PEEK[])")
                if status != "OK" or not msg_data:
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                parsed_listings = listings_from_raw_email(
                    raw,
                    max_age_days=self.settings.max_email_age_days,
                    max_links=self.settings.max_listing_links_per_email,
                )
                print(f"Parsed email '{msg.get('Subject', '')[:80]}' -> {len(parsed_listings)} listing link(s).")
                listings.extend(parsed_listings)

                if self.settings.mark_emails_seen_after_parse:
                    imap.store(msg_id, "+FLAGS", "\\Seen")
        return listings
