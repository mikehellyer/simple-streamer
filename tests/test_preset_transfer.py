import json
from pathlib import Path

import pytest

from simple_streamer.core.preset_transfer import (
    PresetImportError,
    export_presets,
    import_presets,
)
from simple_streamer.core.presets import PresetStore


def _store(directory: Path) -> PresetStore:
    directory.mkdir(parents=True, exist_ok=True)
    return PresetStore(config_path=directory / "presets.json")


def test_export_then_import_reproduces_both_decks_with_images(tmp_path):
    source = _store(tmp_path / "laptop_a")
    source.assign(
        "radio", 8, "BBC Radio 6 Music", "https://example.com/6music.m3u8",
        website="https://www.bbc.co.uk/6music", fallback_urls=["https://example.com/backup"],
    )
    source.set_image("radio", 8, b"6music-logo-bytes", ".png")
    source.assign("podcasts", 2, "The Retro Hour", "https://example.com/feed.rss")
    export_file = tmp_path / "presets.ssp.json"
    export_presets(source, export_file)

    target = _store(tmp_path / "laptop_b")
    import_presets(target, export_file)

    slot = target.slot("radio", 8)
    assert slot.label == "BBC Radio 6 Music"
    assert slot.url == "https://example.com/6music.m3u8"
    assert slot.website == "https://www.bbc.co.uk/6music"
    assert slot.fallback_urls == ["https://example.com/backup"]
    # The logo lands in the *importing* machine's own cache folder, not at
    # the exporting machine's path.
    assert Path(slot.image_path).parent == target.image_cache_dir()
    assert Path(slot.image_path).read_bytes() == b"6music-logo-bytes"
    assert target.slot("podcasts", 2).label == "The Retro Hour"


def test_import_replaces_slots_the_export_has_empty(tmp_path):
    source = _store(tmp_path / "a")
    source.assign("radio", 1, "Kept", "https://example.com/kept")
    export_file = tmp_path / "presets.ssp.json"
    export_presets(source, export_file)

    target = _store(tmp_path / "b")
    target.assign("radio", 5, "Old station", "https://example.com/old")
    target.set_image("radio", 5, b"old-logo", ".png")
    import_presets(target, export_file)

    assert target.slot("radio", 5).is_empty
    assert target.slot("radio", 5).image_path == ""
    assert not list(target.image_cache_dir().glob("radio_5.*"))


def test_import_is_saved_to_disk(tmp_path):
    source = _store(tmp_path / "a")
    source.assign("radio", 3, "Saved", "https://example.com/saved")
    export_file = tmp_path / "presets.ssp.json"
    export_presets(source, export_file)

    target = _store(tmp_path / "b")
    import_presets(target, export_file)

    reloaded = PresetStore(config_path=tmp_path / "b" / "presets.json")
    assert reloaded.slot("radio", 3).label == "Saved"


def test_export_skips_an_image_whose_file_has_gone_missing(tmp_path):
    source = _store(tmp_path / "a")
    source.assign("radio", 1, "Station", "https://example.com/s")
    source.slot("radio", 1).image_path = str(tmp_path / "nowhere.png")
    export_file = tmp_path / "presets.ssp.json"
    export_presets(source, export_file)

    assert json.loads(export_file.read_text())["radio"][0]["image"] is None


def _write(path: Path, data) -> Path:
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


def _valid_export(tmp_path: Path) -> dict:
    source = _store(tmp_path / "source")
    source.assign("radio", 1, "Station", "https://example.com/s")
    export_file = tmp_path / "valid.ssp.json"
    export_presets(source, export_file)
    return json.loads(export_file.read_text())


@pytest.mark.parametrize(
    "contents",
    [
        "not json at all",
        {"format": "something-else", "version": 1, "radio": [], "podcasts": []},
        {"format": "simple-streamer-presets", "version": 99, "radio": [], "podcasts": []},
        {"format": "simple-streamer-presets", "version": 1, "radio": []},
    ],
    ids=["not-json", "wrong-format", "newer-version", "missing-deck"],
)
def test_a_bad_file_is_rejected_and_nothing_changes(tmp_path, contents):
    target = _store(tmp_path / "b")
    target.assign("radio", 1, "Mine", "https://example.com/mine")
    bad_file = _write(tmp_path / "bad.json", contents)

    with pytest.raises(PresetImportError):
        import_presets(target, bad_file)

    assert target.slot("radio", 1).label == "Mine"


def test_a_damaged_slot_late_in_the_file_changes_nothing(tmp_path):
    data = _valid_export(tmp_path)
    data["podcasts"][19]["number"] = 9999  # radio deck is fine; podcasts isn't
    bad_file = _write(tmp_path / "bad.json", data)
    target = _store(tmp_path / "b")
    target.assign("radio", 1, "Mine", "https://example.com/mine")

    with pytest.raises(PresetImportError):
        import_presets(target, bad_file)

    assert target.slot("radio", 1).label == "Mine"


def test_an_image_extension_that_isnt_an_extension_is_rejected(tmp_path):
    data = _valid_export(tmp_path)
    data["radio"][0]["image"] = {"extension": "/../../evil", "data": "aGk="}
    bad_file = _write(tmp_path / "bad.json", data)
    target = _store(tmp_path / "b")

    with pytest.raises(PresetImportError):
        import_presets(target, bad_file)

    assert not (tmp_path / "evil").exists()


def test_extra_pages_survive_export_and_import(tmp_path):
    source = _store(tmp_path / "a")
    source.add_page("radio")
    source.add_page("radio")
    source.assign("radio", 33, "Page Two Station", "https://example.com/p2")
    source.set_image("radio", 33, b"p2-logo", ".png")
    export_file = tmp_path / "presets.ssp.json"
    export_presets(source, export_file)

    target = _store(tmp_path / "b")
    import_presets(target, export_file)

    assert target.page_count("radio") == 3
    assert target.page_count("podcasts") == 1
    assert target.slot("radio", 33).label == "Page Two Station"
    assert Path(target.slot("radio", 33).image_path).read_bytes() == b"p2-logo"


def test_importing_fewer_pages_drops_the_extra_ones(tmp_path):
    source = _store(tmp_path / "a")
    source.assign("radio", 1, "One", "https://example.com/1")
    export_file = tmp_path / "presets.ssp.json"
    export_presets(source, export_file)
    target = _store(tmp_path / "b")
    target.add_page("radio")
    target.assign("radio", 30, "Old page two", "https://example.com/old")

    import_presets(target, export_file)

    assert target.page_count("radio") == 1


def test_a_single_page_export_stays_readable_by_older_versions(tmp_path):
    source = _store(tmp_path / "a")
    export_file = tmp_path / "one-page.ssp.json"
    export_presets(source, export_file)
    assert json.loads(export_file.read_text())["version"] == 1

    source.add_page("podcasts")
    export_presets(source, export_file)
    assert json.loads(export_file.read_text())["version"] == 2
