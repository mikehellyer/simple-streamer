import json
from pathlib import Path

from simple_streamer.core import presets as presets_module
from simple_streamer.core.presets import PresetStore, SLOTS_PER_DECK, CATEGORIES, DEFAULT_PRESETS


def test_new_store_has_ten_empty_slots_per_category(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    for category in CATEGORIES:
        deck = store.deck(category)
        assert len(deck) == SLOTS_PER_DECK
        assert all(slot.is_empty for slot in deck)


def test_assign_and_retrieve_slot(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.assign("radio", 3, "BBC Radio 6", "https://stream.example/bbc6")

    slot = store.slot("radio", 3)
    assert slot.label == "BBC Radio 6"
    assert slot.url == "https://stream.example/bbc6"
    assert not slot.is_empty


def test_new_slot_has_no_website_or_fallbacks_by_default(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    slot = store.slot("radio", 1)
    assert slot.website == ""
    assert slot.fallback_urls == []


def test_assign_with_website_and_fallback_urls(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.assign(
        "radio",
        2,
        "BBC Radio 6",
        "https://stream.example/bbc6-primary",
        website="https://bbc.co.uk/6music",
        fallback_urls=["https://stream.example/bbc6-alt1", "https://stream.example/bbc6-alt2"],
    )

    slot = store.slot("radio", 2)
    assert slot.website == "https://bbc.co.uk/6music"
    assert slot.fallback_urls == [
        "https://stream.example/bbc6-alt1",
        "https://stream.example/bbc6-alt2",
    ]


def test_website_and_fallbacks_round_trip_through_save_and_reload(tmp_path):
    config_path = tmp_path / "presets.json"
    store = PresetStore(config_path=config_path)
    store.assign(
        "podcasts",
        4,
        "Darknet Diaries",
        "https://feed.example/dd.rss",
        website="https://darknetdiaries.com",
        fallback_urls=["https://feed.example/dd-mirror.rss"],
    )
    store.save()

    reloaded = PresetStore(config_path=config_path)
    slot = reloaded.slot("podcasts", 4)
    assert slot.website == "https://darknetdiaries.com"
    assert slot.fallback_urls == ["https://feed.example/dd-mirror.rss"]


def test_categories_are_independent(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.assign("radio", 1, "Radio Paradise", "https://stream.example/rp")

    assert store.slot("podcasts", 1).is_empty


def test_save_and_reload_round_trips(tmp_path):
    config_path = tmp_path / "presets.json"
    store = PresetStore(config_path=config_path)
    store.assign("podcasts", 7, "Darknet Diaries", "https://feed.example/dd.rss")
    store.save()

    reloaded = PresetStore(config_path=config_path)
    slot = reloaded.slot("podcasts", 7)
    assert slot.label == "Darknet Diaries"
    assert slot.url == "https://feed.example/dd.rss"


def test_clear_slot_empties_it(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.assign("radio", 5, "Jazz24", "https://stream.example/jazz24")
    store.clear("radio", 5)

    assert store.slot("radio", 5).is_empty


def test_explicit_config_path_starts_empty_even_on_first_run(tmp_path):
    # A caller-supplied path (e.g. a test) opts out of default seeding, so
    # behavior stays predictable regardless of what's baked into the app.
    store = PresetStore(config_path=tmp_path / "presets.json")

    assert all(slot.is_empty for slot in store.deck("radio"))


def test_real_first_run_seeds_the_starter_presets(tmp_path, monkeypatch):
    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))

    store = PresetStore()

    for category, entries in DEFAULT_PRESETS.items():
        for number, entry in enumerate(entries, start=1):
            slot = store.slot(category, number)
            assert slot.label == entry.label
            assert slot.url == entry.url
            assert slot.website == entry.website
            assert slot.fallback_urls == list(entry.fallback_urls)
    assert target.exists()


def test_a_new_default_reaches_a_machine_with_an_older_saved_file(tmp_path, monkeypatch):
    # Simulate an existing install: its saved file predates a preset that
    # got added to DEFAULT_PRESETS later (e.g. a new podcast). The slot for
    # it exists in the file (every slot is always serialized) but empty.
    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_DECK + 1)]
    old_deck[0] = {"number": 1, "label": "The Diary Of A CEO", "url": "https://old.example/feed.xml"}
    target.write_text(json.dumps({"radio": [], "podcasts": old_deck}))

    store = PresetStore()

    # The user's existing assignment is untouched...
    assert store.slot("podcasts", 1).url == "https://old.example/feed.xml"
    # ...but a default added after that file was written now fills in.
    entry = DEFAULT_PRESETS["podcasts"][4]
    assert store.slot("podcasts", 5).label == entry.label
    assert store.slot("podcasts", 5).url == entry.url


def test_a_website_added_later_backfills_onto_an_already_assigned_slot(tmp_path, monkeypatch):
    # Simulate an install from before `website` existed on DEFAULT_PRESETS:
    # the slot is already assigned (same label/url as today's default) but
    # has no website, since the saved file predates that field.
    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    entry = DEFAULT_PRESETS["radio"][0]
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_DECK + 1)]
    old_deck[0] = {"number": 1, "label": entry.label, "url": entry.url}
    target.write_text(json.dumps({"radio": old_deck, "podcasts": []}))

    store = PresetStore()

    assert store.slot("radio", 1).website == entry.website


def test_website_backfill_skips_a_slot_the_user_repurposed(tmp_path, monkeypatch):
    # Same slot number/category as a default, but a different label — the
    # user has clearly pointed this slot at something else, so it must not
    # get the default's website attached to it.
    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_DECK + 1)]
    old_deck[0] = {"number": 1, "label": "My Own Station", "url": "https://mine.example/stream"}
    target.write_text(json.dumps({"radio": old_deck, "podcasts": []}))

    store = PresetStore()

    assert store.slot("radio", 1).website == ""


def test_new_slot_has_no_image_by_default(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    assert store.slot("radio", 1).image_path == ""


def test_set_image_caches_bytes_to_disk_and_records_the_path(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.assign("radio", 1, "BBC Radio 1", "https://stream.example/bbc1")

    path = store.set_image("radio", 1, b"fake-png-bytes", ".png")

    assert store.slot("radio", 1).image_path == path
    assert Path(path).read_bytes() == b"fake-png-bytes"
    assert Path(path).parent == store.image_cache_dir()


def test_set_image_replaces_a_previous_image_with_a_different_extension(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.assign("radio", 1, "BBC Radio 1", "https://stream.example/bbc1")
    old_path = Path(store.set_image("radio", 1, b"old-ico-bytes", ".ico"))

    new_path = Path(store.set_image("radio", 1, b"new-png-bytes", ".png"))

    assert not old_path.exists()
    assert new_path.read_bytes() == b"new-png-bytes"
    assert store.slot("radio", 1).image_path == str(new_path)


def test_clear_image_removes_the_cached_file_and_the_reference(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.assign("radio", 1, "BBC Radio 1", "https://stream.example/bbc1")
    path = Path(store.set_image("radio", 1, b"png-bytes", ".png"))

    store.clear_image("radio", 1)

    assert not path.exists()
    assert store.slot("radio", 1).image_path == ""


def test_clearing_a_slot_also_removes_its_cached_image(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.assign("radio", 1, "BBC Radio 1", "https://stream.example/bbc1")
    path = Path(store.set_image("radio", 1, b"png-bytes", ".png"))

    store.clear("radio", 1)

    assert not path.exists()


def test_editing_a_slot_preserves_its_existing_image(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.assign("radio", 1, "BBC Radio 1", "https://stream.example/bbc1")
    path = store.set_image("radio", 1, b"png-bytes", ".png")

    store.assign("radio", 1, "BBC Radio 1 (renamed)", "https://stream.example/bbc1-new")

    assert store.slot("radio", 1).image_path == path


def test_image_round_trips_through_save_and_reload(tmp_path):
    config_path = tmp_path / "presets.json"
    store = PresetStore(config_path=config_path)
    store.assign("radio", 1, "BBC Radio 1", "https://stream.example/bbc1")
    path = store.set_image("radio", 1, b"png-bytes", ".png")
    store.save()

    reloaded = PresetStore(config_path=config_path)
    assert reloaded.slot("radio", 1).image_path == path


def test_every_bundled_default_preset_has_a_matching_image(monkeypatch, tmp_path):
    # Regression guard: every entry in DEFAULT_PRESETS is expected to ship
    # a curated logo under core/resources/default_images — this fails
    # loudly if a new default preset is added without one, rather than
    # silently shipping it with no artwork.
    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))

    store = PresetStore()

    for category, entries in DEFAULT_PRESETS.items():
        for number in range(1, len(entries) + 1):
            assert store.slot(category, number).image_path, (
                f"no bundled default image for {category}_{number}"
            )


def test_a_fresh_slot_from_defaults_gets_seeded_with_its_bundled_image(
    tmp_path, monkeypatch
):
    images_dir = tmp_path / "default_images"
    images_dir.mkdir()
    (images_dir / "radio_1.png").write_bytes(b"bundled-logo-bytes")
    monkeypatch.setattr(presets_module, "DEFAULT_IMAGES_DIR", images_dir)

    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))

    store = PresetStore()

    path = Path(store.slot("radio", 1).image_path)
    assert path.read_bytes() == b"bundled-logo-bytes"


def test_default_image_backfills_onto_an_already_assigned_slot(tmp_path, monkeypatch):
    # Same idea as the website backfill: an install from before this
    # feature shipped already has the slot assigned (matching label/url)
    # but no image_path — it should pick up the bundled default image too.
    images_dir = tmp_path / "default_images"
    images_dir.mkdir()
    (images_dir / "radio_1.png").write_bytes(b"bundled-logo-bytes")
    monkeypatch.setattr(presets_module, "DEFAULT_IMAGES_DIR", images_dir)

    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    entry = DEFAULT_PRESETS["radio"][0]
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_DECK + 1)]
    old_deck[0] = {"number": 1, "label": entry.label, "url": entry.url}
    target.write_text(json.dumps({"radio": old_deck, "podcasts": []}))

    store = PresetStore()

    path = Path(store.slot("radio", 1).image_path)
    assert path.read_bytes() == b"bundled-logo-bytes"


def test_default_image_backfill_skips_a_slot_the_user_repurposed(tmp_path, monkeypatch):
    images_dir = tmp_path / "default_images"
    images_dir.mkdir()
    (images_dir / "radio_1.png").write_bytes(b"bundled-logo-bytes")
    monkeypatch.setattr(presets_module, "DEFAULT_IMAGES_DIR", images_dir)

    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_DECK + 1)]
    old_deck[0] = {"number": 1, "label": "My Own Station", "url": "https://mine.example/stream"}
    target.write_text(json.dumps({"radio": old_deck, "podcasts": []}))

    store = PresetStore()

    assert store.slot("radio", 1).image_path == ""


def test_default_image_backfill_skips_a_slot_the_user_already_gave_an_image(
    tmp_path, monkeypatch
):
    images_dir = tmp_path / "default_images"
    images_dir.mkdir()
    (images_dir / "radio_1.png").write_bytes(b"bundled-logo-bytes")
    monkeypatch.setattr(presets_module, "DEFAULT_IMAGES_DIR", images_dir)

    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    entry = DEFAULT_PRESETS["radio"][0]
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_DECK + 1)]
    old_deck[0] = {
        "number": 1,
        "label": entry.label,
        "url": entry.url,
        "image_path": "/somewhere/my-own-image.png",
    }
    target.write_text(json.dumps({"radio": old_deck, "podcasts": []}))

    store = PresetStore()

    assert store.slot("radio", 1).image_path == "/somewhere/my-own-image.png"
