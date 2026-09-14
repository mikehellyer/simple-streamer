"""Turns a block of raw audio samples into levels for a bar-graph display.

Pure numpy, no Qt — the actual PCM tap (QAudioBufferOutput) lives in
gui/audio_visualizer.py; this module is just the "how loud is each
frequency band" math, kept separate so it's testable without a display.
"""
from __future__ import annotations

import numpy as np

DEFAULT_MIN_FREQ = 60.0
DEFAULT_MAX_FREQ = 16000.0


def band_levels(
    samples: np.ndarray,
    sample_rate: int,
    num_bands: int,
    min_freq: float = DEFAULT_MIN_FREQ,
    max_freq: float = DEFAULT_MAX_FREQ,
    gain: float = 16.0,
) -> np.ndarray:
    """Return `num_bands` levels in [0, 1], log-spaced from min_freq to max_freq.

    Each level is a rough loudness for that band, scaled by `gain` and
    compressed with a square root so quieter passages still show some
    movement instead of sitting near zero (matching how a real analog
    level meter responds, not a linear-in-power one).
    """
    n = len(samples)
    if n == 0:
        return np.zeros(num_bands)

    spectrum = np.abs(np.fft.rfft(samples * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
    edges = np.geomspace(min_freq, max_freq, num_bands + 1)

    levels = np.zeros(num_bands)
    for i in range(num_bands):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if np.any(mask):
            levels[i] = spectrum[mask].mean()

    normalized = (levels / n) * gain
    return np.clip(np.sqrt(normalized), 0.0, 1.0)
