import json

from simple_streamer.core.settings import SettingsStore


def test_glow_defaults_to_enabled(tmp_path):
    store = SettingsStore(config_path=tmp_path / "settings.json")
    assert store.glow_enabled is True


def test_set_glow_enabled_persists_within_the_store(tmp_path):
    store = SettingsStore(config_path=tmp_path / "settings.json")
    store.set_glow_enabled(False)
    assert store.glow_enabled is False


def test_glow_setting_round_trips_through_save_and_reload(tmp_path):
    config_path = tmp_path / "settings.json"
    store = SettingsStore(config_path=config_path)
    store.set_glow_enabled(False)

    reloaded = SettingsStore(config_path=config_path)
    assert reloaded.glow_enabled is False


def test_missing_file_is_not_an_error(tmp_path):
    store = SettingsStore(config_path=tmp_path / "does-not-exist.json")
    assert store.glow_enabled is True


def test_corrupt_file_is_ignored_not_fatal(tmp_path):
    config_path = tmp_path / "settings.json"
    config_path.write_text("not json at all")
    store = SettingsStore(config_path=config_path)
    assert store.glow_enabled is True


def test_malformed_value_is_ignored(tmp_path):
    config_path = tmp_path / "settings.json"
    config_path.write_text('{"glow_enabled": "not a bool"}')
    store = SettingsStore(config_path=config_path)
    assert store.glow_enabled is True


def test_volume_defaults_to_full_and_persists(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(config_path=path)
    assert store.volume == 100

    store.set_volume(35)

    assert SettingsStore(config_path=path).volume == 35


def test_volume_is_clamped_and_bad_values_are_ignored(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(config_path=path)
    store.set_volume(150)
    assert store.volume == 100

    path.write_text(json.dumps({"glow_enabled": True, "volume": "loud"}))
    assert SettingsStore(config_path=path).volume == 100
