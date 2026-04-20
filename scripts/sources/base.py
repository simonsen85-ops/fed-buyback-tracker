"""
Base classes for announcement sources.

All sources must return Announcement objects so the main scraper
can handle them uniformly — regardless of where they came from.
"""

from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class Announcement:
    """
    Standardized format for a single weekly buyback announcement.
    All sources (GlobeNewswire, fastejendom.dk, Investegate, etc.)
    must produce Announcement objects with these fields filled in.

    The `uid` field is used for deduplication — it should be stable
    across sources so the same announcement found in two places is
    only stored once.
    """
    # Core identifiers
    uid: str                           # Unique ID, e.g. "fed-2026-04-17"
    announcement_date: str             # YYYY-MM-DD — when published
    source: str                        # e.g. "globenewswire", "fastejendom"
    source_url: str                    # Link to the original announcement

    # Announcement period (the week the buyback covers)
    period_start: str                  # YYYY-MM-DD
    period_end: str                    # YYYY-MM-DD

    # Weekly transaction totals
    week_shares: int                   # Shares bought in this week
    week_amount: int                   # DKK spent this week (integer kroner)
    week_avg_price: float              # Avg price paid this week

    # Program-level accumulated totals (reset when new program starts)
    acc_shares: int                    # Total shares bought in current program
    acc_amount: int                    # Total DKK spent in current program

    # Optional/metadata
    program_id: Optional[int] = None   # Which program this belongs to (1, 2, ...)
    daily_transactions: list = field(default_factory=list)  # Day-by-day if available

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return asdict(self)


class AnnouncementSource:
    """
    Abstract base class. Subclass for each source (GlobeNewswire, etc.).

    Subclasses must set `name` and implement `fetch_recent()`.
    """
    name: str = "abstract"

    def fetch_recent(self, max_announcements: int = 20) -> list[Announcement]:
        """
        Fetch the N most recent buyback announcements from this source.
        Returns them sorted newest-first. Must not raise on network errors —
        return empty list instead.

        Args:
            max_announcements: Upper bound on how many to return.

        Returns:
            List of Announcement objects, newest first. Empty on failure.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement fetch_recent()"
        )


def merge_announcements(
    existing: list[dict],
    incoming: list[Announcement],
) -> tuple[list[dict], int]:
    """
    Merge incoming Announcement objects with existing announcements in data.json.

    Dedup is by `uid`. If an announcement already exists, it is kept unchanged —
    we do not overwrite (to avoid flip-flopping between sources).

    Returns:
        (updated_list, num_new_added)
    """
    existing_uids = {a.get("uid") for a in existing if a.get("uid")}
    added = 0
    out = list(existing)

    for ann in incoming:
        if ann.uid in existing_uids:
            continue
        out.append(ann.to_dict())
        existing_uids.add(ann.uid)
        added += 1

    # Keep list sorted by announcement_date (oldest first for chart rendering)
    out.sort(key=lambda a: a.get("announcement_date", ""))
    return out, added
