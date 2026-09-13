from simple_streamer.gui.preset_deck import _shorten, BUTTON_LABEL_MAX_CHARS


def test_short_label_is_unchanged():
    assert _shorten("BBC Radio 1") == "BBC Radio 1"


def test_label_at_the_limit_is_unchanged():
    label = "x" * BUTTON_LABEL_MAX_CHARS
    assert _shorten(label) == label


def test_long_label_is_elided_with_ellipsis():
    result = _shorten("A Podcast With A Genuinely Very Long Name")
    assert result.endswith("…")
    assert len(result) == BUTTON_LABEL_MAX_CHARS
