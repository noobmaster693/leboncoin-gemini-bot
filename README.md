# Leboncoin Gemini Deal Monitor

A semi-autonomous Python assistant that reads Leboncoin saved-search emails, extracts individual listings, evaluates repair or resale opportunities with Google Gemini, applies hard spending and confidence rules, and sends structured alerts to the terminal or Telegram.

The project is intentionally human-controlled: it can help prioritize listings and open a guided browser session, but it does not complete purchases automatically or bypass CAPTCHA, 2FA, payment confirmation, platform protections, or anti-bot systems.

## What it does

```text
Leboncoin saved-search email
  └─ IMAP inbox reader
       └─ listing-card and link extraction
            ├─ optional listing-page fetch
            └─ Gemini evaluation
                 ├─ buy_ready
                 ├─ ask_seller
                 └─ skip
                      └─ hard safety rules
                           └─ terminal or Telegram alert
```

The normal low-friction mode evaluates the listing information embedded in Leboncoin alert emails. Opening every listing page is optional and disabled by default to reduce CAPTCHA and robot-check triggers.

## Key features

- Reads unread Leboncoin saved-search emails over IMAP
- Extracts multiple listing cards or links from digest emails
- Filters old messages, non-listing notifications, and already processed listings
- Uses Gemini to score deals and produce structured recommendations
- Applies independent hard rules for price, confidence, and score thresholds
- Stores processed deals in a local SQLite database
- Sends alerts to the terminal and optionally Telegram
- Provides a FastAPI endpoint for manual or external listing evaluation
- Opens a persistent Playwright browser profile for guided seller or checkout actions
- Reuses configurable fallback Gemini models when the preferred model is unavailable

## Responsible-use boundary

Use saved-search emails or notifications delivered to your own inbox. Do not use this project to evade platform restrictions, overwhelm Leboncoin, automate deceptive messages, or make purchases without human review.

The guided checkout helper must stop whenever there is uncertainty, CAPTCHA, 2FA, an unexpected price, or a payment confirmation step.

## Requirements

- Python 3.10 or newer
- A Google Gemini API key
- An email inbox receiving Leboncoin saved-search alerts
- An app password or other IMAP-compatible credential for that inbox
- Optional: a Telegram bot and chat ID
- Optional: Playwright Chromium for guided browser actions

## Quick start

```bash
git clone https://github.com/noobmaster693/leboncoin-gemini-bot.git
cd leboncoin-gemini-bot
python -m venv .venv
```

Activate the virtual environment:

```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install dependencies and the Playwright browser:

```bash
pip install -r requirements.txt
playwright install chromium
```

Create your local configuration:

```bash
# macOS/Linux
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

Add at least these values to `.env`:

```dotenv
GEMINI_API_KEY=your_gemini_key_here
IMAP_USER=your_email@gmail.com
IMAP_PASSWORD=your_email_app_password
```

Never commit `.env`, email credentials, Telegram tokens, or real account data.

## Run a single inbox scan

```bash
python scripts/run_once.py
```

This reads matching unread email, extracts listings, evaluates new items, stores the results, and sends configured notifications.

For repeat testing with the same saved emails, temporarily use:

```dotenv
MARK_EMAILS_SEEN_AFTER_PARSE=false
REPROCESS_EXISTING_LISTINGS=true
```

Return both values to their safer defaults when testing is finished.

## Test Gemini evaluation without email

```bash
python scripts/evaluate_sample.py
```

Use this first to verify the API key, selected model, prompt format, and structured response before connecting an inbox.

## Start the API

```bash
uvicorn app.main:app --reload --port 8000
```

Available endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Basic process health check |
| `GET` | `/listings?limit=25` | Return recently stored listing evaluations |
| `POST` | `/evaluate` | Evaluate and store a supplied listing |
| `POST` | `/confirm-purchase/{listing_id}` | Run preflight checks and mark a listing as confirmed for guided checkout |

Example evaluation request:

```bash
curl -X POST http://127.0.0.1:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "id": "example-123",
    "title": "Laptop for parts",
    "price_eur": 75,
    "url": "https://www.leboncoin.fr/example",
    "description": "Does not start; charger included"
  }'
```

The exact accepted fields are defined by the repository's `ListingInput` model.

## Guided checkout

After reviewing a listing and explicitly approving a maximum total:

```bash
python scripts/open_checkout.py LISTING_ID --approved-max-total 120
```

The helper uses the browser profile configured by `PLAYWRIGHT_USER_DATA_DIR`. It is a guarded browser assistant, not an autonomous purchasing bot.

## Configuration reference

### Gemini

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | Empty | Required API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Preferred evaluation model |
| `GEMINI_FALLBACK_MODELS` | `gemini-2.5-flash,gemini-1.5-flash` | Ordered fallback models |
| `GEMINI_TEMPERATURE` | `0.2` | Evaluation temperature |
| `GEMINI_THINKING_BUDGET` | `4096` | Optional model thinking budget; set `-1` to disable where supported |

### Email ingestion

| Variable | Default | Purpose |
| --- | --- | --- |
| `IMAP_HOST` | `imap.gmail.com` | IMAP server |
| `IMAP_PORT` | `993` | TLS IMAP port |
| `IMAP_USER` | Empty | Inbox username |
| `IMAP_PASSWORD` | Empty | IMAP or app password |
| `IMAP_FOLDER` | `INBOX` | Folder to scan |
| `LBC_EMAIL_FILTER` | `leboncoin` | Sender or message filter text |
| `MAX_EMAIL_AGE_DAYS` | `3` | Ignore older unread alerts |
| `MAX_LISTING_LINKS_PER_EMAIL` | `25` | Maximum cards/links processed from one email |
| `MARK_EMAILS_SEEN_AFTER_PARSE` | `true` | Mark successfully parsed messages as seen |
| `REPROCESS_EXISTING_LISTINGS` | `false` | Allow previously stored listings to be evaluated again |

For Gmail, use an app password rather than your normal account password when the account configuration requires it.

### Notifications

| Variable | Default | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Empty | Optional Telegram bot token |
| `TELEGRAM_CHAT_ID` | Empty | Optional destination chat |

If Telegram is not configured, terminal output remains available.

### Risk controls

| Variable | Default | Purpose |
| --- | --- | --- |
| `MAX_TOTAL_EUR` | `120` | Maximum accepted total price |
| `MIN_BUY_READY_SCORE` | `88` | Minimum score for a `buy_ready` recommendation |
| `MIN_CONFIDENCE` | `0.72` | Minimum confidence for a strong recommendation |
| `DAILY_PURCHASE_LIMIT_EUR` | `250` | Daily spending guardrail |
| `PURCHASE_MODE` | `guided` | Keeps purchase activity human-controlled |

Gemini recommendations do not override these rules.

### Listing pages and browser profile

| Variable | Default | Purpose |
| --- | --- | --- |
| `FETCH_LISTING_DETAILS` | `false` | Open listing pages before evaluation |
| `PLAYWRIGHT_USER_DATA_DIR` | `.browser-profile` | Persistent browser session folder |
| `DB_PATH` | `deals.sqlite3` | SQLite deal-history database |

Keep `FETCH_LISTING_DETAILS=false` unless the extra page loads are genuinely needed and acceptable.

## Decision states

- `buy_ready`: the listing appears promising enough for immediate human review
- `ask_seller`: important facts are missing and a seller question is recommended
- `skip`: the listing does not meet the current criteria or appears too risky

A model classification is only one input. Hard rules and human approval remain authoritative.

## Project structure

```text
.
├── app/
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Environment-backed settings
│   ├── gemini_evaluator.py     # Gemini evaluation logic
│   ├── email_monitor.py        # IMAP ingestion and listing extraction
│   ├── rules.py                # Hard safety rules
│   ├── notifier.py             # Terminal and Telegram alerts
│   ├── purchase_assistant.py   # Purchase preflight checks
│   └── storage.py              # Local deal history
├── scripts/
│   ├── run_once.py             # Process inbox once
│   ├── evaluate_sample.py      # Test model evaluation
│   └── open_checkout.py        # Open guided browser session
├── .env.example
└── requirements.txt
```

## Troubleshooting

### No emails are found

Confirm the IMAP host, username, app password, folder, and `LBC_EMAIL_FILTER`. Check whether alerts are older than `MAX_EMAIL_AGE_DAYS` or already marked as read.

### The same listing is skipped

Processed listing IDs are stored in `deals.sqlite3`. Set `REPROCESS_EXISTING_LISTINGS=true` only while intentionally retesting.

### Gemini returns quota or model errors

Verify the API key and use model IDs available to your Google account. The application tries `GEMINI_FALLBACK_MODELS` in order.

### Leboncoin shows CAPTCHA or robot checks

Keep `FETCH_LISTING_DETAILS=false` and rely on information embedded in saved-search emails. Do not attempt to bypass the challenge.

### Telegram alerts do not arrive

Verify the bot token, chat ID, and that the bot has permission to message the destination. Check the terminal output for the original error.

### Playwright cannot open Chromium

Run:

```bash
playwright install chromium
```

Then confirm that `PLAYWRIGHT_USER_DATA_DIR` is writable.

## Data and security notes

- Keep `.env`, `.browser-profile`, and `deals.sqlite3` private.
- Treat seller messages and listing data as personal data.
- Do not store payment details in this project.
- Start in alert-only mode and validate recommendation quality before using guided actions.
- Use a dedicated inbox or carefully scoped mail credentials when possible.
