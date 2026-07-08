from __future__ import annotations

from datetime import datetime, timezone, timedelta
import email
from email.message import Message
from email.utils import parsedate_to_datetime
import hashlib
import html as html_lib
import imaplib
import re
from typing import List, Optional
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from .config import Settings
from .models import ListingInput

URL_RE = re.compile(r"https?://[^\s\"'<>]+")
PRICE_RE = re.compile(r"(?<!\d)(\d{1,5}(?:[\s.,]\d{3})?)(?:\s?€|\s?EUR)", re.IGNORECASE)

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
    "message",
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


def _message_to_text(msg: Message) -> str:
    chunks: list[str] = []
    if msg.is_multipart():
        parts = msg.walk()
    else:
        parts = [msg]

    for part in parts:
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        decoded = payload.decode(charset, errors="replace")
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


def _is_probable_listing_url(url: str) -> bool:
    low = url.lower()
    if any(marker in low for marker in TRACKING_OR_ACCOUNT_URL_MARKERS):
        return False
    return any(marker in low for marker in ["/ad/", "/offre/", "ordinateurs", "informatique"])


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

    direct_urls = [u for u in urls if _is_probable_listing_url(u)]
    # Digest emails may contain many listing links. Treat each as its own listing candidate.
    # If no direct listing URL is found, keep one fallback URL so the fetcher can reject it later.
    candidate_urls = direct_urls[:max_links] if direct_urls else urls[:1]
    email_dt = _email_datetime(msg)
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
                status, msg_data = imap.fetch(msg_id, "(RFC822)")
                if status != "OK" or not msg_data:
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                listings.extend(
                    listings_from_email_message(
                        msg,
                        max_age_days=self.settings.max_email_age_days,
                        max_links=self.settings.max_listing_links_per_email,
                    )
                )
        return listings
