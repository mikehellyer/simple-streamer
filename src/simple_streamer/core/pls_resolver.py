"""Resolve a .pls playlist to the stream URL it currently points at.

Some stations (Planet Rock, at least) don't hand out a stable stream URL —
the .pls redirector they publish embeds a short-lived signed token, so the
File1= line has to be re-fetched at play time rather than stored as-is.
FFmpeg also can't be pointed at the .pls file directly: it misdetects the
INI-like text as an LRC lyrics file instead of following it.
"""
from __future__ import annotations

import re
import urllib.request
from typing import Optional

PLS_TIMEOUT_SECONDS = 6
_FILE_LINE = re.compile(r"^File1=(.+)$", re.MULTILINE)


def resolve_pls(pls_url: str) -> Optional[str]:
    """Return the stream URL a .pls playlist currently points at, or None."""
    request = urllib.request.Request(pls_url, headers={"User-Agent": "Simple-Streamer/1"})
    try:
        with urllib.request.urlopen(request, timeout=PLS_TIMEOUT_SECONDS) as response:
            text = response.read().decode("utf-8", errors="replace")
    except OSError:
        return None

    match = _FILE_LINE.search(text)
    return match.group(1).strip() if match else None
