"""Audio-reactive glow around the window's content.

A dedicated container widget that paints its own soft border, rather
than a QGraphicsEffect applied to the real content: a graphics effect
recomposites its entire widget subtree through an offscreen buffer on
every repaint, which is expensive for a subtree this size (header,
tabs, preset grids, the EQ visualizer redrawing every 40ms) and, in
practice, ended up clipped invisible by the layout margin around it
instead of actually bleeding outward. Painting the glow directly in
this widget's own paintEvent — layered semi-transparent rounded-rect
strokes faking a blur falloff — only ever repaints this one widget.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout

from simple_streamer.core.glow_color import compute_glow

MAX_SPREAD = 18  # pixels the glow extends beyond the wrapped content's edge
LAYERS = 9
MAX_ALPHA = 255
# How much of each tick's target color/intensity to blend in — lower is
# smoother/slower, avoiding a flickery frame-to-frame color jump.
SMOOTHING = 0.2


class AudioGlow(QWidget):
    def __init__(self, content: QWidget, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(MAX_SPREAD, MAX_SPREAD, MAX_SPREAD, MAX_SPREAD)
        layout.addWidget(content)
        self._current = (0.0, 0.0, 0.0, 0.0)  # smoothed red, green, blue, intensity
        self._enabled = True

    def set_glow_enabled(self, enabled: bool) -> None:
        # The reserved margin around `content` stays either way, so
        # toggling this never resizes/reflows the actual window content
        # — only whether paintEvent draws into it.
        self._enabled = enabled
        self.update()

    def update_levels(self, left, right) -> None:
        glow = compute_glow(left, right, time.monotonic())
        prev_red, prev_green, prev_blue, prev_intensity = self._current
        red = prev_red + (glow.red - prev_red) * SMOOTHING
        green = prev_green + (glow.green - prev_green) * SMOOTHING
        blue = prev_blue + (glow.blue - prev_blue) * SMOOTHING
        intensity = prev_intensity + (glow.intensity - prev_intensity) * SMOOTHING
        self._current = (red, green, blue, intensity)
        self.update()

    def paintEvent(self, event) -> None:
        if not self._enabled:
            return
        red, green, blue, intensity = self._current
        if intensity <= 0.01:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(Qt.NoBrush)
        base_rect = self.rect().adjusted(MAX_SPREAD, MAX_SPREAD, -MAX_SPREAD, -MAX_SPREAD)

        # Typical music sits well under full-scale on the underlying
        # band levels — boost intensity with a gamma curve so a normal
        # (not maxed-out) listening level still reads as a clearly
        # visible glow, not a barely-there haze.
        boosted_intensity = min(1.0, intensity) ** 0.35

        for layer in range(LAYERS, 0, -1):
            spread = MAX_SPREAD * layer / LAYERS
            alpha = round(boosted_intensity * MAX_ALPHA * (1 - layer / LAYERS))
            pen = QPen(QColor(round(red), round(green), round(blue), max(0, min(255, alpha))))
            pen.setWidth(3)
            painter.setPen(pen)
            rect = base_rect.adjusted(-spread, -spread, spread, spread)
            painter.drawRoundedRect(rect, 12, 12)
