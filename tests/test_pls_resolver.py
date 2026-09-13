from unittest.mock import patch

from simple_streamer.core.pls_resolver import resolve_pls

SAMPLE_PLS = b"""[playlist]
NumberOfEntries=1
File1=http://edge-bauermz-03-gos2.sharp-stream.com/planetrock.mp3?aw_0_1st.skey=123&aw_0_1st.playerid=BMUK_RPi
Title1=planetrock.mp3 - RadioFeeds.co.uk
Length1=-1
Version=2
"""


class _Response:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_resolve_pls_extracts_the_file1_url():
    with patch("urllib.request.urlopen", return_value=_Response(SAMPLE_PLS)):
        url = resolve_pls("https://example.com/station.pls")

    assert url == "http://edge-bauermz-03-gos2.sharp-stream.com/planetrock.mp3?aw_0_1st.skey=123&aw_0_1st.playerid=BMUK_RPi"


def test_resolve_pls_returns_none_when_unreachable():
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        assert resolve_pls("https://example.com/station.pls") is None


def test_resolve_pls_returns_none_when_no_file_line():
    with patch("urllib.request.urlopen", return_value=_Response(b"[playlist]\nNumberOfEntries=0\n")):
        assert resolve_pls("https://example.com/station.pls") is None
