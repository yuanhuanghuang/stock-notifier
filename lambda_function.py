"""
AWS Lambda entry point for the stock notifier.
Triggered by EventBridge on schedule; auto-detects session from ET time.
"""
import datetime
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
load_dotenv()

ET = ZoneInfo("America/New_York")

SESSION_CONFIG = {
    "morning": {
        "label": "Morning (9:30–10:30)",
        "t0_hour": 9,  "t0_min": 30,
        "t1_hour": 10, "t1_min": 30,
        "t0_label": "9:30 AM", "t1_label": "10:30 AM",
        "trigger_hour": 10,
    },
    "afternoon": {
        "label": "Afternoon (1:30–2:30)",
        "t0_hour": 13, "t0_min": 30,
        "t1_hour": 14, "t1_min": 30,
        "t0_label": "1:30 PM", "t1_label": "2:30 PM",
        "trigger_hour": 14,
    },
}


def lambda_handler(event, context):
    now_et = datetime.datetime.now(tz=ET)

    if now_et.weekday() >= 5:
        print("[lambda] Weekend — skipping.")
        return {"status": "skipped", "reason": "weekend"}

    session_name = event.get("session")
    if not session_name:
        for name, cfg in SESSION_CONFIG.items():
            if now_et.hour == cfg["trigger_hour"]:
                session_name = name
                break

    if not session_name:
        print(f"[lambda] No session matched for ET hour {now_et.hour} — skipping.")
        return {"status": "skipped", "reason": "no session matched"}

    cfg = SESSION_CONFIG[session_name]
    today = datetime.date.today()
    t0 = now_et.replace(hour=cfg["t0_hour"], minute=cfg["t0_min"], second=0, microsecond=0)
    t1 = now_et.replace(hour=cfg["t1_hour"], minute=cfg["t1_min"], second=0, microsecond=0)

    print(f"[lambda] Running {cfg['label']} session — {today}")

    if os.environ.get("TICKER_LIST"):
        tickers = [t.strip().upper() for t in os.environ["TICKER_LIST"].replace(";", ",").split(",") if t.strip()]
    else:
        from tickers import load_tickers
        tickers = load_tickers()

    top_n = int(os.environ.get("TOP_N", "10"))

    from stock_scanner import get_top_gainers
    gainers_df = get_top_gainers(tickers, t0, t1, top_n=top_n)

    if gainers_df.empty:
        print("[lambda] No gainers found.")
        return {"status": "skipped", "reason": "no gainers"}

    print(f"[lambda] Top {len(gainers_df)} gainers found.")

    from news_fetcher import fetch_all_news
    news_map = fetch_all_news(gainers_df["ticker"].tolist())

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

    from emailer import send_report
    send_report(
        session_label=cfg["label"],
        t0_label=cfg["t0_label"],
        t1_label=cfg["t1_label"],
        gainers=gainers_list,
        run_date=today,
        dry_run=False,
    )

    print("[lambda] Done.")
    return {"status": "success", "session": session_name, "gainers": len(gainers_df)}
