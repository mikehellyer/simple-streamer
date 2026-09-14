"""Computes a color and intensity for the window's audio-reactive glow,
from the same per-band levels the EQ visualizer already displays (see
gui/audio_visualizer.py/core/spectrum.py) — no separate audio analysis.

A purely audio-derived hue (weighted toward whichever bands currently
have the most energy) turned out to barely move for typical music —
most tracks/broadcasts keep a fairly similar bass-to-treble balance
from moment to moment, so the color just sat near one hue instead of
"alternating between the main colours" the way a TV ambient light
does. Instead, the hue continuously rotates through the full color
wheel on its own on a fixed cycle, and the audio only nudges it
slightly warmer/cooler on top of that — still audio-reactive, but
guaranteed to actually cycle through red/green/blue/etc. rather than
parking on whatever this particular track's spectral balance is.
Loudness still drives how strong the glow is, fading to nothing in
silence.
"""
from __future__ import annotations

import colorsys
from dataclasses import dataclass
from typing import Sequence

CYCLE_SECONDS = 20.0
# How far the audio's bass/treble balance can nudge the hue away from
# the rotating base — a fraction of the full 0..1 color wheel.
AUDIO_HUE_SWING = 0.12
SATURATION = 1.0
SILENCE_THRESHOLD = 1e-6


@dataclass(frozen=True)
class GlowColor:
    red: int
    green: int
    blue: int
    intensity: float  # 0..1 — how strong the glow should render, 0 = off


def compute_glow(left: Sequence[float], right: Sequence[float], time_seconds: float) -> GlowColor:
    """left/right are equal-length per-band level sequences (each value
    in [0, 1], log-spaced low-to-high frequency) — the same shape
    core.spectrum.band_levels() produces. time_seconds drives the
    rotating base hue — pass a steadily-increasing clock (e.g.
    time.monotonic()), not something reset per call.
    """
    combined = [(l + r) / 2 for l, r in zip(left, right)]
    total = sum(combined)
    if total <= SILENCE_THRESHOLD or not combined:
        return GlowColor(red=0, green=0, blue=0, intensity=0.0)

    band_count = len(combined)
    weighted_index = sum(level * i for i, level in enumerate(combined)) / total
    # -0.5..0.5: how bass- (negative) or treble-heavy (positive) this
    # moment is, relative to the middle band.
    balance = weighted_index / max(1, band_count - 1) - 0.5

    base_hue = (time_seconds / CYCLE_SECONDS) % 1.0
    hue = (base_hue + balance * AUDIO_HUE_SWING) % 1.0

    intensity = min(1.0, total / band_count)
    red, green, blue = colorsys.hsv_to_rgb(hue, SATURATION, 1.0)
    return GlowColor(
        red=round(red * 255), green=round(green * 255), blue=round(blue * 255), intensity=intensity
    )
