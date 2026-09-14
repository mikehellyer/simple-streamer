import numpy as np

from simple_streamer.core.spectrum import band_levels

SAMPLE_RATE = 48000
BLOCK_SIZE = 1152


def _tone(freq: float, amplitude: float = 0.3) -> np.ndarray:
    t = np.arange(BLOCK_SIZE) / SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_silence_gives_all_zero_levels():
    silence = np.zeros(BLOCK_SIZE, dtype=np.float32)
    levels = band_levels(silence, SAMPLE_RATE, num_bands=10)
    assert np.all(levels == 0)


def test_empty_input_gives_all_zero_levels():
    levels = band_levels(np.array([], dtype=np.float32), SAMPLE_RATE, num_bands=10)
    assert len(levels) == 10
    assert np.all(levels == 0)


def test_bass_tone_peaks_in_a_low_band():
    levels = band_levels(_tone(100), SAMPLE_RATE, num_bands=10)
    assert np.argmax(levels) <= 1


def test_treble_tone_peaks_in_a_high_band():
    levels = band_levels(_tone(8000), SAMPLE_RATE, num_bands=10)
    assert np.argmax(levels) >= 7


def test_louder_tone_gives_a_higher_level():
    quiet = band_levels(_tone(1000, amplitude=0.05), SAMPLE_RATE, num_bands=10)
    loud = band_levels(_tone(1000, amplitude=0.5), SAMPLE_RATE, num_bands=10)
    assert loud.max() > quiet.max()


def test_levels_are_clipped_to_zero_one_range():
    loud = _tone(1000, amplitude=5.0)  # deliberately way past normal signal range
    levels = band_levels(loud, SAMPLE_RATE, num_bands=10)
    assert levels.min() >= 0.0
    assert levels.max() <= 1.0
