from __future__ import annotations

from PySide6.QtCore import QUrl, Qt, QObject, QThread, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import QMainWindow, QTabWidget, QStatusBar

from simple_streamer import __version__
from simple_streamer.core.presets import PresetStore, PresetSlot
from simple_streamer.core.podcasts import latest_episode
from simple_streamer.core.updater import check_for_update, API_TIMEOUT_SECONDS
from simple_streamer.gui.preset_deck import PresetDeckWidget

UPDATE_OWNER = "mikehellyer"
UPDATE_REPO = "simple-streamer"
BACKGROUND_JOIN_TIMEOUT_MS = (API_TIMEOUT_SECONDS + 1) * 1000


class _CallableWorker(QObject):
    """Runs a zero-arg callable on a background thread and emits its result."""

    finished = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        self.finished.emit(self._fn())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Simple-Streamer v{__version__}")
        self.resize(600, 580)

        self._store = PresetStore()
        self._background_threads: list[QThread] = []
        self._background_workers: list[_CallableWorker] = []

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

    def _run_in_background(self, fn, on_finished) -> None:
        """Run fn() off the GUI thread; on_finished(result) runs back on it."""
        thread = QThread()
        worker = _CallableWorker(fn)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(on_finished)
        worker.finished.connect(thread.quit)

        def _cleanup():
            self._background_threads.remove(thread)
            self._background_workers.remove(worker)

        thread.finished.connect(_cleanup)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # Both must be kept referenced from self — nothing else holds a
        # Python reference to worker/thread while the thread runs, and
        # Qt's C++-side connections alone don't stop them being garbage
        # collected mid-flight (the thread then hangs forever waiting on
        # a slot bound to an object that no longer exists).
        self._background_threads.append(thread)
        self._background_workers.append(worker)
        thread.start()

    def _play_slot(self, category: str, number: int) -> None:
        slot = self._store.slot(category, number)
        if slot.is_empty:
            return
        self._active_category = category
        self._active_number = number

        if category == "podcasts":
            self._decks[category].set_now_playing(f"Finding the latest episode of {slot.label}…")
            self._run_in_background(
                lambda: latest_episode(slot.url),
                lambda episode: self._on_episode_resolved(slot, episode),
            )
        else:
            self._start_playback(category, slot.url, slot.label)

    def _on_episode_resolved(self, slot: PresetSlot, episode) -> None:
        if self._active_category != "podcasts" or self._active_number != slot.number:
            return  # the user moved on to something else while this was loading
        if episode is None:
            self._decks["podcasts"].set_now_playing(f"Couldn't load {slot.label} right now")
            return
        self._start_playback("podcasts", episode.audio_url, f"{slot.label} — {episode.title}")

    def _start_playback(self, category: str, url: str, label: str) -> None:
        self._player.setSource(QUrl(url))
        self._player.play()
        self._decks[category].set_now_playing(f"Tuning in: {label}…")

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
        self._run_in_background(
            lambda: check_for_update(__version__, UPDATE_OWNER, UPDATE_REPO),
            self._on_update_checked,
        )

    def _on_update_checked(self, info) -> None:
        if info:
            self.statusBar().showMessage(
                f"Update available: {info.version} — see {info.url}", 10_000
            )

    def closeEvent(self, event) -> None:
        for thread in list(self._background_threads):
            thread.quit()
            thread.wait(BACKGROUND_JOIN_TIMEOUT_MS)
        super().closeEvent(event)
