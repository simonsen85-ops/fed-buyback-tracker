"""
Announcement sources for buyback trackers.

Each source is a class that fetches regulatory announcements from a specific
venue (GlobeNewswire, company website, Investegate, etc.) and returns them
in a standardized Announcement format.

Usage:
    from sources.globenewswire import GlobeNewswireSource
    from sources.fastejendom import FastEjendomSource

    sources = [
        GlobeNewswireSource(company="Fast Ejendom Danmark A/S"),
        FastEjendomSource(),
    ]

    for src in sources:
        new_announcements = src.fetch_since(last_known_uids=set(known))
        ...
"""
