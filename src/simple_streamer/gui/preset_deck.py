"""A preset deck, one 20-slot page at a time (used for both the Radio tab and the Podcasts tab)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal, QMimeData
from PySide6.QtGui import QIcon, QPixmap, QDrag
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QToolButton,
    QFrame,
    QSizePolicy,
    QDialog,
    QMenu,
)

from simple_streamer.core.presets import PresetStore, SLOTS_PER_PAGE, MAX_PAGES
from simple_streamer.core.episode_progress import EpisodeProgressStore
from simple_streamer.core.text import shorten, PRESET_BUTTON_LABEL_MAX_CHARS
from simple_streamer.core.image_search import search_and_fetch, download_image, guess_extension
from simple_streamer.core.station_search import search_stations
from simple_streamer.core.podcast_search import search_podcasts
from simple_streamer.core.podcasts import recent_episodes
from simple_streamer.gui.preset_editor import PresetEditorDialog, CLEARED
from simple_streamer.gui.image_search_dialog import ImageSearchDialog
from simple_streamer.gui.preset_search_dialog import PresetSearchDialog
from simple_streamer.gui.episode_list_dialog import EpisodeListDialog, EpisodeEntry

GRID_COLUMNS = 5
BUTTON_ICON_SIZE = 48
# Drag payload: "category:slot number", so a drop on the other tab's deck
# (or anything that isn't a preset) is ignored.
SLOT_MIME_TYPE = "application/x-simple-streamer-slot"


def _drag_payload(event) -> Optional[str]:
    mime = event.mimeData()
    if not mime.hasFormat(SLOT_MIME_TYPE):
        return None
    return bytes(mime.data(SLOT_MIME_TYPE)).decode("utf-8", "replace")


class PresetButton(QToolButton):
    """A preset slot button that can be dragged onto another slot."""

    dropped = Signal(str)  # drag payload of the preset dropped onto this one

    def __init__(self, drag_payload, parent=None):
        super().__init__(parent)
        # Called when a drag starts: the payload to carry, or None if this
        # slot is empty (nothing to move).
        self._drag_payload = drag_payload
        self._press_pos = None
        self.setAcceptDrops(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._press_pos is not None
            and event.buttons() & Qt.LeftButton
            and (event.position().toPoint() - self._press_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._press_pos = None
            payload = self._drag_payload()
            if payload is not None:
                # The release lands inside the drag, so no click fires —
                # just un-press the button visually before handing over.
                self.setDown(False)
                mime = QMimeData()
                mime.setData(SLOT_MIME_TYPE, payload.encode("utf-8"))
                drag = QDrag(self)
                drag.setMimeData(mime)
                drag.setPixmap(self.grab())
                drag.setHotSpot(event.position().toPoint())
                drag.exec(Qt.MoveAction)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if _drag_payload(event) is not None:
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if _drag_payload(event) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event):
        payload = _drag_payload(event)
        if payload is not None:
            event.acceptProposedAction()
            self.dropped.emit(payload)


class PageButton(QToolButton):
    """A "Page N" switcher. Hovering a dragged preset over it switches to
    that page, so a preset can be carried across pages; dropping it on the
    button itself puts it in that page's first empty slot.
    """

    drag_entered = Signal()
    dropped = Signal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setAutoRaise(True)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if _drag_payload(event) is not None:
            event.acceptProposedAction()
            self.drag_entered.emit()

    def dragMoveEvent(self, event):
        if _drag_payload(event) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event):
        payload = _drag_payload(event)
        if payload is not None:
            event.acceptProposedAction()
            self.dropped.emit(payload)


class LegendOverlay(QFrame):
    """Semi-transparent overlay listing the current page's slots, shown while F1 is held."""

    def __init__(self, category: str, store: PresetStore, current_page, parent=None):
        super().__init__(parent)
        self._category = category
        self._store = store
        self._current_page = current_page
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
            widget = self._grid.takeAt(0).widget()
            if widget:
                # Detach now: deleteLater() alone leaves the old label
                # painted over the new ones until the event loop gets to it.
                widget.setParent(None)
                widget.deleteLater()

        page = self._current_page()
        page_note = f" — page {page}" if self._store.page_count(self._category) > 1 else ""
        title = QLabel(f"{self._category.title()} presets{page_note} — hold F1")
        title.setProperty("role", "title")
        self._grid.addWidget(title, 0, 0, 1, 2)

        for position, slot in enumerate(self._store.page_slots(self._category, page), start=1):
            text = f"{slot.number}   {slot.label or '(empty)'}"
            row, col = divmod(position - 1, 2)
            self._grid.addWidget(QLabel(text), row + 1, col)


class PresetDeckWidget(QWidget):
    """One tab's worth of UI: a page of preset buttons in a 5-wide grid,
    page switching, and the F1 legend.
    """

    slot_activated = Signal(str, int)  # category, slot number
    episode_chosen = Signal(int, object)  # slot number, Episode — podcasts only
    # category, {old slot number: new slot number} — after a move or a
    # page removal, so the player can keep track of what it's playing.
    slots_renumbered = Signal(str, object)

    def __init__(
        self,
        category: str,
        store: PresetStore,
        run_in_background,
        episode_progress: Optional[EpisodeProgressStore] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._category = category
        self._store = store
        self._run_in_background = run_in_background
        self._episode_progress = episode_progress
        self._page = 1
        # Keyed by position on the page (1-20), not slot number — the same
        # 20 buttons show whichever page is current.
        self._buttons: dict[int, PresetButton] = {}

        layout = QVBoxLayout(self)

        grid_container = QWidget()
        self._grid = QGridLayout(grid_container)
        for position in range(1, SLOTS_PER_PAGE + 1):
            button = PresetButton(lambda p=position: self._drag_payload_for(p))
            # Image (if any) above the text, both centered — a plain
            # QPushButton always puts its icon to the left of the text,
            # with no built-in way to stack them instead.
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            # Short enough to leave the window some slack (see MainWindow's
            # initial size) while still fitting a 48px logo and its label.
            button.setMinimumHeight(74)
            # Ignored (not Expanding) so a long label like "BBC Radio 5 Live
            # Sports Extra" doesn't inflate this button's own size hint and
            # drag its whole column wider than the others — column width
            # then comes purely from the equal stretch factors below.
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
            button.clicked.connect(
                lambda _checked=False, p=position: self._on_slot_clicked(self._number_at(p))
            )
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, p=position, b=button: self._show_context_menu(self._number_at(p), b, pos)
            )
            button.dropped.connect(
                lambda payload, p=position: self._on_slot_dropped(payload, self._number_at(p))
            )
            row, col = divmod(position - 1, GRID_COLUMNS)
            self._grid.addWidget(button, row, col)
            self._buttons[position] = button

        # Equal stretch on every row/column — otherwise QGridLayout sizes
        # each column to its widest button's natural content (a long label
        # like "BBC Radio 5 Live Sports Extra" would make its whole column
        # wider than the others), leaving same-row buttons visibly uneven.
        row_count = -(-SLOTS_PER_PAGE // GRID_COLUMNS)
        for col in range(GRID_COLUMNS):
            self._grid.setColumnStretch(col, 1)
        for row in range(row_count):
            self._grid.setRowStretch(row, 1)

        layout.addWidget(grid_container)

        page_bar = QHBoxLayout()
        self._page_buttons_layout = QHBoxLayout()
        self._page_buttons: list[PageButton] = []
        page_bar.addLayout(self._page_buttons_layout)
        self._add_page_button = QToolButton()
        self._add_page_button.setText("+")
        self._add_page_button.setAutoRaise(True)
        self._add_page_button.setToolTip("Add a page of presets")
        self._add_page_button.clicked.connect(self._add_page)
        page_bar.addWidget(self._add_page_button)
        page_bar.addStretch(1)
        self._remove_page_button = QToolButton()
        self._remove_page_button.setText("Remove Page")
        self._remove_page_button.setAutoRaise(True)
        self._remove_page_button.setToolTip("Remove this page (only when it's empty)")
        self._remove_page_button.clicked.connect(self._remove_page)
        page_bar.addWidget(self._remove_page_button)
        layout.addLayout(page_bar)

        hint = QLabel(
            "Click a slot to play it · drag to move it · right-click for options"
            " · hold F1 for the legend"
        )
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        self._legend = LegendOverlay(category, store, lambda: self._page, grid_container)
        self._legend.setGeometry(grid_container.rect())
        grid_container.installEventFilter(self)
        self._grid_container = grid_container

        self.refresh_labels()

    def eventFilter(self, watched, event):
        if watched is self._grid_container and event.type() == event.Type.Resize:
            self._legend.setGeometry(self._grid_container.rect())
        return super().eventFilter(watched, event)

    def _number_at(self, position: int) -> int:
        return (self._page - 1) * SLOTS_PER_PAGE + position

    def _drag_payload_for(self, position: int) -> Optional[str]:
        number = self._number_at(position)
        if self._store.slot(self._category, number).is_empty:
            return None
        return f"{self._category}:{number}"

    def _slot_from_payload(self, payload: str) -> Optional[int]:
        category, _, number = payload.partition(":")
        if category != self._category or not number.isdigit():
            return None
        number = int(number)
        return number if 1 <= number <= len(self._store.deck(self._category)) else None

    def refresh_labels(self) -> None:
        self._page = min(self._page, self._store.page_count(self._category))
        for position, slot in enumerate(
            self._store.page_slots(self._category, self._page), start=1
        ):
            button = self._buttons[position]
            if slot.label:
                button.setText(shorten(slot.label, PRESET_BUTTON_LABEL_MAX_CHARS))
                tooltip = f"{slot.label}\n{slot.website}" if slot.website else slot.label
                button.setToolTip(tooltip)
            else:
                button.setText("")
                button.setToolTip("")
            self._set_button_icon(button, slot.image_path)
        self._sync_page_bar()
        self._legend.refresh()

    def _sync_page_bar(self) -> None:
        page_count = self._store.page_count(self._category)
        # Only rebuilt when the number of pages changes — switching pages
        # mid-drag (hovering a page button) must not delete the very
        # button the drag is over.
        if len(self._page_buttons) != page_count:
            for button in self._page_buttons:
                self._page_buttons_layout.removeWidget(button)
                button.setParent(None)
                button.deleteLater()
            self._page_buttons = []
            for page in range(1, page_count + 1):
                button = PageButton(f"Page {page}")
                button.clicked.connect(lambda _checked=False, p=page: self.show_page(p))
                button.drag_entered.connect(lambda p=page: self.show_page(p))
                button.dropped.connect(lambda payload, p=page: self._on_page_dropped(payload, p))
                self._page_buttons_layout.addWidget(button)
                self._page_buttons.append(button)
        for page, button in enumerate(self._page_buttons, start=1):
            button.setChecked(page == self._page)
        self._add_page_button.setEnabled(page_count < MAX_PAGES)
        self._remove_page_button.setEnabled(
            page_count > 1 and self._store.page_is_empty(self._category, self._page)
        )

    def current_page(self) -> int:
        return self._page

    def show_page(self, page: int) -> None:
        if page != self._page:
            self._page = page
            self.refresh_labels()
        else:
            self._sync_page_bar()  # re-check a button a click may have unchecked

    def _add_page(self) -> None:
        page = self._store.add_page(self._category)
        self._store.save()
        self.show_page(page)

    def _remove_page(self) -> None:
        if not self._store.page_is_empty(self._category, self._page):
            return
        renumbered = self._store.remove_page(self._category, self._page)
        self._store.save()
        self.refresh_labels()
        if renumbered:
            self.slots_renumbered.emit(self._category, renumbered)

    def _move(self, from_number: int, to_number: int) -> None:
        if from_number == to_number:
            return
        self._store.move(self._category, from_number, to_number)
        self._store.save()
        self.refresh_labels()
        self.slots_renumbered.emit(
            self._category, {from_number: to_number, to_number: from_number}
        )

    def _on_slot_dropped(self, payload: str, to_number: int) -> None:
        from_number = self._slot_from_payload(payload)
        if from_number is not None:
            self._move(from_number, to_number)

    def _on_page_dropped(self, payload: str, page: int) -> None:
        from_number = self._slot_from_payload(payload)
        if from_number is not None:
            self._move_to_page(from_number, page)

    def _move_to_page(self, from_number: int, page: int) -> None:
        to_number = self._store.first_empty_slot(self._category, page)
        if to_number is None:
            return  # that page is full
        self._page = page
        self._move(from_number, to_number)

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
        if self._category == "podcasts":
            # Podcasts don't auto-play the latest episode on click
            # anymore — straight to picking one, since "whatever's
            # newest" often isn't what the user actually wants next.
            self.browse_episodes(number)
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
            browse_action = menu.addAction("Browse Episodes…")
            browse_action.setEnabled(not slot.is_empty)
            browse_action.triggered.connect(lambda: self.browse_episodes(number))

        search_action = menu.addAction("Search for Image…")
        search_action.setEnabled(not slot.is_empty)
        search_action.triggered.connect(lambda: self._search_image(number))

        if slot.image_path:
            remove_action = menu.addAction("Remove Image")
            remove_action.triggered.connect(lambda: self._remove_image(number))

        page_count = self._store.page_count(self._category)
        if not slot.is_empty and page_count > 1:
            move_menu = menu.addMenu("Move to Page")
            for page in range(1, page_count + 1):
                if page == self._page:
                    continue
                full = self._store.first_empty_slot(self._category, page) is None
                action = move_menu.addAction(f"Page {page} (full)" if full else f"Page {page}")
                action.setEnabled(not full)
                action.triggered.connect(lambda _checked=False, p=page: self._move_to_page(number, p))

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
        # the dialog (typing/clicking), so these lambdas always run on the
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

    def browse_episodes(self, number: int) -> None:
        """Open the episode picker for this podcast slot. Public — also
        called from MainWindow for the player bar's "Episodes" button,
        which needs to browse whatever podcast is currently playing
        regardless of which deck tab is showing.
        """
        slot = self._store.slot(self._category, number)
        if slot.is_empty:
            return
        dialog = EpisodeListDialog(slot.label, parent=self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.episode_chosen.connect(lambda episode: self.episode_chosen.emit(number, episode))
        dialog.open()
        feed_url = slot.url
        self._run_in_background(
            lambda: (dialog, recent_episodes(feed_url)),
            self._on_episodes_fetched,
        )

    def _on_episodes_fetched(self, result) -> None:
        dialog, episodes = result
        progress_for = self._episode_progress.get if self._episode_progress else lambda _url: None
        completed_for = (
            self._episode_progress.is_completed if self._episode_progress else lambda _url: False
        )
        entries = [
            EpisodeEntry(episode, progress_for(episode.audio_url), completed_for(episode.audio_url))
            for episode in episodes
        ]
        try:
            dialog.show_episodes(entries)
        except RuntimeError:
            pass  # the user already closed the dialog before results arrived
