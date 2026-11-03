import io
import ssl
import urllib.request

import pytest

from simple_streamer.core.http import (
    SSL_CONTEXT,
    ResponseTooLargeError,
    UnsafeURLError,
    _WebOnlyRedirectHandler,
    is_web_url,
    read_capped,
    urlopen,
)
from simple_streamer.core.image_search import download_image
from simple_streamer.core.pls_resolver import resolve_pls
from simple_streamer.core.podcasts import recent_episodes



def test_ssl_context_is_a_real_ssl_context():
    assert isinstance(SSL_CONTEXT, ssl.SSLContext)


def test_ssl_context_has_certificates_loaded():
    # cert_store_stats() only returns non-zero counts if a CA bundle was
    # actually loaded — this is what guards against a future refactor
    # accidentally dropping the cafile= argument.
    stats = SSL_CONTEXT.cert_store_stats()
    assert stats["x509_ca"] > 0

@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://example.com/logo.png", True),
        ("http://stream.example.com:8000/live", True),
        ("file:///etc/passwd", False),
        ("ftp://example.com/x", False),
        ("data:text/plain,hi", False),
        ("javascript:alert(1)", False),
        ("https:///no-host", False),
        ("", False),
    ],
)
def test_is_web_url(url, expected):
    assert is_web_url(url) is expected


def test_urlopen_refuses_local_files(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("PRIVATE")
    with pytest.raises(UnsafeURLError):
        urlopen(secret.as_uri(), timeout=1)


def test_downloaders_cant_be_pointed_at_local_files(tmp_path):
    # The real-world worry: a community-edited station logo URL of
    # file:///home/…/.ssh/id_ed25519 being read and cached as an image.
    secret = tmp_path / "id_ed25519"
    secret.write_text("PRIVATE KEY")
    assert download_image(secret.as_uri()) is None
    assert resolve_pls(secret.as_uri()) is None
    assert recent_episodes(secret.as_uri()) == []


def test_redirects_to_a_non_web_url_are_refused():
    handler = _WebOnlyRedirectHandler()
    request = urllib.request.Request("https://example.com/logo.png")
    with pytest.raises(UnsafeURLError):
        handler.redirect_request(request, None, 302, "Found", {}, "file:///etc/passwd")


def test_read_capped_allows_up_to_the_limit_and_refuses_more():
    assert read_capped(io.BytesIO(b"x" * 10), 10) == b"x" * 10
    with pytest.raises(ResponseTooLargeError):
        read_capped(io.BytesIO(b"x" * 11), 10)


def test_safety_errors_count_as_ordinary_network_failures():
    # Every caller already treats OSError as "couldn't fetch it".
    assert issubclass(UnsafeURLError, OSError)
    assert issubclass(ResponseTooLargeError, OSError)
