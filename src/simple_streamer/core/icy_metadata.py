"""Reads the periodic ICY 'StreamTitle' tag from a shoutcast/icecast radio
stream on a background thread.

Qt's own QMediaPlayer metadata API doesn't surface this for a continuous
radio stream (only static, one-time container info like codec/bitrate), so
this opens its own lightweight HTTP connection purely to watch for song
changes, independent of the QMediaPlayer actually decoding the audio.

Protocol: request with `Icy-MetaData: 1`; if the server supports it, it
replies with an `icy-metaint: N` header, then every N bytes of audio data
there is one metadata block: a length byte (block length = byte * 16,
0 meaning "no change"), followed by that many bytes of text containing
`StreamTitle='...';`.
"""
from __future__ import annotations

import re
import threading
import urllib.request
from typing import Callable, Optional

CONNECT_TIMEOUT_SECONDS = 6
READ_TIMEOUT_SECONDS = 15
_STREAM_TITLE_RE = re.compile(r"StreamTitle='(.*?)';")


class IcyMetadataListener:
    """Watches one stream URL for StreamTitle changes until stop() is called."""

    def __init__(self, url: str, on_title: Callable[[str], None]):
        self._url = url
        self._on_title = on_title
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        request = urllib.request.Request(
            self._url, headers={"Icy-MetaData": "1", "User-Agent": "Simple-Streamer/1"}
        )
        try:
            response = urllib.request.urlopen(request, timeout=CONNECT_TIMEOUT_SECONDS)
        except OSError:
            return

        try:
            sock = getattr(response.fp, "raw", response.fp)
            if hasattr(sock, "_sock"):
                sock._sock.settimeout(READ_TIMEOUT_SECONDS)
        except OSError:
            pass

        metaint_header = response.headers.get("icy-metaint")
        if metaint_header is None:
            response.close()
            return  # this station doesn't publish ICY metadata at all

        metaint = int(metaint_header)
        last_title: Optional[str] = None
        try:
            while not self._stop_event.is_set():
                if self._read_exact(response, metaint) is None:
                    break
                length_byte = self._read_exact(response, 1)
                if length_byte is None:
                    break
                length = length_byte[0] * 16
                if length == 0:
                    continue
                meta_bytes = self._read_exact(response, length)
                if meta_bytes is None:
                    break
                match = _STREAM_TITLE_RE.search(meta_bytes.decode("utf-8", errors="replace"))
                title = match.group(1).strip() if match else ""
                if title and title != last_title:
                    last_title = title
                    self._on_title(title)
        except OSError:
            pass
        finally:
            response.close()

    def _read_exact(self, response, count: int) -> Optional[bytes]:
        if count == 0:
            return b""
        chunks = []
        remaining = count
        while remaining > 0:
            if self._stop_event.is_set():
                return None
            try:
                chunk = response.read(remaining)
            except OSError:
                return None
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
