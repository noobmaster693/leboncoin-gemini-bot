from __future__ import annotations

from datetime import datetime, timezone, timedelta
import email
from email.message import Message
from email.utils import parsedate_to_datetime
import hashlib
import imaplib
import re
from typing import List, Optional
from urllib.parse import urlparse

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


def _message_to_text(msg: Message) -> str:
    chunks: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type not in {"text/plain", "text/html"}:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/html":
                decoded = BeautifulSoup(decoded, "html.parser").get_text(" ", strip=True)
            chunks.append(decoded)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            chunks.append(payload.decode(charset, errors="replace"))
    return "\n".join(chunks)


def _extract_urls(text: str) -> list[str]:
    urls = []
    for match in URL_RE.findall(text):
        cleaned = match.rstrip(").,;]")
        if "leboncoin" in cleaned.lower():
            urls.append(cleaned)
    return list(dict.fromkeys(urls))


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

    has_listing_url = any(
        marker in u.lower()
        for u in urls
        for marker in ["/ad/", "/offre/", "ordinateurs", "informatique"]
    )
    has_hint = any(keyword in combined for keyword in LISTING_HINT_KEYWORDS)
    has_price = _extract_price(text) is not None

    # Require at least a listing-ish URL or a listing alert hint with price.
    return has_listing_url or (has_hint and has_price)


def listing_from_email_message(msg: Message, max_age_days: int = 3) -> Optional[ListingInput]:
    if _is_too_old(msg, max_age_days):
        return None

    subject = email.header.make_header(email.header.decode_header(msg.get("Subject", ""))).__str__()
    text = _message_to_text(msg)
    urls = _extract_urls(text)
    if not urls:
        return None

    if not _looks_like_listing_email(subject, text, urls):
        return None

    direct_urls = [u for u in urls if "/ad/" in u.lower() or "/offre/" in u.lower() or "ordinateurs" in u.lower()]
    url = direct_urls[0] if direct_urls else urls[0]
    listing_id = _listing_id_from_url_or_text(url, text)
    email_dt = _email_datetime(msg)

    return ListingInput(
        listing_id=listing_id,
        title=subject or "Leboncoin listing",
        url=url,
        price_eur=_extract_price(text),
        description=text[:2000],
        email_subject=subject,
        raw_text=text,
        first_seen_at=email_dt or datetime.now(timezone.utc),
    )


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
                listing = listing_from_email_message(msg, max_age_days=self.settings.max_email_age_days)
                if listing:
                    listings.append(listing)
        return listings
