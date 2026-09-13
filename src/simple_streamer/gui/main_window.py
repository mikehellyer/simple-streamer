from __future__ import annotations

from PySide6.QtCore import QUrl, Qt, QObject, QThread, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import QMainWindow, QTabWidget, QStatusBar

from simple_streamer import __version__
from simple_streamer.core.presets import PresetStore
from simple_streamer.core.updater import check_for_update, API_TIMEOUT_SECONDS
from simple_streamer.gui.preset_deck import PresetDeckWidget

UPDATE_OWNER = "mikehellyer"
UPDATE_REPO = "simple-streamer"


class _UpdateCheckWorker(QObject):
    finished = Signal(object)  # UpdateInfo | None

    def __init__(self, version: str, owner: str, repo: str):
        super().__init__()
        self._version = version
        self._owner = owner
        self._repo = repo

    def run(self) -> None:
        self.finished.emit(check_for_update(self._version, self._owner, self._repo))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Simple-Streamer v{__version__}")
        self.resize(560, 420)

        self._store = PresetStore()

        self._audio_output = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.errorOccurred.connect(self._on_player_error)

        self._tabs = QTabWidget()
        self._decks: dict[str, PresetDeckWidget] = {}
        for category, title in (("radio", "Radio"), ("podcasts", "Podcasts")):
            deck = PresetDeckWidget(category, self._store)
            deck.slot_activated.connect(self._play_slot)
            self._tabs.addTab(deck, title)
            self._decks[category] = deck
        self.setCentralWidget(self._tabs)

        self.setStatusBar(QStatusBar())
        self._active_category = "radio"
        self._active_number: int | None = None

        self._check_for_updates()

    def _current_deck(self) -> PresetDeckWidget:
        return self._tabs.currentWidget()

    def _play_slot(self, category: str, number: int) -> None:
        slot = self._store.slot(category, number)
        if slot.is_empty:
            return
        self._active_category = category
        self._active_number = number
        self._player.setSource(QUrl(slot.url))
        self._player.play()
        self._decks[category].set_now_playing(f"Tuning in: {slot.label}…")

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if self._active_number is None:
            return
        slot = self._store.slot(self._active_category, self._active_number)
        deck = self._decks[self._active_category]
        if state == QMediaPlayer.PlayingState:
            deck.set_now_playing(f"Now playing: {slot.label}")
        elif state == QMediaPlayer.StoppedState:
            deck.set_now_playing("Nothing playing")

    def _on_player_error(self, error, error_string: str) -> None:
        if self._active_number is None:
            return
        deck = self._decks[self._active_category]
        deck.set_now_playing(f"Couldn't play that stream: {error_string}")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_F1 and not event.isAutoRepeat():
            self._current_deck().show_legend(True)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_F1 and not event.isAutoRepeat():
            self._current_deck().show_legend(False)
            return
        super().keyReleaseEvent(event)

    def _check_for_updates(self) -> None:
        self._update_thread = QThread()
        self._update_worker = _UpdateCheckWorker(__version__, UPDATE_OWNER, UPDATE_REPO)
        self._update_worker.moveToThread(self._update_thread)
        self._update_thread.started.connect(self._update_worker.run)
        self._update_worker.finished.connect(self._on_update_checked)
        self._update_worker.finished.connect(self._update_thread.quit)
        self._update_thread.start()

    def _on_update_checked(self, info) -> None:
        if info:
            self.statusBar().showMessage(
                f"Update available: {info.version} — see {info.url}", 10_000
            )

    def closeEvent(self, event) -> None:
        thread = getattr(self, "_update_thread", None)
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait((API_TIMEOUT_SECONDS + 1) * 1000)
        super().closeEvent(event)
