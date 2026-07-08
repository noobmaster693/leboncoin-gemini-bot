from __future__ import annotations

import html
from typing import Any, Optional

import requests

from .config import Settings
from .storage import DealStore


class TelegramCallbackHandler:
    def __init__(self, settings: Settings, store: DealStore):
        self.settings = settings
        self.store = store
        self.offset: Optional[int] = None

    @property
    def base_url(self) -> str:
        return f"https://api.telegram.org/bot{self.settings.telegram_bot_token}"

    def enabled(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    def poll_once(self, timeout: int = 1) -> int:
        if not self.enabled():
            return 0

        params: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["callback_query"],
        }
        if self.offset is not None:
            params["offset"] = self.offset

        response = requests.get(f"{self.base_url}/getUpdates", params=params, timeout=timeout + 5)
        response.raise_for_status()
        updates = response.json().get("result", [])

        handled = 0
        for update in updates:
            self.offset = int(update["update_id"]) + 1
            callback = update.get("callback_query")
            if not callback:
                continue
            self.handle_callback(callback)
            handled += 1

        return handled

    def handle_callback(self, callback: dict[str, Any]) -> None:
        data = callback.get("data", "")
        callback_id = callback.get("id")
        message = callback.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        message_id = message.get("message_id")

        action, _, listing_id = data.partition(":")
        record = self.store.get(listing_id) if listing_id else None

        if not record:
            self.answer_callback(callback_id, "Listing not found in local database.")
            return

        if action == "skip":
            self.store.update_status(listing_id, "skipped")
            self.answer_callback(callback_id, "Skipped.")
            if chat_id and message_id:
                self.edit_reply_markup(chat_id, message_id)
            return

        if action == "ask":
            self.store.update_status(listing_id, "needs_seller_message")
            suggested = record.evaluation.seller_message_fr or "No seller message was generated. Open the listing and ask for missing info."
            self.answer_callback(callback_id, "Seller message prepared.")
            if chat_id:
                self.send_message(
                    chat_id,
                    "<b>Copy/paste this message to the seller:</b>\n\n" + html.escape(suggested),
                )
            return

        if action == "buy":
            self.store.update_status(listing_id, "purchase_confirmed")
            self.answer_callback(callback_id, "Purchase confirmed locally.")
            if chat_id:
                max_total = record.evaluation.max_buy_price_eur or record.evaluation.estimated_total_cost_eur or record.listing.price_eur or self.settings.max_total_eur
                self.send_message(
                    chat_id,
                    "<b>Purchase confirmed.</b>\n\n"
                    "Run this on the PC to open guided checkout:\n"
                    f"<code>python scripts/open_checkout.py {html.escape(listing_id)} --approved-max-total {max_total}</code>",
                )
            return

        self.answer_callback(callback_id, f"Unknown action: {action}")

    def answer_callback(self, callback_id: Optional[str], text: str) -> None:
        if not callback_id:
            return
        requests.post(
            f"{self.base_url}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": text, "show_alert": False},
            timeout=10,
        ).raise_for_status()

    def send_message(self, chat_id: int, text: str) -> None:
        requests.post(
            f"{self.base_url}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        ).raise_for_status()

    def edit_reply_markup(self, chat_id: int, message_id: int) -> None:
        requests.post(
            f"{self.base_url}/editMessageReplyMarkup",
            json={"chat_id": chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": []}},
            timeout=10,
        ).raise_for_status()
