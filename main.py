"""
Stock Notification App — entry point.

Usage:
  python main.py                        # auto-detect session from current ET time
  python main.py --session morning      # force morning session (9:30 vs 10:30)
  python main.py --session afternoon    # force afternoon session (1:30 vs 2:30)
  python main.py --session morning --dry-run   # print report, skip email
  python main.py --session morning --tickers AAPL MSFT NVDA  # custom ticker list

Required env vars (non-dry-run):
  ANTHROPIC_API_KEY
  GMAIL_SENDER
  GMAIL_APP_PASSWORD

Optional env vars:
  TICKER_LIST    # comma-separated ticker list, e.g. AAPL,MSFT,NVDA
  TOP_N          # number of top gainers to report (default: 10)
"""
import argparse
import datetime
import sys
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

ET = ZoneInfo("America/New_York")

SESSION_CONFIG = {
    "morning": {
        "label": "Morning (9:30–10:30)",
        "t0_hour": 9,
        "t0_min": 30,
        "t1_hour": 10,
        "t1_min": 30,
        "t0_label": "9:30 AM",
        "t1_label": "10:30 AM",
        "trigger_hour": 10,   # auto-detect: if ET hour == 10 → morning
    },
    "afternoon": {
        "label": "Afternoon (1:30–2:30)",
        "t0_hour": 13,
        "t0_min": 30,
        "t1_hour": 14,
        "t1_min": 30,
        "t0_label": "1:30 PM",
        "t1_label": "2:30 PM",
        "trigger_hour": 14,   # auto-detect: if ET hour == 14 → afternoon
    },
}


def _detect_session() -> str | None:
    now = datetime.datetime.now(tz=ET)
    for name, cfg in SESSION_CONFIG.items():
        if now.hour == cfg["trigger_hour"]:
            return name
    return None


def _is_market_open() -> bool:
    now = datetime.datetime.now(tz=ET)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock Notification App")
    parser.add_argument(
        "--session", choices=["morning", "afternoon"],
        help="Which session to run. Auto-detected from ET time if omitted."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print report to terminal and save HTML; skip sending email."
    )
    parser.add_argument(
        "--tickers", nargs="+",
        help="Override: analyze only these tickers (space-separated)."
    )
    parser.add_argument(
        "--top-n", type=int, default=None,
        help="Number of top gainers to report (default: 10 or the TOP_N env var)."
    )
    args = parser.parse_args()

    top_n = args.top_n if args.top_n is not None else int(os.environ.get("TOP_N", "10"))

    # --- Session detection ---
    session_name = args.session
    if session_name is None:
        session_name = _detect_session()
        if session_name is None:
            print(
                "[main] Could not auto-detect session from current ET time. "
                "Use --session morning|afternoon to force a session. Exiting."
            )
            sys.exit(0)

    cfg = SESSION_CONFIG[session_name]
    today = datetime.date.today()
    now_et = datetime.datetime.now(tz=ET)

    if not args.dry_run and not _is_market_open():
        print("[main] Market is closed or today is a weekend. Exiting.")
        sys.exit(0)

    t0 = now_et.replace(hour=cfg["t0_hour"], minute=cfg["t0_min"], second=0, microsecond=0)
    t1 = now_et.replace(hour=cfg["t1_hour"], minute=cfg["t1_min"], second=0, microsecond=0)

    print(f"\n{'='*60}")
    print(f"  Stock Notifier — {cfg['label']}")
    print(f"  Date: {today}  |  Comparing {cfg['t0_label']} vs {cfg['t1_label']} ET")
    print(f"{'='*60}\n")

    # --- 1. Load tickers ---
    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
        print(f"[main] Using custom ticker list: {tickers}")
    elif os.environ.get("TICKER_LIST"):
        ticker_list = os.environ["TICKER_LIST"]
        tickers = [t.strip().upper() for t in ticker_list.replace(";", ",").split(",") if t.strip()]
        print(f"[main] Using ticker list from TICKER_LIST env: {tickers}")
    else:
        from tickers import load_tickers
        tickers = load_tickers()

    # --- 2. Find top gainers ---
    from stock_scanner import get_top_gainers
    gainers_df = get_top_gainers(tickers, t0, t1, top_n=top_n)

    if gainers_df.empty:
        print("[main] No gainers found (possibly outside market hours or data unavailable). Exiting.")
        sys.exit(0)

    print(f"\n[main] Top {len(gainers_df)} gainers:")
    print(gainers_df.to_string(index=False))

    # --- 3. Fetch news ---
    from news_fetcher import fetch_all_news
    top_symbols = gainers_df["ticker"].tolist()
    news_map = fetch_all_news(top_symbols)

    # --- 4. Analyze with Claude ---
    from analyzer import analyze_all
    gainers_list = [
        {
            "ticker": row["ticker"],
            "price_t0": row["price_t0"],
            "price_t1": row["price_t1"],
            "pct_change": row["pct_change"],
            "news": news_map.get(row["ticker"], []),
        }
        for _, row in gainers_df.iterrows()
    ]
    analyses = analyze_all(gainers_list)
    for g in gainers_list:
        g["analysis"] = analyses.get(g["ticker"], "No analysis available.")

    print("\n[main] Analyses complete.")

    # --- 5. Send email ---
    from emailer import send_report
    send_report(
        session_label=cfg["label"],
        t0_label=cfg["t0_label"],
        t1_label=cfg["t1_label"],
        gainers=gainers_list,
        run_date=today,
        dry_run=args.dry_run,
    )

    print("\n[main] Done.")


if __name__ == "__main__":
    main()
