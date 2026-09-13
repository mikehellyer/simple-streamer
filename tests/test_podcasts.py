from unittest.mock import patch

from simple_streamer.core.podcasts import latest_episode

SAMPLE_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>The Retro Hour</title>
    <item>
      <title>548: Before Photoshop</title>
      <enclosure url="https://example.com/548.mp3" type="audio/mpeg" length="123"/>
    </item>
    <item>
      <title>547: An Older Episode</title>
      <enclosure url="https://example.com/547.mp3" type="audio/mpeg" length="123"/>
    </item>
  </channel>
</rss>
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


def test_latest_episode_returns_the_first_item():
    with patch("urllib.request.urlopen", return_value=_Response(SAMPLE_FEED)):
        episode = latest_episode("https://example.com/feed.xml")

    assert episode is not None
    assert episode.title == "548: Before Photoshop"
    assert episode.audio_url == "https://example.com/548.mp3"


def test_latest_episode_returns_none_when_unreachable():
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        assert latest_episode("https://example.com/feed.xml") is None


def test_latest_episode_returns_none_for_malformed_xml():
    with patch("urllib.request.urlopen", return_value=_Response(b"not xml")):
        assert latest_episode("https://example.com/feed.xml") is None


def test_latest_episode_returns_none_when_item_has_no_enclosure():
    feed = b"""<rss><channel><title>Show</title><item><title>No audio</title></item></channel></rss>"""
    with patch("urllib.request.urlopen", return_value=_Response(feed)):
        assert latest_episode("https://example.com/feed.xml") is None
