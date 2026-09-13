from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QUrl, Qt, QObject, QThread, Signal
from PySide6.QtGui import QKeyEvent, QIcon, QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QStatusBar,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
)

from simple_streamer import __version__
from simple_streamer.core.presets import PresetStore, PresetSlot
from simple_streamer.core.podcasts import latest_episode
from simple_streamer.core.pls_resolver import resolve_pls
from simple_streamer.core.icy_metadata import IcyMetadataListener
from simple_streamer.core.updater import check_for_update, API_TIMEOUT_SECONDS
from simple_streamer.gui.preset_deck import PresetDeckWidget

UPDATE_OWNER = "mikehellyer"
UPDATE_REPO = "simple-streamer"
BACKGROUND_JOIN_TIMEOUT_MS = (API_TIMEOUT_SECONDS + 1) * 1000
ICON_PATH = Path(__file__).parent / "resources" / "icon.png"


class _CallableWorker(QObject):
    """Runs a zero-arg callable on a background thread and emits its result."""

    finished = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        self.finished.emit(self._fn())


class _IcySignalBridge(QObject):
    """Lets IcyMetadataListener (plain threading, no Qt affinity) hand a
    title back to the GUI thread safely — emitting a signal is thread-safe
    even though calling a widget method directly from another thread isn't.
    """

    title_changed = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Simple-Streamer v{__version__}")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
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
            deck.stop_requested.connect(self._stop_playback)
            self._tabs.addTab(deck, title)
            self._decks[category] = deck

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 4)
        logo = QLabel()
        logo.setPixmap(
            QPixmap(str(ICON_PATH)).scaled(
                32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )
        header_layout.addWidget(logo)
        wordmark = QLabel("Simple-Streamer")
        wordmark.setStyleSheet("font-size: 18px; font-weight: 700;")
        header_layout.addWidget(wordmark)
        header_layout.addStretch(1)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(header)
        central_layout.addWidget(self._tabs)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())

        self._active_category = "radio"
        self._active_number: int | None = None
        self._now_playing_detail: str | None = None
        self._icy_listener: IcyMetadataListener | None = None
        self._icy_bridge = _IcySignalBridge()
        self._icy_bridge.title_changed.connect(self._on_icy_title)

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

        self._stop_icy_listener()
        self._now_playing_detail = None
        for deck in self._decks.values():
            deck.set_loading(False)

        self._active_category = category
        self._active_number = number
        self._decks[category].set_loading(True)

        if category == "podcasts":
            self._decks[category].set_now_playing(f"Finding the latest episode of {slot.label}…")
            self._run_in_background(
                lambda: latest_episode(slot.url),
                lambda episode: self._on_episode_resolved(slot, episode),
            )
        elif urlparse(slot.url).path.endswith(".pls"):
            # A handful of stations (Planet Rock) hand out a .pls redirector
            # with a short-lived signed URL inside instead of a stable
            # stream link, so it has to be re-resolved on every play.
            self._decks[category].set_now_playing(f"Tuning in: {slot.label}…")
            self._run_in_background(
                lambda: resolve_pls(slot.url),
                lambda resolved_url: self._on_pls_resolved(category, slot, resolved_url),
            )
        else:
            self._start_playback(category, slot.url, slot.label)

    def _on_episode_resolved(self, slot: PresetSlot, episode) -> None:
        if self._active_category != "podcasts" or self._active_number != slot.number:
            return  # the user moved on to something else while this was loading
        if episode is None:
            self._decks["podcasts"].set_now_playing(f"Couldn't load {slot.label} right now")
            self._decks["podcasts"].set_loading(False)
            return
        self._now_playing_detail = episode.title
        self._start_playback("podcasts", episode.audio_url, slot.label)

    def _on_pls_resolved(self, category: str, slot: PresetSlot, resolved_url: str | None) -> None:
        if self._active_category != category or self._active_number != slot.number:
            return  # the user moved on to something else while this was loading
        if resolved_url is None:
            self._decks[category].set_now_playing(f"Couldn't load {slot.label} right now")
            self._decks[category].set_loading(False)
            return
        self._start_playback(category, resolved_url, slot.label)

    def _start_playback(self, category: str, url: str, label: str) -> None:
        self._player.setSource(QUrl(url))
        self._player.play()
        self._decks[category].set_now_playing(f"Tuning in: {label}…")
        if category == "radio":
            self._icy_listener = IcyMetadataListener(url, self._icy_bridge.title_changed.emit)
            self._icy_listener.start()

    def _stop_icy_listener(self) -> None:
        if self._icy_listener is not None:
            self._icy_listener.stop()
            self._icy_listener = None

    def _on_icy_title(self, title: str) -> None:
        if self._active_category != "radio" or self._active_number is None:
            return  # a stale title from a station we've since moved away from
        self._now_playing_detail = title
        self._refresh_now_playing()

    def _refresh_now_playing(self) -> None:
        slot = self._store.slot(self._active_category, self._active_number)
        deck = self._decks[self._active_category]
        if self._now_playing_detail:
            deck.set_now_playing(f"Now playing: {slot.label} — {self._now_playing_detail}")
        else:
            deck.set_now_playing(f"Now playing: {slot.label}")

    def _stop_playback(self) -> None:
        self._player.stop()
        self._stop_icy_listener()
        self._now_playing_detail = None
        if self._active_number is not None:
            self._decks[self._active_category].set_now_playing("Nothing playing")
            self._decks[self._active_category].set_loading(False)
        # Clearing this also invalidates any podcast/pls resolution still in
        # flight (see the guards above), so it won't start playing
        # something after the user asked for silence.
        self._active_number = None

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if self._active_number is None:
            return
        deck = self._decks[self._active_category]
        if state == QMediaPlayer.PlayingState:
            deck.set_loading(False)
            self._refresh_now_playing()
        elif state == QMediaPlayer.StoppedState:
            deck.set_loading(False)
            deck.set_now_playing("Nothing playing")

    def _on_player_error(self, error, error_string: str) -> None:
        if self._active_number is None:
            return
        deck = self._decks[self._active_category]
        deck.set_loading(False)
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
        self._stop_icy_listener()
        for thread in list(self._background_threads):
            thread.quit()
            thread.wait(BACKGROUND_JOIN_TIMEOUT_MS)
        super().closeEvent(event)
