# Leboncoin Broken-Laptop Deal Bot — Gemini API MVP

This is a starter bot for monitoring Leboncoin saved-search emails, evaluating broken-laptop deals with the Gemini API, and sending you a structured alert.

It is intentionally designed as a **semi-autonomous** buying assistant:

1. Read Leboncoin saved-search emails from your inbox.
2. Extract listing link/title/price/snippet.
3. Ask Gemini to classify the listing as:
   - `buy_ready`
   - `ask_seller`
   - `skip`
4. Apply hard safety rules.
5. Notify you in Telegram or terminal.
6. Only after your explicit approval, open a guarded checkout assistant.

It does **not** bypass CAPTCHA, 2FA, platform protections, or anti-bot systems.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Fill `.env` with your Gemini key and optional Telegram/IMAP credentials.

## Run one scan

```bash
python scripts/run_once.py
```

## Test Gemini evaluation

```bash
python scripts/evaluate_sample.py
```

## Start API

```bash
uvicorn app.main:app --reload --port 8000
```

Then POST a listing to:

```text
POST http://127.0.0.1:8000/evaluate
```

## Guided checkout

The checkout helper opens a browser profile and stops when there is any uncertainty, CAPTCHA, 2FA, or payment confirmation issue.

```bash
python scripts/open_checkout.py LISTING_ID --approved-max-total 120
```

## Safety notes

- Use saved-search emails or your own notifications rather than aggressive scraping.
- Keep final purchase approval human-controlled.
- Never store your real Gemini key or email app password in git.
- Start with alerts only, then add messaging/checkout after you verify scoring quality.

## Suggested next upgrades

- Add Telegram inline buttons for `Buy`, `Skip`, and `Ask seller`.
- Add a seller-reply ingestion flow.
- Add a repair/resale price database.
- Add photo analysis by downloading listing photos only from links you are authorized to access.
- Add a daily spending cap and audit log.