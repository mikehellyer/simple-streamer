from simple_streamer.core.text import shorten, PRESET_BUTTON_LABEL_MAX_CHARS


def test_short_label_is_unchanged():
    assert shorten("BBC Radio 1", PRESET_BUTTON_LABEL_MAX_CHARS) == "BBC Radio 1"


def test_label_at_the_limit_is_unchanged():
    label = "x" * PRESET_BUTTON_LABEL_MAX_CHARS
    assert shorten(label, PRESET_BUTTON_LABEL_MAX_CHARS) == label


def test_long_label_is_elided_with_ellipsis():
    result = shorten("A Podcast With A Genuinely Very Long Name", PRESET_BUTTON_LABEL_MAX_CHARS)
    assert result.endswith("…")
    assert len(result) == PRESET_BUTTON_LABEL_MAX_CHARS
