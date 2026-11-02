"""Export both preset decks to a single file, and import one back.

Moves a preset layout between computers. Each machine keeps its own
presets.json, and the image_path values inside it are absolute paths into
that machine's cache folder, so copying the config folder across only
works between identical setups. An export file instead embeds each slot's
logo bytes, so it imports on any OS, under any username.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from pathlib import Path

from simple_streamer import __version__
from simple_streamer.core.presets import CATEGORIES, MAX_PAGES, SLOTS_PER_PAGE, PresetStore

FILE_FORMAT = "simple-streamer-presets"
# Version 2 adds extra pages (slot numbers past 20). An export with only
# one page per deck is still written as version 1, so an older
# Simple-Streamer can import it; one with more says "made by a newer
# Simple-Streamer" there instead of "damaged".
FILE_FORMAT_VERSION = 2
FILE_EXTENSION = ".ssp.json"
MAX_IMPORT_BYTES = 50 * 1024 * 1024
# The extension becomes part of a cache filename on import, so only
# accept something that's plainly an extension, never a path fragment.
_IMAGE_EXTENSION_RE = re.compile(r"^\.[a-z0-9]{1,5}$")


class PresetImportError(Exception):
    """The chosen file isn't a usable preset export; nothing was changed."""


def export_presets(store: PresetStore, path: Path) -> None:
    multi_page = any(store.page_count(category) > 1 for category in CATEGORIES)
    data = {
        "format": FILE_FORMAT,
        "version": FILE_FORMAT_VERSION if multi_page else 1,
        "app_version": __version__,
        "pages": {category: store.page_count(category) for category in CATEGORIES},
    }
    for category in CATEGORIES:
        slots = []
        for slot in store.deck(category):
            image = None
            if slot.image_path:
                image_file = Path(slot.image_path)
                if image_file.is_file():
                    image = {
                        "extension": image_file.suffix.lower(),
                        "data": base64.b64encode(image_file.read_bytes()).decode("ascii"),
                    }
            slots.append(
                {
                    "number": slot.number,
                    "label": slot.label,
                    "url": slot.url,
                    "website": slot.website,
                    "fallback_urls": list(slot.fallback_urls),
                    "image": image,
                }
            )
        data[category] = slots
    path.write_text(json.dumps(data, indent=2))


def import_presets(store: PresetStore, path: Path) -> None:
    """Replace every slot in both decks with the file's contents, and save.

    The whole file is validated before anything is touched, so a bad file
    raises PresetImportError and leaves the current presets exactly as
    they were.
    """
    decks, pages = _read_export(path)
    for category in CATEGORIES:
        for slot in store.deck(category):
            store.clear(category, slot.number)
        store.set_page_count(category, pages[category])
        for number, slot in decks[category].items():
            store.assign(
                category,
                number,
                slot["label"],
                slot["url"],
                website=slot["website"],
                fallback_urls=slot["fallback_urls"],
            )
            if slot["image"] is not None:
                image_bytes, extension = slot["image"]
                store.set_image(category, number, image_bytes, extension)
    store.save()


def _read_export(path: Path) -> tuple[dict[str, dict[int, dict]], dict[str, int]]:
    try:
        if path.stat().st_size > MAX_IMPORT_BYTES:
            raise PresetImportError("That file is too large to be a preset export.")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PresetImportError("That file couldn't be read as a preset export.") from exc

    if not isinstance(data, dict) or data.get("format") != FILE_FORMAT:
        raise PresetImportError("That file isn't a Simple-Streamer preset export.")
    version = data.get("version")
    if not isinstance(version, int) or version > FILE_FORMAT_VERSION:
        raise PresetImportError(
            "That preset export was made by a newer Simple-Streamer — update this one first."
        )

    raw_pages = data.get("pages", {})
    if not isinstance(raw_pages, dict):
        raise PresetImportError("That preset export is damaged.")
    decks: dict[str, dict[int, dict]] = {}
    pages: dict[str, int] = {}
    for category in CATEGORIES:
        raw_slots = data.get(category)
        if not isinstance(raw_slots, list):
            raise PresetImportError(f"That preset export has no {category} presets in it.")
        decks[category] = {}
        for raw in raw_slots:
            slot = _parse_slot(raw)
            if slot is not None:
                decks[category][slot["number"]] = slot
        saved_pages = raw_pages.get(category, 1)
        if not isinstance(saved_pages, int) or not 1 <= saved_pages <= MAX_PAGES:
            raise PresetImportError("That preset export is damaged.")
        needed_pages = -(-max(decks[category], default=1) // SLOTS_PER_PAGE)
        pages[category] = max(saved_pages, needed_pages)
    return decks, pages


def _parse_slot(raw) -> dict | None:
    """A validated slot, or None for an empty one. Raises on anything malformed."""
    if not isinstance(raw, dict):
        raise PresetImportError("That preset export is damaged.")
    number = raw.get("number")
    if not isinstance(number, int) or not 1 <= number <= MAX_PAGES * SLOTS_PER_PAGE:
        raise PresetImportError("That preset export is damaged.")

    label, url, website = (raw.get(key, "") for key in ("label", "url", "website"))
    fallback_urls = raw.get("fallback_urls", [])
    if not all(isinstance(value, str) for value in (label, url, website)) or not (
        isinstance(fallback_urls, list) and all(isinstance(u, str) for u in fallback_urls)
    ):
        raise PresetImportError("That preset export is damaged.")
    if not url:
        return None

    return {
        "number": number,
        "label": label,
        "url": url,
        "website": website,
        "fallback_urls": [u for u in fallback_urls if u],
        "image": _parse_image(raw.get("image")),
    }


def _parse_image(raw) -> tuple[bytes, str] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PresetImportError("That preset export is damaged.")
    extension = raw.get("extension")
    encoded = raw.get("data")
    if not isinstance(extension, str) or not _IMAGE_EXTENSION_RE.match(extension):
        raise PresetImportError("That preset export is damaged.")
    if not isinstance(encoded, str):
        raise PresetImportError("That preset export is damaged.")
    try:
        return base64.b64decode(encoded, validate=True), extension
    except (binascii.Error, ValueError) as exc:
        raise PresetImportError("That preset export is damaged.") from exc
