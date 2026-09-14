"""The single now-playing bar shown above the tabs.

There's only one QMediaPlayer shared between the Radio and Podcasts
decks, so there's only one place that should show what it's doing —
previously each deck had its own now-playing row, which meant switching
tabs could show stale or duplicate state. Framed as its own bordered
box so it reads as a separate element from the tabs below it.
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar

from simple_streamer.core.browser_raise import try_raise_browser_window


class PlayerBar(QFrame):
    stop_requested = Signal()
    play_pause_requested = Signal()
    seek_requested = Signal(int)  # milliseconds to jump, negative for back
    episodes_requested = Signal()

    SEEK_STEP_MS = 15_000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playerBar")
        # Without this, a stylesheet border/background on a plain QFrame
        # subclass silently doesn't paint at all — Qt's default paintEvent
        # skips the style-drawn background/border unless told to use it.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "#playerBar { border: 1px solid rgba(0, 0, 0, 0.22); border-radius: 8px; }"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        top_row = QHBoxLayout()
        self._now_playing = QLabel("Nothing playing")
        self._now_playing.setStyleSheet("font-size: 16px; font-weight: 600;")
        top_row.addWidget(self._now_playing, stretch=1)

        self._website_url = ""
        self._website_button = QPushButton("Website")
        self._website_button.clicked.connect(self._open_website)
        self._website_button.hide()
        top_row.addWidget(self._website_button)

        self._episodes_button = QPushButton("Episodes")
        self._episodes_button.clicked.connect(self.episodes_requested)
        self._episodes_button.hide()
        top_row.addWidget(self._episodes_button)

        self._rewind_button = QPushButton("⏪ 15s")
        self._rewind_button.clicked.connect(lambda: self.seek_requested.emit(-self.SEEK_STEP_MS))
        top_row.addWidget(self._rewind_button)

        self._play_pause_button = QPushButton("Pause")
        self._play_pause_button.clicked.connect(self.play_pause_requested)
        top_row.addWidget(self._play_pause_button)

        self._forward_button = QPushButton("15s ⏩")
        self._forward_button.clicked.connect(lambda: self.seek_requested.emit(self.SEEK_STEP_MS))
        top_row.addWidget(self._forward_button)

        self._stop_button = QPushButton("Stop")
        self._stop_button.clicked.connect(self.stop_requested)
        top_row.addWidget(self._stop_button)
        outer.addLayout(top_row)

        self.set_active(False)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate — we don't know how long a lookup takes
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(4)
        self._progress.hide()
        outer.addWidget(self._progress)

    def set_now_playing(self, text: str) -> None:
        self._now_playing.setText(text)

    def set_loading(self, loading: bool) -> None:
        self._progress.setVisible(loading)

    def set_website(self, url: str) -> None:
        self._website_url = url or ""
        self._website_button.setVisible(bool(self._website_url))

    def set_episodes_available(self, available: bool) -> None:
        """Only podcasts have a list of episodes to browse — radio is a
        single live stream.
        """
        self._episodes_button.setVisible(available)

    def set_active(self, active: bool) -> None:
        """Whether anything is currently loaded (playing or paused) —
        transport controls are meaningless with nothing loaded.
        """
        self._play_pause_button.setEnabled(active)
        self._stop_button.setEnabled(active)
        if not active:
            self._rewind_button.setEnabled(False)
            self._forward_button.setEnabled(False)

    def set_seekable(self, seekable: bool) -> None:
        """Rewind/fast-forward only make sense for an on-demand podcast
        episode — a live radio broadcast has nothing to seek into.
        """
        self._rewind_button.setVisible(seekable)
        self._forward_button.setVisible(seekable)
        if seekable:
            self._rewind_button.setEnabled(True)
            self._forward_button.setEnabled(True)

    def set_playing(self, playing: bool) -> None:
        self._play_pause_button.setText("Pause" if playing else "Play")

    def _open_website(self) -> None:
        if self._website_url:
            QDesktopServices.openUrl(QUrl(self._website_url))
            try_raise_browser_window()
