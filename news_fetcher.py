"""
Fetches recent news for a list of tickers using yfinance.
Falls back to a basic RSS scrape from Finviz if yfinance returns nothing.
"""
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional
import yfinance as yf

MAX_NEWS_PER_TICKER = 6


@dataclass
class NewsItem:
    title: str
    publisher: str
    url: str
    summary: str = ""


def _fetch_yf_news(symbol: str) -> list[NewsItem]:
    try:
        ticker = yf.Ticker(symbol)
        raw = ticker.news or []
        items = []
        for n in raw[:MAX_NEWS_PER_TICKER]:
            content = n.get("content", {})
            title = content.get("title") or n.get("title", "")
            publisher = (
                content.get("provider", {}).get("displayName")
                or n.get("publisher", "")
            )
            # canonical URL
            url = (
                content.get("canonicalUrl", {}).get("url")
                or content.get("clickThroughUrl", {}).get("url")
                or n.get("link", "")
            )
            summary = content.get("summary") or content.get("body") or ""
            if title:
                items.append(NewsItem(title=title, publisher=publisher, url=url, summary=summary[:500]))
        return items
    except Exception as exc:
        print(f"[news] yfinance news failed for {symbol}: {exc}")
        return []


def _fetch_finviz_news(symbol: str) -> list[NewsItem]:
    """Lightweight scrape of Finviz news headlines as a fallback."""
    try:
        url = f"https://finviz.com/quote.ashx?t={urllib.parse.quote(symbol)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        # Very simple grep for news table rows
        items = []
        start = html.find('class="news-link-left"')
        while start != -1 and len(items) < MAX_NEWS_PER_TICKER:
            href_start = html.rfind('href="', 0, start)
            href_end = html.find('"', href_start + 6)
            link = html[href_start + 6: href_end] if href_start != -1 else ""
            title_start = html.find(">", start) + 1
            title_end = html.find("<", title_start)
            title = html[title_start:title_end].strip()
            if title:
                items.append(NewsItem(title=title, publisher="Finviz", url=link))
            start = html.find('class="news-link-left"', start + 1)
        return items
    except Exception:
        return []


def fetch_news(symbol: str) -> list[NewsItem]:
    items = _fetch_yf_news(symbol)
    if not items:
        items = _fetch_finviz_news(symbol)
    return items


def fetch_all_news(symbols: list[str]) -> dict[str, list[NewsItem]]:
    return {sym: fetch_news(sym) for sym in symbols}


if __name__ == "__main__":
    for sym in ["AAPL", "NVDA"]:
        news = fetch_news(sym)
        print(f"\n=== {sym} ({len(news)} items) ===")
        for n in news:
            print(f"  [{n.publisher}] {n.title}")
