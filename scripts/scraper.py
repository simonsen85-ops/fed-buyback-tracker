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
    known_acc_shares = set()
    for a in data["announcements"]:
        known_acc_shares.add(a["acc_shares"])

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

        if result and result["acc_shares"] not in known_acc_shares:
            data["announcements"].append(result)
            known_acc_shares.add(result["acc_shares"])
            data["last_page_index"] = idx
            new_count += 1
            print(f"  ✓ New announcement: {result['announcement_date']}, "
                  f"acc {result['acc_shares']} shares, "
                  f"acc {result['acc_amount']} DKK")
        elif result:
            print(f"  Page {idx}: already known (acc_shares={result['acc_shares']})")
            data["last_page_index"] = idx
        else:
            print(f"  Page {idx}: could not parse table")

        idx += 1

    return new_count


def main():
    print("=" * 60)
    print("Fast Ejendom Danmark — Buyback Scraper")
    print(f"Run time: {datetime.utcnow().isoformat()}Z")
    print("=" * 60)

    data = load_data()
    print(f"Existing announcements: {len(data['announcements'])}")
    print(f"Last page index: {data.get('last_page_index', 'N/A')}")

    new_count = scan_for_new_announcements(data)

    # Sort announcements by accumulated shares (chronological order)
    data["announcements"].sort(key=lambda a: a["acc_shares"])

    # Update NAV history
    data["nav_history"] = NAV_HISTORY
    data["total_shares"] = TOTAL_SHARES

    save_data(data)

    print(f"\nDone. {new_count} new announcement(s) added.")
    print(f"Total: {len(data['announcements'])} announcements")

    if data["announcements"]:
        last = data["announcements"][-1]
        print(f"Latest: {last['announcement_date']} — "
              f"{last['acc_shares']} shares, {last['acc_amount']} DKK")


if __name__ == "__main__":
    main()
