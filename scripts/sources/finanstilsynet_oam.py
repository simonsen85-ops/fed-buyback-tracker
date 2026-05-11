"""
Finanstilsynet OAM scraper for Egne aktier-meddelelser (buyback announcements).

Replaces scripts/sources/globenewswire.py as the primary regulatory source per
the project source hierarchy:
  (1) Exchange/regulatory APIs  <-- THIS MODULE
  (2) Company IR site (fastejendom.dk)
  (3) Commercial distributors (Cision, GlobeNewswire) -- last resort

The Danish FSA (Finanstilsynet) hosts its public OAM database on the GoPublic
platform at https://appft.gold.extension.gopublic.dk. API discovered via HAR
export from the public portal. Document attachments are served from
Azure blob storage (saegressprod.blob.core.windows.net) without auth.

Test mode:
    python -m scripts.sources.finanstilsynet_oam
    # or from inside scripts/sources/:
    python finanstilsynet_oam.py
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Iterator, Optional

import requests
from bs4 import BeautifulSoup

# Source-system integration (the base module sits next to this file)
try:
    from .base import Announcement, AnnouncementSource
except ImportError:
    # Allow running as a standalone script: python finanstilsynet_oam.py
    from base import Announcement, AnnouncementSource  # type: ignore


# ============================================================
# Constants
# ============================================================

# Finanstilsynet's tenant UUID in the GoPublic OAM platform
OAM_TENANT = "9217fa13-5d9a-46c6-9921-69ee7e6cfaf6"
OAM_BASE = f"https://appft.gold.extension.gopublic.dk/api/{OAM_TENANT}"
SEARCH_URL = f"{OAM_BASE}/search"
DETAILS_URL_TPL = f"{OAM_BASE}/details/{{}}"

# FED-specific filtering parameters
FED_ISSUER_QUERY = "Fast Ejendom Danmark"
FED_CVR = "28500971"
FED_LEI = "529900OD0S4ABJLE8K13"

# Politeness
REQUEST_DELAY = 0.4   # seconds between API calls
TIMEOUT = 30

DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "Origin": "https://appft.gold.extension.gopublic.dk",
    "Referer": "https://appft.gold.extension.gopublic.dk/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    ),
}

LOG_PREFIX = "[finanstilsynet]"


# ============================================================
# Data classes
# ============================================================

@dataclass
class OAMAnnouncement:
    """Metadata for a single OAM announcement (search-result level)."""
    id: str
    headline: str
    issuer: str
    publication_date: datetime
    raw: dict = field(default_factory=dict)

    def is_konklusion(self) -> bool:
        return "konklusion" in self.headline.lower()


@dataclass
class OAMDocument:
    """Document attachment metadata from the details endpoint."""
    announcement_id: str
    cvr: Optional[str]
    lei: Optional[str]
    html_url: Optional[str]
    pdf_url: Optional[str]


@dataclass
class DailyTransaction:
    date: date
    shares: int
    avg_price: float
    amount: float
    announcement_id: str
    announcement_date: datetime


@dataclass
class ParsedAnnouncement:
    """Result of parsing one buyback announcement HTML.

    Contains daily transactions plus the 'Akkumuleret' rows for cross-validation.
    """
    daily_transactions: list[tuple[date, int, float, float]]  # (date, shares, avg, amount)
    prev_accum_shares: Optional[int] = None
    prev_accum_amount: Optional[float] = None
    new_accum_shares: Optional[int] = None
    new_accum_amount: Optional[float] = None

    def weekly_shares(self) -> int:
        return sum(t[1] for t in self.daily_transactions)

    def weekly_amount(self) -> float:
        return sum(t[3] for t in self.daily_transactions)

    def weekly_avg_price(self) -> float:
        s = self.weekly_shares()
        return self.weekly_amount() / s if s else 0.0

    def week_start(self) -> Optional[date]:
        return self.daily_transactions[0][0] if self.daily_transactions else None

    def accumulator_check(self) -> tuple[bool, str]:
        """Verify daily sum matches accumulator delta. Returns (ok, message)."""
        if self.prev_accum_shares is None or self.new_accum_shares is None:
            return True, "no accumulator rows"
        expected_sh = self.new_accum_shares - self.prev_accum_shares
        actual_sh = self.weekly_shares()
        if expected_sh != actual_sh:
            return False, f"shares: daily={actual_sh} vs accumulator-delta={expected_sh}"
        if self.prev_accum_amount is not None and self.new_accum_amount is not None:
            expected_amt = self.new_accum_amount - self.prev_accum_amount
            actual_amt = self.weekly_amount()
            # Allow 1 DKK rounding tolerance
            if abs(expected_amt - actual_amt) > 1.0:
                return False, f"amount: daily={actual_amt} vs accumulator-delta={expected_amt}"
        return True, "OK"


# ============================================================
# Helpers
# ============================================================

def _parse_pub_date(s: str) -> datetime:
    """Parse 'DD-MM-YYYY HH:MM:SS' as a naive datetime (Europe/Copenhagen)."""
    return datetime.strptime(s.strip(), "%d-%m-%Y %H:%M:%S")


# Danish month names (lower-case, as appears in OAM HTML buyback tables)
DK_MONTHS = {
    "januar": 1, "februar": 2, "marts": 3, "april": 4,
    "maj": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}


def _parse_dk_date(s: str) -> Optional[date]:
    """Parse Danish dates. Handles 'DD-MM-YYYY', 'DD.MM.YYYY', 'YYYY-MM-DD',
    and Danish text form like '1. maj 2026'."""
    s = s.strip()
    if not s:
        return None
    # Numeric formats
    for fmt in ("%d-%m-%Y", "%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Text form: "1. maj 2026", "12 oktober 2025"
    m = re.match(r"^(\d{1,2})\.?\s+([a-zæøå]+)\s+(\d{4})$", s, re.IGNORECASE)
    if m:
        day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        if month_name in DK_MONTHS:
            try:
                return date(year, DK_MONTHS[month_name], day)
            except ValueError:
                pass
    return None


def _parse_dk_number(s: str) -> Optional[float]:
    """Danish number format: 1.234,56 (dot=thousands, comma=decimal)."""
    if not s:
        return None
    s = s.strip().replace("\xa0", "").replace(" ", "")
    if not s or s in ("-", "–", "—"):
        return None
    # Remove thousand-dots, then comma -> dot
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None





# ============================================================
# API client
# ============================================================

def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    return s


def search_announcements(
    issuer_query: str = FED_ISSUER_QUERY,
    category: str = "OwnShares",
    page_size: int = 25,
    max_pages: Optional[int] = None,
    session: Optional[requests.Session] = None,
) -> Iterator[OAMAnnouncement]:
    """Yield all announcements matching issuer_query and category, paginated."""
    sess = session or _make_session()
    page = 1
    while True:
        body = {
            "query": issuer_query,
            "filters": [
                {"type": "dropdown", "key": "CategoryFilter", "options": [category]}
            ],
            "page": page,
            "pageSize": page_size,
        }
        resp = sess.post(SEARCH_URL, json=body, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        for row in data.get("data", {}).get("rows", []):
            try:
                yield OAMAnnouncement(
                    id=row["id"],
                    headline=row["HeadlineColumn"],
                    issuer=row["IssuerColumn"],
                    publication_date=_parse_pub_date(row["PublicationDateColumn"]),
                    raw=row,
                )
            except (KeyError, ValueError) as exc:
                print(f"{LOG_PREFIX} skipping malformed row: {exc} | {row!r}")

        total_pages = data.get("paging", {}).get("totalPages", 1)
        if page >= total_pages or (max_pages and page >= max_pages):
            break
        page += 1
        time.sleep(REQUEST_DELAY)


def get_document_info(
    announcement_id: str,
    session: Optional[requests.Session] = None,
) -> OAMDocument:
    """Fetch details endpoint and extract document URLs + CVR/LEI for validation."""
    sess = session or _make_session()
    resp = sess.get(DETAILS_URL_TPL.format(announcement_id), timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    cvr = lei = html_url = pdf_url = None
    for section in data.get("sections", []):
        for el in section.get("elements", []):
            key = el.get("key", {}).get("name", "")
            val = el.get("value", {})
            if key == "CVR-nr.":
                cvr = val.get("value")
            elif key == "LEI-kode":
                lei = val.get("value") or lei
            if val.get("type") == "link":
                url = val.get("url", "")
                if url.endswith(".html") and html_url is None:
                    html_url = url
                elif url.endswith(".pdf") and pdf_url is None:
                    pdf_url = url

    return OAMDocument(
        announcement_id=announcement_id,
        cvr=cvr,
        lei=lei,
        html_url=html_url,
        pdf_url=pdf_url,
    )


def fetch_document_html(html_url: str, session: Optional[requests.Session] = None) -> str:
    """Download announcement HTML from Azure blob storage."""
    sess = session or requests.Session()  # blob doesn't need our auth headers
    resp = sess.get(html_url, timeout=TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


# ============================================================
# HTML parsing (conservative - prints diagnostics)
# ============================================================
# Danish weekly buyback announcements typically contain a transaction table:
#   Dato | Antal købte aktier | Gennemsnitlig købskurs (kr.) | Samlet beløb i kr.
# Plus an accumulated table. We parse the daily granular table.
#
# If parsing produces zero transactions for a known-buyback announcement, run
# in --debug mode to dump all tables found and adjust keyword matching.

TABLE_HEADER_KEYWORDS = (
    ("antal", "kurs"),         # 'antal købte aktier' + 'gennemsnitlig kurs/købskurs'
    ("aktier", "gennemsnit"),  # fallback variant
)

def _table_is_transactions(table) -> bool:
    """Heuristic: header row mentions both share count and avg price."""
    text = " ".join(c.get_text(" ", strip=True).lower()
                    for c in table.find_all(["th", "td"])[:12])
    return any(all(kw in text for kw in pair) for pair in TABLE_HEADER_KEYWORDS)


def parse_buyback_html(html: str, debug: bool = False) -> ParsedAnnouncement:
    """Parse a buyback announcement HTML into a ParsedAnnouncement.

    Recognises:
      - the daily transaction table by 'antal' + 'kurs' in the header
      - 'Akkumuleret under programmet jf. seneste meddelelse'    -> prev accumulator
      - 'Akkumuleret under programmet jf. ovenstående transaktioner' -> new accumulator
      - daily rows where col 0 parses as a Danish date
    Ignores the trade-by-trade 'Bilag' table (header Stk/Kode/Pris/Tidspunkt/Børs).
    """
    soup = BeautifulSoup(html, "html.parser")
    parsed = ParsedAnnouncement(daily_transactions=[])
    tables = soup.find_all("table")
    if debug:
        print(f"{LOG_PREFIX}   [debug] found {len(tables)} <table> elements")

    for ti, table in enumerate(tables):
        is_tx = _table_is_transactions(table)
        if debug:
            header_preview = " | ".join(
                c.get_text(" ", strip=True)
                for c in table.find_all(["th", "td"])[:6]
            )[:200]
            print(f"{LOG_PREFIX}   [debug] table#{ti} tx={is_tx} header={header_preview!r}")
        if not is_tx:
            continue

        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) < 4:
                continue
            col0_lc = cells[0].lower()

            # Capture accumulator rows
            if "akkumuleret" in col0_lc:
                sh = _parse_dk_number(cells[1])
                amt = _parse_dk_number(cells[3])
                if "seneste" in col0_lc:
                    parsed.prev_accum_shares = int(sh) if sh is not None else None
                    parsed.prev_accum_amount = amt
                elif "ovenstående" in col0_lc or "ovenstaende" in col0_lc:
                    parsed.new_accum_shares = int(sh) if sh is not None else None
                    parsed.new_accum_amount = amt
                continue

            # Daily row
            d = _parse_dk_date(cells[0])
            if d is None:
                continue
            shares = _parse_dk_number(cells[1])
            avg = _parse_dk_number(cells[2])
            amt = _parse_dk_number(cells[3])
            if None in (shares, avg, amt):
                continue
            parsed.daily_transactions.append((d, int(shares), float(avg), float(amt)))

    return parsed


# ============================================================
# High-level orchestration
# ============================================================

def fetch_fed_transactions(
    max_pages: int = 10,
    validate_cvr: bool = True,
    debug: bool = False,
) -> list[DailyTransaction]:
    """Full pipeline: discover announcements -> fetch HTML -> parse transactions."""
    session = _make_session()

    print(f"{LOG_PREFIX} Scanning OAM for {FED_ISSUER_QUERY} (filter: Egne aktier)...")
    announcements = list(search_announcements(
        FED_ISSUER_QUERY, category="OwnShares",
        max_pages=max_pages, session=session,
    ))
    print(f"{LOG_PREFIX} Found {len(announcements)} announcements")

    results: list[DailyTransaction] = []
    skipped_cvr = 0
    for ann in announcements:
        if ann.is_konklusion():
            print(f"{LOG_PREFIX}   {ann.id} {ann.publication_date.date()} "
                  f"[konklusion, no daily transactions]")
            continue

        time.sleep(REQUEST_DELAY)
        try:
            doc = get_document_info(ann.id, session=session)
        except Exception as exc:
            print(f"{LOG_PREFIX}   {ann.id}: details fetch failed ({exc})")
            continue

        if validate_cvr and doc.cvr and doc.cvr != FED_CVR:
            skipped_cvr += 1
            print(f"{LOG_PREFIX}   {ann.id}: CVR {doc.cvr} != FED ({FED_CVR}), skipping")
            continue

        if not doc.html_url:
            print(f"{LOG_PREFIX}   {ann.id}: no HTML attachment "
                  f"(pdf_url={'yes' if doc.pdf_url else 'no'})")
            continue

        try:
            html = fetch_document_html(doc.html_url, session=session)
            parsed = parse_buyback_html(html, debug=debug)
        except Exception as exc:
            print(f"{LOG_PREFIX}   {ann.id}: parse failed ({exc})")
            continue

        ok, msg = parsed.accumulator_check()
        check_tag = "" if ok else f" [VALIDATION FAIL: {msg}]"
        print(f"{LOG_PREFIX}   {ann.id} {ann.publication_date.date()}: "
              f"{len(parsed.daily_transactions)} daily transactions "
              f"(week sum: {parsed.weekly_shares()} sh @ "
              f"{parsed.weekly_avg_price():.2f} = {parsed.weekly_amount():,.0f} DKK)"
              f"{check_tag}")
        for d, sh, ap, am in parsed.daily_transactions:
            results.append(DailyTransaction(
                date=d, shares=sh, avg_price=ap, amount=am,
                announcement_id=ann.id,
                announcement_date=ann.publication_date,
            ))

    if skipped_cvr:
        print(f"{LOG_PREFIX} skipped {skipped_cvr} announcements with wrong CVR")
    print(f"{LOG_PREFIX} parsed {len(results)} total daily transactions")
    return results


# ============================================================
# Drop-in AnnouncementSource for scraper.py
# ============================================================
# Replaces GlobeNewswireSource. Returns base.Announcement objects with the
# same field shape so merge_announcements / _dedup_by_period work unchanged.
#
# Wiring in scraper.py:
#     from sources.finanstilsynet_oam import FinanstilsynetSource
#     ...
#     sources = [
#         FinanstilsynetSource(
#             company=COMPANY_NAME,
#             uid_prefix=UID_PREFIX,
#             cvr=FED_CVR,
#             programs=PROGRAMS,
#             max_pages=2,
#         ),
#         FastEjendomSource(...),
#     ]
# Plus update _dedup_by_period() priority: put 'finanstilsynet' at 0.


class FinanstilsynetSource(AnnouncementSource):
    """Fetches buyback announcements from the Danish FSA OAM portal.

    Filters to announcements whose period_start falls within one of the
    configured programs — this prevents pulling in pre-program historical
    data (the OAM holds many years of older announcements).
    """
    name = "finanstilsynet"

    def __init__(
        self,
        company: str,
        uid_prefix: str,
        cvr: Optional[str] = None,
        programs: Optional[list[dict]] = None,
        max_pages: int = 2,
        validate_cvr: bool = True,
    ):
        self.company = company
        self.uid_prefix = uid_prefix
        self.cvr = cvr or FED_CVR
        self.programs = programs or []
        self.max_pages = max_pages
        self.validate_cvr = validate_cvr

    def _program_for_date(self, d: date) -> Optional[dict]:
        """Return the program whose effective range covers d, else None.

        Effective end = closed_on if set, else end. This handles the case
        where program 1's nominal range overlaps program 2 (e.g. program 1
        ran 2025-10-24..2026-10-23 nominally but closed 2026-04-17, then
        program 2 started 2026-04-20).
        """
        iso = d.isoformat()
        for prog in self.programs:
            start = prog.get("start", "")
            eff_end = prog.get("closed_on") or prog.get("end", "9999-12-31")
            if start <= iso <= eff_end:
                return prog
        return None

    def fetch_recent(self, max_announcements: int = 20) -> list[Announcement]:
        try:
            return self._fetch(max_announcements)
        except Exception as exc:
            # Per base.py contract: never raise — return empty on failure.
            print(f"  [{self.name}] fetch failed: {exc}")
            return []

    def _fetch(self, max_announcements: int) -> list[Announcement]:
        session = _make_session()
        print(f"  [{self.name}] Scanning OAM for {self.company} (Egne aktier)...")

        # Pages × 25 / page; cap at what we need
        pages_needed = max(1, (max_announcements + 24) // 25)
        pages_needed = min(pages_needed, self.max_pages)

        oam_anns = list(search_announcements(
            self.company, category="OwnShares",
            max_pages=pages_needed, session=session,
        ))
        print(f"  [{self.name}] Found {len(oam_anns)} OAM entries (first {pages_needed} pages)")

        results: list[Announcement] = []
        skipped_pre_program = 0
        skipped_cvr = 0

        for oam_ann in oam_anns:
            if len(results) >= max_announcements:
                break
            if oam_ann.is_konklusion():
                # Konklusion meddelelse marks program completion — no new
                # transactions, so skip. The previous weekly announcement
                # already carries the final cumulative.
                continue

            time.sleep(REQUEST_DELAY)
            try:
                doc = get_document_info(oam_ann.id, session=session)
            except Exception as exc:
                print(f"  [{self.name}]   {oam_ann.id}: details fetch failed ({exc})")
                continue

            if self.validate_cvr and doc.cvr and doc.cvr != self.cvr:
                skipped_cvr += 1
                continue
            if not doc.html_url:
                # Older entries (~pre-2025) sometimes only have a PDF.
                # Currently no PDF fallback — skip with a notice.
                print(f"  [{self.name}]   {oam_ann.id}: no HTML attachment (PDF only)")
                continue

            try:
                html = fetch_document_html(doc.html_url, session=session)
                parsed = parse_buyback_html(html)
            except Exception as exc:
                print(f"  [{self.name}]   {oam_ann.id}: parse failed ({exc})")
                continue

            if not parsed.daily_transactions:
                continue

            period_start = min(t[0] for t in parsed.daily_transactions)
            period_end = max(t[0] for t in parsed.daily_transactions)

            # Filter: only keep announcements within a configured program
            prog = self._program_for_date(period_start)
            if self.programs and prog is None:
                skipped_pre_program += 1
                continue

            # Cross-validate parsed daily totals against accumulator rows
            ok, msg = parsed.accumulator_check()
            if not ok:
                print(f"  [{self.name}]   {oam_ann.id} validation FAIL: {msg}")
                # Continue anyway — log and let the user investigate

            week_shares = parsed.weekly_shares()
            week_amount_int = int(round(parsed.weekly_amount()))
            week_avg = parsed.weekly_avg_price()

            acc_shares = (parsed.new_accum_shares
                          if parsed.new_accum_shares is not None
                          else week_shares)
            acc_amount = (int(round(parsed.new_accum_amount))
                          if parsed.new_accum_amount is not None
                          else week_amount_int)

            results.append(Announcement(
                uid=f"{self.uid_prefix}-oam-{oam_ann.id}",
                announcement_date=oam_ann.publication_date.date().isoformat(),
                source=self.name,
                source_url=doc.html_url,
                period_start=period_start.isoformat(),
                period_end=period_end.isoformat(),
                week_shares=week_shares,
                week_amount=week_amount_int,
                week_avg_price=round(week_avg, 4),
                acc_shares=acc_shares,
                acc_amount=acc_amount,
                program_id=prog.get("id") if prog else None,
                daily_transactions=[
                    {"date": d.isoformat(), "shares": sh,
                     "avg_price": ap, "amount": int(round(am))}
                    for d, sh, ap, am in parsed.daily_transactions
                ],
            ))

        if skipped_cvr:
            print(f"  [{self.name}] skipped {skipped_cvr} entries with non-matching CVR")
        if skipped_pre_program:
            print(f"  [{self.name}] skipped {skipped_pre_program} entries outside configured programs")
        print(f"  [{self.name}] returning {len(results)} Announcement(s)")
        return results


# ============================================================
# Standalone test mode
# ============================================================

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Test the Finanstilsynet OAM scraper")
    p.add_argument("--max-pages", type=int, default=1,
                   help="Pages to fetch (25/page). Default 1 = newest 25.")
    p.add_argument("--debug", action="store_true",
                   help="Print all tables found in each HTML for parser debugging")
    p.add_argument("--save-sample", metavar="ID",
                   help="Save the HTML of one announcement ID to /tmp for inspection")
    args = p.parse_args()

    if args.save_sample:
        session = _make_session()
        doc = get_document_info(args.save_sample, session=session)
        print(f"CVR: {doc.cvr}  LEI: {doc.lei}")
        print(f"HTML URL: {doc.html_url}")
        print(f"PDF URL:  {doc.pdf_url}")
        if doc.html_url:
            html = fetch_document_html(doc.html_url, session=session)
            path = f"/tmp/oam_{args.save_sample}.html"
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"Saved {len(html)} bytes to {path}")
    else:
        txns = fetch_fed_transactions(max_pages=args.max_pages, debug=args.debug)
        print()
        print(f"=== DAILY SAMPLE (first 8 of {len(txns)}) ===")
        for t in txns[:8]:
            print(f"  {t.date}  shares={t.shares:>5}  "
                  f"avg={t.avg_price:>8.2f}  amount={t.amount:>12,.0f}  "
                  f"(ann {t.announcement_id})")
        print()
        # Show weekly aggregation
        from collections import defaultdict
        by_ann = defaultdict(list)
        for t in txns:
            by_ann[t.announcement_id].append(t)
        print(f"=== WEEKLY SUMMARY ({len(by_ann)} weeks) ===")
        weeks = []
        for ann_id, daily in by_ann.items():
            ts = sum(d.shares for d in daily)
            ta = sum(d.amount for d in daily)
            weeks.append((min(d.date for d in daily), ts, ta/ts if ts else 0, ta, ann_id))
        weeks.sort()
        for ws, sh, ap, am, aid in weeks:
            print(f"  {ws}  shares={sh:>6}  avg={ap:>8.2f}  amount={am:>12,.0f}  (ann {aid})")
