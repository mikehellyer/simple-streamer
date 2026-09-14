import io
import time
from unittest.mock import patch

from simple_streamer.core.icy_metadata import IcyMetadataListener


class _FakeResponse:
    """A minimal stand-in for the object urllib.request.urlopen returns."""

    def __init__(self, headers: dict, body: bytes):
        self.headers = headers
        self._buffer = io.BytesIO(body)
        self.fp = self._buffer  # no .raw/._sock, so the settimeout probe is skipped
        self.closed = False

    def read(self, n):
        return self._buffer.read(n)

    def close(self):
        self.closed = True


def _icy_block(text: str) -> bytes:
    payload = text.encode("utf-8")
    # Pad to a multiple of 16, as a real server would.
    padded_len = -(-len(payload) // 16) * 16
    payload = payload.ljust(padded_len, b"\x00")
    return bytes([padded_len // 16]) + payload


def test_reports_a_stream_title_change():
    metaint = 8
    audio_chunk = b"\x00" * metaint
    body = audio_chunk + _icy_block("StreamTitle='Scott Walker - Joanna';") + audio_chunk + b"\x00"
    response = _FakeResponse({"icy-metaint": str(metaint)}, body)

    titles = []
    with patch("urllib.request.urlopen", return_value=response):
        listener = IcyMetadataListener("http://example.com/stream", titles.append)
        listener.start()
        for _ in range(50):
            if titles:
                break
            time.sleep(0.05)
        listener.stop()
        listener._thread.join(timeout=2)

    assert titles == ["Scott Walker - Joanna"]


def test_ignores_a_junk_placeholder_title():
    # Real observed behavior from talkSPORT: StreamTitle is a bare "_"
    # since talk radio has no song to announce. Followed by a real title
    # to confirm the listener keeps working afterward rather than getting
    # stuck once it's seen junk.
    metaint = 8
    audio_chunk = b"\x00" * metaint
    body = (
        audio_chunk
        + _icy_block("StreamTitle='_';")
        + audio_chunk
        + _icy_block("StreamTitle='Real Show Title';")
        + audio_chunk
        + b"\x00"
    )
    response = _FakeResponse({"icy-metaint": str(metaint)}, body)

    titles = []
    with patch("urllib.request.urlopen", return_value=response):
        listener = IcyMetadataListener("http://example.com/stream", titles.append)
        listener.start()
        for _ in range(50):
            if titles:
                break
            time.sleep(0.05)
        listener.stop()
        listener._thread.join(timeout=2)

    assert titles == ["Real Show Title"]


def test_exits_cleanly_when_no_icy_metaint_header():
    response = _FakeResponse({}, b"\x00" * 100)

    with patch("urllib.request.urlopen", return_value=response):
        listener = IcyMetadataListener("http://example.com/stream", lambda t: None)
        listener.start()
        listener._thread.join(timeout=2)

    assert not listener._thread.is_alive()
    assert response.closed


def test_exits_cleanly_when_unreachable():
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        listener = IcyMetadataListener("http://example.com/stream", lambda t: None)
        listener.start()
        listener._thread.join(timeout=2)

    assert not listener._thread.is_alive()
