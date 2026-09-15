from simple_streamer.core.episode_progress import EpisodeProgressStore, NEAR_END_THRESHOLD_MS


def test_unknown_episode_has_no_progress(tmp_path):
    store = EpisodeProgressStore(config_path=tmp_path / "progress.json")
    assert store.get("https://example.com/1.mp3") is None


def test_set_and_get_position(tmp_path):
    store = EpisodeProgressStore(config_path=tmp_path / "progress.json")
    store.set_position("https://example.com/1.mp3", 90_000, 2_820_000)

    progress = store.get("https://example.com/1.mp3")
    assert progress.position_ms == 90_000
    assert progress.duration_ms == 2_820_000


def test_position_near_the_end_is_treated_as_finished(tmp_path):
    store = EpisodeProgressStore(config_path=tmp_path / "progress.json")
    duration = 2_820_000
    store.set_position("https://example.com/1.mp3", duration - NEAR_END_THRESHOLD_MS, duration)

    assert store.get("https://example.com/1.mp3") is None


def test_finishing_an_episode_clears_previously_saved_progress(tmp_path):
    store = EpisodeProgressStore(config_path=tmp_path / "progress.json")
    duration = 2_820_000
    store.set_position("https://example.com/1.mp3", 90_000, duration)
    store.set_position("https://example.com/1.mp3", duration, duration)

    assert store.get("https://example.com/1.mp3") is None


def test_negative_position_clamps_to_zero(tmp_path):
    store = EpisodeProgressStore(config_path=tmp_path / "progress.json")
    store.set_position("https://example.com/1.mp3", -500, 100_000)

    assert store.get("https://example.com/1.mp3").position_ms == 0


def test_progress_round_trips_through_save_and_reload(tmp_path):
    config_path = tmp_path / "progress.json"
    store = EpisodeProgressStore(config_path=config_path)
    store.set_position("https://example.com/1.mp3", 90_000, 2_820_000)

    reloaded = EpisodeProgressStore(config_path=config_path)
    progress = reloaded.get("https://example.com/1.mp3")
    assert progress.position_ms == 90_000
    assert progress.duration_ms == 2_820_000


def test_missing_file_is_not_an_error(tmp_path):
    store = EpisodeProgressStore(config_path=tmp_path / "does-not-exist.json")
    assert store.get("https://example.com/1.mp3") is None


def test_corrupt_file_is_ignored_not_fatal(tmp_path):
    config_path = tmp_path / "progress.json"
    config_path.write_text("not json at all")
    store = EpisodeProgressStore(config_path=config_path)
    assert store.get("https://example.com/1.mp3") is None


def test_a_malformed_entry_is_skipped_without_failing_the_rest(tmp_path):
    config_path = tmp_path / "progress.json"
    config_path.write_text(
        '{"https://example.com/bad.mp3": {"position_ms": "oops"}, '
        '"https://example.com/good.mp3": {"position_ms": 1000, "duration_ms": 2000}}'
    )
    store = EpisodeProgressStore(config_path=config_path)

    assert store.get("https://example.com/bad.mp3") is None
    assert store.get("https://example.com/good.mp3").position_ms == 1000


def test_unknown_episode_is_not_completed(tmp_path):
    store = EpisodeProgressStore(config_path=tmp_path / "progress.json")
    assert store.is_completed("https://example.com/1.mp3") is False


def test_finishing_an_episode_marks_it_completed(tmp_path):
    store = EpisodeProgressStore(config_path=tmp_path / "progress.json")
    duration = 2_820_000
    store.set_position("https://example.com/1.mp3", duration, duration)

    assert store.is_completed("https://example.com/1.mp3") is True


def test_an_in_progress_episode_is_not_yet_completed(tmp_path):
    store = EpisodeProgressStore(config_path=tmp_path / "progress.json")
    store.set_position("https://example.com/1.mp3", 90_000, 2_820_000)

    assert store.is_completed("https://example.com/1.mp3") is False


def test_completed_status_round_trips_through_save_and_reload(tmp_path):
    config_path = tmp_path / "progress.json"
    store = EpisodeProgressStore(config_path=config_path)
    duration = 2_820_000
    store.set_position("https://example.com/1.mp3", duration, duration)

    reloaded = EpisodeProgressStore(config_path=config_path)
    assert reloaded.is_completed("https://example.com/1.mp3") is True


def test_replaying_part_of_a_completed_episode_keeps_it_marked_completed(tmp_path):
    store = EpisodeProgressStore(config_path=tmp_path / "progress.json")
    duration = 2_820_000
    store.set_position("https://example.com/1.mp3", duration, duration)
    store.set_position("https://example.com/1.mp3", 5_000, duration)

    assert store.is_completed("https://example.com/1.mp3") is True


def test_loading_a_pre_existing_flat_format_file_has_no_completed_episodes(tmp_path):
    # A file saved before "completed" existed — just the old flat
    # {audio_url: {position_ms, duration_ms}} map, no wrapper keys.
    config_path = tmp_path / "progress.json"
    config_path.write_text(
        '{"https://example.com/1.mp3": {"position_ms": 1000, "duration_ms": 2000}}'
    )
    store = EpisodeProgressStore(config_path=config_path)

    assert store.get("https://example.com/1.mp3").position_ms == 1000
    assert store.is_completed("https://example.com/1.mp3") is False
