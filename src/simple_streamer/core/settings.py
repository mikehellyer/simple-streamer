"""Persisted user preferences — currently just whether the audio-reactive
window glow is turned on.
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

    def load(self) -> None:
        if not self._config_path.exists():
            return
        try:
            data = json.loads(self._config_path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data.get("glow_enabled"), bool):
            self._settings.glow_enabled = data["glow_enabled"]

    def save(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(json.dumps(asdict(self._settings), indent=2))
