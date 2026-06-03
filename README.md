# Stock Notifier

Scans a list of tickers twice a day, finds the top gainers over a one-hour window, fetches recent news, and emails an AI-generated analysis via Claude.

## How it works

Two sessions run each market day:

| Session | Window | Trigger hour (ET) |
|---------|--------|-------------------|
| Morning | 9:30 AM → 10:30 AM | 10 AM |
| Afternoon | 1:30 PM → 2:30 PM | 2 PM |

Each run:
1. Pulls prices at the start and end of the window via `yfinance`
2. Ranks tickers by % gain and takes the top N (default 10)
3. Fetches recent news headlines for each winner
4. Sends each ticker + news to Claude for a short analysis
5. Emails an HTML report via Gmail

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your keys
```

**.env**

```
ANTHROPIC_API_KEY=...
GMAIL_SENDER=you@gmail.com
GMAIL_APP_PASSWORD=...
```

## Usage

```bash
# Auto-detect session from current time
python main.py

# Force a session
python main.py --session morning
python main.py --session afternoon

# Dry run — prints report, skips email
python main.py --session morning --dry-run

# Custom tickers
python main.py --tickers AAPL MSFT NVDA

# Custom top-N
python main.py --top-n 5
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `GMAIL_SENDER` | Yes | Gmail address to send from |
| `GMAIL_APP_PASSWORD` | Yes | Gmail app password |
| `TICKER_LIST` | No | Comma-separated tickers (overrides default list) |
| `TOP_N` | No | Number of top gainers to report (default: 10) |

## TODO

- [ ] Watchlist feature — track a personal list of tickers and always include them in the report regardless of their gain rank
