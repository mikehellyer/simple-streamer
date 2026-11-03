"""Showing text that came from outside the app — song titles from a stream,
episode titles, station names from a directory, update error output — as
exactly that text.

QLabel and tooltips guess from the text itself whether it's HTML, so a
stream titled "<b>…</b><img src=…>" would otherwise be rendered as markup.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import Qt as GuiQt
from PySide6.QtWidgets import QLabel


def plain_label(text: str = "") -> QLabel:
    label = QLabel()
    label.setTextFormat(Qt.PlainText)
    label.setText(text)
    return label


def plain_tooltip(text: str) -> str:
    """A tooltip string that displays `text` literally (empty stays empty)."""
    return GuiQt.convertFromPlainText(text) if text else ""
