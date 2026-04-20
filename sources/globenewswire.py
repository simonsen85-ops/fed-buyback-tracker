"""
GlobeNewswire announcement source.

GlobeNewswire is Nasdaq Nordic's official news distribution channel. All
regulatory announcements from Nasdaq Copenhagen, Stockholm, Helsinki, and
Iceland-listed companies are published here — typically hours before they
appear on the company's own website.

Listing URL structure:
    https://www.globenewswire.com/en/search/organization/{URL_ENCODED_NAME}
    (plus ?page=N for pagination)

Each release links to:
    https://www.globenewswire.com/news-release/YYYY/MM/DD/{RELEASE_ID}/0/{lang}/{slug}.html

The release ID is globally unique across GlobeNewswire, which makes it
perfect as our deduplication key.

This source is generic — it takes a company name and extracts any
announcement whose title matches a buyback keyword (configurable).
"""

import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import quote
from urllib.request import urlopen, Request

from .base import Announcement, AnnouncementSource


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# Helpers — shared with fastejendom.py
# ============================================================
def parse_number(s):
    """Parse Danish-formatted number '9.999.890' or '210,57' → float."""
    if not s:
        return 0
    s = str(s).strip()
    s = s.replace(".", "").replace(",", ".").replace("\xa0", "").replace(" ", "")
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0


def parse_date_danish(s):
    """Parse Danish date '13. april 2026' → '2026-04-13'."""
    if not s:
        return None
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
        try:
            return f"{year}-{month}-{day.zfill(2)}"
        except ValueError:
            return None
    return None


# ============================================================
# HTML table parser (shared with fastejendom.py)
# ============================================================
class _TableParser(HTMLParser):
    """Extracts all table rows from an HTML page as list[list[str]]."""
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
            self.current_row.append(self.current_data.strip())
            self.in_td = False
        elif tag == "th" and self.in_th:
            self.current_row.append(self.current_data.strip())
            self.in_th = False
        elif tag == "tr" and self.in_table and self.current_row:
            self.rows.append(self.current_row)
            self.current_row = []

    def handle_data(self, data):
        if self.in_td or self.in_th:
            self.current_data += data


# ============================================================
# Announcement body parser — extracts buyback table data
# ============================================================
def _extract_announcement_body(html, source_url, source_id, announcement_date):
    """
    Given the HTML of a single GlobeNewswire release, extract the buyback
    transaction table. Returns a partial dict with:
        week_shares, week_amount, week_avg_price,
        acc_shares, acc_amount,
        period_start, period_end,
        daily_transactions

    Returns None if parsing fails.
    """
    parser = _TableParser()
    parser.feed(html)
    rows = parser.rows

    if not rows:
        return None

    daily_transactions = []
    prev_acc = None
    new_acc = None

    for row in rows:
        if len(row) < 3:
            continue
        text = " ".join(row).lower()

        # Previous accumulated (start of program or last week's close)
        if "seneste meddelelse" in text:
            prev_acc = {
                "shares": int(parse_number(row[1])) if len(row) > 1 else 0,
                "amount": int(parse_number(row[3])) if len(row) > 3 else 0,
            }
            continue

        # Current (post-this-week) accumulated
        if "ovenstående" in text:
            new_acc = {
                "shares": int(parse_number(row[1])) if len(row) > 1 else 0,
                "avg_price": parse_number(row[2]) if len(row) > 2 else 0,
                "amount": int(parse_number(row[3])) if len(row) > 3 else 0,
            }
            continue

        # Daily transaction — row[0] is a Danish date
        date_str = parse_date_danish(row[0])
        if date_str and len(row) >= 4:
            shares = int(parse_number(row[1]))
            price = parse_number(row[2])
            amount = int(parse_number(row[3]))
            if shares > 0:
                daily_transactions.append({
                    "date": date_str,
                    "shares": shares,
                    "price": price,
                    "amount": amount,
                })

    if not new_acc or new_acc["shares"] == 0:
        return None

    # Weekly totals = sum of daily transactions
    week_shares = sum(t["shares"] for t in daily_transactions)
    week_amount = sum(t["amount"] for t in daily_transactions)

    # Sanity check: company sometimes publishes same acc_shares in consecutive
    # announcements by mistake. If acc didn't move but we have purchases,
    # trust the weekly data and recompute acc from prev_acc.
    if prev_acc and new_acc["shares"] == prev_acc["shares"] and week_shares > 0:
        new_acc["shares"] = prev_acc["shares"] + week_shares
        new_acc["amount"] = prev_acc["amount"] + week_amount

    week_avg = week_amount / week_shares if week_shares > 0 else 0

    # Period = first and last daily transaction dates
    if daily_transactions:
        dates_sorted = sorted(t["date"] for t in daily_transactions)
        period_start = dates_sorted[0]
        period_end = dates_sorted[-1]
    else:
        # Fallback: use announcement date
        period_start = announcement_date
        period_end = announcement_date

    return {
        "week_shares": week_shares,
        "week_amount": week_amount,
        "week_avg_price": round(week_avg, 2),
        "acc_shares": new_acc["shares"],
        "acc_amount": new_acc["amount"],
        "period_start": period_start,
        "period_end": period_end,
        "daily_transactions": daily_transactions,
    }


# ============================================================
# The source class
# ============================================================
class GlobeNewswireSource(AnnouncementSource):
    """
    Fetches buyback announcements from GlobeNewswire for a given company.

    Args:
        company: Full company name as shown on GlobeNewswire
                 (e.g. "Fast Ejendom Danmark A/S").
        uid_prefix: Prefix for generated UIDs (e.g. "fed"). Used to make
                    UIDs readable and prevent collisions across trackers.
        buyback_keywords: List of lowercased substrings to match in release
                          titles. Default matches Danish/Swedish/English
                          buyback announcement titles.
        listing_max_pages: How many paginated listing pages to scan (10 per
                           page). Default 3 = 30 most recent releases.
    """

    name = "globenewswire"

    DEFAULT_KEYWORDS = (
        "aktietilbagekøb",         # Danish
        "aktietilbagekøbsprogram", # Danish, longer form
        "återköp",                 # Swedish
        "share buyback",           # English
        "share repurchase",        # English
    )

    # Regex to extract release URLs from listing page
    # Matches: /news-release/YYYY/MM/DD/{numeric_id}/0/{lang}/{slug}.html
    _RELEASE_URL_RE = re.compile(
        r'href="(/news-release/(\d{4})/(\d{2})/(\d{2})/(\d+)/[^"]+)"',
        re.IGNORECASE,
    )

    def __init__(
        self,
        company: str,
        uid_prefix: str,
        buyback_keywords: Optional[tuple[str, ...]] = None,
        listing_max_pages: int = 3,
    ):
        self.company = company
        self.uid_prefix = uid_prefix
        self.buyback_keywords = tuple(
            k.lower() for k in (buyback_keywords or self.DEFAULT_KEYWORDS)
        )
        self.listing_max_pages = listing_max_pages

    # --------------------------------------------------------
    # URL construction
    # --------------------------------------------------------
    def _listing_url(self, page: int = 1) -> str:
        """Build the search listing URL for this company."""
        # GlobeNewswire uses double URL-encoding: "/" → %2F → %252F
        encoded = quote(self.company, safe="")       # Fast%20Ejendom%20Danmark%20A%2FS
        encoded = encoded.replace("%", "%25")         # Double-encode
        base = f"https://www.globenewswire.com/en/search/organization/{encoded}"
        if page > 1:
            return f"{base}?page={page}"
        return base

    @staticmethod
    def _fetch(url: str, timeout: int = 20) -> Optional[str]:
        """HTTP GET with standard headers. Returns text or None on error."""
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  [globenewswire] fetch failed: {url} — {e}")
            return None

    # --------------------------------------------------------
    # Listing page → list of release metadata
    # --------------------------------------------------------
    def _list_releases(self) -> list[dict]:
        """
        Scan the listing pages and return a list of release metadata dicts:
            {url, release_id, announcement_date, title}

        Only releases whose title contains a buyback keyword are returned.
        """
        found = []
        seen_ids = set()

        for page in range(1, self.listing_max_pages + 1):
            url = self._listing_url(page)
            html = self._fetch(url)
            if not html:
                break

            # Find all release URLs on this page
            matches = self._RELEASE_URL_RE.findall(html)
            if not matches:
                break

            for path, year, month, day, rel_id in matches:
                if rel_id in seen_ids:
                    continue
                seen_ids.add(rel_id)

                # Extract title near this URL for keyword matching
                # Titles appear in <a> anchors after the URL match
                title = self._extract_title_near(html, path)

                if not self._matches_buyback(title):
                    continue

                found.append({
                    "url": f"https://www.globenewswire.com{path}",
                    "release_id": rel_id,
                    "announcement_date": f"{year}-{month}-{day}",
                    "title": title,
                })

        return found

    @staticmethod
    def _extract_title_near(html: str, path: str) -> str:
        """Find the anchor text associated with a given release path."""
        # Match: <a href="{path}">TITLE</a> (case-insensitive, non-greedy)
        escaped = re.escape(path)
        m = re.search(
            rf'<a[^>]+href="{escaped}"[^>]*>([^<]+)</a>',
            html, re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()
        return ""

    def _matches_buyback(self, title: str) -> bool:
        """Check if a release title looks like a buyback announcement."""
        if not title:
            return False
        low = title.lower()
        # Exclude program-start announcements (no transactions yet)
        # We want the weekly transaction announcements
        exclude = ("igangsætning", "konklusion")
        if any(x in low for x in exclude):
            # Still include conclusion announcements — they contain the final week's buys
            if "konklusion" in low:
                return True
            return False
        return any(kw in low for kw in self.buyback_keywords)

    # --------------------------------------------------------
    # Main entry point
    # --------------------------------------------------------
    def fetch_recent(self, max_announcements: int = 20) -> list[Announcement]:
        """Fetch recent buyback announcements. Returns newest-first."""
        print(f"\n[globenewswire] Scanning for {self.company}...")

        metadata_list = self._list_releases()
        print(f"  [globenewswire] Found {len(metadata_list)} buyback releases in listings")

        announcements: list[Announcement] = []

        for meta in metadata_list[:max_announcements]:
            html = self._fetch(meta["url"])
            if not html:
                continue

            body = _extract_announcement_body(
                html,
                source_url=meta["url"],
                source_id=meta["release_id"],
                announcement_date=meta["announcement_date"],
            )
            if not body:
                print(f"  [globenewswire] Could not parse table in {meta['url']}")
                continue

            ann = Announcement(
                uid=f"{self.uid_prefix}-gnw-{meta['release_id']}",
                announcement_date=meta["announcement_date"],
                source=self.name,
                source_url=meta["url"],
                period_start=body["period_start"],
                period_end=body["period_end"],
                week_shares=body["week_shares"],
                week_amount=body["week_amount"],
                week_avg_price=body["week_avg_price"],
                acc_shares=body["acc_shares"],
                acc_amount=body["acc_amount"],
                daily_transactions=body["daily_transactions"],
            )
            announcements.append(ann)
            print(
                f"  [globenewswire] ✓ {ann.announcement_date}: "
                f"week {ann.week_shares}sh / acc {ann.acc_shares}sh"
            )

        # Newest first
        announcements.sort(key=lambda a: a.announcement_date, reverse=True)
        return announcements
