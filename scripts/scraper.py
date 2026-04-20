#!/usr/bin/env python3
"""
Fast Ejendom Danmark — Buyback Scraper (orchestrator).

This is a thin coordinator. All the real work lives in sources/:

  sources.globenewswire.GlobeNewswireSource — primary announcement source
  sources.fastejendom.FastEjendomSource     — fallback for FED
  sources.volume.compute                    — Safe Harbour calculations
  sources.volume.nasdaq / yahoo             — volume data providers

Flow:
  1. Load data.json
  2. Fetch recent announcements from GlobeNewswire (+ fastejendom.dk as fallback)
  3. Dedup & merge into data.json
  4. Fetch daily volume data (Nasdaq primary, Yahoo fallback)
  5. Compute Safe Harbour metrics (25% rule, tempo, etc.)
  6. Fetch current price (Yahoo)
  7. Save data.json
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from sources.base import merge_announcements
from sources.globenewswire import GlobeNewswireSource
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
YAHOO_TICKER = "FED.CO"
NASDAQ_INSTRUMENT_ID = "TX1484734"
NASDAQ_REFERER = (
    "https://www.nasdaq.com/european-market-activity/shares/fed?id=TX1484734"
)

# Share count (used by the dashboard for NAV-accretion calculations)
TOTAL_SHARES = 2659442

# NAV history — UPDATE when new quarterly reports are published
NAV_HISTORY = [
    {"from": "2025-10-24", "nav": 281.26, "label": "Q3 2025"},
    {"from": "2026-02-17", "nav": 306.60, "label": "FY 2025"},
]

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


def _dedup_by_period(data: dict) -> int:
    """
    Additional dedup: if we have two announcements covering the exact same
    period (e.g. one from legacy fastejendom + one from new GlobeNewswire),
    prefer the GlobeNewswire one (it's authoritative).

    Returns number of duplicates removed.
    """
    announcements = data.get("announcements", [])
    by_period: dict[tuple, list[int]] = {}
    for i, a in enumerate(announcements):
        key = (a.get("period_start"), a.get("period_end"), a.get("acc_shares"))
        by_period.setdefault(key, []).append(i)

    to_remove = set()
    for key, indices in by_period.items():
        if len(indices) <= 1 or key == (None, None, None):
            continue
        priority = {"globenewswire": 0, "fastejendom": 1, "legacy": 2}
        indices_sorted = sorted(
            indices,
            key=lambda i: priority.get(announcements[i].get("source", "legacy"), 99),
        )
        # Keep the first (highest priority), remove the rest
        for i in indices_sorted[1:]:
            to_remove.add(i)

    if to_remove:
        data["announcements"] = [
            a for i, a in enumerate(announcements) if i not in to_remove
        ]
        print(f"Removed {len(to_remove)} duplicate announcement(s)")
    return len(to_remove)


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
        GlobeNewswireSource(
            company=COMPANY_NAME,
            uid_prefix=UID_PREFIX,
            listing_max_pages=3,
        ),
        FastEjendomSource(
            starting_page_slug=next_slug,
            max_consecutive_404s=3,
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

    _dedup_by_period(data)

    data["announcements"].sort(key=lambda a: a.get("announcement_date", ""))

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
    data["nav_history"] = NAV_HISTORY
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
