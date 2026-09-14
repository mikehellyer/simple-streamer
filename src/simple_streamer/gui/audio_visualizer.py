"""An '80s-style stereo LED graphic equalizer, driven by the real decoded
audio (via QAudioBufferOutput tapping the QMediaPlayer), not a canned
animation.

Two rows of segmented bars — Left on top, Right below — each column a
log-spaced frequency band computed in core/spectrum.py. Ballistics are
classic analog-meter style: a bar jumps up instantly to a louder level
but falls back down gradually, which is what actually makes it read as
"reacting to music" rather than just jittering.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget, QSizePolicy

from simple_streamer.core.spectrum import band_levels

NUM_BANDS = 10
SEGMENTS_PER_BAR = 6
DECAY_FACTOR = 0.80  # per repaint tick — how fast a bar falls when it gets quieter
REPAINT_INTERVAL_MS = 40

BACKGROUND = QColor(18, 20, 20)
BORDER = QColor(60, 64, 64)
SEGMENT_OFF = QColor(40, 44, 44)
GREEN = QColor(70, 220, 110)
YELLOW = QColor(232, 200, 60)
RED = QColor(224, 80, 70)


def _segment_color(segment_index: int) -> QColor:
    if segment_index >= SEGMENTS_PER_BAR - 1:
        return RED
    if segment_index >= SEGMENTS_PER_BAR - 3:
        return YELLOW
    return GREEN


class StereoVisualizer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(72)
        self.setMinimumWidth(140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._target = {"left": np.zeros(NUM_BANDS), "right": np.zeros(NUM_BANDS)}
        self._display = {"left": np.zeros(NUM_BANDS), "right": np.zeros(NUM_BANDS)}

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(REPAINT_INTERVAL_MS)

    def feed_buffer(self, buffer) -> None:
        fmt = buffer.format()
        if fmt.channelCount() < 1 or buffer.frameCount() == 0:
            return
        samples = np.frombuffer(buffer.constData(), dtype=np.float32)
        samples = samples.reshape(-1, fmt.channelCount())
        sample_rate = fmt.sampleRate()

        self._target["left"] = band_levels(samples[:, 0], sample_rate, NUM_BANDS)
        right_channel = samples[:, 1] if fmt.channelCount() > 1 else samples[:, 0]
        self._target["right"] = band_levels(right_channel, sample_rate, NUM_BANDS)

    def clear(self) -> None:
        self._target["left"] = np.zeros(NUM_BANDS)
        self._target["right"] = np.zeros(NUM_BANDS)
        self._display["left"] = np.zeros(NUM_BANDS)
        self._display["right"] = np.zeros(NUM_BANDS)
        self.update()

    def _tick(self) -> None:
        for channel in ("left", "right"):
            target = self._target[channel]
            display = self._display[channel]
            self._display[channel] = np.where(target > display, target, display * DECAY_FACTOR)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setPen(BORDER)
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)

        margin = 4
        gap = 3
        usable_width = self.width() - 2 * margin
        bar_width = (usable_width - gap * (NUM_BANDS - 1)) / NUM_BANDS
        row_height = (self.height() - 2 * margin - gap) / 2
        seg_gap = 1
        seg_height = (row_height - seg_gap * (SEGMENTS_PER_BAR - 1)) / SEGMENTS_PER_BAR

        painter.setPen(Qt.NoPen)
        for row_index, channel in enumerate(("left", "right")):
            row_top = margin + row_index * (row_height + gap)
            lit_counts = np.round(self._display[channel] * SEGMENTS_PER_BAR).astype(int)
            for band_index in range(NUM_BANDS):
                x = margin + band_index * (bar_width + gap)
                lit = lit_counts[band_index]
                for seg in range(SEGMENTS_PER_BAR):
                    y = row_top + row_height - (seg + 1) * seg_height - seg * seg_gap
                    painter.setBrush(_segment_color(seg) if seg < lit else SEGMENT_OFF)
                    painter.drawRoundedRect(int(x), int(y), int(bar_width), int(seg_height), 1, 1)
