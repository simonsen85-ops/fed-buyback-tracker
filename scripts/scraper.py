#!/usr/bin/env python3
"""
Fast Ejendom Danmark — Buyback Scraper
Runs via GitHub Actions every Wednesday and Friday.
Scrapes the latest buyback announcement from fastejendom.dk,
parses the table, and updates data.json.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from html.parser import HTMLParser


# ============================================================
# CONFIG
# ============================================================
# The announcement pages follow this pattern:
# https://fastejendom.dk/aktietilbagekoebsprogram-{N}/
# We start from the latest known and increment to find new ones.

DATA_FILE = Path(__file__).parent.parent / "data.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FED-Tracker/1.0)"
}

# NAV history — UPDATE THIS when new quarterly reports are published
NAV_HISTORY = [
    {"from": "2025-10-24", "nav": 281.26, "label": "Q3 2025"},
    {"from": "2026-02-17", "nav": 306.60, "label": "FY 2025"},
]

# Buyback programs — UPDATE when new programs are announced
# Each program has its own frame (ramme) and period
PROGRAMS = [
    {
        "id": 1,
        "start": "2025-10-24",
        "end": "2026-10-23",
        "max_amount": 10000000,  # 10 mio. DKK
        "announced": "2025-10-23",
        "closed_on": "2026-04-17",  # Closed early (hit 10 mio)
    },
    {
        "id": 2,
        "start": "2026-04-20",
        "end": "2027-04-19",
        "max_amount": 10000000,  # 10 mio. DKK
        "announced": "2026-04-17",
        "closed_on": None,  # Still active
    },
]

TOTAL_SHARES = 2659442


# ============================================================
# HTML TABLE PARSER
# ============================================================
class TableParser(HTMLParser):
    """Extracts table rows from HTML."""
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_td = False
        self.in_th = False
        self.current_row = []
        self.rows = []
        self.current_data = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
        elif tag == "td" and self.in_table:
            self.in_td = True
            self.current_data = ""
        elif tag == "th" and self.in_table:
            self.in_th = True
            self.current_data = ""
        elif tag == "tr" and self.in_table:
            self.current_row = []

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        elif tag == "td" and self.in_td:
            self.in_td = False
            self.current_row.append(self.current_data.strip())
        elif tag == "th" and self.in_th:
            self.in_th = False
            self.current_row.append(self.current_data.strip())
        elif tag == "tr" and self.in_table and self.current_row:
            self.rows.append(self.current_row)

    def handle_data(self, data):
        if self.in_td or self.in_th:
            self.current_data += data


def fetch_page(url):
    """Fetch a URL and return the HTML content."""
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        print(f"  Could not fetch {url}: {e}")
        return None


def parse_number(s):
    """Parse a Danish-formatted number string to float."""
    s = s.strip().replace(".", "").replace(",", ".").replace("\xa0", "")
    s = re.sub(r"[^\d.\-]", "", s)
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_date_danish(s):
    """Parse '24. oktober 2025' to '2025-10-24'."""
    months = {
        "januar": "01", "februar": "02", "marts": "03", "april": "04",
        "maj": "05", "juni": "06", "juli": "07", "august": "08",
        "september": "09", "oktober": "10", "november": "11", "december": "12"
    }
    s = s.strip().rstrip(".")
    parts = s.split()
    if len(parts) >= 3:
        day = parts[0].rstrip(".")
        month = months.get(parts[1].lower(), "01")
        year = parts[2]
        return f"{year}-{month}-{day.zfill(2)}"
    return None


def extract_announcement(html):
    """
    Extract buyback data from an announcement page.
    Returns dict with weekly transactions and accumulated totals,
    or None if parsing fails.
    """
    parser = TableParser()
    parser.feed(html)
    rows = parser.rows

    if len(rows) < 3:
        return None

    # Find the announcement date from the page
    date_match = re.search(
        r'<li>\s*<a[^>]*>(\w+ \d{1,2}, \d{4})</a>', html
    ) or re.search(
        r'(\w+ \d{1,2}, \d{4})', html[:3000]
    )

    # Parse table rows
    # Row structure:
    # Row 0: header (Antal aktier | Gennemsnitlig købskurs | Beløb)
    # Row 1: Akkumuleret jf. seneste meddelelse
    # Rows 2-N: Daily transactions
    # Last row before final: empty or separator
    # Final row: Akkumuleret jf. ovenstående

    daily_transactions = []
    prev_acc = None
    new_acc = None

    for row in rows:
        if len(row) < 3:
            continue

        text = " ".join(row).lower()

        # Previous accumulated
        if "seneste meddelelse" in text:
            prev_acc = {
                "shares": int(parse_number(row[1])) if len(row) > 1 else 0,
                "amount": parse_number(row[3]) if len(row) > 3 else 0,
            }
            continue

        # New accumulated
        if "ovenstående" in text:
            new_acc = {
                "shares": int(parse_number(row[1])) if len(row) > 1 else 0,
                "avg_price": parse_number(row[2]) if len(row) > 2 else 0,
                "amount": parse_number(row[3]) if len(row) > 3 else 0,
            }
            continue

        # Daily transaction row — starts with a date
        date_str = parse_date_danish(row[0])
        if date_str and len(row) >= 4:
            shares = int(parse_number(row[1]))
            price = parse_number(row[2])
            amount = parse_number(row[3])
            if shares > 0:
                daily_transactions.append({
                    "date": date_str,
                    "shares": shares,
                    "price": price,
                    "amount": amount
                })

    if not new_acc or new_acc["shares"] == 0:
        return None

    # Calculate week totals
    week_shares = sum(t["shares"] for t in daily_transactions)
    week_amount = sum(t["amount"] for t in daily_transactions)
    week_avg = week_amount / week_shares if week_shares > 0 else 0

    # Sanity check: if acc totals didn't change but there were purchases,
    # the company made an error in the announcement. Recalculate.
    if prev_acc and week_shares > 0 and new_acc["shares"] == prev_acc["shares"]:
        print(f"  Warning: acc_shares unchanged despite {week_shares} purchases — recalculating")
        new_acc["shares"] = prev_acc["shares"] + week_shares
        new_acc["amount"] = prev_acc["amount"] + week_amount
        new_acc["avg_price"] = new_acc["amount"] / new_acc["shares"] if new_acc["shares"] > 0 else 0

    # Determine period string
    if daily_transactions:
        first_date = daily_transactions[0]["date"]
        last_date = daily_transactions[-1]["date"]
    else:
        first_date = last_date = ""

    return {
        "announcement_date": last_date,
        "period_start": first_date,
        "period_end": last_date,
        "week_shares": week_shares,
        "week_amount": round(week_amount),
        "week_avg_price": round(week_avg, 2),
        "acc_shares": new_acc["shares"],
        "acc_amount": round(new_acc["amount"]),
        "acc_avg_price": round(new_acc["avg_price"], 2),
        "daily": daily_transactions,
    }


def load_data():
    """Load existing data.json or return default structure."""
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {
        "total_shares": TOTAL_SHARES,
        "nav_history": NAV_HISTORY,
        "program_max": 10000000,
        "program_start": "2025-10-24",
        "program_end": "2026-10-23",
        "last_page_index": 107,  # Will start scanning from 108
        "announcements": [],
        "last_updated": None,
    }


def save_data(data):
    """Save data.json."""
    data["last_updated"] = datetime.utcnow().isoformat() + "Z"
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(data['announcements'])} announcements to {DATA_FILE}")


def scan_for_new_announcements(data):
    """
    Scan fastejendom.dk for new buyback announcements.
    Starts from last_page_index + 1 and keeps going until 404.
    """
    start_idx = data.get("last_page_index", 107) + 1
    known_pages = set()
    for a in data["announcements"]:
        if "page_index" in a:
            known_pages.add(a["page_index"])

    new_count = 0
    idx = start_idx
    max_consecutive_fails = 3
    fails = 0

    while fails < max_consecutive_fails:
        url = f"https://fastejendom.dk/aktietilbagekoebsprogram-{idx}/"
        print(f"Fetching page {idx}: {url}")

        html = fetch_page(url)
        if not html or "aktietilbagekøbsprogram" not in html.lower():
            print(f"  Page {idx}: not found or not a buyback page")
            fails += 1
            idx += 1
            continue

        fails = 0  # Reset on success
        result = extract_announcement(html)

        if result and idx not in known_pages:
            result["page_index"] = idx
            data["announcements"].append(result)
            known_pages.add(idx)
            data["last_page_index"] = idx
            new_count += 1
            print(f"  ✓ New announcement: {result['announcement_date']}, "
                  f"acc {result['acc_shares']} shares, "
                  f"acc {result['acc_amount']} DKK")
        elif result:
            print(f"  Page {idx}: already known")
            data["last_page_index"] = idx
        else:
            print(f"  Page {idx}: could not parse table")

        idx += 1

    return new_count


def fetch_today_nasdaq_volume():
    """
    Fetch today's intraday trades from Nasdaq's JSON API.
    Returns total volume for the current trading day, or None on failure.
    This is the authoritative source for FED.CO volume.
    """
    try:
        url = ('https://api.nasdaq.com/api/nordic//instruments/TX1484734/trades'
               '?type=INTRADAY&assetClass=SHARES&lang=en')
        req = Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nasdaq.com/european-market-activity/shares/fed?id=TX1484734',
            'Origin': 'https://www.nasdaq.com',
        })
        with urlopen(req, timeout=15) as resp:
            status = resp.status
            raw_body = resp.read()
            print(f"  [debug] Nasdaq intraday: status={status}, bytes={len(raw_body)}")
            data = json.loads(raw_body)

        # Response structure: data.data.rows contains trades
        rows = data.get('data', {}).get('rows', []) if data.get('data') else []
        if not rows:
            # Debug: show top-level keys so we can understand the response shape
            top_keys = list(data.keys()) if isinstance(data, dict) else []
            print(f"  [debug] No rows. Top-level keys: {top_keys}")
            if 'status' in data:
                print(f"  [debug] status field: {data.get('status')}")
            return None

        total_vol = 0
        trade_date = None
        for row in rows:
            # Volume field might be string with commas/quotes
            vol_str = str(row.get('volume', '')).replace(',', '').replace('"', '').strip()
            if vol_str.isdigit():
                total_vol += int(vol_str)
            # Capture date from first trade's timestamp
            if trade_date is None:
                ts = row.get('time') or row.get('executionTime') or ''
                # Format: "2026-04-17T14:54:41+0200" or "14:54:41"
                if 'T' in ts:
                    trade_date = ts.split('T')[0]

        # If no date from trades, assume today
        if trade_date is None:
            trade_date = datetime.utcnow().strftime('%Y-%m-%d')

        return {'date': trade_date, 'volume': total_vol, 'trades': len(rows)}
    except Exception as e:
        print(f"  Nasdaq intraday fetch failed: {e}")
        return None


def load_nasdaq_csv_bulk():
    """
    Fetch daily historical volumes from Nasdaq's chart download endpoint.

    Despite the 'download' in the URL, this endpoint returns JSON, not CSV.
    The browser's CSV button converts the JSON to CSV client-side.

    Response shape (simplified):
        {
          "data": {
            "chartData": {
              "orderbookId": "TX1484734",
              ...
              "rows": [
                {"Date": "2026-04-17", "High": "216.00", "Low": "212.00",
                 "ClosePrice": "216.00", "Volume": "2,152", "Turnover": "459,176",
                 "Trades": "19"},
                ...
              ]
            }
          }
        }

    Returns dict of {date_str: volume_int}.
    """
    from datetime import timedelta

    result = {}
    try:
        # Fetch ~400 days of history (enough for 20-day rolling average with buffer)
        end_date = datetime.utcnow().strftime('%Y-%m-%d')
        start_date = (datetime.utcnow() - timedelta(days=400)).strftime('%Y-%m-%d')

        url = (
            'https://api.nasdaq.com/api/nordic/instruments/TX1484734/chart/download'
            f'?assetClass=SHARES&fromDate={start_date}&toDate={end_date}'
        )
        req = Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json,text/csv,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nasdaq.com/european-market-activity/shares/fed?id=TX1484734',
            'Origin': 'https://www.nasdaq.com',
        })
        with urlopen(req, timeout=20) as resp:
            raw = resp.read().decode('utf-8-sig', errors='replace')

        # Response is JSON
        data = json.loads(raw)

        # Navigate to rows array
        chart_data = data.get('data', {})
        if chart_data is None:
            chart_data = {}
        chart_inner = chart_data.get('chartData', {}) if isinstance(chart_data, dict) else {}

        # Find the rows — could be under 'rows', 'marketData', 'series', etc.
        rows = None
        for key in ['rows', 'marketData', 'series', 'data']:
            candidate = chart_inner.get(key)
            if isinstance(candidate, list) and candidate:
                rows = candidate
                print(f"  [debug] Found {len(rows)} rows under chartData.{key}")
                break

        if not rows:
            # Show top-level keys to help debug
            top_keys = list(chart_inner.keys()) if isinstance(chart_inner, dict) else []
            print(f"  [debug] No rows found. chartData keys: {top_keys}")
            return {}

        # Parse each row — try multiple field name variants
        for row in rows:
            if not isinstance(row, dict):
                continue
            # Date field candidates
            d = None
            for k in ['Date', 'date', 'tradeDate']:
                if k in row and row[k]:
                    d = str(row[k]).strip()
                    break
            # Volume field candidates
            v_str = None
            for k in ['Volume', 'volume', 'totalVolume', 'Total volume', 'shareVolume']:
                if k in row and row[k] is not None:
                    v_str = str(row[k])
                    break

            if d and v_str:
                v_clean = v_str.replace(',', '').replace('"', '').replace(' ', '').strip()
                if v_clean.isdigit():
                    # Normalize date to YYYY-MM-DD
                    if '/' in d:
                        # Could be MM/DD/YYYY
                        try:
                            dt = datetime.strptime(d, '%m/%d/%Y')
                            d = dt.strftime('%Y-%m-%d')
                        except ValueError:
                            pass
                    result[d] = int(v_clean)

        if result:
            print(f"  ✓ Nasdaq chart/download: {len(result)} daily volumes")
        else:
            print(f"  (Parsed JSON but extracted 0 volumes — field names may differ)")
            # Show first row's keys to aid debugging
            if rows:
                print(f"  [debug] First row keys: {list(rows[0].keys())[:15]}")
    except Exception as e:
        print(f"  Nasdaq chart/download failed: {e}")

    return result


def fetch_yahoo_history():
    """Fetch 2 years of daily volumes from Yahoo Finance (fallback)."""
    daily_vol = {}
    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/FED.CO?interval=1d&range=2y'
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read())

        result = raw['chart']['result'][0]
        timestamps = result['timestamp']
        volumes = result['indicators']['quote'][0]['volume']

        for ts, vol in zip(timestamps, volumes):
            d = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
            if vol is not None:
                daily_vol[d] = vol
    except Exception as e:
        print(f"  Yahoo history fetch failed: {e}")
    return daily_vol


def fetch_weekly_volumes(announcements, data):
    """
    Build daily volume history using three sources (priority order):
    1. Nasdaq chart/download API — 1-year historical daily volumes (automatic)
    2. Nasdaq intraday API — today's volume, accumulates into data.json
    3. Yahoo Finance — fallback for any gaps
    """
    print("\nFetching trading volumes...")

    # SOURCE 1: Bulk Nasdaq CSV (manually maintained)
    nasdaq_bulk = load_nasdaq_csv_bulk()

    # SOURCE 2: Accumulated daily Nasdaq data (from API calls)
    nasdaq_history = data.get('nasdaq_daily_volumes', {})

    # Fetch today's volume from Nasdaq intraday API
    today_data = fetch_today_nasdaq_volume()
    if today_data and today_data['volume'] > 0:
        nasdaq_history[today_data['date']] = today_data['volume']
        print(f"  ✓ Nasdaq today ({today_data['date']}): {today_data['volume']} aktier in {today_data['trades']} trades")
    else:
        print(f"  (Nasdaq intraday unavailable — using existing history only)")

    data['nasdaq_daily_volumes'] = nasdaq_history

    # SOURCE 3: Yahoo Finance fallback
    yahoo_vol = fetch_yahoo_history()
    if yahoo_vol:
        print(f"  ✓ Yahoo Finance: {len(yahoo_vol)} daily entries")

    # Merge in priority order: bulk CSV wins > intraday API > Yahoo
    daily_vol = dict(yahoo_vol)           # Start with Yahoo
    daily_vol.update(nasdaq_history)      # Override with intraday-accumulated
    daily_vol.update(nasdaq_bulk)         # Override with bulk CSV (highest priority)

    # Track source for each date (for tooltip)
    source_map = {}
    for d in daily_vol:
        if d in nasdaq_bulk:
            source_map[d] = 'nasdaq'
        elif d in nasdaq_history:
            source_map[d] = 'nasdaq'
        else:
            source_map[d] = 'yahoo'

    nasdaq_count = sum(1 for s in source_map.values() if s == 'nasdaq')
    yahoo_count = len(source_map) - nasdaq_count
    print(f"  Merged: {len(daily_vol)} days ({nasdaq_count} Nasdaq, {yahoo_count} Yahoo)")

    if not daily_vol:
        print("  Warning: No volume data available from any source")
        return

    try:
        # Build sorted list for 20-day rolling average
        daily_list = sorted(daily_vol.items())
        date_to_idx = {d: i for i, (d, _) in enumerate(daily_list)}

        # For each announcement, compute weekly market volume AND theoretical max
        for a in announcements:
            start = a.get('period_start', '')
            end = a.get('period_end', '')
            if not start or not end:
                continue

            period_dates = sorted([d for d in daily_vol if start <= d <= end])
            week_vol = sum(daily_vol[d] for d in period_dates)

            max_allowed_sum = 0
            valid_days = 0
            daily_detail = []
            for d in period_dates:
                idx = date_to_idx.get(d)
                if idx is not None and idx >= 20:
                    prior_20 = [daily_list[i][1] for i in range(idx - 20, idx)]
                    avg_20 = sum(prior_20) / 20
                    max_d = round(0.25 * avg_20)
                    max_allowed_sum += max_d
                    valid_days += 1
                    daily_detail.append({
                        "date": d,
                        "day_volume": daily_vol[d],
                        "avg_20d": round(avg_20),
                        "max_allowed": max_d,
                        "source": source_map.get(d, 'yahoo')
                    })

            a['market_volume'] = week_vol
            a['max_allowed_week'] = max_allowed_sum if valid_days > 0 else 0
            a['daily_volume_detail'] = daily_detail

            if daily_detail:
                a['avg_volume_20d'] = round(sum(d['avg_20d'] for d in daily_detail) / len(daily_detail))
            else:
                a['avg_volume_20d'] = 0

            if a['week_shares'] > 0 and week_vol > 0:
                a['buyback_pct_of_volume'] = round(a['week_shares'] / week_vol * 100, 1)
            else:
                a['buyback_pct_of_volume'] = 0

            if max_allowed_sum > 0:
                a['utilization_pct'] = round(a['week_shares'] / max_allowed_sum * 100, 1)
            else:
                a['utilization_pct'] = 0

        print("  Volume and 25% Safe Harbour limits matched to announcements")

    except Exception as e:
        print(f"  Warning: Error processing volume data: {e}")


def fetch_current_price(data):
    """Fetch the latest closing price from Yahoo Finance."""
    print("\nFetching current price from Yahoo Finance...")
    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/FED.CO?interval=1d&range=5d'
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read())

        result = raw['chart']['result'][0]
        closes = result['indicators']['quote'][0]['close']
        # Get last non-None close
        price = None
        for c in reversed(closes):
            if c is not None:
                price = round(c, 2)
                break

        if price:
            data['current_price'] = price
            print(f"  Current price: {price} DKK")
        else:
            print("  Warning: Could not determine price")

    except Exception as e:
        print(f"  Warning: Could not fetch price: {e}")


def main():
    print("=" * 60)
    print("Fast Ejendom Danmark — Buyback Scraper")
    print(f"Run time: {datetime.utcnow().isoformat()}Z")
    print("=" * 60)

    data = load_data()
    print(f"Existing announcements: {len(data['announcements'])}")
    print(f"Last page index: {data.get('last_page_index', 'N/A')}")

    new_count = scan_for_new_announcements(data)

    # Sort announcements by date (handles program transitions where acc_shares resets)
    data["announcements"].sort(key=lambda a: a["announcement_date"])

    # Fetch trading volumes
    fetch_weekly_volumes(data["announcements"], data)

    # Fetch current price
    fetch_current_price(data)

    # Update NAV history and programs config
    data["nav_history"] = NAV_HISTORY
    data["total_shares"] = TOTAL_SHARES
    data["programs"] = PROGRAMS
    data["program_max"] = sum(p["max_amount"] for p in PROGRAMS)  # Cumulative cap

    save_data(data)

    print(f"\nDone. {new_count} new announcement(s) added.")
    print(f"Total: {len(data['announcements'])} announcements")

    if data["announcements"]:
        last = data["announcements"][-1]
        print(f"Latest: {last['announcement_date']} — "
              f"{last['acc_shares']} shares, {last['acc_amount']} DKK")
        if 'market_volume' in last:
            print(f"  Market volume: {last['market_volume']}, "
                  f"buyback = {last.get('buyback_pct_of_volume', 0)}% of volume")


if __name__ == "__main__":
    main()
