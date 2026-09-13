"""Resolve a podcast's RSS feed to its most recent episode.

Presets in the Podcasts deck store a feed URL rather than a fixed audio file,
so playing a slot always gets whatever the show published most recently.
"""
from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

FEED_TIMEOUT_SECONDS = 8


@dataclass
class Episode:
    title: str
    audio_url: str


def latest_episode(feed_url: str) -> Optional[Episode]:
    """Fetch an RSS feed and return its most recent episode, or None on any failure."""
    request = urllib.request.Request(feed_url, headers={"User-Agent": "Simple-Streamer/1 (+podcast player)"})
    try:
        with urllib.request.urlopen(request, timeout=FEED_TIMEOUT_SECONDS) as response:
            root = ET.fromstring(response.read())
    except (OSError, ET.ParseError):
        return None

    channel = root.find("channel")
    if channel is None:
        return None
    item = channel.find("item")
    if item is None:
        return None
    enclosure = item.find("enclosure")
    audio_url = enclosure.get("url") if enclosure is not None else None
    if not audio_url:
        return None

    return Episode(title=item.findtext("title", default="Untitled episode"), audio_url=audio_url)
