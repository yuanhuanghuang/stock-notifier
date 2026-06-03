"""
Fetches and caches the full list of US-listed equity tickers from NASDAQ FTP.
Refreshes the cache weekly. Filters out non-equity instruments.
"""
import os
import io
import ssl
import time
import urllib.request

import certifi
import pandas as pd

CACHE_DIR = os.path.expanduser("~/.stock_notifier")
CACHE_FILE = os.path.join(CACHE_DIR, "tickers.csv")
CACHE_TTL_SECONDS = 7 * 24 * 3600  # 1 week

NASDAQ_FILES = [
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
]

# Suffixes that indicate non-common-equity instruments
_EXCLUDE_SUFFIXES = {
    "W", "WS", "WT",   # warrants
    "R", "RT",          # rights
    "U",                # units
    "Z",                # when-issued
    "P", "A", "B", "C", "D", "E", "F", "G", "H",  # preferred share classes
}


def _is_common_equity(symbol: str) -> bool:
    parts = symbol.split(".")
    if len(parts) > 1 and parts[-1].upper() in _EXCLUDE_SUFFIXES:
        return False
    # Skip symbols with special characters (^, -, /)
    if any(c in symbol for c in ("^", "-", "/")):
        return False
    return True


def _download_tickers() -> list[str]:
    tickers: set[str] = set()
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    for url in NASDAQ_FILES:
        try:
            with urllib.request.urlopen(url, context=ssl_context, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
            df = pd.read_csv(io.StringIO(content), sep="|")
            # Both files have a "Symbol" column; last row is a file-creation-date trailer
            if "Symbol" in df.columns:
                syms = df["Symbol"].dropna().astype(str).tolist()
                tickers.update(s.strip() for s in syms if s.strip())
        except Exception as exc:
            print(f"[tickers] Warning: could not fetch {url}: {exc}")
    # Filter to common equity only
    return sorted(s for s in tickers if _is_common_equity(s))


def load_tickers(force_refresh: bool = False) -> list[str]:
    os.makedirs(CACHE_DIR, exist_ok=True)
    # Check cache freshness
    if not force_refresh and os.path.exists(CACHE_FILE):
        age = time.time() - os.path.getmtime(CACHE_FILE)
        if age < CACHE_TTL_SECONDS:
            df = pd.read_csv(CACHE_FILE)
            tickers = df["ticker"].tolist()
            print(f"[tickers] Loaded {len(tickers)} tickers from cache.")
            return tickers

    print("[tickers] Refreshing ticker list from NASDAQ FTP...")
    tickers = _download_tickers()
    if not tickers:
        # Fall back to cache even if stale
        if os.path.exists(CACHE_FILE):
            df = pd.read_csv(CACHE_FILE)
            tickers = df["ticker"].tolist()
            print(f"[tickers] FTP failed — using stale cache ({len(tickers)} tickers).")
            return tickers
        raise RuntimeError("Could not fetch ticker list and no cache available.")
    pd.DataFrame({"ticker": tickers}).to_csv(CACHE_FILE, index=False)
    print(f"[tickers] Cached {len(tickers)} tickers.")
    return tickers


if __name__ == "__main__":
    t = load_tickers(force_refresh=True)
    print(f"Total tickers: {len(t)}")
    print(t[:20])
