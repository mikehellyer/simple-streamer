import io
from unittest.mock import patch

from simple_streamer.core.self_update import download_asset, find_asset_for_this_platform


ASSETS = [
    ("Simple-Streamer-0.2.0-Windows-Setup.exe", "https://dl/win.exe"),
    ("Simple-Streamer-0.2.0-macOS.dmg", "https://dl/mac.dmg"),
    ("simple-streamer_0.2.0_amd64.deb", "https://dl/lin.deb"),
]


def test_finds_windows_asset():
    with patch("sys.platform", "win32"):
        assert find_asset_for_this_platform(ASSETS) == "https://dl/win.exe"


def test_finds_macos_asset():
    with patch("sys.platform", "darwin"):
        assert find_asset_for_this_platform(ASSETS) == "https://dl/mac.dmg"


def test_finds_linux_asset():
    with patch("sys.platform", "linux"):
        assert find_asset_for_this_platform(ASSETS) == "https://dl/lin.deb"


def test_returns_none_when_no_matching_asset():
    with patch("sys.platform", "win32"):
        assert find_asset_for_this_platform(ASSETS[1:]) is None


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_download_asset_writes_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.mkdtemp", lambda prefix="": str(tmp_path))
    with patch("urllib.request.urlopen", return_value=_Response(b"installer bytes")):
        path = download_asset("https://dl/Simple-Streamer-0.2.0-macOS.dmg")

    assert path is not None
    assert path.name == "Simple-Streamer-0.2.0-macOS.dmg"
    assert path.read_bytes() == b"installer bytes"


def test_download_asset_returns_none_when_unreachable():
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        assert download_asset("https://dl/whatever.exe") is None
