"""Dialog shown from a podcast preset's "Browse Episodes..." context menu.

Purely presentational, same as the other search/list dialogs in this
app — MainWindow fetches episodes via `_run_in_background` and hands
them to show_episodes(); picking one is immediate (no further network
call needed, unlike the image/station search dialogs), so this closes
itself as soon as a choice is made.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QDialogButtonBox,
)

from simple_streamer.core.episode_progress import EpisodeProgress
from simple_streamer.core.podcasts import Episode
from simple_streamer.core.text import format_duration_ms, format_pub_date


class EpisodeListDialog(QDialog):
    episode_chosen = Signal(object)  # Episode

    def __init__(self, podcast_label: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Episodes — {podcast_label}")
        # Wide enough for a long real-world episode title (many podcasts
        # pack a lot into one) without wrapping mid-word — narrower
        # dialogs made titles wrap awkwardly.
        self.setMinimumSize(640, 420)

        layout = QVBoxLayout(self)
        self._status = QLabel("Loading recent episodes…")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._list = QListWidget()
        self._list.setWordWrap(True)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(lambda _item: self._play_selected())
        layout.addWidget(self._list, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        self._play_button = QPushButton("Play This Episode")
        self._play_button.setEnabled(False)
        self._play_button.clicked.connect(self._play_selected)
        buttons.addButton(self._play_button, QDialogButtonBox.AcceptRole)
        layout.addWidget(buttons)

    def show_episodes(self, episodes: list[tuple[Episode, Optional[EpisodeProgress]]]) -> None:
        self._list.clear()
        if not episodes:
            self._status.setText(
                "Couldn't load episodes for this podcast — check the feed is still online."
            )
            return

        self._status.setText("Pick an episode:")
        for episode, progress in episodes:
            item = QListWidgetItem(self._describe(episode, progress))
            item.setData(Qt.UserRole, episode)
            self._list.addItem(item)
        self._list.setCurrentRow(0)

    @staticmethod
    def _describe(episode: Episode, progress: Optional[EpisodeProgress]) -> str:
        text = episode.title
        meta = []

        date_str = format_pub_date(episode.published)
        if date_str:
            meta.append(date_str)

        if progress and progress.duration_ms > 0:
            percent = round(progress.position_ms / progress.duration_ms * 100)
            meta.append(
                f"resume at {format_duration_ms(progress.position_ms)} of "
                f"{format_duration_ms(progress.duration_ms)} ({percent}%)"
            )
        elif episode.duration_seconds:
            meta.append(format_duration_ms(episode.duration_seconds * 1000))

        if meta:
            text += "\n" + " · ".join(meta)
        return text

    def _on_selection_changed(self) -> None:
        self._play_button.setEnabled(bool(self._list.selectedItems()))

    def _play_selected(self) -> None:
        items = self._list.selectedItems()
        if not items:
            return
        episode = items[0].data(Qt.UserRole)
        self.episode_chosen.emit(episode)
        self.accept()
