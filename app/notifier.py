from __future__ import annotations

import html
import requests
from typing import Optional

from .config import Settings
from .models import DealRecord, Decision
from .rules import SafetyDecision


def _format_record(record: DealRecord, safety: Optional[SafetyDecision] = None) -> str:
    listing = record.listing
    ev = record.evaluation
    safety_notes = ""
    if safety and safety.reasons:
        safety_notes = "\n<b>Safety blocks:</b>\n" + "\n".join(f"- {html.escape(r)}" for r in safety.reasons)

    msg = f"""
<b>{html.escape(listing.title)}</b>

<b>Decision:</b> {ev.decision.value}
<b>Score:</b> {ev.deal_score}/100
<b>Confidence:</b> {ev.confidence:.2f}
<b>Risk:</b> {ev.risk_level.value}
<b>Price:</b> {listing.price_eur if listing.price_eur is not None else 'unknown'}€
<b>Model guess:</b> {html.escape(ev.model_guess)}
<b>CPU guess:</b> {html.escape(ev.cpu_guess)}
<b>Condition:</b> {html.escape(ev.condition_summary)}
<b>Max buy price:</b> {ev.max_buy_price_eur if ev.max_buy_price_eur is not None else 'unknown'}€
<b>Expected profit:</b> {ev.expected_profit_eur if ev.expected_profit_eur is not None else 'unknown'}€

<b>Reason:</b> {html.escape(ev.reason)}

<b>Missing info:</b> {html.escape(', '.join(ev.missing_info) or 'none')}
<b>Red flags:</b> {html.escape(', '.join(ev.red_flags) or 'none')}
{safety_notes}

<a href="{html.escape(listing.url)}">Open listing</a>
""".strip()
    if ev.seller_message_fr:
        msg += f"\n\n<b>Suggested message:</b>\n{html.escape(ev.seller_message_fr)}"
    return msg


class Notifier:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send_deal_alert(self, record: DealRecord, safety: Optional[SafetyDecision] = None) -> None:
        text = _format_record(record, safety)
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            print("\n--- DEAL ALERT ---")
            print(text.replace("<b>", "").replace("</b>", ""))
            print("--- END ALERT ---\n")
            return

        listing_id = record.listing.listing_id
        buttons = []
        if record.evaluation.decision == Decision.buy_ready and safety and safety.allowed_for_buy_alert:
            buttons.append([
                {"text": "⚡ Open checkout now", "callback_data": f"buy:{listing_id}"},
                {"text": "❌ Skip", "callback_data": f"skip:{listing_id}"},
            ])
        elif record.evaluation.decision == Decision.ask_seller:
            buttons.append([
                {"text": "✉️ Ask seller", "callback_data": f"ask:{listing_id}"},
                {"text": "❌ Skip", "callback_data": f"skip:{listing_id}"},
            ])
        else:
            buttons.append([{ "text": "❌ Mark skipped", "callback_data": f"skip:{listing_id}" }])

        payload = {
            "chat_id": self.settings.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
            "reply_markup": {"inline_keyboard": buttons},
        }
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        response = requests.post(url, json=payload, timeout=20)
        response.raise_for_status()
