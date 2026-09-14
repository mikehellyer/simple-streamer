from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QUrl, Qt, QObject, QThread, Signal, QTimer
from PySide6.QtGui import QKeyEvent, QIcon, QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudioBufferOutput
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
from simple_streamer.core.presets import PresetStore
from simple_streamer.core.podcasts import latest_episode
from simple_streamer.core.pls_resolver import resolve_pls
from simple_streamer.core.icy_metadata import IcyMetadataListener
from simple_streamer.core.bbc_nowplaying import bbc_service_id_from_url
from simple_streamer.core.updater import check_for_update, API_TIMEOUT_SECONDS
from simple_streamer.core.self_update import (
    find_asset_for_this_platform,
    download_asset,
    launch_installer,
)
from simple_streamer.gui.preset_deck import PresetDeckWidget
from simple_streamer.gui.player_bar import PlayerBar
from simple_streamer.gui.update_banner import UpdateBanner
from simple_streamer.gui.audio_visualizer import StereoVisualizer
from simple_streamer.gui.bbc_now_playing_poller import BbcNowPlayingPoller

UPDATE_OWNER = "mikehellyer"
UPDATE_REPO = "simple-streamer"
BACKGROUND_JOIN_TIMEOUT_MS = (API_TIMEOUT_SECONDS + 1) * 1000
ICON_PATH = Path(__file__).parent / "resources" / "icon.png"
WORDMARK_PATH = Path(__file__).parent / "resources" / "wordmark.png"


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
        self.resize(1120, 580)

        self._store = PresetStore()
        self._background_threads: list[QThread] = []
        self._background_workers: list[_CallableWorker] = []

        self._audio_output = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.errorOccurred.connect(self._on_player_error)

        self._visualizer = StereoVisualizer()
        self._audio_buffer_output = QAudioBufferOutput()
        self._player.setAudioBufferOutput(self._audio_buffer_output)
        self._audio_buffer_output.audioBufferReceived.connect(self._visualizer.feed_buffer)

        self._tabs = QTabWidget()
        self._decks: dict[str, PresetDeckWidget] = {}
        for category, title in (("radio", "Radio"), ("podcasts", "Podcasts")):
            deck = PresetDeckWidget(category, self._store, self._run_in_background)
            deck.slot_activated.connect(self._play_slot)
            self._tabs.addTab(deck, title)
            self._decks[category] = deck

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 4)
        wordmark = QLabel()
        wordmark.setPixmap(
            QPixmap(str(WORDMARK_PATH)).scaledToHeight(
                80, Qt.SmoothTransformation
            )
        )
        header_layout.addWidget(wordmark)
        header_layout.addWidget(self._visualizer, stretch=1)

        self._update_banner = UpdateBanner()
        self._update_banner.update_clicked.connect(self._start_update)

        self._player_bar = PlayerBar()
        self._player_bar.stop_requested.connect(self._stop_playback)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(8)
        central_layout.addWidget(header)
        central_layout.addWidget(self._update_banner)
        central_layout.addWidget(self._player_bar)
        central_layout.addWidget(self._tabs)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())

        self._active_category = "radio"
        self._active_number: int | None = None
        self._now_playing_detail: str | None = None
        # A "play" bumps this; any resolve/error callback that arrives after
        # a newer play or an explicit stop checks its own captured attempt
        # number against this and quietly no-ops if it's stale.
        self._playback_attempt = 0
        self._remaining_candidates: list[str] = []
        self._current_attempt_for_player = -1
        self._icy_listener: IcyMetadataListener | None = None
        self._icy_bridge = _IcySignalBridge()
        self._icy_bridge.title_changed.connect(self._on_icy_title)
        self._bbc_poller = BbcNowPlayingPoller(self._run_in_background)
        self._bbc_poller.title_changed.connect(self._on_bbc_title)
        self._pending_update = None

        self._check_for_updates()

    def _current_deck(self) -> PresetDeckWidget:
        return self._tabs.currentWidget()

    def _run_in_background(self, fn, on_finished) -> None:
        """Run fn() off the GUI thread; on_finished(result) runs back on it."""
        thread = QThread()
        worker = _CallableWorker(fn)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # Explicit QueuedConnection, not Auto: Auto only recognizes it needs
        # to marshal onto the receiver's thread when the receiver is a
        # QObject method, since that's how it looks up thread affinity. A
        # plain lambda has no such receiver, so Auto runs it directly on
        # this worker thread instead — harmless for a callback that only
        # mutates existing widgets, but fatal the moment one constructs a
        # new widget (macOS aborts outright: "NSWindow should only be
        # instantiated on the main thread!").
        worker.finished.connect(on_finished, Qt.QueuedConnection)
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

        self._stop_metadata_watchers()
        self._now_playing_detail = None
        self._visualizer.clear()
        self._active_category = category
        self._active_number = number
        self._playback_attempt += 1
        self._player_bar.set_loading(True)
        self._player_bar.set_website(slot.website)
        self._remaining_candidates = [slot.url] + [u for u in slot.fallback_urls if u]
        self._try_next_candidate(self._playback_attempt)

    def _try_next_candidate(self, attempt: int) -> None:
        if attempt != self._playback_attempt:
            return  # superseded by a newer play or an explicit stop

        if not self._remaining_candidates:
            slot = self._store.slot(self._active_category, self._active_number)
            self._player_bar.set_now_playing(f"Couldn't play {slot.label} — no working source")
            self._player_bar.set_loading(False)
            self._visualizer.clear()
            return

        url = self._remaining_candidates.pop(0)
        category = self._active_category
        slot = self._store.slot(category, self._active_number)

        if category == "podcasts":
            self._player_bar.set_now_playing(f"Finding the latest episode of {slot.label}…")
            self._run_in_background(
                lambda: latest_episode(url),
                lambda episode: self._on_episode_resolved(attempt, episode),
            )
        elif urlparse(url).path.endswith(".pls"):
            # A handful of stations (Planet Rock) hand out a .pls redirector
            # with a short-lived signed URL inside instead of a stable
            # stream link, so it has to be re-resolved on every play.
            self._player_bar.set_now_playing(f"Tuning in: {slot.label}…")
            self._run_in_background(
                lambda: resolve_pls(url),
                lambda resolved_url: self._on_pls_resolved(attempt, resolved_url),
            )
        else:
            self._start_playback(category, url, slot.label, attempt)

    def _on_episode_resolved(self, attempt: int, episode) -> None:
        if attempt != self._playback_attempt:
            return  # the user moved on to something else while this was loading
        if episode is None:
            self._try_next_candidate(attempt)
            return
        self._now_playing_detail = episode.title
        slot = self._store.slot(self._active_category, self._active_number)
        self._start_playback("podcasts", episode.audio_url, slot.label, attempt)

    def _on_pls_resolved(self, attempt: int, resolved_url: str | None) -> None:
        if attempt != self._playback_attempt:
            return  # the user moved on to something else while this was loading
        if resolved_url is None:
            self._try_next_candidate(attempt)
            return
        slot = self._store.slot(self._active_category, self._active_number)
        self._start_playback(self._active_category, resolved_url, slot.label, attempt)

    def _start_playback(self, category: str, url: str, label: str, attempt: int) -> None:
        self._current_attempt_for_player = attempt
        self._player.setSource(QUrl(url))
        self._player.play()
        self._player_bar.set_now_playing(f"Tuning in: {label}…")
        if category == "radio":
            bbc_service_id = bbc_service_id_from_url(url)
            if bbc_service_id:
                # BBC's streams are HLS — no ICY tags to read, so this
                # polls BBC's own now-playing API instead (see
                # gui/bbc_now_playing_poller.py).
                self._bbc_poller.start(bbc_service_id)
            else:
                self._icy_listener = IcyMetadataListener(url, self._icy_bridge.title_changed.emit)
                self._icy_listener.start()

    def _stop_metadata_watchers(self) -> None:
        if self._icy_listener is not None:
            self._icy_listener.stop()
            self._icy_listener = None
        self._bbc_poller.stop()

    def _on_icy_title(self, title: str) -> None:
        if self._active_category != "radio" or self._active_number is None:
            return  # a stale title from a station we've since moved away from
        self._now_playing_detail = title
        self._refresh_now_playing()

    def _on_bbc_title(self, title: str) -> None:
        if self._active_category != "radio" or self._active_number is None:
            return  # a stale title from a station we've since moved away from
        self._now_playing_detail = title
        self._refresh_now_playing()

    def _refresh_now_playing(self) -> None:
        slot = self._store.slot(self._active_category, self._active_number)
        if self._now_playing_detail:
            self._player_bar.set_now_playing(f"Now playing: {slot.label} — {self._now_playing_detail}")
        else:
            self._player_bar.set_now_playing(f"Now playing: {slot.label}")

    def _stop_playback(self) -> None:
        self._player.stop()
        self._stop_metadata_watchers()
        self._now_playing_detail = None
        self._visualizer.clear()
        # Bumping this invalidates any resolve/error callback still in
        # flight for the old attempt (see the guards in each), so it won't
        # start playing — or try a fallback — after the user asked for
        # silence.
        self._playback_attempt += 1
        self._remaining_candidates = []
        if self._active_number is not None:
            self._player_bar.set_now_playing("Nothing playing")
            self._player_bar.set_loading(False)
            self._player_bar.set_website("")
        self._active_number = None

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if self._active_number is None:
            return
        if state == QMediaPlayer.PlayingState:
            self._player_bar.set_loading(False)
            self._refresh_now_playing()
        # StoppedState is deliberately not handled here: it fires for many
        # reasons (user stop, a failed source, switching to the next
        # fallback candidate) and _stop_playback()/_on_player_error()
        # already set the right message for the cases that matter — an
        # unconditional "Nothing playing" here could overwrite a fallback
        # attempt that's already under way.

    def _on_player_error(self, error, error_string: str) -> None:
        if self._active_number is None:
            return
        if self._current_attempt_for_player != self._playback_attempt:
            return  # a stale error from a source we've already moved on from
        self._visualizer.clear()
        if self._remaining_candidates:
            self._try_next_candidate(self._playback_attempt)
        else:
            slot = self._store.slot(self._active_category, self._active_number)
            self._player_bar.set_loading(False)
            self._player_bar.set_now_playing(f"Couldn't play {slot.label} — no working source")

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
            self._pending_update = info
            self._update_banner.announce(info.version)

    def _start_update(self) -> None:
        if self._pending_update is None:
            return
        asset_url = find_asset_for_this_platform(self._pending_update.assets)
        if asset_url is None:
            self._update_banner.set_status(
                f"No installer for this platform — see {self._pending_update.url}"
            )
            return

        self._update_banner.set_busy(True, "Downloading…")
        self._run_in_background(
            lambda: download_asset(asset_url),
            self._on_update_downloaded,
        )

    def _on_update_downloaded(self, path) -> None:
        if path is None:
            self._update_banner.set_status("Couldn't download the update — try again")
            self._update_banner.set_busy(False)
            return

        if launch_installer(path):
            self._update_banner.set_status("Installer launched — closing to finish…")
            QTimer.singleShot(1500, self.close)
        else:
            self._update_banner.set_status(f"Downloaded to {path} — open it manually")
            self._update_banner.set_busy(False)

    def closeEvent(self, event) -> None:
        self._stop_metadata_watchers()
        for thread in list(self._background_threads):
            thread.quit()
            thread.wait(BACKGROUND_JOIN_TIMEOUT_MS)
        super().closeEvent(event)
