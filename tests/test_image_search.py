from unittest.mock import patch

from simple_streamer.core.image_search import (
    MAX_LOCAL_IMAGE_BYTES,
    download_image,
    guess_extension,
    search_images,
    validate_local_image,
)


class _Response:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_search_images_returns_nothing_for_a_blank_query():
    assert search_images("radio", "   ") == []


def test_podcast_search_uses_itunes_artwork_and_collection_name():
    body = (
        b'{"results": [{"collectionName": "The Retro Hour", '
        b'"artistName": "Someone", "artworkUrl600": "https://x/art600.jpg", '
        b'"artworkUrl100": "https://x/art100.jpg"}]}'
    )
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        results = search_images("podcasts", "retro hour")
    assert len(results) == 1
    assert results[0].title == "The Retro Hour"
    assert results[0].image_url == "https://x/art600.jpg"


def test_podcast_search_falls_back_to_the_100px_artwork():
    body = b'{"results": [{"artistName": "Someone", "artworkUrl100": "https://x/art100.jpg"}]}'
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        results = search_images("podcasts", "retro hour")
    assert results[0].image_url == "https://x/art100.jpg"


def test_podcast_search_skips_results_missing_artwork():
    body = b'{"results": [{"collectionName": "No Art Here"}]}'
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        assert search_images("podcasts", "retro hour") == []


def test_radio_search_uses_radio_browser_favicon_and_name():
    body = b'[{"name": "BBC Radio 1", "favicon": "https://x/bbc1.png"}]'
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        results = search_images("radio", "bbc radio 1")
    assert results == [type(results[0])(title="BBC Radio 1", image_url="https://x/bbc1.png")]


def test_radio_search_skips_stations_without_a_favicon():
    body = b'[{"name": "No Logo Station", "favicon": ""}]'
    with patch("urllib.request.urlopen", return_value=_Response(body)):
        assert search_images("radio", "no logo") == []


def test_search_returns_nothing_when_unreachable():
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert search_images("radio", "bbc radio 1") == []
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert search_images("podcasts", "retro hour") == []


def test_download_image_returns_the_response_body():
    with patch("urllib.request.urlopen", return_value=_Response(b"\x89PNG...")):
        assert download_image("https://x/art.png") == b"\x89PNG..."


def test_download_image_returns_none_when_unreachable():
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert download_image("https://x/art.png") is None


def test_guess_extension_from_a_known_suffix():
    assert guess_extension("https://x/logo.PNG?v=2") == ".png"
    assert guess_extension("https://x/logo.ico") == ".ico"


def test_guess_extension_defaults_to_png_when_unknown_or_missing():
    assert guess_extension("https://x/logo") == ".png"
    assert guess_extension("https://x/logo.weird") == ".png"


def test_validate_local_image_accepts_a_reasonable_png(tmp_path):
    path = tmp_path / "logo.png"
    path.write_bytes(b"fake-png-bytes")
    assert validate_local_image(path) is None


def test_validate_local_image_rejects_an_unsupported_extension(tmp_path):
    path = tmp_path / "logo.tiff"
    path.write_bytes(b"fake-bytes")
    error = validate_local_image(path)
    assert error is not None
    assert "tiff" in error.lower()


def test_validate_local_image_rejects_a_file_over_the_size_cap(tmp_path):
    path = tmp_path / "logo.png"
    path.write_bytes(b"x" * (MAX_LOCAL_IMAGE_BYTES + 1))
    error = validate_local_image(path)
    assert error is not None
    assert "MB" in error


def test_validate_local_image_rejects_a_missing_file(tmp_path):
    error = validate_local_image(tmp_path / "does-not-exist.png")
    assert error is not None
