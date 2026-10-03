#!/usr/bin/env python3
"""
Fast Ejendom Danmark — Buyback Scraper (orchestrator).

This is a thin coordinator. All the real work lives in sources/:

  sources.finanstilsynet_oam.FinanstilsynetSource — primary regulatory source
  sources.fastejendom.FastEjendomSource           — fallback for FED
  sources.volume.compute                          — Safe Harbour calculations
  sources.volume.nasdaq / yahoo                   — volume data providers

Flow:
  1. Load data.json
  2. Fetch recent announcements from Finanstilsynet OAM (+ fastejendom.dk fallback)
  3. Dedup & merge into data.json
  4. Fetch daily volume data (Nasdaq primary, Yahoo fallback)
  5. Compute Safe Harbour metrics (25% rule, tempo, etc.)
  6. Fetch current price (Yahoo)
  7. Save data.json
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sources.base import merge_announcements
from sources.finanstilsynet_oam import FinanstilsynetSource
from sources.fastejendom import FastEjendomSource
from sources.volume.compute import (
    build_daily_volume_dict,
    compute_safe_harbour_metrics,
)
from sources.volume.yahoo import fetch_yahoo_current_price


# ============================================================
# CONFIG — change these when adapting to another stock
# ============================================================
DATA_FILE = Path(__file__).parent.parent / "data.json"

# Company identity
COMPANY_NAME = "Fast Ejendom Danmark A/S"
UID_PREFIX = "fed"
CVR = "28500971"
YAHOO_TICKER = "FED.CO"
NASDAQ_INSTRUMENT_ID = "TX1484734"
NASDAQ_REFERER = (
    "https://www.nasdaq.com/european-market-activity/shares/fed?id=TX1484734"
)

# Share count (used by the dashboard for NAV-accretion calculations)
TOTAL_SHARES = 2659442

# NAV history — manual anchors ("from" = report publication date).
# New quarters are also auto-detected from fastejendom.dk (see
# _auto_detect_nav); adding them here is optional but makes them permanent.
NAV_HISTORY = [
    {"from": "2025-10-24", "nav": 281.26, "label": "Q3 2025"},
    {"from": "2026-02-17", "nav": 306.60, "label": "FY 2025"},
    {"from": "2026-04-22", "nav": 311.99, "label": "Q1 2026"},
    {"from": "2026-08-24", "nav": 315.42, "label": "H1 2026"},
]
NAV_SOURCE_URL = "https://fastejendom.dk/investor/aktionaer/"

# Buyback programs — UPDATE when new programs are announced
PROGRAMS = [
    {
        "id": 1,
        "start": "2025-10-24",
        "end": "2026-10-23",
        "max_amount": 10000000,
        "announced": "2025-10-23",
        "closed_on": "2026-04-17",
    },
    {
        "id": 2,
        "start": "2026-04-20",
        "end": "2027-04-19",
        "max_amount": 10000000,
        "announced": "2026-04-17",
        "closed_on": "2026-10-01",   # 10.0 mio. reached — meddelelse nr. 49/2026
    },
    {
        "id": 3,
        "start": "2026-10-05",
        "end": "2027-10-04",
        "max_amount": 10000000,
        "announced": "2026-10-02",   # meddelelse nr. 50/2026
        "closed_on": None,
    },
]


# ============================================================
# Legacy migration
# ============================================================
def _ensure_uids(data: dict) -> int:
    """
    Ensure every existing announcement has a 'uid' field.

    Older data.json entries were created before the modular refactor and
    don't have uids. We synthesize one from their page_index so they dedup
    correctly against new fastejendom.dk fetches.

    Returns number of announcements migrated.
    """
    migrated = 0
    for a in data.get("announcements", []):
        if not a.get("uid"):
            page_idx = a.get("page_index")
            if page_idx is not None:
                a["uid"] = f"fed-fed-page{page_idx}"
                a.setdefault("source", "fastejendom")
            else:
                date = a.get("announcement_date", "unknown")
                acc = a.get("acc_shares", 0)
                a["uid"] = f"fed-legacy-{date}-{acc}"
                a.setdefault("source", "legacy")
            migrated += 1
    if migrated:
        print(f"Migrated {migrated} legacy announcements (added uid/source fields)")
    return migrated


def _sanitize_dates(data: dict) -> int:
    """
    An announcement can't be published before the period it reports on.
    Older fastejendom.dk scrapes picked up the program start date from page
    boilerplate (e.g. 2026-04-20 for a 18-24 Sep week), which put rows in the
    wrong order and attached the wrong NAV. Repair: announcement_date >= period_end.

    Returns number of rows repaired.
    """
    fixed = 0
    for a in data.get("announcements", []):
        pe, ad = a.get("period_end"), a.get("announcement_date")
        if pe and (not ad or ad < pe):
            a["announcement_date"] = pe
            fixed += 1
    if fixed:
        print(f"Repaired announcement_date on {fixed} row(s) (was before period_end)")
    return fixed


def _dedup_by_period(data: dict) -> int:
    """
    One row per buyback week. Sources disagree on period_end (e.g. legacy
    02-12 vs OAM 02-13) and fastejendom.dk sometimes mis-parses acc_shares,
    so the key is period_start alone. Highest-priority source wins.

    Duplicates matter: the dashboard sums week_shares across ALL rows, so
    every duplicate inflates total shares/amount bought.

    Returns number of duplicates removed.
    """
    priority = {"finanstilsynet": 0, "globenewswire": 1, "fastejendom": 2, "legacy": 3}
    announcements = data.get("announcements", [])
    by_week: dict[str, list[int]] = {}
    for i, a in enumerate(announcements):
        ps = a.get("period_start")
        if ps:
            by_week.setdefault(ps, []).append(i)

    to_remove = set()
    for ps, indices in by_week.items():
        if len(indices) <= 1:
            continue
        ranked = sorted(
            indices,
            key=lambda i: priority.get(announcements[i].get("source", "legacy"), 99),
        )
        keep = announcements[ranked[0]]
        for i in ranked[1:]:
            drop = announcements[i]
            if drop.get("week_shares") != keep.get("week_shares"):
                print(f"  ! week {ps}: {keep.get('source')}={keep.get('week_shares')} sh vs "
                      f"{drop.get('source')}={drop.get('week_shares')} sh — keeping {keep.get('source')}")
            to_remove.add(i)

    if to_remove:
        data["announcements"] = [
            a for i, a in enumerate(announcements) if i not in to_remove
        ]
        print(f"Removed {len(to_remove)} duplicate announcement(s)")
    return len(to_remove)


_DK_MONTHS = {
    "januar": 1, "februar": 2, "marts": 3, "april": 4, "maj": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
}


def _auto_detect_nav(data: dict) -> None:
    """
    fastejendom.dk shows 'Indre værdi: 315,42 pr. 30. juni 2026' on every page.
    If that value isn't in NAV_HISTORY yet, store it in data['nav_auto'] with
    from = today (the run after the report). Non-fatal: any problem just logs.
    """
    try:
        import requests
        from bs4 import BeautifulSoup

        html = requests.get(
            NAV_SOURCE_URL, timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (fed-buyback-tracker)"},
        ).text
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        m = re.search(
            r"Indre\s+v\S*rdi:\s*([\d.]+,\d{2})\s*pr\.?\s*(\d{1,2})\.\s*([a-zæøå]+)\s+(\d{4})",
            text, re.IGNORECASE,
        )
        if not m:
            print("  [nav] no 'Indre værdi' found on fastejendom.dk — skipping")
            return
        nav = float(m.group(1).replace(".", "").replace(",", "."))
        month = _DK_MONTHS.get(m.group(3).lower())
        year = int(m.group(4))
        if not month:
            print(f"  [nav] unrecognised month {m.group(3)!r} — skipping")
            return

        known = NAV_HISTORY + data.get("nav_auto", [])
        if any(abs(e["nav"] - nav) < 0.005 for e in known):
            print(f"  [nav] {nav:.2f} (pr. {m.group(2)}. {m.group(3)} {year}) already known")
            return
        last = NAV_HISTORY[-1]["nav"]
        if not (0.75 * last <= nav <= 1.25 * last):
            print(f"  [nav] {nav:.2f} fails sanity check vs {last:.2f} — skipping")
            return

        label = f"FY {year}" if month == 12 else f"Q{(month - 1) // 3 + 1} {year}"
        today = datetime.now(timezone.utc).date().isoformat()
        data.setdefault("nav_auto", []).append(
            {"from": today, "nav": nav, "label": f"{label} (auto)"}
        )
        print(f"  [nav] NEW: {nav:.2f} ({label}) from {today} — consider adding to NAV_HISTORY")
    except Exception as exc:
        print(f"  [nav] auto-detect failed: {exc}")


def _merged_nav_history(data: dict) -> list[dict]:
    """Manual NAV_HISTORY + auto-detected values not (yet) in the manual list."""
    manual_navs = [e["nav"] for e in NAV_HISTORY]
    auto = [
        e for e in data.get("nav_auto", [])
        if not any(abs(e["nav"] - n) < 0.005 for n in manual_navs)
    ]
    data["nav_auto"] = auto
    return sorted(NAV_HISTORY + auto, key=lambda e: e["from"])


# ============================================================
# Data load/save
# ============================================================
def load_data() -> dict:
    """Load data.json, or return a fresh empty structure."""
    if DATA_FILE.exists():
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {
        "total_shares": TOTAL_SHARES,
        "nav_history": NAV_HISTORY,
        "programs": PROGRAMS,
        "program_max": sum(p["max_amount"] for p in PROGRAMS),
        "last_page_index": 107,
        "announcements": [],
        "last_updated": None,
    }


def save_data(data: dict) -> None:
    """Persist data.json."""
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(data['announcements'])} announcements to {DATA_FILE}")


# ============================================================
# Announcement fetching
# ============================================================
def fetch_all_announcements(data: dict) -> int:
    """
    Fetch from all configured sources, merge into data['announcements'].
    Returns number of new announcements added.
    """
    next_slug = data.get("last_page_index", 107) + 1

    sources = [
        FinanstilsynetSource(
            company=COMPANY_NAME,
            uid_prefix=UID_PREFIX,
            cvr=CVR,
            programs=PROGRAMS,
            max_pages=2,
        ),
        FastEjendomSource(
            starting_page_slug=next_slug,
            max_consecutive_404s=10,
        ),
    ]

    total_new = 0
    for src in sources:
        try:
            announcements = src.fetch_recent(max_announcements=20)
        except Exception as e:
            print(f"  [{src.name}] failed: {e}")
            continue

        updated_list, added = merge_announcements(
            data["announcements"], announcements
        )
        data["announcements"] = updated_list
        total_new += added
        print(f"  [{src.name}] merged {added} new announcement(s)")

        if src.name == "fastejendom":
            for ann in announcements:
                if ann.uid.startswith("fed-fed-page"):
                    try:
                        slug = int(ann.uid.rsplit("page", 1)[1])
                        data["last_page_index"] = max(
                            data.get("last_page_index", 107), slug
                        )
                    except (ValueError, IndexError):
                        pass

    return total_new


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 60)
    print("Fast Ejendom Danmark — Buyback Scraper (modular)")
    print(f"Run time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    data = load_data()
    print(f"Existing announcements: {len(data['announcements'])}")

    _ensure_uids(data)

    new_count = fetch_all_announcements(data)

    _sanitize_dates(data)
    _dedup_by_period(data)

    # Chronological by the week covered (dashboard accumulates in array order)
    data["announcements"].sort(
        key=lambda a: (a.get("period_start") or "", a.get("announcement_date") or "")
    )

    daily_vol, source_map = build_daily_volume_dict(
        data,
        instrument_id=NASDAQ_INSTRUMENT_ID,
        referer_url=NASDAQ_REFERER,
        yahoo_ticker=YAHOO_TICKER,
    )
    compute_safe_harbour_metrics(data["announcements"], daily_vol, source_map)

    print("\nFetching current price...")
    price = fetch_yahoo_current_price(YAHOO_TICKER)
    if price:
        data["current_price"] = price
        print(f"  Current price: {price} DKK")

    # Refresh config (in case manually edited)
    print("\nChecking NAV...")
    _auto_detect_nav(data)
    data["nav_history"] = _merged_nav_history(data)
    data["total_shares"] = TOTAL_SHARES
    data["programs"] = PROGRAMS
    data["program_max"] = sum(p["max_amount"] for p in PROGRAMS)

    save_data(data)

    print(f"\nDone. {new_count} new announcement(s) added.")
    print(f"Total: {len(data['announcements'])} announcements")

    if data["announcements"]:
        last = data["announcements"][-1]
        print(
            f"Latest: {last.get('announcement_date')} — "
            f"{last.get('acc_shares')} shares, {last.get('acc_amount')} DKK "
            f"(source: {last.get('source', '?')})"
        )


if __name__ == "__main__":
    main()
