"""The dialog for assigning or editing one preset slot.

Name and the stream/feed URL are required; website and fallback URLs
are optional. A "Clear this slot" button empties the preset entirely —
exposed here via a custom QDialog.done() code since exec() otherwise
only distinguishes Accepted/Rejected.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QVBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QDialogButtonBox,
    QPushButton,
)

from simple_streamer.core.presets import PresetSlot

CLEARED = 2  # a QDialog.done() result code distinct from Accepted(1)/Rejected(0)


class PresetEditorDialog(QDialog):
    def __init__(self, category: str, slot: PresetSlot, parent=None):
        super().__init__(parent)
        is_podcast = category == "podcasts"
        kind = "podcast" if is_podcast else "station"
        self.setWindowTitle(f"Edit {kind} — slot {slot.number}")
        self.setMinimumWidth(420)

        self._name = QLineEdit(slot.label)
        self._website = QLineEdit(slot.website)
        self._website.setPlaceholderText("https://…  (optional)")
        self._url = QLineEdit(slot.url)
        self._fallbacks = QPlainTextEdit("\n".join(slot.fallback_urls))
        self._fallbacks.setPlaceholderText(
            "One URL per line (optional) — tried in order if the main one fails"
        )
        self._fallbacks.setFixedHeight(70)

        form = QFormLayout()
        form.addRow("Name:", self._name)
        form.addRow("Website:", self._website)
        form.addRow("RSS feed URL:" if is_podcast else "Stream URL:", self._url)
        form.addRow("Fallback URLs:", self._fallbacks)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        clear_button = QPushButton("Clear this slot")
        clear_button.clicked.connect(lambda: self.done(CLEARED))
        buttons.addButton(clear_button, QDialogButtonBox.DestructiveRole)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        if not self._name.text().strip() or not self._url.text().strip():
            return  # both required — leave the dialog open rather than save a broken preset
        self.accept()

    def result_data(self) -> dict:
        fallback_urls = [
            line.strip() for line in self._fallbacks.toPlainText().splitlines() if line.strip()
        ]
        return {
            "label": self._name.text().strip(),
            "url": self._url.text().strip(),
            "website": self._website.text().strip(),
            "fallback_urls": fallback_urls,
        }
