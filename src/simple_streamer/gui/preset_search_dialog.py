"""Dialog shown from a preset's "Find New Station..."/"Find New Podcast..."
context menu.

Purely presentational, same as ImageSearchDialog — PresetDeckWidget owns
every background network call via MainWindow's `_run_in_background` and
feeds results back in via show_results(). Emits plain signals for the
two things that need a network call (searching, and fetching the
chosen result's artwork) rather than doing either itself.

Radio (core/station_search.py) and podcasts (core/podcast_search.py)
are two different APIs with differently-named fields, but the dialog
itself only ever needs a result's `.name` and `.description` to
display it and hands the object straight back opaquely — so one
dialog, parametrized by `kind`, serves both instead of two
near-identical copies.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QDialogButtonBox,
)

_WORDING = {
    "station": {
        "title": "Find New Station",
        "placeholder": "e.g. old time radio, jazz, BBC…",
        "initial_hint": "Search for a station by name or genre, e.g. “old time radio”.",
        "noun": "station",
    },
    "podcast": {
        "title": "Find New Podcast",
        "placeholder": "e.g. true crime, comedy, news…",
        "initial_hint": "Search for a podcast by name or topic, e.g. “true crime”.",
        "noun": "podcast",
    },
}


class PresetSearchDialog(QDialog):
    search_requested = Signal(str)
    result_chosen = Signal(object)

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        wording = _WORDING[kind]
        self._noun = wording["noun"]
        self.setWindowTitle(wording["title"])
        self.setMinimumSize(480, 420)

        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText(wording["placeholder"])
        self._query.returnPressed.connect(self._trigger_search)
        search_row.addWidget(self._query, stretch=1)
        self._search_button = QPushButton("Search")
        self._search_button.clicked.connect(self._trigger_search)
        search_row.addWidget(self._search_button)
        layout.addLayout(search_row)

        self._status = QLabel(wording["initial_hint"])
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._list = QListWidget()
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(lambda _item: self._use_selected())
        layout.addWidget(self._list, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        self._use_button = QPushButton(f"Use This {self._noun.capitalize()}")
        self._use_button.setEnabled(False)
        self._use_button.clicked.connect(self._use_selected)
        buttons.addButton(self._use_button, QDialogButtonBox.AcceptRole)
        layout.addWidget(buttons)

    def _trigger_search(self) -> None:
        query = self._query.text().strip()
        if not query:
            return
        self._list.clear()
        self._use_button.setEnabled(False)
        self._status.setText(f"Searching for “{query}”…")
        self._search_button.setEnabled(False)
        self.search_requested.emit(query)

    def show_results(self, results: list) -> None:
        self._search_button.setEnabled(True)
        self._list.clear()
        if not results:
            self._status.setText(f"No {self._noun}s found. Try a different search term.")
            return

        self._status.setText(f"Found {len(results)} {self._noun}(s) — pick one:")
        for result in results:
            text = result.name
            if result.description:
                text += f"\n{result.description}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, result)
            self._list.addItem(item)

    def _on_selection_changed(self) -> None:
        self._use_button.setEnabled(bool(self._list.selectedItems()))

    def _use_selected(self) -> None:
        items = self._list.selectedItems()
        if not items:
            return
        result = items[0].data(Qt.UserRole)
        self._status.setText(f"Adding “{result.name}”…")
        self._use_button.setEnabled(False)
        self._search_button.setEnabled(False)
        self._query.setEnabled(False)
        self._list.setEnabled(False)
        self.result_chosen.emit(result)
