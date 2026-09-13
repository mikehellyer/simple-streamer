from simple_streamer.core.presets import PresetStore, SLOTS_PER_DECK, CATEGORIES


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
