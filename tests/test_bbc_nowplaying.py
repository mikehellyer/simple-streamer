from unittest.mock import patch

from simple_streamer.core.bbc_nowplaying import bbc_service_id_from_url, fetch_now_playing


def test_extracts_service_id_from_lsn_lv_resolver_url():
    url = "https://lsn.lv/bbcradio.m3u8?station=bbc_radio_one&bitrate=320000"
    assert bbc_service_id_from_url(url) == "bbc_radio_one"


def test_extracts_service_id_from_a_direct_cdn_url():
    url = (
        "http://as-hls-uk-live.akamaized.net/pool_47700285/live/uk/"
        "bbc_radio_five_live_sports_extra/bbc_radio_five_live_sports_extra.isml/"
        "bbc_radio_five_live_sports_extra-audio=320000.norewind.m3u8"
    )
    assert bbc_service_id_from_url(url) == "bbc_radio_five_live_sports_extra"


def test_returns_none_for_a_non_bbc_url():
    assert bbc_service_id_from_url("http://icecast.thisisdax.com/LBCUKMP3") is None


class _Response:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_fetch_now_playing_formats_artist_and_track():
    body = b'{"data": [{"titles": {"primary": "Rihanna", "secondary": "We Found Love"}}]}'
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        info = fetch_now_playing("bbc_radio_one")
    assert info.title == "Rihanna - We Found Love"


def test_fetch_now_playing_falls_back_to_track_only_without_an_artist():
    body = b'{"data": [{"titles": {"primary": null, "secondary": "News at Nine"}}]}'
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        info = fetch_now_playing("bbc_radio_fourfm")
    assert info.title == "News at Nine"


def test_fetch_now_playing_returns_none_when_no_segment_data():
    # Real behavior for speech stations like Radio 4 or 5 Live — not an
    # error, just nothing to report.
    body = b'{"total": 0, "data": []}'
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        assert fetch_now_playing("bbc_radio_fourfm") is None


def test_fetch_now_playing_returns_none_when_unreachable():
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        assert fetch_now_playing("bbc_radio_one") is None
