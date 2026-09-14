import json
from unittest.mock import patch

from simple_streamer.core.station_search import search_stations


class _Response:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _station(**overrides):
    base = {
        "name": "WALM - Old Time Radio",
        "url": "https://icecast.walmradio.com:8443/otr",
        "url_resolved": "https://icecast.walmradio.com:8443/otr",
        "homepage": "https://walmradio.com/otr",
        "favicon": "https://icecast.walmradio.com:8443/otr.jpg",
        "tags": "78,comedy,drama,old time radio,otr",
        "countrycode": "US",
        "bitrate": 64,
        "codec": "MP3",
    }
    base.update(overrides)
    return base


def test_returns_nothing_for_a_blank_query():
    assert search_stations("   ") == []


def test_parses_a_station_result():
    body = json.dumps([_station()]).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        results = search_stations("old time radio")
    assert len(results) == 1
    station = results[0]
    assert station.name == "WALM - Old Time Radio"
    assert station.stream_url == "https://icecast.walmradio.com:8443/otr"
    assert station.website == "https://walmradio.com/otr"
    assert station.favicon_url == "https://icecast.walmradio.com:8443/otr.jpg"
    assert station.description == "US · 78, comedy, drama · 64kbps MP3"


def test_prefers_url_resolved_over_the_raw_url():
    body = json.dumps(
        [_station(url="https://redirector.example/x", url_resolved="https://real-stream.example/y")]
    ).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        results = search_stations("old time radio")
    assert results[0].stream_url == "https://real-stream.example/y"


def test_falls_back_to_the_raw_url_when_unresolved():
    body = json.dumps([_station(url="https://only-this.example/z", url_resolved="")]).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        results = search_stations("old time radio")
    assert results[0].stream_url == "https://only-this.example/z"


def test_skips_a_station_with_no_playable_url():
    body = json.dumps([_station(url="", url_resolved="")]).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        assert search_stations("old time radio") == []


def test_skips_a_station_with_no_name():
    body = json.dumps([_station(name="")]).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        assert search_stations("old time radio") == []


def test_description_omits_missing_fields_gracefully():
    body = json.dumps(
        [_station(countrycode="", tags="", bitrate=None, codec="")]
    ).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        results = search_stations("old time radio")
    assert results[0].description == ""


def test_returns_nothing_when_unreachable():
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert search_stations("old time radio") == []
