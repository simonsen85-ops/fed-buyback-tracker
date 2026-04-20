"""
Volume-based metric computations.

These functions take a merged daily-volume dict and existing announcement
data, and compute derived metrics:
- market_volume (total volume during the announcement's week)
- buyback_pct_of_volume (how aggressive relative to all trading)
- 25% Safe Harbour ceiling (from EU Regulation 2016/1052)
- utilization_pct (how close the buyback came to the ceiling)

The Safe Harbour rule: "cannot buy more than 25% of the average daily
trading volume over the 20 preceding trading days". The 20-day window is
the rolling average — we compute it for each trading day in the period
using the 20 days immediately preceding it.
"""

from .nasdaq import fetch_nasdaq_daily_history, fetch_nasdaq_intraday_volume
from .yahoo import fetch_yahoo_daily_history


def build_daily_volume_dict(
    data: dict,
    instrument_id: str,
    referer_url: str,
    yahoo_ticker: str,
) -> tuple[dict[str, int], dict[str, str]]:
    """
    Build a merged daily-volume dict from three sources (priority order):
    1. Nasdaq chart/download — ~1 year of accurate history
    2. Nasdaq intraday API — today's volume (accumulates in data.json)
    3. Yahoo Finance — fallback for older gaps

    Args:
        data: The main data.json dict (mutated to persist intraday history)
        instrument_id: Nasdaq instrument ID (e.g. "TX1484734")
        referer_url: Nasdaq page URL for proper Referer header
        yahoo_ticker: Yahoo Finance ticker (e.g. "FED.CO")

    Returns:
        (daily_vol_dict, source_map) where source_map tells which source
        provided each date's data (for tooltip display in the dashboard)
    """
    print("\nFetching trading volumes...")

    # 1. Nasdaq bulk historical
    nasdaq_bulk = fetch_nasdaq_daily_history(instrument_id, referer_url)

    # 2. Nasdaq intraday (today) — persisted in data.json for long-term accuracy
    nasdaq_history = data.get("nasdaq_daily_volumes", {})
    today_data = fetch_nasdaq_intraday_volume(instrument_id, referer_url)
    if today_data and today_data["volume"] > 0:
        nasdaq_history[today_data["date"]] = today_data["volume"]
        print(
            f"  [nasdaq] today ({today_data['date']}): "
            f"{today_data['volume']} aktier in {today_data['trades']} trades"
        )
    else:
        print("  [nasdaq] intraday unavailable (weekend/holiday or API error)")
    data["nasdaq_daily_volumes"] = nasdaq_history

    # 3. Yahoo fallback
    yahoo_vol = fetch_yahoo_daily_history(yahoo_ticker)

    # Merge in priority order: bulk wins > intraday > Yahoo
    daily_vol = dict(yahoo_vol)
    daily_vol.update(nasdaq_history)
    daily_vol.update(nasdaq_bulk)

    # Build source map (so we can show data provenance in the UI)
    source_map = {}
    for d in daily_vol:
        if d in nasdaq_bulk or d in nasdaq_history:
            source_map[d] = "nasdaq"
        else:
            source_map[d] = "yahoo"

    nasdaq_count = sum(1 for s in source_map.values() if s == "nasdaq")
    yahoo_count = len(source_map) - nasdaq_count
    print(
        f"  Merged: {len(daily_vol)} days "
        f"({nasdaq_count} Nasdaq, {yahoo_count} Yahoo)"
    )

    return daily_vol, source_map


def compute_safe_harbour_metrics(
    announcements: list[dict],
    daily_vol: dict[str, int],
    source_map: dict[str, str],
) -> None:
    """
    Compute market_volume, % af vol, 25% Safe Harbour ceiling, and
    utilization_pct for each announcement. Mutates announcements in place.

    Args:
        announcements: List of announcement dicts (must have period_start,
                       period_end, week_shares fields)
        daily_vol: Merged daily volume dict from build_daily_volume_dict()
        source_map: Source attribution dict from build_daily_volume_dict()
    """
    if not daily_vol:
        print("  Warning: No volume data — skipping Safe Harbour calculations")
        return

    # Build sorted list for rolling average lookups
    daily_list = sorted(daily_vol.items())
    date_to_idx = {d: i for i, (d, _) in enumerate(daily_list)}

    for a in announcements:
        start = a.get("period_start", "")
        end = a.get("period_end", "")
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
                    "source": source_map.get(d, "yahoo"),
                })

        a["market_volume"] = week_vol
        a["max_allowed_week"] = max_allowed_sum if valid_days > 0 else 0
        a["daily_volume_detail"] = daily_detail

        if daily_detail:
            a["avg_volume_20d"] = round(
                sum(d["avg_20d"] for d in daily_detail) / len(daily_detail)
            )
        else:
            a["avg_volume_20d"] = 0

        week_shares = a.get("week_shares", 0)

        if week_shares > 0 and week_vol > 0:
            a["buyback_pct_of_volume"] = round(week_shares / week_vol * 100, 1)
        else:
            a["buyback_pct_of_volume"] = 0

        if max_allowed_sum > 0:
            a["utilization_pct"] = round(week_shares / max_allowed_sum * 100, 1)
        else:
            a["utilization_pct"] = 0

    print("  Volume and 25% Safe Harbour limits matched to announcements")
