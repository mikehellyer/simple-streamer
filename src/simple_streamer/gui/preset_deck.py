"""A single 20-slot preset deck (used for both the Radio tab and the Podcasts tab)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QToolButton,
    QFrame,
    QSizePolicy,
    QDialog,
    QMenu,
)

from simple_streamer.core.presets import PresetStore
from simple_streamer.core.text import shorten, PRESET_BUTTON_LABEL_MAX_CHARS
from simple_streamer.core.image_search import search_and_fetch, download_image, guess_extension
from simple_streamer.core.station_search import search_stations
from simple_streamer.core.podcast_search import search_podcasts
from simple_streamer.gui.preset_editor import PresetEditorDialog, CLEARED
from simple_streamer.gui.image_search_dialog import ImageSearchDialog
from simple_streamer.gui.preset_search_dialog import PresetSearchDialog

GRID_COLUMNS = 5
BUTTON_ICON_SIZE = 48


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
    """One tab's worth of UI: a 5-wide grid of preset buttons and their legend."""

    slot_activated = Signal(str, int)  # category, slot number

    def __init__(self, category: str, store: PresetStore, run_in_background, parent=None):
        super().__init__(parent)
        self._category = category
        self._store = store
        self._run_in_background = run_in_background
        self._buttons: dict[int, QToolButton] = {}

        layout = QVBoxLayout(self)

        grid_container = QWidget()
        self._grid = QGridLayout(grid_container)
        for slot in store.deck(category):
            button = QToolButton()
            # Image (if any) above the text, both centered — a plain
            # QPushButton always puts its icon to the left of the text,
            # with no built-in way to stack them instead.
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setMinimumHeight(88)
            # Ignored (not Expanding) so a long label like "BBC Radio 5 Live
            # Sports Extra" doesn't inflate this button's own size hint and
            # drag its whole column wider than the others — column width
            # then comes purely from the equal stretch factors below.
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
            button.clicked.connect(lambda _checked=False, n=slot.number: self._on_slot_clicked(n))
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, n=slot.number, b=button: self._show_context_menu(n, b, pos)
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

        hint = QLabel(
            "Click a slot to play it · right-click for options · hold F1 for the legend"
        )
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
                button.setText(shorten(slot.label, PRESET_BUTTON_LABEL_MAX_CHARS))
                tooltip = f"{slot.label}\n{slot.website}" if slot.website else slot.label
                button.setToolTip(tooltip)
            else:
                button.setText("")
                button.setToolTip("")
            self._set_button_icon(button, slot.image_path)
        self._legend.refresh()

    def _set_button_icon(self, button: QToolButton, image_path: str) -> None:
        pixmap = QPixmap(image_path) if image_path and Path(image_path).exists() else None
        if pixmap and not pixmap.isNull():
            button.setIcon(QIcon(pixmap))
            button.setIconSize(QSize(BUTTON_ICON_SIZE, BUTTON_ICON_SIZE))
        else:
            button.setIcon(QIcon())

    def show_legend(self, visible: bool) -> None:
        if visible:
            self._legend.refresh()
            self._legend.setGeometry(self._grid_container.rect())
            self._legend.raise_()
            self._legend.show()
        else:
            self._legend.hide()

    def _on_slot_clicked(self, number: int) -> None:
        slot = self._store.slot(self._category, number)
        if slot.is_empty:
            self._assign_slot(number)
            return
        self.slot_activated.emit(self._category, number)

    def _assign_slot(self, number: int) -> None:
        # .open() (not .exec()) — modal for input, but it doesn't run its
        # own nested event loop the way exec() does. A right-click-then-
        # Cancel through exec() left other preset buttons stuck showing a
        # pressed/hover state and unresponsive to clicks afterward; that
        # smelled like some interaction between exec()'s nested loop and
        # this window's own timers/threads (the EQ visualizer repaints
        # every 40ms, background threads for updates/podcasts, etc.).
        # open() sidesteps the nested loop entirely, so the result has to
        # be picked up via the finished signal instead of a return value.
        slot = self._store.slot(self._category, number)
        dialog = PresetEditorDialog(self._category, slot, parent=self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.finished.connect(
            lambda result_code: self._on_editor_finished(number, dialog, result_code)
        )
        dialog.open()

    def _on_editor_finished(self, number: int, dialog: PresetEditorDialog, result_code: int) -> None:
        if result_code == CLEARED:
            self._store.clear(self._category, number)
        elif result_code == QDialog.Accepted:
            self._store.assign(self._category, number, **dialog.result_data())
        else:
            return
        self._store.save()
        self.refresh_labels()

    def _show_context_menu(self, number: int, button: QToolButton, pos) -> None:
        slot = self._store.slot(self._category, number)
        menu = QMenu(self)

        edit_action = menu.addAction("Edit Preset…")
        edit_action.triggered.connect(lambda: self._assign_slot(number))

        if self._category == "radio":
            find_action = menu.addAction("Find New Station…")
            find_action.triggered.connect(lambda: self._find_station(number))
        else:
            find_action = menu.addAction("Find New Podcast…")
            find_action.triggered.connect(lambda: self._find_podcast(number))

        search_action = menu.addAction("Search for Image…")
        search_action.setEnabled(not slot.is_empty)
        search_action.triggered.connect(lambda: self._search_image(number))

        if slot.image_path:
            remove_action = menu.addAction("Remove Image")
            remove_action.triggered.connect(lambda: self._remove_image(number))

        # popup() (not exec()) — exec()'s nested event loop is what left
        # preset buttons stuck mid-hover after a right-click-then-Cancel
        # on the editor dialog (see the comment on _assign_slot); popup()
        # shows the menu without one.
        menu.popup(button.mapToGlobal(pos))

    def _search_image(self, number: int) -> None:
        slot = self._store.slot(self._category, number)
        dialog = ImageSearchDialog(slot.label, parent=self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.finished.connect(
            lambda result_code: self._on_image_search_finished(number, dialog, result_code)
        )
        dialog.open()
        category = self._category
        label = slot.label
        # on_finished must be a plain bound method, not a lambda — Qt only
        # recognizes it has to marshal the callback onto the main thread
        # when it can see a real QObject receiver (via a bound method's
        # __self__); a lambda wrapper hides that, so the callback below
        # would otherwise run on the worker thread and silently fail to
        # add its new buttons to a grid owned by the main thread (see the
        # Qt.QueuedConnection comment in MainWindow._run_in_background).
        # Bundling dialog+results into one tuple return value avoids
        # needing a lambda here to bind dialog as an extra argument.
        self._run_in_background(
            lambda: (dialog, search_and_fetch(category, label)),
            self._on_image_results,
        )

    def _on_image_results(self, result) -> None:
        dialog, fetched = result
        try:
            dialog.show_results(fetched)
        except RuntimeError:
            pass  # the user already closed the dialog before results arrived

    def _on_image_search_finished(
        self, number: int, dialog: ImageSearchDialog, result_code: int
    ) -> None:
        if result_code != QDialog.Accepted:
            return
        chosen = dialog.chosen_image()
        if chosen is None:
            return
        self._store.set_image(self._category, number, chosen.image_bytes, chosen.extension)
        self._store.save()
        self.refresh_labels()

    def _remove_image(self, number: int) -> None:
        self._store.clear_image(self._category, number)
        self._store.save()
        self.refresh_labels()

    def _find_station(self, number: int) -> None:
        dialog = PresetSearchDialog("station", parent=self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)

        # Both signals are only ever emitted from user interaction inside
        # the dialog (typing/clicking), so — unlike the _run_in_background
        # callbacks below — a lambda here is fine: it always runs on the
        # main thread already, nothing to marshal.
        dialog.search_requested.connect(
            lambda query: self._run_in_background(
                lambda: (dialog, search_stations(query)),
                self._on_find_results,
            )
        )
        dialog.result_chosen.connect(
            lambda station: self._run_in_background(
                lambda: (dialog, number, station, self._fetch_url(station.favicon_url)),
                self._on_station_chosen,
            )
        )
        dialog.open()

    def _find_podcast(self, number: int) -> None:
        dialog = PresetSearchDialog("podcast", parent=self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.search_requested.connect(
            lambda query: self._run_in_background(
                lambda: (dialog, search_podcasts(query)),
                self._on_find_results,
            )
        )
        dialog.result_chosen.connect(
            lambda podcast: self._run_in_background(
                lambda: (dialog, number, podcast, self._fetch_url(podcast.artwork_url)),
                self._on_podcast_chosen,
            )
        )
        dialog.open()

    @staticmethod
    def _fetch_url(url: str) -> Optional[bytes]:
        if not url:
            return None
        return download_image(url)

    def _on_find_results(self, result) -> None:
        dialog, results = result
        try:
            dialog.show_results(results)
        except RuntimeError:
            pass  # the user already closed the dialog before results arrived

    def _replace_slot(self, number: int, label: str, url: str, website: str, image_bytes, image_url: str) -> None:
        self._store.assign(self._category, number, label, url, website=website)
        # assign() preserves whatever image the slot already had (right,
        # for the ordinary Edit Preset path, which never touches images) —
        # but this replaces the slot with a whole different station/
        # podcast, so one with no artwork of its own must not keep a
        # stale old image.
        if image_bytes:
            self._store.set_image(self._category, number, image_bytes, guess_extension(image_url))
        else:
            self._store.clear_image(self._category, number)
        self._store.save()
        self.refresh_labels()

    def _on_station_chosen(self, result) -> None:
        dialog, number, station, image_bytes = result
        self._replace_slot(
            number, station.name, station.stream_url, station.website, image_bytes, station.favicon_url
        )
        try:
            dialog.accept()
        except RuntimeError:
            pass  # the user already closed the dialog while the logo was downloading

    def _on_podcast_chosen(self, result) -> None:
        dialog, number, podcast, image_bytes = result
        self._replace_slot(
            number, podcast.name, podcast.feed_url, podcast.website, image_bytes, podcast.artwork_url
        )
        try:
            dialog.accept()
        except RuntimeError:
            pass  # the user already closed the dialog while the artwork was downloading
