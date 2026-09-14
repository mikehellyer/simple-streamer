from simple_streamer.core.text import (
    shorten,
    PRESET_BUTTON_LABEL_MAX_CHARS,
    format_duration_ms,
    format_pub_date,
)


def test_short_label_is_unchanged():
    assert shorten("BBC Radio 1", PRESET_BUTTON_LABEL_MAX_CHARS) == "BBC Radio 1"


def test_label_at_the_limit_is_unchanged():
    label = "x" * PRESET_BUTTON_LABEL_MAX_CHARS
    assert shorten(label, PRESET_BUTTON_LABEL_MAX_CHARS) == label


def test_long_label_is_elided_with_ellipsis():
    result = shorten("A Podcast With A Genuinely Very Long Name", PRESET_BUTTON_LABEL_MAX_CHARS)
    assert result.endswith("…")
    assert len(result) == PRESET_BUTTON_LABEL_MAX_CHARS


def test_format_duration_under_an_hour():
    assert format_duration_ms(45 * 60_000 + 10_000) == "45:10"


def test_format_duration_pads_seconds():
    assert format_duration_ms(5_000) == "0:05"


def test_format_duration_over_an_hour():
    assert format_duration_ms((1 * 3600 + 47 * 60 + 3) * 1000) == "1:47:03"


def test_format_duration_clamps_negative_to_zero():
    assert format_duration_ms(-5000) == "0:00"


def test_format_pub_date_parses_rfc822():
    assert format_pub_date("Sun, 14 Sep 2026 10:13:11 +0000") == "14 Sep 2026"


def test_format_pub_date_returns_empty_for_blank_or_unparseable():
    assert format_pub_date("") == ""
    assert format_pub_date("not a date") == ""
