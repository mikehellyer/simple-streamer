"""Resolve a podcast's RSS feed to its recent episodes.

Presets in the Podcasts deck store a feed URL rather than a fixed audio
file, so playing a slot always looks at whatever the show has actually
published — either just the latest episode, or a short list to pick from
(see gui/episode_list_dialog.py).
"""
from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

from simple_streamer.core.http import SSL_CONTEXT

FEED_TIMEOUT_SECONDS = 8
DEFAULT_RECENT_LIMIT = 6
_ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"


@dataclass
class Episode:
    title: str
    audio_url: str
    published: str = ""  # raw RSS pubDate, best-effort display only
    duration_seconds: Optional[int] = None


def latest_episode(feed_url: str) -> Optional[Episode]:
    """Fetch an RSS feed and return its most recent episode, or None on any failure."""
    episodes = recent_episodes(feed_url, limit=1)
    return episodes[0] if episodes else None


def recent_episodes(feed_url: str, limit: int = DEFAULT_RECENT_LIMIT) -> list[Episode]:
    """Fetch an RSS feed and return up to `limit` of its most recent
    episodes (in feed order, which is newest-first by RSS convention).
    Empty on any failure — offline, malformed XML, nothing usable.
    """
    request = urllib.request.Request(
        feed_url, headers={"User-Agent": "Simple-Streamer/1 (+podcast player)"}
    )
    try:
        with urllib.request.urlopen(
            request, timeout=FEED_TIMEOUT_SECONDS, context=SSL_CONTEXT
        ) as response:
            root = ET.fromstring(response.read())
    except (OSError, ET.ParseError):
        return []

    channel = root.find("channel")
    if channel is None:
        return []

    episodes = []
    for item in channel.findall("item"):
        if len(episodes) >= limit:
            break
        episode = _parse_item(item)
        if episode is not None:
            episodes.append(episode)
    return episodes


def _parse_item(item) -> Optional[Episode]:
    enclosure = item.find("enclosure")
    audio_url = enclosure.get("url") if enclosure is not None else None
    if not audio_url:
        return None  # an item with no playable audio isn't a usable episode

    return Episode(
        title=item.findtext("title", default="Untitled episode"),
        audio_url=audio_url,
        published=item.findtext("pubDate", default=""),
        duration_seconds=_parse_itunes_duration(
            item.findtext(f"{{{_ITUNES_NS}}}duration")
        ),
    )


def _parse_itunes_duration(raw: Optional[str]) -> Optional[int]:
    """itunes:duration is inconsistently either plain seconds ("2823") or
    HH:MM:SS / MM:SS — best-effort, None if it's neither.
    """
    if not raw:
        return None
    raw = raw.strip()
    parts = raw.split(":")
    try:
        numbers = [int(p) for p in parts]
    except ValueError:
        return None

    if len(numbers) == 1:
        return numbers[0]
    if len(numbers) == 2:
        minutes, seconds = numbers
        return minutes * 60 + seconds
    if len(numbers) == 3:
        hours, minutes, seconds = numbers
        return hours * 3600 + minutes * 60 + seconds
    return None
