"""
Downloads 1-minute intraday data for a list of tickers and finds the top N gainers
between two timestamps on the same trading day.
"""
import time
import datetime
from zoneinfo import ZoneInfo
from typing import Optional
import pandas as pd
import yfinance as yf

ET = ZoneInfo("America/New_York")
CHUNK_SIZE = 200       # tickers per yfinance batch request
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5        # seconds between retries
PRICE_TOLERANCE = datetime.timedelta(minutes=3)  # window to search for price


def _now_et() -> datetime.datetime:
    return datetime.datetime.now(tz=ET)


def _find_price(series: pd.Series, target: datetime.datetime) -> Optional[float]:
    """Return the Close price closest to `target` within PRICE_TOLERANCE."""
    if series is None or series.empty:
        return None
    # Ensure the index is timezone-aware
    idx = series.index
    if idx.tzinfo is None:
        idx = idx.tz_localize("UTC").tz_convert(ET)
    else:
        idx = idx.tz_convert(ET)

    target_ts = pd.Timestamp(target)
    diffs = abs(idx - target_ts)
    min_diff = diffs.min()
    if min_diff > pd.Timedelta(PRICE_TOLERANCE):
        return None
    return float(series.iloc[diffs.argmin()])


def _download_chunk(tickers: list[str]) -> dict[str, pd.Series]:
    """Download 1m data for a chunk; return {ticker: Close series}."""
    joined = " ".join(tickers)
    for attempt in range(RETRY_ATTEMPTS):
        try:
            data = yf.download(
                joined,
                period="1d",
                interval="1m",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            result: dict[str, pd.Series] = {}
            if len(tickers) == 1:
                # Single ticker: flat DataFrame
                if "Close" in data.columns and not data.empty:
                    result[tickers[0]] = data["Close"]
            else:
                for sym in tickers:
                    try:
                        close = data[sym]["Close"] if sym in data.columns.get_level_values(0) else None
                        if close is not None and not close.empty:
                            result[sym] = close
                    except (KeyError, TypeError):
                        pass
            return result
        except Exception as exc:
            if attempt < RETRY_ATTEMPTS - 1:
                print(f"[scanner] Retry {attempt + 1} after error: {exc}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"[scanner] Chunk failed after {RETRY_ATTEMPTS} attempts: {exc}")
                return {}
    return {}


def get_top_gainers(
    tickers: list[str],
    t0: datetime.datetime,
    t1: datetime.datetime,
    top_n: int = 5,
) -> pd.DataFrame:
    """
    For each ticker, compare Close price at t0 vs t1.
    Returns a DataFrame with columns: ticker, price_t0, price_t1, pct_change
    sorted descending by pct_change, limited to top_n.
    """
    print(f"[scanner] Scanning {len(tickers)} tickers from {t0:%H:%M} to {t1:%H:%M} ET ...")
    rows = []
    total_chunks = (len(tickers) + CHUNK_SIZE - 1) // CHUNK_SIZE

    for i in range(0, len(tickers), CHUNK_SIZE):
        chunk = tickers[i: i + CHUNK_SIZE]
        chunk_num = i // CHUNK_SIZE + 1
        print(f"[scanner] Chunk {chunk_num}/{total_chunks} ({len(chunk)} tickers)...")
        closes = _download_chunk(chunk)

        for sym, series in closes.items():
            p0 = _find_price(series, t0)
            p1 = _find_price(series, t1)
            if p0 and p1 and p0 > 0:
                pct = (p1 - p0) / p0 * 100
                rows.append({"ticker": sym, "price_t0": p0, "price_t1": p1, "pct_change": pct})

    if not rows:
        return pd.DataFrame(columns=["ticker", "price_t0", "price_t1", "pct_change"])

    df = pd.DataFrame(rows)
    df.sort_values("pct_change", ascending=False, inplace=True)
    return df.head(top_n).reset_index(drop=True)


if __name__ == "__main__":
    # Quick smoke test with a small list
    now = _now_et()
    t0 = now.replace(hour=9, minute=30, second=0, microsecond=0)
    t1 = now.replace(hour=10, minute=30, second=0, microsecond=0)
    sample = ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "META", "GOOGL", "NFLX", "AMD", "INTC"]
    df = get_top_gainers(sample, t0, t1, top_n=5)
    print(df.to_string(index=False))
