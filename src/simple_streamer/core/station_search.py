"""Search radio-browser.info for new radio stations to fill a preset with.

Unlike core/image_search.py's use of the same API (which only wants a
logo for a station whose name is already known), this is a general
keyword search — "old time radio", "jazz", "BBC" — that returns enough
about each match (stream URL, website, logo) to populate an entire
preset slot from one pick.
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
class StationResult:
    name: str
    stream_url: str
    website: str
    favicon_url: str
    description: str


def search_stations(query: str) -> list[StationResult]:
    query = query.strip()
    if not query:
        return []

    url = "https://de1.api.radio-browser.info/json/stations/search?" + urllib.parse.urlencode(
        {
            "name": query,
            "limit": MAX_RESULTS,
            "order": "votes",
            "reverse": "true",
            "hidebroken": "true",
        }
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Simple-Streamer/1 (+https://github.com/mikehellyer/simple-streamer)"
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS, context=SSL_CONTEXT
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []

    results = []
    for item in payload:
        name = (item.get("name") or "").strip()
        stream_url = (item.get("url_resolved") or item.get("url") or "").strip()
        if not name or not stream_url:
            continue
        results.append(
            StationResult(
                name=name,
                stream_url=stream_url,
                website=(item.get("homepage") or "").strip(),
                favicon_url=(item.get("favicon") or "").strip(),
                description=_describe(item),
            )
        )
    return results


def _describe(item: dict) -> str:
    parts = []
    country = (item.get("countrycode") or "").strip()
    if country:
        parts.append(country)

    tags = (item.get("tags") or "").strip()
    if tags:
        top_tags = [t.strip() for t in tags.split(",") if t.strip()][:3]
        if top_tags:
            parts.append(", ".join(top_tags))

    bitrate = item.get("bitrate")
    codec = (item.get("codec") or "").strip()
    if bitrate and codec:
        parts.append(f"{bitrate}kbps {codec}")
    elif codec:
        parts.append(codec)

    return " · ".join(parts)
