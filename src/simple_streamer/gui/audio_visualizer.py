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
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import QWidget, QSizePolicy

from simple_streamer.core.spectrum import band_levels

NUM_BANDS = 10
SEGMENTS_PER_BAR = 6
DECAY_FACTOR = 0.80  # per repaint tick — how fast a bar falls when it gets quieter
REPAINT_INTERVAL_MS = 40
LABEL_WIDTH = 16

BACKGROUND = QColor(18, 20, 20)
BORDER = QColor(60, 64, 64)
SEGMENT_OFF = QColor(40, 44, 44)
LABEL_COLOR = QColor(150, 158, 156)
GREEN = QColor(70, 220, 110)
YELLOW = QColor(232, 200, 60)
RED = QColor(224, 80, 70)


def _segment_color(segment_index: int) -> QColor:
    if segment_index >= SEGMENTS_PER_BAR - 1:
        return RED
    if segment_index >= SEGMENTS_PER_BAR - 3:
        return YELLOW
    return GREEN


def _blend(off: QColor, on: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(off.red() + (on.red() - off.red()) * t),
        int(off.green() + (on.green() - off.green()) * t),
        int(off.blue() + (on.blue() - off.blue()) * t),
    )


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
        row_height = (self.height() - 2 * margin - gap) / 2

        # "L" / "R" labels, so it's obvious which row is which channel
        # rather than just two unlabeled rows of bars.
        label_font = QFont(painter.font())
        label_font.setBold(True)
        label_font.setPixelSize(max(9, int(row_height * 0.55)))
        painter.setFont(label_font)
        painter.setPen(LABEL_COLOR)
        for row_index, letter in enumerate(("L", "R")):
            row_top = margin + row_index * (row_height + gap)
            label_rect = QRect(margin, int(row_top), LABEL_WIDTH, int(row_height))
            painter.drawText(label_rect, Qt.AlignCenter, letter)

        bars_left = margin + LABEL_WIDTH
        usable_width = self.width() - bars_left - margin
        bar_width = (usable_width - gap * (NUM_BANDS - 1)) / NUM_BANDS
        seg_gap = 1
        seg_height = (row_height - seg_gap * (SEGMENTS_PER_BAR - 1)) / SEGMENTS_PER_BAR

        painter.setPen(Qt.NoPen)
        for row_index, channel in enumerate(("left", "right")):
            row_top = margin + row_index * (row_height + gap)
            # Raw (fractional) height rather than a rounded segment count —
            # otherwise two channels with genuinely different levels often
            # round to the same whole number of lit segments and the rows
            # look like duplicates of each other. The boundary segment gets
            # a brightness blend for its fractional part, so movement (and
            # the difference between L and R) stays visible continuously
            # while the bar still reads as discrete LED blocks.
            raw_heights = self._display[channel] * SEGMENTS_PER_BAR
            for band_index in range(NUM_BANDS):
                x = bars_left + band_index * (bar_width + gap)
                raw = raw_heights[band_index]
                full_lit = int(np.floor(raw))
                partial = raw - full_lit
                for seg in range(SEGMENTS_PER_BAR):
                    y = row_top + row_height - (seg + 1) * seg_height - seg * seg_gap
                    if seg < full_lit:
                        color = _segment_color(seg)
                    elif seg == full_lit and partial > 0.05:
                        color = _blend(SEGMENT_OFF, _segment_color(seg), partial)
                    else:
                        color = SEGMENT_OFF
                    painter.setBrush(color)
                    painter.drawRoundedRect(int(x), int(y), int(bar_width), int(seg_height), 1, 1)
