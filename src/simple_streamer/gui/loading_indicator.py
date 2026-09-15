"""A "tuning in" loading bar that looks and animates the same on every
platform.

QProgressBar's indeterminate mode (setRange(0, 0)) delegates its actual
animation to the OS's native Qt style, which turned out to vary a lot
in practice: a continuous back-and-forth bounce on macOS, but a single
fast left-to-right sweep that then just stops under a Linux desktop's
Fusion/GTK style — nothing left animating. Painting the bounce
ourselves, on our own QTimer, guarantees the same look everywhere.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

BAR_HEIGHT = 4
BACKGROUND_COLOR = QColor(224, 224, 224)
SEGMENT_COLOR = QColor(70, 130, 220)
SEGMENT_FRACTION = 0.28  # the moving segment's width, as a fraction of the bar's own width
STEP_INTERVAL_MS = 16
STEP_FRACTION = 0.012  # how far the segment moves per tick, as a fraction of the bar's width


class LoadingIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(BAR_HEIGHT)
        self._position = 0.0  # 0..(1 - SEGMENT_FRACTION): the segment's left edge
        self._direction = 1
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self.hide()

    def set_loading(self, loading: bool) -> None:
        if loading:
            self._position = 0.0
            self._direction = 1
            self._timer.start(STEP_INTERVAL_MS)
            self.show()
        else:
            self._timer.stop()
            self.hide()

    def _step(self) -> None:
        self._position += STEP_FRACTION * self._direction
        if self._position >= 1.0 - SEGMENT_FRACTION:
            self._position = 1.0 - SEGMENT_FRACTION
            self._direction = -1
        elif self._position <= 0.0:
            self._position = 0.0
            self._direction = 1
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKGROUND_COLOR)
        width = self.width()
        segment_width = max(4, round(width * SEGMENT_FRACTION))
        x = round(self._position * width)
        painter.fillRect(x, 0, segment_width, self.height(), SEGMENT_COLOR)
