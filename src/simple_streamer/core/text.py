"""Small text helpers with no Qt dependency, so they're testable headlessly."""
from __future__ import annotations

# Fits the longest built-in preset name ("BBC Radio 5 Live Sports Extra")
# at the default window width — see gui/preset_deck.py's grid sizing.
PRESET_BUTTON_LABEL_MAX_CHARS = 30


def shorten(label: str, max_chars: int) -> str:
    """Elide label to at most max_chars, ending in an ellipsis if it was cut."""
    if len(label) <= max_chars:
        return label
    return label[: max_chars - 1].rstrip() + "…"
