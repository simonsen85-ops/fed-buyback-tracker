"""
Yahoo Finance volume data source (fallback).

Yahoo returns ~2 years of daily OHLCV data for free. It's less accurate
for Danish small-caps than Nasdaq's own data (may omit auction volumes
and Safe Harbour-flagged buyback trades), but useful as a backup to
fill gaps in the Nasdaq data.
"""

import json
from datetime import datetime
from urllib.request import urlopen, Request


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BuybackTracker/1.0)",
}


def fetch_yahoo_daily_history(ticker: str) -> dict[str, int]:
    """
    Fetch ~2 years of daily volumes from Yahoo Finance.

    Args:
        ticker: Yahoo ticker (e.g. "FED.CO", "EVO.ST", "IMB.L")

    Returns:
        Dict of {date_str: volume_int}
    """
    result = {}
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2y"
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read())

        chart_result = raw["chart"]["result"][0]
        timestamps = chart_result["timestamp"]
        volumes = chart_result["indicators"]["quote"][0]["volume"]

        for ts, vol in zip(timestamps, volumes):
            if vol is not None:
                d = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                result[d] = vol

        if result:
            print(f"  [yahoo] {ticker}: {len(result)} daily entries")
    except Exception as e:
        print(f"  [yahoo] {ticker} failed: {e}")

    return result


def fetch_yahoo_current_price(ticker: str) -> float | None:
    """Fetch the latest closing price."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read())

        closes = raw["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        # Last non-None close
        for c in reversed(closes):
            if c is not None:
                return round(c, 2)
    except Exception as e:
        print(f"  [yahoo] price fetch failed for {ticker}: {e}")
    return None
