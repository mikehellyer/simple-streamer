"""Preset slots for Simple-Streamer: two independent 10-slot decks (radio, podcasts)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir

SLOTS_PER_DECK = 10
CATEGORIES = ("radio", "podcasts")


@dataclass
class PresetSlot:
    number: int
    label: str = ""
    url: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.url


class PresetStore:
    """Holds the radio and podcast preset decks and persists them to disk."""

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or self._default_config_path()
        self._decks: dict[str, list[PresetSlot]] = {
            category: [PresetSlot(number=n) for n in range(1, SLOTS_PER_DECK + 1)]
            for category in CATEGORIES
        }
        self.load()

    @staticmethod
    def _default_config_path() -> Path:
        return Path(user_config_dir("Simple-Streamer")) / "presets.json"

    def deck(self, category: str) -> list[PresetSlot]:
        return self._decks[category]

    def slot(self, category: str, number: int) -> PresetSlot:
        return self._decks[category][number - 1]

    def assign(self, category: str, number: int, label: str, url: str) -> None:
        self._decks[category][number - 1] = PresetSlot(number=number, label=label, url=url)

    def clear(self, category: str, number: int) -> None:
        self._decks[category][number - 1] = PresetSlot(number=number)

    def load(self) -> None:
        if not self._config_path.exists():
            return
        try:
            data = json.loads(self._config_path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for category in CATEGORIES:
            for raw in data.get(category, []):
                number = raw.get("number")
                if isinstance(number, int) and 1 <= number <= SLOTS_PER_DECK:
                    self._decks[category][number - 1] = PresetSlot(
                        number=number,
                        label=raw.get("label", ""),
                        url=raw.get("url", ""),
                    )

    def save(self) -> None:
        data = {
            category: [asdict(slot) for slot in slots]
            for category, slots in self._decks.items()
        }
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(json.dumps(data, indent=2))
