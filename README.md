# Leboncoin Broken-Laptop Deal Bot

A semi-autonomous buying assistant that reads Leboncoin saved-search emails, uses Google Gemini to assess broken-laptop listings, and sends structured deal alerts to the terminal or Telegram.

The bot helps you decide what deserves attention; it does not make an unattended purchase. Checkout opens in a visible Playwright browser only after an explicit approval and stops at platform protections, payment confirmation, or uncertainty.

## What it does

1. Reads unread Leboncoin saved-search messages over IMAP.
2. Extracts listing titles, links, prices, locations, and email snippets.
3. Asks Gemini to classify each listing as `buy_ready`, `ask_seller`, or `skip`.
4. Applies deterministic budget, confidence, score, and red-flag rules.
5. Stores evaluations in a local SQLite database.
6. Sends an alert to Telegram or prints it in the terminal.
7. Optionally helps send a seller message or opens a human-controlled checkout session.

## Key features

- Gemini scoring focused on damaged laptops and repair/resale estimates
- Gmail and other IMAP-compatible mailbox support
- Terminal alerts with no Telegram setup required
- Optional Telegram alerts and action buttons
- Conservative hard rules layered on top of AI output
- Duplicate-listing protection with local SQLite storage
- One-shot and continuous-monitor modes
- FastAPI endpoints for evaluating listings from other tools
- Visible, persistent Playwright browser profile for guided actions

## Safety boundary

This project does not bypass CAPTCHA, 2FA, rate limits, anti-bot controls, or payment confirmation. Use saved-search emails instead of aggressive scraping, verify every listing and seller yourself, and keep final purchase approval human-controlled.

AI estimates can be wrong. Treat scores, model guesses, repair costs, and resale values as leads to investigate—not financial advice or proof that a listing is legitimate.

## Requirements

- Python 3.10 or newer
- A [Gemini API key](https://aistudio.google.com/app/apikey)
- A Leboncoin saved search that sends email alerts
- IMAP credentials for the receiving mailbox
- Optional: a Telegram bot and chat ID

For Gmail, enable two-step verification and create an app password. Do not put your normal Google password in `.env`.

## Quick start

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/noobmaster693/leboncoin-gemini-bot.git
cd leboncoin-gemini-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

On Windows Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
```

Edit `.env` and set at least:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
IMAP_USER=your_email@gmail.com
IMAP_PASSWORD=your_gmail_app_password
```

The defaults target Gmail and Leboncoin messages. Review `.env.example` before running the monitor, especially the price and confidence limits.

## Recommended first run

Test Gemini without connecting to your inbox:

```bash
python scripts/evaluate_sample.py
```

Then process one batch of unread saved-search emails:

```bash
python scripts/run_once.py
```

Without Telegram credentials, results are printed to the terminal.

To test a downloaded Leboncoin email before enabling mailbox access:

```bash
python scripts/test_eml_parser.py path/to/message.eml
```

## Run continuously

```bash
python scripts/monitor.py
```

The monitor checks for new messages every `MONITOR_INTERVAL_SECONDS` and continues after a single listing fails. Press <kbd>Ctrl</kbd>+<kbd>C</kbd> to stop it.

Windows users can run:

- `run_bot.bat` for one scan;
- `run_monitor.bat` for the continuous monitor plus Telegram button listener.

## Telegram setup (optional)

1. Create a bot with [@BotFather](https://t.me/BotFather).
2. Send your bot a message.
3. Obtain the target chat ID.
4. Add both values to `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Run the callback listener when you want Telegram action buttons to work:

```bash
python scripts/telegram_listener.py
```

The `Ask seller` and checkout actions open a visible browser using the profile directory configured by `PLAYWRIGHT_USER_DATA_DIR`. Log in manually and respect any verification challenge shown by Leboncoin.

## Guided checkout

Evaluated listings are stored by listing ID. To open one after reviewing its alert:

```bash
python scripts/open_checkout.py LISTING_ID --approved-max-total 120
```

The command rechecks the AI decision and configured spending limits before opening the listing. It does not enter payment details or complete a purchase.

## API mode

Start the local API:

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Main endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check that the API is running. |
| `GET` | `/listings` | Return recent stored evaluations. |
| `POST` | `/evaluate` | Evaluate and store a `ListingInput` JSON object. |
| `POST` | `/confirm-purchase/{listing_id}` | Run preflight checks for a stored listing. |

Example evaluation:

```bash
curl -X POST http://127.0.0.1:8000/evaluate \
  -H 'Content-Type: application/json' \
  -d '{
    "listing_id": "example-001",
    "title": "Laptop with broken screen",
    "url": "https://www.leboncoin.fr/ad/ordinateurs/example-001",
    "price_eur": 80,
    "description": "Works over HDMI; SSD not included"
  }'
```

## Important configuration

The complete template is in `.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Primary evaluation model. |
| `IMAP_HOST` / `IMAP_PORT` | `imap.gmail.com` / `993` | Mail server connection. |
| `LBC_EMAIL_FILTER` | `leboncoin` | Text used to identify relevant email. |
| `MAX_EMAIL_AGE_DAYS` | `3` | Ignores older unread messages. |
| `MARK_EMAILS_SEEN_AFTER_PARSE` | `true` | Marks successfully parsed messages as seen. |
| `REPROCESS_EXISTING_LISTINGS` | `false` | Prevents duplicate evaluations by default. |
| `MAX_TOTAL_EUR` | `120` | Maximum estimated total for a buy-ready alert. |
| `MIN_BUY_READY_SCORE` | `88` | Minimum deal score for a buy-ready alert. |
| `MIN_CONFIDENCE` | `0.72` | Minimum Gemini confidence. |
| `FETCH_LISTING_DETAILS` | `false` | Avoids opening each listing page by default. |
| `MONITOR_INTERVAL_SECONDS` | `60` | Delay between continuous scans. |
| `DB_PATH` | `deals.sqlite3` | Local evaluation database. |

Start conservatively. Keep `FETCH_LISTING_DETAILS=false` until you understand the added requests and the risk of platform challenges.

## Local data and secrets

The application may create:

- `.env`, containing API and mailbox credentials;
- `deals.sqlite3`, containing processed listings and evaluations;
- `.browser-profile/`, containing a persistent browser login profile.

These paths are ignored by Git. Back them up or delete them according to your own privacy requirements. Never commit API keys, app passwords, Telegram tokens, cookies, or browser profiles.

## Troubleshooting

### No listings are found

- Confirm that saved-search emails are unread and no older than `MAX_EMAIL_AGE_DAYS`.
- Check `IMAP_FOLDER` and `LBC_EMAIL_FILTER`.
- Run `scripts/test_eml_parser.py` against a downloaded message.
- Temporarily set `MARK_EMAILS_SEEN_AFTER_PARSE=false` while testing the same message.

### Gmail rejects the login

Use an app password, not the normal account password. Confirm that `IMAP_USER` contains the full email address.

### Gemini returns a model or quota error

Check your Google AI Studio quota and set `GEMINI_MODEL` to a model available to your account.

### Telegram alerts work but buttons do not

Keep `python scripts/telegram_listener.py` running and confirm that the bot token and chat ID are correct.

### Leboncoin shows CAPTCHA or a login prompt

Complete the step manually in the visible browser. Do not automate or bypass it.

## Project status

This is an MVP for personal experimentation. Validate its scoring on historical examples and start with alert-only operation before relying on seller messaging or guided checkout.
