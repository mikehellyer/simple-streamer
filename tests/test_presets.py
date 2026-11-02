import json
from pathlib import Path

import pytest

from simple_streamer.core import presets as presets_module
from simple_streamer.core.presets import PresetStore, SLOTS_PER_PAGE, MAX_PAGES, CATEGORIES, DEFAULT_PRESETS


def test_new_store_has_ten_empty_slots_per_category(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    for category in CATEGORIES:
        deck = store.deck(category)
        assert len(deck) == SLOTS_PER_PAGE
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


def test_a_deleted_starter_preset_stays_deleted_after_a_restart(tmp_path, monkeypatch):
    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    store = PresetStore()
    store.clear("radio", 2)
    store.save()

    restarted = PresetStore()
    restarted_again = PresetStore()

    assert restarted.slot("radio", 2).is_empty
    assert restarted_again.slot("radio", 2).is_empty


def test_a_starter_preset_moved_elsewhere_doesnt_reappear_in_its_old_slot(tmp_path, monkeypatch):
    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    store = PresetStore()
    entry = DEFAULT_PRESETS["radio"][7]
    store.assign("radio", 19, entry.label, entry.url)
    store.clear("radio", 8)
    store.save()

    restarted = PresetStore()

    assert restarted.slot("radio", 8).is_empty
    assert restarted.slot("radio", 19).label == entry.label


def test_a_file_from_before_offered_defaults_gets_one_last_fill(tmp_path, monkeypatch):
    # An install upgrading from a version that didn't record which
    # defaults it had offered: its empty default slots fill one final
    # time, then deleting one sticks like on any other install.
    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_PAGE + 1)]
    target.write_text(json.dumps({"radio": old_deck, "podcasts": []}))

    upgraded = PresetStore()
    assert upgraded.slot("radio", 1).label == DEFAULT_PRESETS["radio"][0].label
    upgraded.clear("radio", 1)
    upgraded.save()

    assert PresetStore().slot("radio", 1).is_empty


def test_a_default_added_in_a_later_version_still_arrives(tmp_path, monkeypatch):
    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    PresetStore()  # an install that has been offered today's defaults

    new_default = presets_module.DefaultPreset("Brand New FM", "https://example.com/new")
    radio = list(DEFAULT_PRESETS["radio"]) + [new_default]
    monkeypatch.setitem(presets_module.DEFAULT_PRESETS, "radio", radio)
    store = PresetStore()

    assert store.slot("radio", len(radio)).label == "Brand New FM"


def test_a_new_default_reaches_a_machine_with_an_older_saved_file(tmp_path, monkeypatch):
    # Simulate an existing install: its saved file predates a preset that
    # got added to DEFAULT_PRESETS later (e.g. a new podcast). The slot for
    # it exists in the file (every slot is always serialized) but empty.
    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_PAGE + 1)]
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
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_PAGE + 1)]
    old_deck[0] = {"number": 1, "label": entry.label, "url": entry.url}
    target.write_text(json.dumps({"radio": old_deck, "podcasts": []}))

    store = PresetStore()

    assert store.slot("radio", 1).website == entry.website


def _radio_default_with_replaced_url():
    for number, entry in enumerate(DEFAULT_PRESETS["radio"], start=1):
        if entry.replaces_urls:
            return number, entry
    raise AssertionError("no radio default has replaces_urls")


def test_a_slot_on_a_retired_default_url_is_upgraded(tmp_path, monkeypatch):
    # e.g. BBC Radio Scotland moving off the worldwide feed: an install
    # that saved the old default URL picks up the new one on startup.
    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    number, entry = _radio_default_with_replaced_url()
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_PAGE + 1)]
    old_deck[number - 1] = {"number": number, "label": entry.label, "url": entry.replaces_urls[0]}
    target.write_text(json.dumps({"radio": old_deck, "podcasts": []}))

    store = PresetStore()

    assert store.slot("radio", number).url == entry.url
    assert store.slot("radio", number).fallback_urls == list(entry.fallback_urls)


def test_url_upgrade_leaves_a_slot_the_user_pointed_elsewhere(tmp_path, monkeypatch):
    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    number, entry = _radio_default_with_replaced_url()
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_PAGE + 1)]
    old_deck[number - 1] = {"number": number, "label": entry.label, "url": "https://my.own/stream"}
    target.write_text(json.dumps({"radio": old_deck, "podcasts": []}))

    store = PresetStore()

    assert store.slot("radio", number).url == "https://my.own/stream"


def test_website_backfill_skips_a_slot_the_user_repurposed(tmp_path, monkeypatch):
    # Same slot number/category as a default, but a different label — the
    # user has clearly pointed this slot at something else, so it must not
    # get the default's website attached to it.
    target = tmp_path / "presets.json"
    monkeypatch.setattr(PresetStore, "_default_config_path", staticmethod(lambda: target))
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_PAGE + 1)]
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
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_PAGE + 1)]
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
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_PAGE + 1)]
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
    old_deck = [{"number": n, "label": "", "url": ""} for n in range(1, SLOTS_PER_PAGE + 1)]
    old_deck[0] = {
        "number": 1,
        "label": entry.label,
        "url": entry.url,
        "image_path": "/somewhere/my-own-image.png",
    }
    target.write_text(json.dumps({"radio": old_deck, "podcasts": []}))

    store = PresetStore()

    assert store.slot("radio", 1).image_path == "/somewhere/my-own-image.png"


def test_moving_a_preset_onto_an_occupied_slot_swaps_them_with_their_images(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.assign("radio", 2, "Two", "https://example.com/2", website="https://two")
    store.set_image("radio", 2, b"logo-two", ".png")
    store.assign("radio", 9, "Nine", "https://example.com/9")
    store.set_image("radio", 9, b"logo-nine", ".jpg")

    store.move("radio", 2, 9)

    assert store.slot("radio", 9).label == "Two"
    assert store.slot("radio", 9).website == "https://two"
    assert store.slot("radio", 9).number == 9
    assert Path(store.slot("radio", 9).image_path).read_bytes() == b"logo-two"
    assert store.slot("radio", 2).label == "Nine"
    assert Path(store.slot("radio", 2).image_path).read_bytes() == b"logo-nine"
    assert sorted(p.name for p in store.image_cache_dir().iterdir()) == ["radio_2.jpg", "radio_9.png"]


def test_moving_a_preset_into_an_empty_slot_leaves_the_old_one_empty(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.assign("radio", 1, "One", "https://example.com/1")
    store.set_image("radio", 1, b"logo", ".png")

    store.move("radio", 1, 5)

    assert store.slot("radio", 5).label == "One"
    assert store.slot("radio", 1).is_empty
    assert store.slot("radio", 1).image_path == ""
    assert not list(store.image_cache_dir().glob("radio_1.*"))


def test_add_page_appends_twenty_empty_slots(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")

    assert store.add_page("radio") == 2

    assert store.page_count("radio") == 2
    assert len(store.deck("radio")) == 2 * SLOTS_PER_PAGE
    assert [s.number for s in store.page_slots("radio", 2)] == list(range(21, 41))
    assert store.page_count("podcasts") == 1  # decks page independently


def test_extra_pages_round_trip_through_save_and_reload(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.add_page("radio")
    store.add_page("radio")  # page 3 stays empty but is kept
    store.assign("radio", 25, "Page Two", "https://example.com/p2")
    store.save()

    reloaded = PresetStore(config_path=tmp_path / "presets.json")

    assert reloaded.page_count("radio") == 3
    assert reloaded.slot("radio", 25).label == "Page Two"


def test_a_preset_can_move_to_another_page(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.assign("radio", 3, "Mover", "https://example.com/m")
    store.add_page("radio")

    store.move("radio", 3, store.first_empty_slot("radio", 2))

    assert store.slot("radio", 21).label == "Mover"
    assert store.slot("radio", 3).is_empty


def test_removing_an_empty_middle_page_shifts_later_pages_up(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    store.add_page("radio")
    store.add_page("radio")
    store.assign("radio", 45, "Page Three", "https://example.com/p3")
    store.set_image("radio", 45, b"logo", ".png")

    renumbered = store.remove_page("radio", 2)

    assert renumbered == {45: 25}
    assert store.page_count("radio") == 2
    assert store.slot("radio", 25).label == "Page Three"
    assert Path(store.slot("radio", 25).image_path).read_bytes() == b"logo"


def test_a_page_with_presets_or_the_last_page_cant_be_removed(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    with pytest.raises(ValueError):
        store.remove_page("radio", 1)  # the only page
    store.add_page("radio")
    store.assign("radio", 22, "Busy", "https://example.com/b")
    with pytest.raises(ValueError):
        store.remove_page("radio", 2)
    assert store.slot("radio", 22).label == "Busy"


def test_pages_stop_at_the_maximum(tmp_path):
    store = PresetStore(config_path=tmp_path / "presets.json")
    for _ in range(MAX_PAGES - 1):
        store.add_page("radio")
    with pytest.raises(ValueError):
        store.add_page("radio")
