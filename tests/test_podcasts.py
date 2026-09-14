from unittest.mock import patch

from simple_streamer.core.podcasts import latest_episode, recent_episodes

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

FEED_WITH_METADATA = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>The Retro Hour</title>
    <item>
      <title>548: Before Photoshop</title>
      <pubDate>Sun, 14 Sep 2026 10:13:11 +0000</pubDate>
      <itunes:duration>1:47:03</itunes:duration>
      <enclosure url="https://example.com/548.mp3" type="audio/mpeg" length="123"/>
    </item>
    <item>
      <title>547: Plain Seconds Duration</title>
      <itunes:duration>2823</itunes:duration>
      <enclosure url="https://example.com/547.mp3" type="audio/mpeg" length="123"/>
    </item>
    <item>
      <title>546: No Audio, Skipped</title>
    </item>
    <item>
      <title>545: MM:SS Duration</title>
      <itunes:duration>45:10</itunes:duration>
      <enclosure url="https://example.com/545.mp3" type="audio/mpeg" length="123"/>
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


def test_recent_episodes_returns_up_to_the_limit_newest_first():
    with patch("urllib.request.urlopen", return_value=_Response(SAMPLE_FEED)):
        episodes = recent_episodes("https://example.com/feed.xml", limit=1)
    assert [e.title for e in episodes] == ["548: Before Photoshop"]


def test_recent_episodes_returns_none_when_unreachable():
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        assert recent_episodes("https://example.com/feed.xml") == []


def test_recent_episodes_skips_items_with_no_audio_but_keeps_the_rest():
    with patch("urllib.request.urlopen", return_value=_Response(FEED_WITH_METADATA)):
        episodes = recent_episodes("https://example.com/feed.xml", limit=10)
    assert [e.title for e in episodes] == [
        "548: Before Photoshop",
        "547: Plain Seconds Duration",
        "545: MM:SS Duration",
    ]


def test_recent_episodes_parses_pub_date_and_hms_duration():
    with patch("urllib.request.urlopen", return_value=_Response(FEED_WITH_METADATA)):
        episodes = recent_episodes("https://example.com/feed.xml", limit=1)
    episode = episodes[0]
    assert episode.published == "Sun, 14 Sep 2026 10:13:11 +0000"
    assert episode.duration_seconds == 1 * 3600 + 47 * 60 + 3


def test_recent_episodes_parses_plain_seconds_duration():
    with patch("urllib.request.urlopen", return_value=_Response(FEED_WITH_METADATA)):
        episodes = recent_episodes("https://example.com/feed.xml", limit=10)
    assert episodes[1].duration_seconds == 2823


def test_recent_episodes_parses_mm_ss_duration():
    with patch("urllib.request.urlopen", return_value=_Response(FEED_WITH_METADATA)):
        episodes = recent_episodes("https://example.com/feed.xml", limit=10)
    assert episodes[2].duration_seconds == 45 * 60 + 10


def test_recent_episodes_leaves_duration_none_when_missing_or_unparseable():
    feed = b"""<rss><channel><item><title>x</title>
        <enclosure url="https://example.com/x.mp3"/></item></channel></rss>"""
    with patch("urllib.request.urlopen", return_value=_Response(feed)):
        episodes = recent_episodes("https://example.com/feed.xml")
    assert episodes[0].duration_seconds is None
