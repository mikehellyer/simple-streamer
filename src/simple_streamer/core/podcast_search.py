"""Search Apple's iTunes Search API for new podcasts to fill a preset with.

Same idea as core/station_search.py for radio, but sourced from the
iTunes Search API — a general keyword search that returns enough
(RSS feed, artwork) about each match to populate a whole preset slot
from one pick, rather than core/image_search.py's narrower use of the
same API (which only wants artwork for a podcast whose name is already
known).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

from simple_streamer.core.http import SSL_CONTEXT

REQUEST_TIMEOUT_SECONDS = 6
MAX_RESULTS = 20


@dataclass(frozen=True)
class PodcastResult:
    name: str
    feed_url: str
    website: str
    artwork_url: str
    description: str


def search_podcasts(query: str) -> list[PodcastResult]:
    query = query.strip()
    if not query:
        return []

    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
        {"term": query, "media": "podcast", "limit": MAX_RESULTS}
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Simple-Streamer/1"})
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS, context=SSL_CONTEXT
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []

    results = []
    for item in payload.get("results", []):
        name = (item.get("collectionName") or item.get("trackName") or "").strip()
        feed_url = (item.get("feedUrl") or "").strip()
        if not name or not feed_url:
            continue
        # iTunes doesn't give a podcast's own homepage, only its Apple
        # Podcasts page — still a real, useful link, just not the same
        # thing as the curated defaults' own-domain websites.
        website = (item.get("collectionViewUrl") or item.get("trackViewUrl") or "").strip()
        artwork_url = item.get("artworkUrl600") or item.get("artworkUrl100") or ""
        results.append(
            PodcastResult(
                name=name,
                feed_url=feed_url,
                website=website,
                artwork_url=artwork_url,
                description=_describe(item),
            )
        )
    return results


def _describe(item: dict) -> str:
    parts = []
    artist = (item.get("artistName") or "").strip()
    if artist:
        parts.append(artist)

    genre = (item.get("primaryGenreName") or "").strip()
    if genre:
        parts.append(genre)

    count = item.get("trackCount")
    if isinstance(count, int) and count > 0:
        parts.append(f"{count} episode{'s' if count != 1 else ''}")

    return " · ".join(parts)
