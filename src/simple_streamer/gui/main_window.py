from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QUrl, Qt, QObject, Signal, QTimer
from PySide6.QtGui import QKeyEvent, QIcon, QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudioBufferOutput, QtAudio
from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QStatusBar,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFileDialog,
    QMessageBox,
)

from simple_streamer import __version__
from simple_streamer.core.presets import PresetStore
from simple_streamer.core.preset_transfer import (
    FILE_EXTENSION as PRESET_FILE_EXTENSION,
    PresetImportError,
    export_presets,
    import_presets,
)
from simple_streamer.core.episode_progress import EpisodeProgressStore
from simple_streamer.core.settings import SettingsStore
from simple_streamer.core.pls_resolver import resolve_pls
from simple_streamer.core.icy_metadata import IcyMetadataListener
from simple_streamer.core.bbc_nowplaying import bbc_service_id_from_url
from simple_streamer.core.podcasts import recent_episodes
from simple_streamer.core.schedule import Occurrence, ScheduleStore, current_item, next_start
from simple_streamer.core.updater import check_for_update, API_TIMEOUT_SECONDS
from simple_streamer.core.self_update import (
    find_asset_for_this_platform,
    download_asset,
    launch_installer,
)
from simple_streamer.gui.preset_deck import PresetDeckWidget
from simple_streamer.gui.player_bar import PlayerBar
from simple_streamer.gui.update_banner import UpdateBanner
from simple_streamer.gui.workers import BackgroundRunner
from simple_streamer.gui.audio_visualizer import StereoVisualizer
from simple_streamer.gui.bbc_now_playing_poller import BbcNowPlayingPoller
from simple_streamer.gui.audio_glow import AudioGlow
from simple_streamer.gui.schedule_editor import ScheduleDialog

PROGRESS_SAVE_INTERVAL_MS = 10_000
SCHEDULE_TICK_MS = 10_000
# The schedule's status-bar note is shortened with "…" past this width,
# so a long note can't stretch the window.
SCHEDULE_LABEL_MAX_WIDTH = 620

UPDATE_OWNER = "mikehellyer"
UPDATE_REPO = "simple-streamer"
BACKGROUND_JOIN_TIMEOUT_MS = (API_TIMEOUT_SECONDS + 1) * 1000
ICON_PATH = Path(__file__).parent / "resources" / "icon.png"
WORDMARK_PATH = Path(__file__).parent / "resources" / "wordmark.png"


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
        self._episode_progress = EpisodeProgressStore()
        self._settings = SettingsStore()
        self._schedule = ScheduleStore()
        self._background = BackgroundRunner(self)

        self._audio_output = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.errorOccurred.connect(self._on_player_error)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.positionChanged.connect(self._on_position_changed)

        self._visualizer = StereoVisualizer()
        self._audio_buffer_output = QAudioBufferOutput()
        self._player.setAudioBufferOutput(self._audio_buffer_output)
        self._audio_buffer_output.audioBufferReceived.connect(self._visualizer.feed_buffer)

        self._tabs = QTabWidget()
        self._decks: dict[str, PresetDeckWidget] = {}
        for category, title in (("radio", "Radio"), ("podcasts", "Podcasts")):
            deck = PresetDeckWidget(category, self._store, self._run_in_background, self._episode_progress)
            deck.slot_activated.connect(self._play_slot)
            deck.episode_chosen.connect(self._play_chosen_episode)
            deck.slots_renumbered.connect(self._on_slots_renumbered)
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
        self._player_bar.play_pause_requested.connect(self._toggle_play_pause)
        self._player_bar.seek_requested.connect(self._seek)
        self._player_bar.episodes_requested.connect(self._browse_episodes)
        self._player_bar.position_seek_requested.connect(self._seek_to)
        self._player_bar.set_volume(self._settings.volume)
        self._apply_volume(self._settings.volume)
        self._player_bar.volume_changed.connect(self._on_volume_changed)
        # The button and the Schedule menu's tick are two views of one
        # switch: the button drives the menu action, whose toggled handler
        # (_on_schedule_toggled) does the work and updates the button.
        self._player_bar.schedule_toggled.connect(
            lambda on: self._schedule_action.setChecked(on)
        )
        # Saved a moment after the slider stops moving, not on every step.
        self._volume_save_timer = QTimer(self)
        self._volume_save_timer.setSingleShot(True)
        self._volume_save_timer.setInterval(500)
        self._volume_save_timer.timeout.connect(
            lambda: self._settings.set_volume(self._player_bar_volume)
        )
        self._player_bar_volume = self._settings.volume

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(8)
        central_layout.addWidget(header)
        central_layout.addWidget(self._update_banner)
        central_layout.addWidget(self._player_bar)
        central_layout.addWidget(self._tabs)

        self._audio_glow = AudioGlow(central)
        self._audio_glow.set_glow_enabled(self._settings.glow_enabled)
        self.setCentralWidget(self._audio_glow)
        self._visualizer.levels_updated.connect(self._audio_glow.update_levels)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("Export Presets && Schedule…").triggered.connect(self._export_presets)
        file_menu.addAction("Import Presets && Schedule…").triggered.connect(self._import_presets)

        schedule_menu = self.menuBar().addMenu("Schedule")
        # Deliberately not remembered between launches: the schedule is
        # off every time the app starts, until switched on here.
        self._schedule_action = schedule_menu.addAction("Schedule On")
        self._schedule_action.setCheckable(True)
        self._schedule_action.toggled.connect(self._on_schedule_toggled)
        schedule_menu.addAction("Edit Schedule…").triggered.connect(self._edit_schedule)

        view_menu = self.menuBar().addMenu("View")
        self._glow_action = view_menu.addAction("Audio Glow")
        self._glow_action.setCheckable(True)
        self._glow_action.setChecked(self._settings.glow_enabled)
        self._glow_action.toggled.connect(self._on_glow_toggled)

        self.setStatusBar(QStatusBar())
        self._clock_label = QLabel()
        self._clock_label.setStyleSheet("font-family: monospace;")
        # A permanent widget sits on the right of the status bar, separate
        # from the transient left-aligned messages (showMessage() etc.).
        self._schedule_label = QLabel()
        self._schedule_label.setStyleSheet("padding-right: 16px;")
        self._schedule_label.hide()
        self.statusBar().addPermanentWidget(self._schedule_label)
        self.statusBar().addPermanentWidget(self._clock_label)
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

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

        # The currently-loaded podcast episode's audio URL — None for
        # radio (nothing to resume) or when nothing's loaded. Doubles as
        # what periodic saving keys its position/duration snapshot to.
        self._current_episode_audio_url: str | None = None
        # A saved position to jump to once the player has actually loaded
        # whatever it just started — applied on mediaStatusChanged
        # reaching LoadedMedia, not durationChanged, since durationChanged
        # only fires when the duration *value* changes: replaying the
        # same episode again has the same duration as last time, so that
        # signal would never re-fire and the resume would silently do
        # nothing. Every fresh setSource() genuinely transitions through
        # LoadingMedia before LoadedMedia, so that always fires.
        self._pending_resume_ms: int | None = None
        self._progress_save_timer = QTimer(self)
        self._progress_save_timer.timeout.connect(self._save_current_progress)
        self._progress_save_timer.start(PROGRESS_SAVE_INTERVAL_MS)
        self._bbc_poller = BbcNowPlayingPoller(self._run_in_background)
        self._bbc_poller.title_changed.connect(self._on_bbc_title)
        self._pending_update = None

        self._schedule_on = False
        # What the schedule last started (an item's run on a given day), so
        # a tick only acts when that changes — switching station by hand
        # in between is respected until the next scheduled change.
        self._schedule_key: Occurrence | None = None
        # Podcast appointments already heard today: once the episode ends
        # the appointment is over and the scheduled radio takes over again.
        self._schedule_finished: set[Occurrence] = set()
        # (appointment, episode audio URL) while a scheduled episode plays.
        self._schedule_episode: tuple[Occurrence, str] | None = None
        self._schedule_timer = QTimer(self)
        self._schedule_timer.timeout.connect(self._schedule_tick)

        # Open with enough spare height for the update banner, so it can
        # appear later without the window having to grow to fit it (the
        # preset grid gives up the space instead).
        spare = self._update_banner.sizeHint().height() + 8
        self.resize(self.width(), max(self.height(), self.minimumSizeHint().height() + spare))

        self._check_for_updates()

    def _current_deck(self) -> PresetDeckWidget:
        return self._tabs.currentWidget()

    def _run_in_background(self, fn, on_finished) -> None:
        """Run fn() off the GUI thread; on_finished(result) runs back on it."""
        self._background.run(fn, on_finished)

    def _play_slot(self, category: str, number: int) -> None:
        slot = self._store.slot(category, number)
        if slot.is_empty:
            return

        self._save_current_progress()
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

        # Only ever radio here — clicking a podcast preset goes straight
        # to the episode picker (PresetDeckWidget.browse_episodes) rather
        # than emitting slot_activated at all, so this candidate-resolution
        # path (fallback URLs, .pls re-resolution) never sees "podcasts".
        if urlparse(url).path.endswith(".pls"):
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
        self._current_episode_audio_url = url if category == "podcasts" else None
        # QMediaPlayer ignores setSource() with the URL it already has, so
        # replaying the station just stopped would only call play() on the
        # old, stopped pipeline — which an HLS stream (every BBC preset)
        # never recovers from: PlayingState, but silence. Clearing it first
        # forces a genuine reload through LoadingMedia every time.
        if self._player.source() == QUrl(url):
            self._player.setSource(QUrl())
        self._player.setSource(QUrl(url))
        self._player.play()
        self._player_bar.set_artwork(self._store.slot(category, self._active_number).image_path)
        self._player_bar.set_now_playing(f"Tuning in: {label}…")
        self._player_bar.set_active(True)
        # A podcast episode is an on-demand file — fully seekable. A radio
        # stream is live: there's nothing ahead to fast-forward into, and
        # none of our icecast/shoutcast stations support seeking back
        # either (an HLS one like BBC might keep a short live buffer, but
        # that's inconsistent enough across stations to be worse than no
        # rewind/forward controls at all).
        self._player_bar.set_seekable(category == "podcasts")
        self._player_bar.set_episodes_available(category == "podcasts")
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
        # Before self._player.stop(), which resets position() to 0 —
        # saving after would always persist "0 seconds in".
        self._save_current_progress()
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
            self._player_bar.set_active(False)
            self._player_bar.set_episodes_available(False)
            self._player_bar.set_artwork("")
        self._active_number = None
        self._current_episode_audio_url = None

    def _toggle_play_pause(self) -> None:
        if self._active_number is None:
            return
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._save_current_progress()
            self._player.pause()
            # Every other path that stops audio flowing (stop, switching
            # presets, a failed source) clears the EQ meter — pause was
            # the one gap, left showing whatever bars happened to be lit
            # the instant playback froze until the decay ballistics
            # eventually faded them out on their own.
            self._visualizer.clear()
        else:
            self._player.play()

    def _seek(self, delta_ms: int) -> None:
        if self._active_number is None:
            return
        new_position = max(0, self._player.position() + delta_ms)
        duration = self._player.duration()
        if duration > 0:
            new_position = min(new_position, duration)
        self._player.setPosition(new_position)

    def _seek_to(self, position_ms: int) -> None:
        if self._active_number is None:
            return
        self._player.setPosition(position_ms)

    def _on_position_changed(self, position_ms: int) -> None:
        if self._current_episode_audio_url is None:
            return  # radio — no progress bar showing, nothing to update
        self._player_bar.set_progress(position_ms, self._player.duration())

    def _queue_resume(self, audio_url: str) -> None:
        progress = self._episode_progress.get(audio_url)
        self._pending_resume_ms = progress.position_ms if progress else None

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._schedule_episode is not None:
            occurrence, audio_url = self._schedule_episode
            if audio_url == self._current_episode_audio_url:
                self._schedule_finished.add(occurrence)
                self._schedule_episode = None
                QTimer.singleShot(0, self._schedule_tick)
        if self._pending_resume_ms is None:
            return
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self._player.setPosition(self._pending_resume_ms)
            self._pending_resume_ms = None

    def _save_current_progress(self) -> None:
        if self._current_episode_audio_url is None:
            return
        duration = self._player.duration()
        if duration <= 0:
            return  # not loaded far enough yet to know how long it is
        self._episode_progress.set_position(
            self._current_episode_audio_url, self._player.position(), duration
        )

    def _browse_episodes(self) -> None:
        # The player bar's "Episodes" button only appears for the
        # currently-active podcast — the same dialog is also reachable by
        # right-clicking any podcast preset directly (PresetDeckWidget's
        # context menu), which is where the actual fetch/list logic lives
        # since it needs to work without anything playing yet.
        if self._active_category != "podcasts" or self._active_number is None:
            return
        self._decks["podcasts"].browse_episodes(self._active_number)

    def _play_chosen_episode(self, number: int, episode) -> None:
        self._save_current_progress()
        self._stop_metadata_watchers()
        slot = self._store.slot("podcasts", number)
        self._active_category = "podcasts"
        self._active_number = number
        self._now_playing_detail = episode.title
        self._visualizer.clear()
        self._playback_attempt += 1
        self._remaining_candidates = []
        self._player_bar.set_loading(True)
        self._player_bar.set_website(slot.website)
        self._queue_resume(episode.audio_url)
        self._start_playback("podcasts", episode.audio_url, slot.label, self._playback_attempt)

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if self._active_number is None:
            return
        self._player_bar.set_playing(state == QMediaPlayer.PlayingState)
        if state == QMediaPlayer.PlayingState:
            self._player_bar.set_loading(False)
            self._refresh_now_playing()
        # StoppedState is otherwise deliberately not handled here: it
        # fires for many reasons (user stop, a failed source, switching
        # to the next fallback candidate) and _stop_playback()/
        # _on_player_error() already set the right message for the cases
        # that matter — an unconditional "Nothing playing" here could
        # overwrite a fallback attempt that's already under way.

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

        try:
            process = launch_installer(path)
        except OSError:
            self._update_banner.set_status(f"Downloaded to {path} — open it manually")
            self._update_banner.set_busy(False)
            return

        self._update_banner.set_status("Installer launched — closing to finish…")
        if sys.platform not in ("win32", "darwin") and process is not None:
            # Linux: wait for the installer (pkexec apt, or xdg-open as a
            # fallback) to actually finish before quitting — quitting
            # immediately can kill its password prompt before it's
            # answered, since the desktop session ties a launched app's
            # child processes to its own lifetime.
            self._run_in_background(
                lambda: (path, self._wait_for_installer(process)),
                self._on_installer_finished,
            )
        else:
            QTimer.singleShot(1500, self.close)

    @staticmethod
    def _wait_for_installer(process) -> tuple[int, str]:
        """Runs on the background thread — blocks on process.wait(), then
        reads whatever the process wrote to stderr (only piped for the
        pkexec/apt path; None, hence "", for xdg-open).
        """
        returncode = process.wait()
        stderr_text = process.stderr.read().strip() if process.stderr is not None else ""
        return returncode, stderr_text

    def _on_installer_finished(self, result) -> None:
        path, (returncode, stderr_text) = result
        if returncode == 0:
            self.close()
            return
        # pkexec/apt didn't actually succeed — a cancelled password
        # prompt, no polkit agent running on this desktop, wrong
        # password, etc. Quitting anyway here is exactly the bug this
        # replaces: it looked like clicking Update did nothing.
        detail = f" — {stderr_text}" if stderr_text else ""
        self._update_banner.set_status(
            f"Update didn't install (exit code {returncode}){detail} — "
            f"you can install it manually: {path}"
        )
        self._update_banner.set_busy(False)

    def _update_clock(self) -> None:
        self._clock_label.setText(datetime.now().strftime("%d %b %Y  %H:%M:%S"))

    def _apply_volume(self, volume: int) -> None:
        # The slider is perceptual: QAudioOutput's volume is linear
        # amplitude, which crams nearly all the audible change into the
        # bottom of the slider. Logarithmic -> linear makes each step of
        # the slider sound like a similar change in loudness.
        linear = QtAudio.convertVolume(
            volume / 100,
            QtAudio.VolumeScale.LogarithmicVolumeScale,
            QtAudio.VolumeScale.LinearVolumeScale,
        )
        self._audio_output.setVolume(max(0.0, min(1.0, linear)))

    def _on_volume_changed(self, volume: int) -> None:
        self._apply_volume(volume)
        self._player_bar_volume = volume
        self._volume_save_timer.start()

    def _on_slots_renumbered(self, category: str, renumbered: dict) -> None:
        # The playing preset was dragged elsewhere (or its page moved up):
        # follow it, so stop/now-playing/episodes still point at it.
        if category == self._active_category and self._active_number in renumbered:
            self._active_number = renumbered[self._active_number]
            # Its logo file is renamed to match its new slot number.
            self._player_bar.set_artwork(self._store.slot(category, self._active_number).image_path)

    def _on_schedule_toggled(self, on: bool) -> None:
        self._schedule_on = on
        self._player_bar.set_schedule_on(on)
        # Forgetting what last played makes the first tick act at once:
        # switching on mid-slot jumps straight to what's scheduled now.
        self._schedule_key = None
        self._schedule_episode = None
        if on:
            self._schedule_timer.start(SCHEDULE_TICK_MS)
            self._schedule_tick()
        else:
            self._schedule_timer.stop()
            self._update_schedule_label(None)

    def _schedule_tick(self) -> None:
        if not self._schedule_on:
            return
        now = datetime.now()
        item = current_item(self._schedule.items, now, self._schedule_finished)
        key = Occurrence(item.id, now.date()) if item else None
        if key != self._schedule_key:
            previous, self._schedule_key = self._schedule_key, key
            if item is not None:
                self._play_schedule_item(item, key)
            elif previous is not None:
                self._stop_playback()  # a scheduled slot ended with nothing after it
        self._update_schedule_label(item, now)

    def _find_preset_for(self, item) -> int | None:
        """The slot holding this item's station: by URL, so a moved or
        renamed preset still matches, or else by name, if its URL was edited.
        """
        deck = [slot for slot in self._store.deck(item.category) if not slot.is_empty]
        for slot in deck:
            if slot.url == item.url:
                return slot.number
        for slot in deck:
            if slot.label == item.label:
                return slot.number
        return None

    def _play_schedule_item(self, item, occurrence: Occurrence) -> None:
        number = self._find_preset_for(item)
        if number is None:
            self.statusBar().showMessage(
                f"Schedule: “{item.label}” isn’t in your presets any more", 10_000
            )
            return
        if item.category == "radio":
            self._schedule_episode = None
            already_on = (
                self._active_category == "radio"
                and self._active_number == number
                and self._player.playbackState() == QMediaPlayer.PlayingState
            )
            if not already_on:  # e.g. 6 Music at 9am, still 6 Music at 10am
                self._play_slot("radio", number)
            return
        feed_url = self._store.slot("podcasts", number).url
        self._player_bar.set_now_playing(f"Schedule: finding an episode of {item.label}…")
        self._run_in_background(
            lambda: recent_episodes(feed_url),
            lambda episodes: self._on_schedule_episodes(occurrence, number, episodes),
        )

    def _on_schedule_episodes(self, occurrence: Occurrence, number: int, episodes) -> None:
        if not self._schedule_on or self._schedule_key != occurrence:
            return  # switched off, or the schedule moved on while fetching
        episode = next(
            (e for e in episodes if not self._episode_progress.is_completed(e.audio_url)), None
        )
        if episode is None:
            # Nothing unheard (or the feed couldn't be reached): count the
            # appointment as kept and fall back to the scheduled radio.
            slot = self._store.slot("podcasts", number)
            self.statusBar().showMessage(f"Schedule: no new episode of {slot.label} to play", 10_000)
            self._schedule_finished.add(occurrence)
            self._schedule_tick()
            return
        self._schedule_episode = (occurrence, episode.audio_url)
        self._play_chosen_episode(number, episode)

    def _update_schedule_label(self, item, now: datetime | None = None) -> None:
        if not self._schedule_on:
            self._schedule_label.hide()
            return
        now = now or datetime.now()
        if item is None:
            text = "Schedule on · nothing scheduled now"
        else:
            text = f"Schedule on · now: {item.label}" + (f" ({item.note})" if item.note else "")
        upcoming = next_start(self._schedule.items, now)
        if upcoming:
            when, next_item = upcoming
            day = "" if when.date() == now.date() else when.strftime("%a ")
            text += f" · next: {day}{when:%H:%M} {next_item.label}"
        self._schedule_label.setToolTip(text)
        self._schedule_label.setText(
            self._schedule_label.fontMetrics().elidedText(text, Qt.ElideRight, SCHEDULE_LABEL_MAX_WIDTH)
        )
        self._schedule_label.show()

    def _edit_schedule(self) -> None:
        dialog = ScheduleDialog(self._schedule.items, self._store, parent=self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.accepted.connect(lambda: self._on_schedule_edited(dialog.result_items()))
        dialog.open()

    def _on_schedule_edited(self, items) -> None:
        self._schedule.items = items
        self._schedule.save()
        # Only acts if the edit changed what should be on right now.
        self._schedule_tick()

    def _export_presets(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Presets & Schedule",
            str(Path.home() / f"Simple-Streamer-presets{PRESET_FILE_EXTENSION}"),
            f"Simple-Streamer presets (*{PRESET_FILE_EXTENSION})",
        )
        if not filename:
            return
        path = Path(filename)
        if not path.name.endswith(PRESET_FILE_EXTENSION):
            path = path.with_name(path.name + PRESET_FILE_EXTENSION)
        try:
            export_presets(self._store, path, self._schedule)
        except OSError as exc:
            QMessageBox.warning(self, "Export Presets & Schedule", f"Couldn't save the file:\n{exc}")
            return
        self.statusBar().showMessage(f"Presets and schedule exported to {path}", 8000)

    def _import_presets(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import Presets & Schedule",
            str(Path.home()),
            f"Simple-Streamer presets (*{PRESET_FILE_EXTENSION});;All files (*)",
        )
        if not filename:
            return
        answer = QMessageBox.question(
            self,
            "Import Presets & Schedule",
            "Replace all your current Radio and Podcast presets — and your schedule, if the"
            " file has one — with the ones in this file?",
        )
        if answer != QMessageBox.Yes:
            return
        # The playing slot may be about to become a different station.
        self._stop_playback()
        try:
            schedule_imported = import_presets(self._store, Path(filename), self._schedule)
        except PresetImportError as exc:
            QMessageBox.warning(
                self, "Import Presets & Schedule", f"{exc}\n\nNothing has been changed."
            )
            return
        for deck in self._decks.values():
            deck.refresh_labels()
        if schedule_imported:
            # A different schedule: start afresh from what it says is on now.
            self._schedule_key = None
            self._schedule_finished.clear()
            self._schedule_episode = None
            self._schedule_tick()
            self.statusBar().showMessage("Presets and schedule imported", 8000)
        else:
            self.statusBar().showMessage("Presets imported (that file has no schedule)", 8000)

    def _on_glow_toggled(self, enabled: bool) -> None:
        self._settings.set_glow_enabled(enabled)
        self._audio_glow.set_glow_enabled(enabled)

    def closeEvent(self, event) -> None:
        if self._volume_save_timer.isActive():
            self._volume_save_timer.stop()
            self._settings.set_volume(self._player_bar_volume)
        self._save_current_progress()
        self._stop_metadata_watchers()
        self._background.shutdown(BACKGROUND_JOIN_TIMEOUT_MS)
        super().closeEvent(event)
