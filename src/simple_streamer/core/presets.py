"""Preset slots for Simple-Streamer: two independent 20-slot decks (radio, podcasts)."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir

SLOTS_PER_DECK = 20
CATEGORIES = ("radio", "podcasts")

# Curated logos/artwork for the starter presets below (see the
# "Search for Image" feature, core/image_search.py, for how a user picks
# their own later) — bundled so a fresh install already looks finished,
# named to match PresetStore's own {category}_{number} cache filenames.
DEFAULT_IMAGES_DIR = Path(__file__).parent / "resources" / "default_images"

@dataclass(frozen=True)
class DefaultPreset:
    label: str
    url: str
    website: str = ""
    # Tried in order, after `url`, if the main stream/feed fails.
    fallback_urls: tuple[str, ...] = ()


# Seeded into a fresh preset store (first run, no saved presets.json yet).
# Radio entries are direct live-stream URLs (a .pls entry is a redirector
# with a short-lived signed URL inside, re-resolved at play time — see
# core/pls_resolver.py); podcast entries are RSS feed URLs, resolved to the
# latest episode at play time (see core/podcasts.py).
DEFAULT_PRESETS: dict[str, list[DefaultPreset]] = {
    "radio": [
        DefaultPreset(
            "BBC Radio 1",
            "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_one&bitrate=320000",
            website="https://www.bbc.co.uk/radio1",
        ),
        DefaultPreset(
            "BBC Radio 2",
            "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_two&bitrate=320000",
            website="https://www.bbc.co.uk/radio2",
        ),
        DefaultPreset(
            "BBC Radio 3",
            "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_three&bitrate=320000",
            website="https://www.bbc.co.uk/radio3",
        ),
        DefaultPreset(
            "BBC Radio 4",
            "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_fourfm&bitrate=320000",
            website="https://www.bbc.co.uk/radio4",
        ),
        DefaultPreset(
            "BBC Radio 5 Live",
            "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_five_live&bitrate=320000",
            website="https://www.bbc.co.uk/5live",
        ),
        DefaultPreset(
            "BBC Radio 5 Live Sports Extra",
            # The lsn.lv resolver's mapping for this one is stale — it
            # points at the worldwide CDN pool, which 403s for this
            # specific (rights-restricted) station. The UK pool works;
            # keep the resolver as a fallback in case Akamai's pool id
            # rotates and the direct URL below goes stale before this
            # does.
            "http://as-hls-uk-live.akamaized.net/pool_47700285/live/uk/bbc_radio_five_live_sports_extra/bbc_radio_five_live_sports_extra.isml/bbc_radio_five_live_sports_extra-audio%3d320000.norewind.m3u8",
            website="https://www.bbc.co.uk/sounds/play/live:bbc_radio_five_live_sports_extra",
            fallback_urls=(
                "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_five_live_sports_extra&bitrate=320000",
            ),
        ),
        DefaultPreset(
            "BBC Radio Scotland",
            "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_scotland_fm&bitrate=320000",
            website="https://www.bbc.co.uk/radioscotland",
        ),
        DefaultPreset(
            "talkSPORT",
            "http://talksport.live.stream.broadcasting.news/stream-mp3?ref=RF",
            website="https://talksport.com",
        ),
        DefaultPreset(
            "talkSPORT 2",
            "http://talksport.live.stream.broadcasting.news/stream2-mp3?ref=RF",
            website="https://talksport.com/play/talksport2",
        ),
        DefaultPreset(
            "LBC",
            "http://icecast.thisisdax.com/LBCUKMP3",
            website="https://www.lbc.co.uk",
        ),
        DefaultPreset(
            "Planet Rock",
            "http://www.radiofeeds.net/playlists/bauerflash.pls?station=planetrock-mp3",
            website="https://planetrock.com",
        ),
        DefaultPreset(
            "Manx Radio FM",
            "http://listen-manxradio.sharp-stream.com/manxradiofm.mp3?ref=RF",
            website="https://www.manxradio.com",
        ),
        DefaultPreset(
            "Sportsnet 590 The Fan",
            "https://rogers-hls.leanstream.co/rogers/tor590.stream/icy",
            website="https://www.sportsnet.ca/590/",
        ),
    ],
    "podcasts": [
        DefaultPreset(
            "The Diary Of A CEO",
            "https://rss2.flightcast.com/xmsftuzjjykcmqwolaqn6mdn",
            website="https://www.diaryofaceo.co.uk",
        ),
        DefaultPreset(
            "The Rock and Roll Geek Show",
            "https://www.americanheartbreak.com/rnrgeekwp/?feed=podcast",
            website="https://www.americanheartbreak.com/rnrgeekwp/",
        ),
        DefaultPreset(
            "This Week in Retro",
            "https://feed.podbean.com/TWIR/feed.xml",
            website="https://thisweekinretro.com",
        ),
        DefaultPreset(
            "The Retro Hour",
            "https://audioboom.com/channels/4970769.rss",
            website="https://theretrohour.com",
        ),
        DefaultPreset(
            "Rees Rambles",
            "https://anchor.fm/s/7c6f7b84/podcast/rss",
            website="https://ctrl-alt-rees.com/rambles.html",
        ),
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
    # Path to a locally cached logo/artwork picked via the "Search for
    # Image" context menu (core/image_search.py) — not a remote URL, since
    # re-fetching on every startup would make the preset buttons depend on
    # both network access and some third party's URL staying alive.
    image_path: str = ""

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
        self._backfill_new_default_fields()
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
                if self.slot(category, number).is_empty:
                    self.assign(
                        category,
                        number,
                        entry.label,
                        entry.url,
                        website=entry.website,
                        fallback_urls=list(entry.fallback_urls),
                    )
                    self._seed_default_image(category, number)

    def _backfill_new_default_fields(self) -> None:
        """Add a website/fallback URLs to an already-assigned slot that's
        missing them, if the current default for that slot still has them
        and the slot's label matches — i.e. it looks like the same default
        the user hasn't customized away from. This is how a website or
        fallback URL added to DEFAULT_PRESETS after a slot was already
        assigned by an earlier version reaches an existing install, without
        touching a label/url the user did customize.
        """
        for category, entries in DEFAULT_PRESETS.items():
            for number, entry in enumerate(entries, start=1):
                slot = self.slot(category, number)
                if slot.is_empty or slot.label != entry.label:
                    continue
                if not slot.website and entry.website:
                    slot.website = entry.website
                if not slot.fallback_urls and entry.fallback_urls:
                    slot.fallback_urls = list(entry.fallback_urls)
                if not slot.image_path:
                    self._seed_default_image(category, number)

    def _seed_default_image(self, category: str, number: int) -> None:
        """Cache the bundled logo/artwork for a default preset, if one
        ships for this slot — the user can always replace it later via
        "Search for Image" (or "Remove Image"), same as any other image.
        """
        for candidate in DEFAULT_IMAGES_DIR.glob(f"{category}_{number}.*"):
            self.set_image(category, number, candidate.read_bytes(), candidate.suffix)
            return

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
        # The preset editor doesn't touch images at all, so an edit to the
        # name/URL of a slot that already has one shouldn't silently lose
        # it — only clear()/clear_image() should do that.
        existing_image = self._decks[category][number - 1].image_path
        self._decks[category][number - 1] = PresetSlot(
            number=number,
            label=label,
            url=url,
            website=website,
            fallback_urls=list(fallback_urls) if fallback_urls else [],
            image_path=existing_image,
        )

    def clear(self, category: str, number: int) -> None:
        self._clear_cached_image_file(category, number)
        self._decks[category][number - 1] = PresetSlot(number=number)

    def image_cache_dir(self) -> Path:
        return self._config_path.parent / "images"

    def set_image(self, category: str, number: int, image_bytes: bytes, extension: str) -> str:
        """Cache image_bytes to disk for this slot and return the path."""
        self._clear_cached_image_file(category, number)
        directory = self.image_cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{category}_{number}{extension}"
        path.write_bytes(image_bytes)
        self.slot(category, number).image_path = str(path)
        return str(path)

    def clear_image(self, category: str, number: int) -> None:
        self._clear_cached_image_file(category, number)
        self.slot(category, number).image_path = ""

    def _clear_cached_image_file(self, category: str, number: int) -> None:
        for stale in self.image_cache_dir().glob(f"{category}_{number}.*"):
            stale.unlink(missing_ok=True)

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
                        image_path=raw.get("image_path", ""),
                    )

    def save(self) -> None:
        data = {
            category: [asdict(slot) for slot in slots]
            for category, slots in self._decks.items()
        }
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(json.dumps(data, indent=2))
