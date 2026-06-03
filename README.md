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

## Deployment (AWS Lambda)

The script runs as an AWS Lambda function triggered by EventBridge on a schedule. Dependencies are packaged as a Lambda layer and stored in S3.

### Prerequisites

- AWS CLI installed (`brew install awscli`) and configured (`aws configure`)
- IAM user with the following policies:
  - `AWSLambdaFullAccess`
  - `IAMFullAccess`
  - `AmazonEventBridgeFullAccess`
  - `AmazonS3FullAccess`
  - `CloudWatchLogsFullAccess`

### Deploy

```bash
chmod +x deploy.sh
./deploy.sh
```

The script will:
1. Build a Linux-compatible dependencies layer and upload to S3
2. Package and upload your function code
3. Create the IAM execution role for Lambda
4. Create the Lambda function with all env vars from `.env`
5. Set up two EventBridge rules to trigger it Mon–Fri

**Schedule (EDT, summer):** 10:30 AM and 2:30 PM ET. Update cron times in `deploy.sh` in November when DST ends (`14→15`, `18→19` UTC).

### View logs

[CloudWatch → stock-notifier](https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/%2Faws%2Flambda%2Fstock-notifier)

## Local usage

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your keys
```

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
| `EMAIL_RECIPIENTS` | No | Comma-separated or JSON array of recipients |
| `TICKER_LIST` | No | Comma-separated tickers (overrides default list) |
| `TOP_N` | No | Number of top gainers to report (default: 10) |

## TODO

- [ ] Watchlist feature — track a personal list of tickers and always include them in the report regardless of their gain rank
