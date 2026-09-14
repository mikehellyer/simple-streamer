"""Tracks how far into each podcast episode the user has listened, so
picking that episode again (from the recent-episodes list, or because
it's still the latest one) resumes where they left off instead of
starting over.

Keyed by the episode's audio URL — the same value already used as the
actual playback source, so it's a natural, already-unique identifier
without needing a separate episode id from the feed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir

# Close enough to the end that "resume" would just replay the outro/
# credits — treat it as finished instead of a still-in-progress episode.
NEAR_END_THRESHOLD_MS = 15_000


@dataclass
class EpisodeProgress:
    position_ms: int
    duration_ms: int


class EpisodeProgressStore:
    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or self._default_config_path()
        self._progress: dict[str, EpisodeProgress] = {}
        self.load()

    @staticmethod
    def _default_config_path() -> Path:
        return Path(user_config_dir("Simple-Streamer")) / "episode_progress.json"

    def get(self, audio_url: str) -> Optional[EpisodeProgress]:
        return self._progress.get(audio_url)

    def set_position(self, audio_url: str, position_ms: int, duration_ms: int) -> None:
        if duration_ms > 0 and position_ms >= duration_ms - NEAR_END_THRESHOLD_MS:
            self._progress.pop(audio_url, None)
        else:
            self._progress[audio_url] = EpisodeProgress(
                position_ms=max(0, position_ms), duration_ms=max(0, duration_ms)
            )
        self.save()

    def load(self) -> None:
        if not self._config_path.exists():
            return
        try:
            data = json.loads(self._config_path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for audio_url, entry in data.items():
            try:
                self._progress[audio_url] = EpisodeProgress(
                    position_ms=int(entry["position_ms"]),
                    duration_ms=int(entry["duration_ms"]),
                )
            except (KeyError, TypeError, ValueError):
                continue  # a corrupt/foreign entry — skip rather than fail the whole load

    def save(self) -> None:
        data = {url: asdict(progress) for url, progress in self._progress.items()}
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(json.dumps(data, indent=2))
