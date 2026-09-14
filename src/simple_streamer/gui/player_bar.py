"""The single now-playing bar shown above the tabs.

There's only one QMediaPlayer shared between the Radio and Podcasts
decks, so there's only one place that should show what it's doing —
previously each deck had its own now-playing row, which meant switching
tabs could show stale or duplicate state. Framed as its own bordered
box so it reads as a separate element from the tabs below it.
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar


class PlayerBar(QFrame):
    stop_requested = Signal()

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

        self._stop_button = QPushButton("Stop")
        self._stop_button.clicked.connect(self.stop_requested)
        top_row.addWidget(self._stop_button)
        outer.addLayout(top_row)

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
