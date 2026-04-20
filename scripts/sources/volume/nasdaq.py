"""
Nasdaq volume data source.

Two endpoints:
1. chart/download — returns up to ~1 year of daily OHLCV data as JSON
2. trades (intraday) — today's tick-by-tick trades

Used to compute:
- Daily total market volume (for "% af volumen" metric)
- 20-day rolling average volume (for 25% Safe Harbour ceiling calculation)

The `instrument_id` differs per stock. For FED.CO it's TX1484734.
Find it by inspecting api.nasdaq.com requests on the relevant Nasdaq page.
"""

import json
from datetime import datetime, timedelta
from urllib.request import urlopen, Request


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/csv,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com",
}


def fetch_nasdaq_daily_history(
    instrument_id: str,
    referer_url: str,
    days_back: int = 400,
) -> dict[str, int]:
    """
    Fetch daily trading volumes from Nasdaq's chart/download endpoint.

    Args:
        instrument_id: Nasdaq internal ID (e.g. "TX1484734" for FED.CO)
        referer_url: Nasdaq page URL for this stock, used as Referer header
                     to avoid bot detection
        days_back: How many days of history to fetch (default 400)

    Returns:
        Dict of {date_str: volume_int} where date_str is "YYYY-MM-DD"
    """
    result = {}
    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    url = (
        f"https://api.nasdaq.com/api/nordic/instruments/{instrument_id}/chart/download"
        f"?assetClass=SHARES&fromDate={start_date}&toDate={end_date}"
    )

    headers = dict(HEADERS)
    headers["Referer"] = referer_url

    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8-sig", errors="replace")

        data = json.loads(raw)
        rows = (data.get("data") or {}).get("charts", {}).get("rows", []) or []

        for row in rows:
            if not isinstance(row, dict):
                continue
            d = str(row.get("dateTime", "")).strip()
            v_str = str(row.get("totalVolume", "")).replace(",", "").replace('"', "").strip()
            if d and v_str.isdigit():
                result[d] = int(v_str)

        if result:
            print(f"  [nasdaq] chart/download: {len(result)} daily volumes")
        else:
            print(f"  [nasdaq] chart/download: 0 rows parsed (rows={len(rows)})")
    except Exception as e:
        print(f"  [nasdaq] chart/download failed: {e}")

    return result


def fetch_nasdaq_intraday_volume(
    instrument_id: str,
    referer_url: str,
) -> dict | None:
    """
    Fetch today's intraday trades, return total volume.

    Args:
        instrument_id: Nasdaq internal ID
        referer_url: Nasdaq page URL for this stock

    Returns:
        Dict {date: "YYYY-MM-DD", volume: int, trades: int} or None
    """
    url = (
        f"https://api.nasdaq.com/api/nordic//instruments/{instrument_id}/trades"
        f"?type=INTRADAY&assetClass=SHARES&lang=en"
    )
    headers = dict(HEADERS)
    headers["Referer"] = referer_url

    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        rows = (data.get("data") or {}).get("rows", []) or []
        if not rows:
            return None

        total_vol = 0
        trade_date = None
        for row in rows:
            vol_str = str(row.get("volume", "")).replace(",", "").replace('"', "").strip()
            if vol_str.isdigit():
                total_vol += int(vol_str)
            if trade_date is None:
                ts = row.get("time") or row.get("executionTime") or ""
                if "T" in str(ts):
                    trade_date = str(ts).split("T")[0]

        if trade_date is None:
            trade_date = datetime.utcnow().strftime("%Y-%m-%d")

        return {"date": trade_date, "volume": total_vol, "trades": len(rows)}
    except Exception as e:
        print(f"  [nasdaq] intraday failed: {e}")
        return None
