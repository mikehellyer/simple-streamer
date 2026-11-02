"""The Schedule editor: a list of schedule items, and the dialog for one item.

Edits happen on a copy of the items; nothing is saved until the editor's
Save button (MainWindow picks the result up via result_items()). Both
dialogs are shown with open(), not exec(), for the same nested-event-loop
reason as PresetDeckWidget._assign_slot.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from simple_streamer.core.presets import PresetStore
from simple_streamer.core.schedule import (
    DAY_NAMES,
    WEEKDAYS,
    WEEKEND,
    ScheduleItem,
    describe_days,
    sorted_items,
)

CATEGORY_NAMES = {"radio": "Radio", "podcasts": "Podcast"}


@dataclass(frozen=True)
class PresetChoice:
    category: str
    label: str
    url: str

    @property
    def text(self) -> str:
        return f"{CATEGORY_NAMES[self.category]} · {self.label}"


def preset_choices(store: PresetStore) -> list[PresetChoice]:
    choices = []
    for category in ("radio", "podcasts"):
        for slot in store.deck(category):
            if not slot.is_empty:
                choices.append(PresetChoice(category, slot.label or slot.url, slot.url))
    return choices


def _to_qtime(hhmm: str, fallback: str) -> QTime:
    time = QTime.fromString(hhmm or fallback, "HH:mm")
    return time if time.isValid() else QTime.fromString(fallback, "HH:mm")


class ScheduleItemDialog(QDialog):
    def __init__(self, item: ScheduleItem | None, choices: list[PresetChoice], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Schedule Item" if item else "Add Schedule Item")
        self.setMinimumWidth(460)
        self._item = item

        days_row = QHBoxLayout()
        self._day_boxes = []
        for index, name in enumerate(DAY_NAMES):
            box = QCheckBox(name)
            box.setChecked(item is not None and index in item.days)
            self._day_boxes.append(box)
            days_row.addWidget(box)
        shortcuts = QHBoxLayout()
        for text, days in (("Weekdays", WEEKDAYS), ("Weekend", WEEKEND), ("Every day", range(7))):
            button = QPushButton(text)
            button.setAutoDefault(False)
            button.clicked.connect(lambda _checked=False, d=tuple(days): self._set_days(d))
            shortcuts.addWidget(button)
        shortcuts.addStretch(1)

        self._preset = QComboBox()
        self._choices = list(choices)
        if item is not None and not any(c.url == item.url for c in self._choices):
            # Its preset has since been deleted — keep it selectable
            # rather than silently switching the item to something else.
            self._choices.insert(0, PresetChoice(item.category, f"{item.label} (not in presets)", item.url))
        for choice in self._choices:
            self._preset.addItem(choice.text)
        if item is not None:
            self._preset.setCurrentIndex(next(i for i, c in enumerate(self._choices) if c.url == item.url))
        self._preset.currentIndexChanged.connect(self._sync_end_time)

        self._start = QTimeEdit(_to_qtime(item.start if item else "", "09:00"))
        self._start.setDisplayFormat("HH:mm")
        self._end = QTimeEdit(_to_qtime(item.end if item else "", "10:00"))
        self._end.setDisplayFormat("HH:mm")
        self._end_note = QLabel("Plays the newest episode you haven't finished, then back to the radio.")
        self._end_note.setWordWrap(True)
        self._end_note.setStyleSheet("color: gray;")
        self._note = QLineEdit(item.note if item else "")
        self._note.setPlaceholderText("e.g. Lauren Laverne  (optional)")
        self._enabled = QCheckBox("Include this in the schedule")
        self._enabled.setChecked(item.enabled if item else True)

        days_widget = QWidget()
        days_layout = QVBoxLayout(days_widget)
        days_layout.setContentsMargins(0, 0, 0, 0)
        days_layout.addLayout(days_row)
        days_layout.addLayout(shortcuts)

        form = QFormLayout()
        form.addRow("Days:", days_widget)
        form.addRow("Plays:", self._preset)
        form.addRow("Starts:", self._start)
        self._end_label = QLabel("Ends:")
        form.addRow(self._end_label, self._end)
        form.addRow("", self._end_note)
        form.addRow("Note:", self._note)
        form.addRow("", self._enabled)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        if not self._choices:
            layout.addWidget(QLabel("Add some presets first — schedule items play a preset."))
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._sync_end_time()
        self._result: ScheduleItem | None = None

    def _set_days(self, days) -> None:
        for index, box in enumerate(self._day_boxes):
            box.setChecked(index in days)

    def _current_choice(self) -> PresetChoice | None:
        index = self._preset.currentIndex()
        return self._choices[index] if 0 <= index < len(self._choices) else None

    def _sync_end_time(self) -> None:
        choice = self._current_choice()
        is_podcast = choice is not None and choice.category == "podcasts"
        self._end.setVisible(not is_podcast)
        self._end_label.setVisible(not is_podcast)
        self._end_note.setVisible(is_podcast)

    def _on_save(self) -> None:
        choice = self._current_choice()
        item = ScheduleItem(
            days=[i for i, box in enumerate(self._day_boxes) if box.isChecked()],
            start=self._start.time().toString("HH:mm"),
            category=choice.category if choice else "",
            label=choice.label.removesuffix(" (not in presets)") if choice else "",
            url=choice.url if choice else "",
            end="" if choice and choice.category == "podcasts" else self._end.time().toString("HH:mm"),
            note=self._note.text().strip(),
            enabled=self._enabled.isChecked(),
        )
        if self._item is not None:
            item.id = self._item.id
        try:
            item.validate()
        except ValueError as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return
        self._result = item
        self.accept()

    def result_item(self) -> ScheduleItem | None:
        return self._result


class ScheduleDialog(QDialog):
    COLUMNS = ("On", "Days", "Time", "Plays", "Note")

    def __init__(self, items: list[ScheduleItem], store: PresetStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Schedule")
        self.resize(820, 480)
        self._items = copy.deepcopy(items)
        self._store = store

        intro = QLabel(
            "When the schedule is switched on (Schedule menu), these play automatically."
            " Where items overlap, the one that started most recently wins — so a 2pm"
            " podcast takes over from the afternoon music, which resumes when it ends."
        )
        intro.setWordWrap(True)

        self._table = QTableWidget(0, len(self.COLUMNS))
        self._table.setHorizontalHeaderLabels(self.COLUMNS)
        self._table.verticalHeader().hide()
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.cellDoubleClicked.connect(lambda row, _col: self._edit(row))

        add = QPushButton("Add…")
        add.clicked.connect(lambda: self._open_item_dialog(None))
        self._edit_button = QPushButton("Edit…")
        self._edit_button.clicked.connect(lambda: self._edit(self._table.currentRow()))
        self._remove_button = QPushButton("Remove")
        self._remove_button.clicked.connect(self._remove)
        for button in (add, self._edit_button, self._remove_button):
            button.setAutoDefault(False)
        row_buttons = QHBoxLayout()
        row_buttons.addWidget(add)
        row_buttons.addWidget(self._edit_button)
        row_buttons.addWidget(self._remove_button)
        row_buttons.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self._table)
        layout.addLayout(row_buttons)
        layout.addWidget(buttons)

        self._table.itemSelectionChanged.connect(self._sync_buttons)
        self._refresh()

    def result_items(self) -> list[ScheduleItem]:
        return self._items

    def _refresh(self) -> None:
        self._table.blockSignals(True)
        self._items = sorted_items(self._items)
        self._table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            on = QTableWidgetItem()
            on.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            on.setCheckState(Qt.Checked if item.enabled else Qt.Unchecked)
            time = f"{item.start}–{item.end}" if item.category == "radio" else f"{item.start} (episode)"
            plays = f"{CATEGORY_NAMES[item.category]} · {item.label}"
            cells = [on, QTableWidgetItem(describe_days(item.days)), QTableWidgetItem(time),
                     QTableWidgetItem(plays), QTableWidgetItem(item.note)]
            for column, cell in enumerate(cells):
                self._table.setItem(row, column, cell)
        self._table.blockSignals(False)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        has_row = self._table.currentRow() >= 0 and bool(self._table.selectedItems())
        self._edit_button.setEnabled(has_row)
        self._remove_button.setEnabled(has_row)

    def _on_item_changed(self, cell: QTableWidgetItem) -> None:
        if cell.column() == 0:
            self._items[cell.row()].enabled = cell.checkState() == Qt.Checked

    def _edit(self, row: int) -> None:
        if 0 <= row < len(self._items):
            self._open_item_dialog(self._items[row])

    def _open_item_dialog(self, item: ScheduleItem | None) -> None:
        dialog = ScheduleItemDialog(item, preset_choices(self._store), parent=self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.accepted.connect(lambda: self._on_item_saved(item, dialog.result_item()))
        dialog.open()

    def _on_item_saved(self, original: ScheduleItem | None, saved: ScheduleItem | None) -> None:
        if saved is None:
            return
        if original is None:
            self._items.append(saved)
        else:
            self._items[self._items.index(original)] = saved
        self._refresh()

    def _remove(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._items):
            del self._items[row]
            self._refresh()
