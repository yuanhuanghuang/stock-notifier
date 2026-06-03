"""
Uses the Claude API (claude-sonnet-4-6) with prompt caching to generate a
concise, investment-focused explanation of why each stock is gaining.
"""
import os
import anthropic
from news_fetcher import NewsItem

_SYSTEM_PROMPT = (
    "You are a concise financial analyst. "
    "Given a stock ticker, its intraday price gain percentage, and a list of recent news headlines/summaries, "
    "write 2-3 sentences explaining the most likely reason the stock is up. "
    "Be specific: cite the news that is most relevant. "
    "Do not add disclaimers or generic boilerplate."
)


def analyze_stock(
    symbol: str,
    pct_change: float,
    news_items: list[NewsItem],
    client: anthropic.Anthropic | None = None,
) -> str:
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    news_block = "\n".join(
        f"- [{item.publisher}] {item.title}" + (f"\n  Summary: {item.summary}" if item.summary else "")
        for item in news_items
    ) or "No recent news found."

    user_content = (
        f"Stock: {symbol}\n"
        f"Intraday gain: +{pct_change:.2f}%\n\n"
        f"Recent news:\n{news_block}\n\n"
        "Why is this stock up?"
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},  # cache the static system prompt
            }
        ],
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text.strip()


def analyze_all(
    gainers: list[dict],  # list of {ticker, pct_change, news: list[NewsItem]}
) -> dict[str, str]:
    """Analyze all tickers; reuse a single client instance for connection pooling."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    results: dict[str, str] = {}
    for entry in gainers:
        sym = entry["ticker"]
        print(f"[analyzer] Analyzing {sym} ...")
        try:
            analysis = analyze_stock(sym, entry["pct_change"], entry["news"], client=client)
        except Exception as exc:
            analysis = f"Analysis unavailable: {exc}"
        results[sym] = analysis
    return results


if __name__ == "__main__":
    from news_fetcher import fetch_news
    sym = "NVDA"
    news = fetch_news(sym)
    result = analyze_stock(sym, 4.5, news)
    print(result)
