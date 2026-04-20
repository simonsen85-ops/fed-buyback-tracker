"""
Fast Ejendom Danmark website source.

This is the FED-specific fallback source that scrapes fastejendom.dk directly.
Used when GlobeNewswire is unavailable or hasn't indexed a new announcement yet.

URL pattern: https://fastejendom.dk/aktietilbagekoebsprogram-{N}/
where N is a sequentially incrementing slug number (106, 107, 108, ...).

This is NOT the meddelelse number (1-20+) — it's a page slug specific to
FED's WordPress install. Not all N values have announcements (some are
other post types), so we scan through 404s to find the next one.

Historical fact: FED typically publishes here 1-3 days AFTER the
GlobeNewswire regulatory release. Which is why we check GlobeNewswire first.
"""

import re
from html.parser import HTMLParser
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import urlopen, Request

from .base import Announcement, AnnouncementSource


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FED-Tracker/1.0)"
}


# ============================================================
# Helpers (duplicated from globenewswire.py for independence)
# ============================================================
def _parse_number(s):
    """'9.999.890' or '210,57' → float."""
    if not s:
        return 0
    s = str(s).strip()
    s = s.replace(".", "").replace(",", ".").replace("\xa0", "").replace(" ", "")
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0


def _parse_date_danish(s):
    """'13. april 2026' → '2026-04-13'."""
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


class _TableParser(HTMLParser):
    """Extracts all table rows from HTML."""
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
# The source class
# ============================================================
class FastEjendomSource(AnnouncementSource):
    """
    Scrapes fastejendom.dk for FED buyback announcements.

    This is FED-specific — fastejendom.dk is FED's own website, and the
    URL pattern is theirs. Cannot be reused for other companies.

    Args:
        starting_page_slug: First page slug to scan from. Tracker keeps
                            track of the latest found slug and passes it in
                            on subsequent runs.
        max_consecutive_404s: How many 404s in a row before giving up
                              (in case slugs skip numbers).
    """

    name = "fastejendom"
    uid_prefix = "fed"

    URL_PATTERN = "https://fastejendom.dk/aktietilbagekoebsprogram-{idx}/"

    def __init__(
        self,
        starting_page_slug: int = 108,
        max_consecutive_404s: int = 3,
    ):
        self.starting_page_slug = starting_page_slug
        self.max_consecutive_404s = max_consecutive_404s

    # --------------------------------------------------------
    @staticmethod
    def _fetch(url: str, timeout: int = 15) -> Optional[str]:
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except HTTPError as e:
            if e.code == 404:
                return None
            print(f"  [fastejendom] HTTP {e.code} on {url}")
            return None
        except (URLError, Exception) as e:
            print(f"  [fastejendom] fetch failed: {url} — {e}")
            return None

    # --------------------------------------------------------
    def _extract_announcement(self, html: str, page_idx: int, url: str) -> Optional[Announcement]:
        """Parse a single FED announcement page into an Announcement object."""
        parser = _TableParser()
        parser.feed(html)
        rows = parser.rows

        if len(rows) < 3:
            return None

        # Announcement date — FED's WP pages show it in a listing or meta tag
        date_match = re.search(
            r'(\d{1,2}\.\s*(?:januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december)\s*\d{4})',
            html, re.IGNORECASE,
        )
        announcement_date = None
        if date_match:
            announcement_date = _parse_date_danish(date_match.group(1))

        daily_transactions = []
        prev_acc = None
        new_acc = None

        for row in rows:
            if len(row) < 3:
                continue
            text = " ".join(row).lower()

            if "seneste meddelelse" in text:
                prev_acc = {
                    "shares": int(_parse_number(row[1])) if len(row) > 1 else 0,
                    "amount": int(_parse_number(row[3])) if len(row) > 3 else 0,
                }
                continue

            if "ovenstående" in text:
                new_acc = {
                    "shares": int(_parse_number(row[1])) if len(row) > 1 else 0,
                    "avg_price": _parse_number(row[2]) if len(row) > 2 else 0,
                    "amount": int(_parse_number(row[3])) if len(row) > 3 else 0,
                }
                continue

            date_str = _parse_date_danish(row[0])
            if date_str and len(row) >= 4:
                shares = int(_parse_number(row[1]))
                price = _parse_number(row[2])
                amount = int(_parse_number(row[3]))
                if shares > 0:
                    daily_transactions.append({
                        "date": date_str,
                        "shares": shares,
                        "price": price,
                        "amount": amount,
                    })

        if not new_acc or new_acc["shares"] == 0:
            return None

        week_shares = sum(t["shares"] for t in daily_transactions)
        week_amount = sum(t["amount"] for t in daily_transactions)

        # Sanity check — company sometimes reports stale acc numbers
        if prev_acc and new_acc["shares"] == prev_acc["shares"] and week_shares > 0:
            new_acc["shares"] = prev_acc["shares"] + week_shares
            new_acc["amount"] = prev_acc["amount"] + week_amount

        week_avg = week_amount / week_shares if week_shares > 0 else 0

        if daily_transactions:
            dates_sorted = sorted(t["date"] for t in daily_transactions)
            period_start = dates_sorted[0]
            period_end = dates_sorted[-1]
        else:
            period_start = announcement_date or ""
            period_end = announcement_date or ""

        # Fallback for announcement date: use period_end
        if not announcement_date:
            announcement_date = period_end

        # UID — stable across re-runs
        uid = f"{self.uid_prefix}-fed-page{page_idx}"

        return Announcement(
            uid=uid,
            announcement_date=announcement_date,
            source=self.name,
            source_url=url,
            period_start=period_start,
            period_end=period_end,
            week_shares=week_shares,
            week_amount=week_amount,
            week_avg_price=round(week_avg, 2),
            acc_shares=new_acc["shares"],
            acc_amount=new_acc["amount"],
            daily_transactions=daily_transactions,
        )

    # --------------------------------------------------------
    def fetch_recent(self, max_announcements: int = 20) -> list[Announcement]:
        """
        Scan fastejendom.dk starting from `starting_page_slug`, looking for
        new announcements. Stops after `max_consecutive_404s` in a row.
        """
        print(f"\n[fastejendom] Scanning from slug {self.starting_page_slug}...")

        results: list[Announcement] = []
        idx = self.starting_page_slug
        consecutive_fails = 0

        while consecutive_fails < self.max_consecutive_404s and len(results) < max_announcements:
            url = self.URL_PATTERN.format(idx=idx)
            html = self._fetch(url)

            if not html or "aktietilbagekøbsprogram" not in html.lower():
                consecutive_fails += 1
                print(f"  [fastejendom] slug {idx}: not a buyback page")
                idx += 1
                continue

            consecutive_fails = 0
            ann = self._extract_announcement(html, page_idx=idx, url=url)
            if ann:
                print(
                    f"  [fastejendom] ✓ slug {idx} → {ann.announcement_date}: "
                    f"week {ann.week_shares}sh / acc {ann.acc_shares}sh"
                )
                results.append(ann)
            else:
                print(f"  [fastejendom] slug {idx}: could not parse")
            idx += 1

        # Newest first
        results.sort(key=lambda a: a.announcement_date, reverse=True)
        return results
