"""Periodically polls BBC's now-playing API while a BBC station is active.

Unlike ICY StreamTitle updates (pushed inline with an icecast/shoutcast
stream — see core/icy_metadata.py), BBC's segment data has to be asked
for, so this polls it on a timer instead of listening for it.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from simple_streamer.core.bbc_nowplaying import fetch_now_playing

POLL_INTERVAL_MS = 15_000


class BbcNowPlayingPoller(QObject):
    title_changed = Signal(str)

    def __init__(self, run_in_background: Callable, parent=None):
        super().__init__(parent)
        self._run_in_background = run_in_background
        self._service_id: Optional[str] = None
        self._last_title: Optional[str] = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

    def start(self, service_id: str) -> None:
        self._service_id = service_id
        self._last_title = None
        self._poll()
        self._timer.start(POLL_INTERVAL_MS)

    def stop(self) -> None:
        self._timer.stop()
        self._service_id = None

    def _poll(self) -> None:
        service_id = self._service_id
        if service_id is None:
            return
        self._run_in_background(lambda: fetch_now_playing(service_id), self._on_fetched)

    def _on_fetched(self, info) -> None:
        if self._service_id is None:
            return  # stopped (or moved to a different station) while this was in flight
        title = info.title if info else None
        if title and title != self._last_title:
            self._last_title = title
            self.title_changed.emit(title)
