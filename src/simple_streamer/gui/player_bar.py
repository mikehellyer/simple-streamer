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
    QSlider,
    QWidget,
)

from simple_streamer.core.browser_raise import try_raise_browser_window
from simple_streamer.core.text import format_duration_ms
from simple_streamer.gui.loading_indicator import LoadingIndicator


class PlayerBar(QFrame):
    stop_requested = Signal()
    play_pause_requested = Signal()
    seek_requested = Signal(int)  # milliseconds to jump, negative for back
    position_seek_requested = Signal(int)  # absolute milliseconds, from dragging the progress bar
    episodes_requested = Signal()
    volume_changed = Signal(int)  # 0-100
    schedule_toggled = Signal(bool)

    SEEK_STEP_MS = 15_000
    # Schedule button colours: (normal, hover) — green when on, red when off.
    SCHEDULE_ON_COLOURS = ("#2e7d32", "#1b5e20")
    SCHEDULE_OFF_COLOURS = ("#c62828", "#8e0000")
    VOLUME_BOX_WIDTH = 190

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
        # Volume sits at the right-hand end and the schedule switch at the
        # left, in same-width boxes so the transport buttons stay centred.
        volume_box = QWidget()
        volume_box.setFixedWidth(self.VOLUME_BOX_WIDTH)
        volume_layout = QHBoxLayout(volume_box)
        volume_layout.setContentsMargins(0, 0, 0, 0)
        volume_icon = QLabel("🔊")
        volume_icon.setToolTip("Volume")
        self._volume_slider = QSlider(Qt.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setToolTip("Volume")
        self._volume_label = QLabel()
        self._volume_label.setStyleSheet("color: gray; font-size: 11px;")
        self._volume_label.setMinimumWidth(32)
        self._volume_slider.valueChanged.connect(self._on_volume_slider_changed)
        volume_layout.addWidget(volume_icon)
        volume_layout.addWidget(self._volume_slider, stretch=1)
        volume_layout.addWidget(self._volume_label)
        schedule_box = QWidget()
        schedule_box.setFixedWidth(self.VOLUME_BOX_WIDTH)
        schedule_layout = QHBoxLayout(schedule_box)
        schedule_layout.setContentsMargins(0, 0, 0, 0)
        self._schedule_button = QPushButton()
        self._schedule_button.setCheckable(True)
        self._schedule_button.setToolTip(
            "Switch the schedule on or off (Schedule → Edit Schedule… to change it)"
        )
        self._schedule_button.toggled.connect(self._on_schedule_button_toggled)
        schedule_layout.addWidget(self._schedule_button)
        schedule_layout.addStretch(1)
        self.set_schedule_on(False)
        controls_row.addWidget(schedule_box)
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
        controls_row.addWidget(volume_box)
        outer.addLayout(controls_row)

        self.set_active(False)

        self._progress = LoadingIndicator()
        outer.addWidget(self._progress)

    def set_schedule_on(self, on: bool) -> None:
        """Show the schedule as on/off without emitting schedule_toggled."""
        self._schedule_button.blockSignals(True)
        self._schedule_button.setChecked(on)
        self._schedule_button.blockSignals(False)
        self._show_schedule_state(on)

    def _on_schedule_button_toggled(self, on: bool) -> None:
        self._show_schedule_state(on)
        self.schedule_toggled.emit(on)

    def _show_schedule_state(self, on: bool) -> None:
        self._schedule_button.setText("📅 Schedule: On" if on else "📅 Schedule: Off")
        normal, hover = self.SCHEDULE_ON_COLOURS if on else self.SCHEDULE_OFF_COLOURS
        self._schedule_button.setStyleSheet(
            f"QPushButton {{ background-color: {normal}; color: white; font-weight: 600;"
            f" border: none; border-radius: 4px; padding: 4px 10px; }}"
            f"QPushButton:hover, QPushButton:pressed {{ background-color: {hover}; }}"
        )

    def set_volume(self, volume: int) -> None:
        """Show `volume` on the slider without emitting volume_changed."""
        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(volume)
        self._volume_slider.blockSignals(False)
        self._volume_label.setText(f"{volume}%")

    def _on_volume_slider_changed(self, volume: int) -> None:
        self._volume_label.setText(f"{volume}%")
        self.volume_changed.emit(volume)

    def set_now_playing(self, text: str) -> None:
        self._now_playing.setText(text)

    def set_loading(self, loading: bool) -> None:
        self._progress.set_loading(loading)

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
