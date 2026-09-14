"""Now-playing info for BBC stations, via BBC's own (undocumented but
widely used) segments API.

BBC's radio streams are HLS, which doesn't carry ICY tags the way a
shoutcast/icecast stream does — core/icy_metadata.py has nothing to read
from them. This polls BBC's "what's playing right now" endpoint instead,
since that data isn't pushed inline with the audio the way ICY StreamTitle
updates are (see gui/bbc_now_playing_poller.py for the polling side).
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Optional

from simple_streamer.core.http import SSL_CONTEXT

API_TIMEOUT_SECONDS = 5
_SERVICE_ID_RE = re.compile(r"bbc_radio_[a-z0-9_]+")


@dataclass
class NowPlaying:
    title: str


def bbc_service_id_from_url(stream_url: str) -> Optional[str]:
    """Pull a BBC service id (e.g. "bbc_radio_one") out of one of our
    stream URLs, however it's shaped — as the lsn.lv resolver's `station=`
    query param, or embedded directly in a CDN path — or None if this
    doesn't look like a BBC stream at all.
    """
    match = _SERVICE_ID_RE.search(stream_url)
    return match.group(0) if match else None


def fetch_now_playing(service_id: str) -> Optional[NowPlaying]:
    """Return what's currently playing on a BBC service, or None.

    None covers both failure (offline, bad response) and "nothing to
    report" — speech stations like Radio 4 or 5 Live genuinely have no
    music segment to name, which isn't an error.
    """
    url = (
        f"https://rms.api.bbc.co.uk/v2/services/{service_id}"
        "/segments/latest?experience=domestic&offset=0&limit=1"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Simple-Streamer/1"})
    try:
        with urllib.request.urlopen(
            request, timeout=API_TIMEOUT_SECONDS, context=SSL_CONTEXT
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None

    items = payload.get("data") or []
    if not items:
        return None

    titles = items[0].get("titles") or {}
    primary = (titles.get("primary") or "").strip()
    secondary = (titles.get("secondary") or "").strip()
    if not secondary:
        return None

    title = f"{primary} - {secondary}" if primary else secondary
    return NowPlaying(title=title)
