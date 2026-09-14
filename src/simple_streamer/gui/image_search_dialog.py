"""Dialog shown from a preset's "Search for Image..." context menu.

Purely presentational — PresetDeckWidget kicks off the actual network
lookup via MainWindow's `_run_in_background` (the app's one already-
correct background-thread helper, see main_window.py) and hands results
to this dialog via show_results(). Keeping this dialog thread-free
avoids re-solving thread-lifetime/GC pitfalls a second time.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
    QDialogButtonBox,
)

from simple_streamer.core.image_search import FetchedImage

THUMBNAIL_SIZE = 96
GRID_COLUMNS = 4


class ImageSearchDialog(QDialog):
    def __init__(self, query: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Search for image — {query}")
        self.setMinimumSize(460, 360)
        self._chosen: Optional[FetchedImage] = None

        layout = QVBoxLayout(self)
        self._status = QLabel(f"Searching for “{query}”…")
        layout.addWidget(self._status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._results_widget = QWidget()
        self._grid = QGridLayout(self._results_widget)
        scroll.setWidget(self._results_widget)
        layout.addWidget(scroll, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def show_results(self, fetched: list[FetchedImage]) -> None:
        if not fetched:
            self._status.setText(
                "No images found. Try renaming the preset to something more "
                "specific, or search again later."
            )
            return

        self._status.setText(f"Found {len(fetched)} result(s) — click one to use it:")
        shown = 0
        for item in fetched:
            pixmap = QPixmap()
            if not pixmap.loadFromData(item.image_bytes):
                continue  # an unrecognized/corrupt image format — skip it
            button = QPushButton()
            button.setIcon(
                pixmap.scaled(
                    THUMBNAIL_SIZE, THUMBNAIL_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
            button.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
            button.setFixedSize(THUMBNAIL_SIZE + 24, THUMBNAIL_SIZE + 24)
            button.setToolTip(item.title)
            button.clicked.connect(lambda _checked=False, i=item: self._choose(i))
            row, col = divmod(shown, GRID_COLUMNS)
            self._grid.addWidget(button, row, col)
            shown += 1

        if shown == 0:
            self._status.setText("Found results, but none loaded as a usable image.")

    def _choose(self, item: FetchedImage) -> None:
        self._chosen = item
        self.accept()

    def chosen_image(self) -> Optional[FetchedImage]:
        return self._chosen
