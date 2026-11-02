"""Persisted user preferences: whether the audio-reactive window glow is
turned on, and the playback volume.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir


@dataclass
class Settings:
    glow_enabled: bool = True
    # 0-100, as shown on the player bar's slider. 100 = full output, which
    # is how loud playback always was before there was a volume control.
    volume: int = 100


class SettingsStore:
    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or self._default_config_path()
        self._settings = Settings()
        self.load()

    @staticmethod
    def _default_config_path() -> Path:
        return Path(user_config_dir("Simple-Streamer")) / "settings.json"

    @property
    def glow_enabled(self) -> bool:
        return self._settings.glow_enabled

    def set_glow_enabled(self, enabled: bool) -> None:
        self._settings.glow_enabled = enabled
        self.save()

    @property
    def volume(self) -> int:
        return self._settings.volume

    def set_volume(self, volume: int) -> None:
        self._settings.volume = max(0, min(100, int(volume)))
        self.save()

    def load(self) -> None:
        if not self._config_path.exists():
            return
        try:
            data = json.loads(self._config_path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data.get("glow_enabled"), bool):
            self._settings.glow_enabled = data["glow_enabled"]
        volume = data.get("volume")
        if isinstance(volume, int) and not isinstance(volume, bool):
            self._settings.volume = max(0, min(100, volume))

    def save(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(json.dumps(asdict(self._settings), indent=2))
