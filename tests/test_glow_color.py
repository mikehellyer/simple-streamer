import colorsys

from simple_streamer.core.glow_color import compute_glow, CYCLE_SECONDS


def _hue_of(glow) -> float:
    h, _s, _v = colorsys.rgb_to_hsv(glow.red / 255, glow.green / 255, glow.blue / 255)
    return h


def test_silence_produces_no_glow():
    glow = compute_glow([0.0] * 10, [0.0] * 10, time_seconds=0.0)
    assert glow.intensity == 0.0
    assert (glow.red, glow.green, glow.blue) == (0, 0, 0)


def test_bass_heavy_audio_sits_at_a_lower_hue_than_treble_heavy_at_the_same_moment():
    bass = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    treble = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    # A moment safely away from the 0.0/1.0 wraparound point, so "lower
    # hue" is unambiguous regardless of which side the swing lands on.
    moment = CYCLE_SECONDS / 4
    bass_glow = compute_glow(bass, bass, time_seconds=moment)
    treble_glow = compute_glow(treble, treble, time_seconds=moment)
    assert _hue_of(bass_glow) < _hue_of(treble_glow)
    assert bass_glow.intensity > 0
    assert treble_glow.intensity > 0


def test_hue_rotates_over_time_for_identical_audio():
    levels = [0.5] * 10
    early = compute_glow(levels, levels, time_seconds=0.0)
    later = compute_glow(levels, levels, time_seconds=CYCLE_SECONDS / 2)
    assert (early.red, early.green, early.blue) != (later.red, later.green, later.blue)


def test_hue_completes_a_full_cycle():
    levels = [0.5] * 10
    start = compute_glow(levels, levels, time_seconds=0.0)
    one_full_cycle_later = compute_glow(levels, levels, time_seconds=CYCLE_SECONDS)
    assert (start.red, start.green, start.blue) == (
        one_full_cycle_later.red,
        one_full_cycle_later.green,
        one_full_cycle_later.blue,
    )


def test_louder_audio_has_higher_intensity():
    quiet = compute_glow([0.1] * 10, [0.1] * 10, time_seconds=0.0)
    loud = compute_glow([0.8] * 10, [0.8] * 10, time_seconds=0.0)
    assert loud.intensity > quiet.intensity


def test_intensity_is_capped_at_one():
    glow = compute_glow([1.0] * 10, [1.0] * 10, time_seconds=0.0)
    assert glow.intensity == 1.0


def test_handles_empty_bands():
    glow = compute_glow([], [], time_seconds=0.0)
    assert glow.intensity == 0.0


def test_uneven_channels_are_paired_up_to_the_shorter_one():
    # zip() truncates to the shorter sequence — shouldn't raise.
    glow = compute_glow([0.5, 0.5, 0.5], [0.5, 0.5], time_seconds=0.0)
    assert glow.intensity > 0
