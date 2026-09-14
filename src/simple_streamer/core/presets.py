"""Preset slots for Simple-Streamer: two independent 20-slot decks (radio, podcasts)."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir

SLOTS_PER_DECK = 20
CATEGORIES = ("radio", "podcasts")

# Seeded into a fresh preset store (first run, no saved presets.json yet).
# Radio entries are direct live-stream URLs (a .pls entry is a redirector
# with a short-lived signed URL inside, re-resolved at play time — see
# core/pls_resolver.py); podcast entries are RSS feed URLs, resolved to the
# latest episode at play time (see core/podcasts.py). An entry may include
# a third element, a list of fallback URLs tried in order if the main one
# fails.
DEFAULT_PRESETS: dict[str, list[tuple]] = {
    "radio": [
        ("BBC Radio 1", "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_one&bitrate=320000"),
        ("BBC Radio 2", "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_two&bitrate=320000"),
        ("BBC Radio 3", "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_three&bitrate=320000"),
        ("BBC Radio 4", "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_fourfm&bitrate=320000"),
        ("BBC Radio 5 Live", "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_five_live&bitrate=320000"),
        (
            "BBC Radio 5 Live Sports Extra",
            # The lsn.lv resolver's mapping for this one is stale — it
            # points at the worldwide CDN pool, which 403s for this
            # specific (rights-restricted) station. The UK pool works;
            # keep the resolver as a fallback in case Akamai's pool id
            # rotates and the direct URL below goes stale before this
            # does.
            "http://as-hls-uk-live.akamaized.net/pool_47700285/live/uk/bbc_radio_five_live_sports_extra/bbc_radio_five_live_sports_extra.isml/bbc_radio_five_live_sports_extra-audio%3d320000.norewind.m3u8",
            ["https://lsn.lv/bbcradio.m3u8?station=bbc_radio_five_live_sports_extra&bitrate=320000"],
        ),
        ("BBC Radio Scotland", "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_scotland_fm&bitrate=320000"),
        ("talkSPORT", "http://talksport.live.stream.broadcasting.news/stream-mp3?ref=RF"),
        ("talkSPORT 2", "http://talksport.live.stream.broadcasting.news/stream2-mp3?ref=RF"),
        ("LBC", "http://icecast.thisisdax.com/LBCUKMP3"),
        ("Planet Rock", "http://www.radiofeeds.net/playlists/bauerflash.pls?station=planetrock-mp3"),
        ("Manx Radio FM", "http://listen-manxradio.sharp-stream.com/manxradiofm.mp3?ref=RF"),
        ("Sportsnet 590 The Fan", "https://rogers-hls.leanstream.co/rogers/tor590.stream/icy"),
    ],
    "podcasts": [
        ("The Diary Of A CEO", "https://rss2.flightcast.com/xmsftuzjjykcmqwolaqn6mdn"),
        ("The Rock and Roll Geek Show", "https://www.americanheartbreak.com/rnrgeekwp/?feed=podcast"),
        ("This Week in Retro", "https://feed.podbean.com/TWIR/feed.xml"),
        ("The Retro Hour", "https://audioboom.com/channels/4970769.rss"),
        ("Rees Rambles", "https://anchor.fm/s/7c6f7b84/podcast/rss"),
    ],
}


@dataclass
class PresetSlot:
    number: int
    label: str = ""
    url: str = ""
    website: str = ""
    # Tried in order, after `url`, if the main stream/feed fails to load —
    # see MainWindow's playback-attempt queue in gui/main_window.py.
    fallback_urls: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.url


class PresetStore:
    """Holds the radio and podcast preset decks and persists them to disk."""

    def __init__(self, config_path: Optional[Path] = None):
        explicit_path = config_path is not None
        self._config_path = config_path or self._default_config_path()
        self._decks: dict[str, list[PresetSlot]] = {
            category: [PresetSlot(number=n) for n in range(1, SLOTS_PER_DECK + 1)]
            for category in CATEGORIES
        }

        if explicit_path:
            # A caller-supplied path (e.g. the test suite) opts out of
            # defaults entirely, so behavior stays predictable no matter
            # what's baked into the app.
            self.load()
            return

        if self._config_path.exists():
            self.load()
        self._fill_empty_slots_from_defaults()
        self.save()

    def _fill_empty_slots_from_defaults(self) -> None:
        """Populate any still-empty slot from DEFAULT_PRESETS.

        Runs on every real startup, not just the very first one: an empty
        slot means nothing has been assigned to it, so it's always safe to
        drop in whatever Simple-Streamer currently ships as a default. This
        is how a newly added default preset, or a bigger deck, reaches a
        machine that already has a presets.json from an earlier version.
        """
        for category, entries in DEFAULT_PRESETS.items():
            for number, entry in enumerate(entries, start=1):
                label, url = entry[0], entry[1]
                fallback_urls = entry[2] if len(entry) > 2 else None
                if self.slot(category, number).is_empty:
                    self.assign(category, number, label, url, fallback_urls=fallback_urls)

    @staticmethod
    def _default_config_path() -> Path:
        return Path(user_config_dir("Simple-Streamer")) / "presets.json"

    def deck(self, category: str) -> list[PresetSlot]:
        return self._decks[category]

    def slot(self, category: str, number: int) -> PresetSlot:
        return self._decks[category][number - 1]

    def assign(
        self,
        category: str,
        number: int,
        label: str,
        url: str,
        website: str = "",
        fallback_urls: Optional[list[str]] = None,
    ) -> None:
        self._decks[category][number - 1] = PresetSlot(
            number=number,
            label=label,
            url=url,
            website=website,
            fallback_urls=list(fallback_urls) if fallback_urls else [],
        )

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
                        website=raw.get("website", ""),
                        fallback_urls=list(raw.get("fallback_urls", [])),
                    )

    def save(self) -> None:
        data = {
            category: [asdict(slot) for slot in slots]
            for category, slots in self._decks.items()
        }
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(json.dumps(data, indent=2))
