"""
Mortgage-bond prices from Nasdaq Copenhagen (used by the Gæld tab).

Endpoint: api.nasdaq.com/api/nordic/instruments/{orderbookId}/info?assetClass=MORTGAGE_BONDS
returns qdHeader.primaryData.lastSalePrice, e.g. "DKK 98.40". Nasdaq's daily-history
endpoint (chart/download) times out for these bonds, so we don't use it: the scraper
stores one observation per run in data.json["bond_prices"][isin] and the history
grows from there.
"""

import json
import re
from datetime import datetime, timezone
from urllib.request import Request, urlopen

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/european-market-activity/mortgage-bonds",
}


def fetch_bond_last_price(orderbook_id: str) -> dict | None:
    """Return {"price": float, "nasdaq_ts": str} or None if Nasdaq has no last sale."""
    url = (
        f"https://api.nasdaq.com/api/nordic/instruments/{orderbook_id}/info"
        f"?assetClass=MORTGAGE_BONDS&lang=en"
    )
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8-sig", errors="replace"))
        pd = (((data.get("data") or {}).get("qdHeader") or {}).get("primaryData")) or {}
        m = re.search(r"(\d+(?:\.\d+)?)", pd.get("lastSalePrice") or "")
        if not m:
            print(f"  [bonds] {orderbook_id}: no last sale price")
            return None
        return {"price": float(m.group(1)), "nasdaq_ts": pd.get("lastTradeTimestamp") or ""}
    except Exception as e:  # network/format problems must not break the buyback scrape
        print(f"  [bonds] {orderbook_id} failed: {e}")
        return None


def update_bond_prices(data: dict, bonds: list[dict]) -> None:
    """Append today's last price per bond to data["bond_prices"][isin] (one row per date)."""
    store = data.setdefault("bond_prices", {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for b in bonds:
        q = fetch_bond_last_price(b["orderbook_id"])
        if not q:
            continue
        hist = [r for r in store.get(b["isin"], []) if r.get("date") != today]
        hist.append({"date": today, "price": q["price"], "nasdaq_ts": q["nasdaq_ts"]})
        store[b["isin"]] = sorted(hist, key=lambda r: r["date"])
        print(f"  [bonds] {b['name']} ({b['isin']}): {q['price']}")
