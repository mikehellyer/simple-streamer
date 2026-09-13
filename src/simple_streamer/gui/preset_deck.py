"""A single 20-slot preset deck (used for both the Radio tab and the Podcasts tab)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QInputDialog,
    QFrame,
    QProgressBar,
    QSizePolicy,
)

GRID_COLUMNS = 5
BUTTON_LABEL_MAX_CHARS = 30  # fits the longest built-in preset name at the default window width


def _shorten(label: str) -> str:
    """Fit a preset's name on a button of the fixed grid size.

    All buttons are forced to the same width (see the grid-stretch setup in
    PresetDeckWidget), so a long name is elided rather than allowed to
    widen its own column — the full name still shows in the F1 legend and
    as this button's tooltip.
    """
    if len(label) <= BUTTON_LABEL_MAX_CHARS:
        return label
    return label[: BUTTON_LABEL_MAX_CHARS - 1].rstrip() + "…"

from simple_streamer.core.presets import PresetStore


class LegendOverlay(QFrame):
    """Semi-transparent overlay listing every slot's label, shown while F1 is held."""

    def __init__(self, category: str, store: PresetStore, parent=None):
        super().__init__(parent)
        self._category = category
        self._store = store
        self.setObjectName("legendOverlay")
        self.setStyleSheet(
            "#legendOverlay { background-color: rgba(15, 17, 19, 0.72); border-radius: 6px; }"
            "QLabel { color: white; font-size: 13px; }"
            "QLabel[role='title'] { color: #9fb; font-size: 11px; letter-spacing: 1px; }"
        )
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(16, 16, 16, 16)
        self.hide()

    def refresh(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        title = QLabel(f"{self._category.title()} presets — hold F1")
        title.setProperty("role", "title")
        self._grid.addWidget(title, 0, 0, 1, 2)

        for slot in self._store.deck(self._category):
            text = f"{slot.number}   {slot.label or '(empty)'}"
            row, col = divmod(slot.number - 1, 2)
            self._grid.addWidget(QLabel(text), row + 1, col)


class PresetDeckWidget(QWidget):
    """One tab's worth of UI: a now-playing readout and a 5-wide grid of preset buttons."""

    slot_activated = Signal(str, int)  # category, slot number
    stop_requested = Signal()

    def __init__(self, category: str, store: PresetStore, parent=None):
        super().__init__(parent)
        self._category = category
        self._store = store
        self._buttons: dict[int, QPushButton] = {}

        layout = QVBoxLayout(self)

        now_playing_row = QHBoxLayout()
        self._now_playing = QLabel("Nothing playing")
        self._now_playing.setObjectName("nowPlaying")
        self._now_playing.setStyleSheet("font-size: 16px; font-weight: 600; padding: 8px;")
        now_playing_row.addWidget(self._now_playing, stretch=1)

        self._stop_button = QPushButton("Stop")
        self._stop_button.clicked.connect(self.stop_requested)
        now_playing_row.addWidget(self._stop_button)
        layout.addLayout(now_playing_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate — we don't know how long a lookup takes
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(4)
        self._progress.hide()
        layout.addWidget(self._progress)

        grid_container = QWidget()
        self._grid = QGridLayout(grid_container)
        for slot in store.deck(category):
            button = QPushButton()
            button.setMinimumHeight(64)
            # Ignored (not Expanding) so a long label like "BBC Radio 5 Live
            # Sports Extra" doesn't inflate this button's own size hint and
            # drag its whole column wider than the others — column width
            # then comes purely from the equal stretch factors below.
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
            button.clicked.connect(lambda _checked=False, n=slot.number: self._on_slot_clicked(n))
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda _pos, n=slot.number: self._assign_slot(n)
            )
            row, col = divmod(slot.number - 1, GRID_COLUMNS)
            self._grid.addWidget(button, row, col)
            self._buttons[slot.number] = button

        # Equal stretch on every row/column — otherwise QGridLayout sizes
        # each column to its widest button's natural content (a long label
        # like "BBC Radio 5 Live Sports Extra" would make its whole column
        # wider than the others), leaving same-row buttons visibly uneven.
        row_count = -(-len(store.deck(category)) // GRID_COLUMNS)
        for col in range(GRID_COLUMNS):
            self._grid.setColumnStretch(col, 1)
        for row in range(row_count):
            self._grid.setRowStretch(row, 1)

        layout.addWidget(grid_container)

        hint = QLabel("Click a slot to play it · right-click to assign · hold F1 for the legend")
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        self._legend = LegendOverlay(category, store, grid_container)
        self._legend.setGeometry(grid_container.rect())
        grid_container.installEventFilter(self)
        self._grid_container = grid_container

        self.refresh_labels()

    def eventFilter(self, watched, event):
        if watched is self._grid_container and event.type() == event.Type.Resize:
            self._legend.setGeometry(self._grid_container.rect())
        return super().eventFilter(watched, event)

    def refresh_labels(self) -> None:
        for slot in self._store.deck(self._category):
            button = self._buttons[slot.number]
            if slot.label:
                button.setText(f"{slot.number}\n{_shorten(slot.label)}")
                button.setToolTip(slot.label)
            else:
                button.setText(str(slot.number))
                button.setToolTip("")
        self._legend.refresh()

    def show_legend(self, visible: bool) -> None:
        if visible:
            self._legend.refresh()
            self._legend.setGeometry(self._grid_container.rect())
            self._legend.raise_()
            self._legend.show()
        else:
            self._legend.hide()

    def set_now_playing(self, text: str) -> None:
        self._now_playing.setText(text)

    def set_loading(self, loading: bool) -> None:
        self._progress.setVisible(loading)

    def _on_slot_clicked(self, number: int) -> None:
        slot = self._store.slot(self._category, number)
        if slot.is_empty:
            self._assign_slot(number)
            return
        self.slot_activated.emit(self._category, number)

    def _assign_slot(self, number: int) -> None:
        slot = self._store.slot(self._category, number)
        label, ok = QInputDialog.getText(self, "Assign preset", "Name:", text=slot.label)
        if not ok or not label:
            return
        url_prompt = "Podcast RSS feed URL:" if self._category == "podcasts" else "Stream URL:"
        url, ok = QInputDialog.getText(self, "Assign preset", url_prompt, text=slot.url)
        if not ok or not url:
            return
        self._store.assign(self._category, number, label, url)
        self._store.save()
        self.refresh_labels()
