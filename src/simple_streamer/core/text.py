"""Small text helpers with no Qt dependency, so they're testable headlessly."""
from __future__ import annotations

from email.utils import parsedate_to_datetime

# Fits the longest built-in preset name ("BBC Radio 5 Live Sports Extra")
# at the default window width — see gui/preset_deck.py's grid sizing.
PRESET_BUTTON_LABEL_MAX_CHARS = 30


def shorten(label: str, max_chars: int) -> str:
    """Elide label to at most max_chars, ending in an ellipsis if it was cut."""
    if len(label) <= max_chars:
        return label
    return label[: max_chars - 1].rstrip() + "…"


def format_duration_ms(milliseconds: int) -> str:
    """e.g. 45:10, or 1:47:03 once it's over an hour."""
    total_seconds = max(0, milliseconds) // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def format_pub_date(raw: str) -> str:
    """An RSS pubDate (RFC 822, e.g. "Sun, 14 Sep 2026 10:13:11 +0000")
    formatted as "14 Sep 2026", or "" if it's missing or doesn't parse —
    feeds vary enough in date formatting that this is best-effort, not
    guaranteed.
    """
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return ""
