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
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QSlider,
)

from simple_streamer.core.browser_raise import try_raise_browser_window
from simple_streamer.core.text import format_duration_ms


class PlayerBar(QFrame):
    stop_requested = Signal()
    play_pause_requested = Signal()
    seek_requested = Signal(int)  # milliseconds to jump, negative for back
    position_seek_requested = Signal(int)  # absolute milliseconds, from dragging the progress bar
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

        # Title gets its own full-width row — sharing a row with the
        # buttons let a long episode title push/squeeze them (sometimes
        # off the edge of the window entirely) since they had to split
        # the same horizontal space.
        title_row = QHBoxLayout()
        self._now_playing = QLabel("Nothing playing")
        self._now_playing.setStyleSheet("font-size: 16px; font-weight: 600;")
        title_row.addWidget(self._now_playing, stretch=1)
        outer.addLayout(title_row)

        progress_row = QHBoxLayout()
        self._is_scrubbing = False
        self._progress_slider = QSlider(Qt.Horizontal)
        self._progress_slider.setRange(0, 0)
        self._progress_slider.sliderPressed.connect(self._on_slider_pressed)
        self._progress_slider.sliderReleased.connect(self._on_slider_released)
        progress_row.addWidget(self._progress_slider, stretch=1)
        self._progress_time_label = QLabel("")
        self._progress_time_label.setStyleSheet("color: gray; font-size: 11px;")
        progress_row.addWidget(self._progress_time_label)
        outer.addLayout(progress_row)

        # Buttons centered on their own row below the progress bar,
        # rather than sharing space with the title.
        controls_row = QHBoxLayout()
        controls_row.addStretch(1)

        self._website_url = ""
        self._website_button = QPushButton("Website")
        self._website_button.clicked.connect(self._open_website)
        self._website_button.hide()
        controls_row.addWidget(self._website_button)

        self._episodes_button = QPushButton("Episodes")
        self._episodes_button.clicked.connect(self.episodes_requested)
        self._episodes_button.hide()
        controls_row.addWidget(self._episodes_button)

        self._rewind_button = QPushButton("⏪ 15s")
        self._rewind_button.clicked.connect(lambda: self.seek_requested.emit(-self.SEEK_STEP_MS))
        controls_row.addWidget(self._rewind_button)

        self._play_pause_button = QPushButton("Pause")
        self._play_pause_button.clicked.connect(self.play_pause_requested)
        controls_row.addWidget(self._play_pause_button)

        self._forward_button = QPushButton("15s ⏩")
        self._forward_button.clicked.connect(lambda: self.seek_requested.emit(self.SEEK_STEP_MS))
        controls_row.addWidget(self._forward_button)

        self._stop_button = QPushButton("Stop")
        self._stop_button.clicked.connect(self.stop_requested)
        controls_row.addWidget(self._stop_button)

        controls_row.addStretch(1)
        outer.addLayout(controls_row)

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
            self.set_progress(0, 0)

    def set_seekable(self, seekable: bool) -> None:
        """Rewind/fast-forward, and the progress/seek bar, only make
        sense for an on-demand podcast episode — a live radio broadcast
        has nothing to seek into and no fixed length to show progress
        against.
        """
        self._rewind_button.setVisible(seekable)
        self._forward_button.setVisible(seekable)
        self._progress_slider.setVisible(seekable)
        self._progress_time_label.setVisible(seekable)
        if seekable:
            self._rewind_button.setEnabled(True)
            self._forward_button.setEnabled(True)

    def set_playing(self, playing: bool) -> None:
        self._play_pause_button.setText("Pause" if playing else "Play")

    def set_progress(self, position_ms: int, duration_ms: int) -> None:
        if duration_ms > 0:
            self._progress_slider.setRange(0, duration_ms)
            if not self._is_scrubbing:
                self._progress_slider.setValue(position_ms)
            self._progress_time_label.setText(
                f"{format_duration_ms(position_ms)} / {format_duration_ms(duration_ms)}"
            )
        else:
            self._progress_slider.setRange(0, 0)
            self._progress_time_label.setText("")

    def _on_slider_pressed(self) -> None:
        self._is_scrubbing = True

    def _on_slider_released(self) -> None:
        self._is_scrubbing = False
        self.position_seek_requested.emit(self._progress_slider.value())

    def _open_website(self) -> None:
        if self._website_url:
            QDesktopServices.openUrl(QUrl(self._website_url))
            try_raise_browser_window()
