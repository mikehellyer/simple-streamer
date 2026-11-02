"""Preset slots for Simple-Streamer: two independent decks (radio, podcasts),
each made of one or more 20-slot pages."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field, replace
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir

SLOTS_PER_PAGE = 20
MAX_PAGES = 10
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
    # Earlier default URLs for this slot. A saved slot still pointing at
    # one of these is upgraded to `url`/`fallback_urls` on startup (see
    # PresetStore._backfill_new_default_fields) — one the user changed
    # won't match, so it's left alone.
    replaces_urls: tuple[str, ...] = ()


# Seeded into a fresh preset store (first run, no saved presets.json yet).
# Radio entries are direct live-stream URLs (a .pls entry is a redirector
# with a short-lived signed URL inside, re-resolved at play time — see
# core/pls_resolver.py); podcast entries are RSS feed URLs, resolved to the
# latest episode at play time (see core/podcasts.py).
DEFAULT_PRESETS: dict[str, list[DefaultPreset]] = {
    "radio": [
        # BBC stations use the UK pool directly: the lsn.lv resolver hands
        # out the worldwide pool, which swaps out live sport commentary
        # (5 Live football, Sportsound) for rights reasons. The UK pool
        # only plays from a UK connection, so the resolver stays as a
        # fallback — no sport abroad, but not silence.
        DefaultPreset(
            "BBC Radio 1",
            "http://as-hls-uk-live.akamaized.net/pool_01505109/live/uk/bbc_radio_one/bbc_radio_one.isml/bbc_radio_one-audio%3d320000.norewind.m3u8",
            website="https://www.bbc.co.uk/radio1",
            fallback_urls=("https://lsn.lv/bbcradio.m3u8?station=bbc_radio_one&bitrate=320000",),
            replaces_urls=("https://lsn.lv/bbcradio.m3u8?station=bbc_radio_one&bitrate=320000",),
        ),
        DefaultPreset(
            "BBC Radio 2",
            "http://as-hls-uk-live.akamaized.net/pool_74208725/live/uk/bbc_radio_two/bbc_radio_two.isml/bbc_radio_two-audio%3d320000.norewind.m3u8",
            website="https://www.bbc.co.uk/radio2",
            fallback_urls=("https://lsn.lv/bbcradio.m3u8?station=bbc_radio_two&bitrate=320000",),
            replaces_urls=("https://lsn.lv/bbcradio.m3u8?station=bbc_radio_two&bitrate=320000",),
        ),
        DefaultPreset(
            "BBC Radio 3",
            "http://as-hls-uk-live.akamaized.net/pool_23461179/live/uk/bbc_radio_three/bbc_radio_three.isml/bbc_radio_three-audio%3d320000.norewind.m3u8",
            website="https://www.bbc.co.uk/radio3",
            fallback_urls=("https://lsn.lv/bbcradio.m3u8?station=bbc_radio_three&bitrate=320000",),
            replaces_urls=("https://lsn.lv/bbcradio.m3u8?station=bbc_radio_three&bitrate=320000",),
        ),
        DefaultPreset(
            "BBC Radio 4",
            "http://as-hls-uk-live.akamaized.net/pool_55057080/live/uk/bbc_radio_fourfm/bbc_radio_fourfm.isml/bbc_radio_fourfm-audio%3d320000.norewind.m3u8",
            website="https://www.bbc.co.uk/radio4",
            fallback_urls=("https://lsn.lv/bbcradio.m3u8?station=bbc_radio_fourfm&bitrate=320000",),
            replaces_urls=("https://lsn.lv/bbcradio.m3u8?station=bbc_radio_fourfm&bitrate=320000",),
        ),
        DefaultPreset(
            "BBC Radio 5 Live",
            "http://as-hls-uk-live.akamaized.net/pool_89021708/live/uk/bbc_radio_five_live/bbc_radio_five_live.isml/bbc_radio_five_live-audio%3d320000.norewind.m3u8",
            website="https://www.bbc.co.uk/5live",
            fallback_urls=("https://lsn.lv/bbcradio.m3u8?station=bbc_radio_five_live&bitrate=320000",),
            replaces_urls=("https://lsn.lv/bbcradio.m3u8?station=bbc_radio_five_live&bitrate=320000",),
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
            "http://as-hls-uk-live.akamaized.net/pool_43322914/live/uk/bbc_radio_scotland_fm/bbc_radio_scotland_fm.isml/bbc_radio_scotland_fm-audio%3d320000.norewind.m3u8",
            website="https://www.bbc.co.uk/radioscotland",
            fallback_urls=(
                "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_scotland_fm&bitrate=320000",
            ),
            replaces_urls=(
                "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_scotland_fm&bitrate=320000",
            ),
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
        DefaultPreset(
            "MFR",
            "https://stream-mz.hellorayo.co.uk/mfrfm.aac?aw_0_1st.skey=1602676850",
            website="https://planetradio.co.uk/mfr/",
            fallback_urls=("https://hls-mz.hellorayo.co.uk/mfrfm.aac/playlist.m3u8",),
        ),
        # The old MFR 2 AM stream, which now carries Greatest Hits Radio
        # (North East Scotland) — radio-browser.info doesn't list the
        # regional GHR stations, so station search can't find it.
        DefaultPreset(
            "MFR 2 (Greatest Hits)",
            "https://stream-mz.hellorayo.co.uk/mfram.aac?aw_0_1st.skey=1602676850",
            website="https://planetradio.co.uk/greatest-hits/",
            fallback_urls=("https://hls-mz.hellorayo.co.uk/mfram.aac/playlist.m3u8",),
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
            category: [PresetSlot(number=n) for n in range(1, SLOTS_PER_PAGE + 1)]
            for category in CATEGORIES
        }  # one page each to start; load() grows them to the saved page count
        # Labels of the DEFAULT_PRESETS already offered to this install, so
        # each default is placed at most once — a starter preset the user
        # deletes stays deleted instead of coming back on the next launch.
        self._offered_defaults: dict[str, set[str]] = {
            category: set() for category in CATEGORIES
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
        """Place each not-yet-offered DEFAULT_PRESETS entry in its slot, if
        that slot is empty.

        Runs on every real startup, so a default added in a later version
        still reaches a machine with an older presets.json. Each default is
        only ever offered once, though: an empty slot can mean the user
        deleted that default, and it mustn't keep coming back. (A file from
        before this was tracked has no record, so it gets one last fill.)
        """
        for category, entries in DEFAULT_PRESETS.items():
            for number, entry in enumerate(entries, start=1):
                if entry.label in self._offered_defaults[category]:
                    continue
                self._offered_defaults[category].add(entry.label)
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
                if slot.url in entry.replaces_urls:
                    slot.url = entry.url
                    slot.fallback_urls = list(entry.fallback_urls)
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

    def page_count(self, category: str) -> int:
        return len(self._decks[category]) // SLOTS_PER_PAGE

    def page_slots(self, category: str, page: int) -> list[PresetSlot]:
        start = (page - 1) * SLOTS_PER_PAGE
        return self._decks[category][start : start + SLOTS_PER_PAGE]

    def page_is_empty(self, category: str, page: int) -> bool:
        return all(slot.is_empty for slot in self.page_slots(category, page))

    def set_page_count(self, category: str, pages: int) -> None:
        """Grow or shrink a deck to `pages` pages. Only ever drops empty
        slots — shrinking past a page with presets on it raises instead.
        """
        if not 1 <= pages <= MAX_PAGES:
            raise ValueError(f"a deck has between 1 and {MAX_PAGES} pages")
        deck = self._decks[category]
        new_size = pages * SLOTS_PER_PAGE
        if any(not slot.is_empty for slot in deck[new_size:]):
            raise ValueError("can't drop a page that still has presets on it")
        del deck[new_size:]
        deck.extend(PresetSlot(number=n) for n in range(len(deck) + 1, new_size + 1))

    def add_page(self, category: str) -> int:
        """Append an empty page and return its page number."""
        self.set_page_count(category, self.page_count(category) + 1)
        return self.page_count(category)

    def remove_page(self, category: str, page: int) -> dict[int, int]:
        """Remove an empty page; later pages move up one to close the gap.

        Returns {old slot number: new slot number} for every preset that
        moved, so anything holding a slot number (the player) can follow.
        """
        if self.page_count(category) <= 1:
            raise ValueError("a deck always keeps at least one page")
        if not self.page_is_empty(category, page):
            raise ValueError("only an empty page can be removed")
        renumbered = {}
        first_after = page * SLOTS_PER_PAGE + 1
        for number in range(first_after, len(self._decks[category]) + 1):
            if not self.slot(category, number).is_empty:
                self._relocate(category, number, number - SLOTS_PER_PAGE)
                renumbered[number] = number - SLOTS_PER_PAGE
        self.set_page_count(category, self.page_count(category) - 1)
        return renumbered

    def move(self, category: str, from_number: int, to_number: int) -> None:
        """Move a preset to another slot, swapping with whatever's there.
        Each preset's cached logo goes with it.
        """
        if from_number == to_number:
            return
        moving = self.slot(category, from_number)
        displaced = self.slot(category, to_number)
        moving_image = self._take_image(category, from_number)
        displaced_image = self._take_image(category, to_number)
        self._decks[category][to_number - 1] = replace(moving, number=to_number, image_path="")
        self._decks[category][from_number - 1] = replace(displaced, number=from_number, image_path="")
        if moving_image:
            self.set_image(category, to_number, *moving_image)
        if displaced_image:
            self.set_image(category, from_number, *displaced_image)

    def first_empty_slot(self, category: str, page: int) -> Optional[int]:
        for slot in self.page_slots(category, page):
            if slot.is_empty:
                return slot.number
        return None

    def _relocate(self, category: str, from_number: int, to_number: int) -> None:
        """Move a preset into an empty slot (see move() for the general case)."""
        assert self.slot(category, to_number).is_empty
        self.move(category, from_number, to_number)

    def _take_image(self, category: str, number: int) -> Optional[tuple[bytes, str]]:
        """Read a slot's cached logo and delete it from the cache, so it
        can be re-written under a different slot number.
        """
        image_path = self.slot(category, number).image_path
        if not image_path or not Path(image_path).is_file():
            return None
        image = (Path(image_path).read_bytes(), Path(image_path).suffix)
        self._clear_cached_image_file(category, number)
        return image

    def load(self) -> None:
        if not self._config_path.exists():
            return
        try:
            data = json.loads(self._config_path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        pages = data.get("pages", {})
        for category in CATEGORIES:
            saved_pages = pages.get(category) if isinstance(pages, dict) else None
            if isinstance(saved_pages, int):
                self.set_page_count(category, max(1, min(saved_pages, MAX_PAGES)))
            for raw in data.get(category, []):
                number = raw.get("number")
                if isinstance(number, int) and 1 <= number <= MAX_PAGES * SLOTS_PER_PAGE:
                    needed_pages = -(-number // SLOTS_PER_PAGE)
                    if needed_pages > self.page_count(category):
                        self.set_page_count(category, needed_pages)
                    self._decks[category][number - 1] = PresetSlot(
                        number=number,
                        label=raw.get("label", ""),
                        url=raw.get("url", ""),
                        website=raw.get("website", ""),
                        fallback_urls=list(raw.get("fallback_urls", [])),
                        image_path=raw.get("image_path", ""),
                    )
        offered = data.get("offered_defaults", {})
        if isinstance(offered, dict):
            for category in CATEGORIES:
                labels = offered.get(category, [])
                if isinstance(labels, list):
                    self._offered_defaults[category] = {
                        label for label in labels if isinstance(label, str)
                    }

    def save(self) -> None:
        data = {
            category: [asdict(slot) for slot in slots]
            for category, slots in self._decks.items()
        }
        data["pages"] = {category: self.page_count(category) for category in CATEGORIES}
        data["offered_defaults"] = {
            category: sorted(labels) for category, labels in self._offered_defaults.items()
        }
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(json.dumps(data, indent=2))
