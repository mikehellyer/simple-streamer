import json
from unittest.mock import patch

from simple_streamer.core.podcast_search import search_podcasts


class _Response:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _episode(**overrides):
    base = {
        "collectionName": "Old Time Radio Theater",
        "trackName": "Old Time Radio Theater",
        "artistName": "MysteryShows.com",
        "feedUrl": "https://www.mysteryshows.com/Podcasts/Mystery-Shows-Feed.xml",
        "collectionViewUrl": "https://podcasts.apple.com/us/podcast/old-time-radio-theater/id290159292",
        "trackViewUrl": "https://podcasts.apple.com/us/podcast/old-time-radio-theater/id290159292",
        "artworkUrl600": "https://example.com/art600.jpg",
        "artworkUrl100": "https://example.com/art100.jpg",
        "primaryGenreName": "Performing Arts",
        "trackCount": 78,
    }
    base.update(overrides)
    return base


def _payload(*items):
    return json.dumps({"results": list(items)}).encode("utf-8")


def test_returns_nothing_for_a_blank_query():
    assert search_podcasts("   ") == []


def test_parses_a_podcast_result():
    with patch("urllib.request.urlopen", return_value=_Response(_payload(_episode()))):
        results = search_podcasts("old time radio")
    assert len(results) == 1
    podcast = results[0]
    assert podcast.name == "Old Time Radio Theater"
    assert podcast.feed_url == "https://www.mysteryshows.com/Podcasts/Mystery-Shows-Feed.xml"
    assert podcast.website == "https://podcasts.apple.com/us/podcast/old-time-radio-theater/id290159292"
    assert podcast.artwork_url == "https://example.com/art600.jpg"
    assert podcast.description == "MysteryShows.com · Performing Arts · 78 episodes"


def test_falls_back_to_the_100px_artwork():
    with patch(
        "urllib.request.urlopen",
        return_value=_Response(_payload(_episode(artworkUrl600=""))),
    ):
        results = search_podcasts("old time radio")
    assert results[0].artwork_url == "https://example.com/art100.jpg"


def test_falls_back_to_track_view_url_for_website():
    with patch(
        "urllib.request.urlopen",
        return_value=_Response(_payload(_episode(collectionViewUrl=""))),
    ):
        results = search_podcasts("old time radio")
    assert results[0].website == "https://podcasts.apple.com/us/podcast/old-time-radio-theater/id290159292"


def test_skips_a_result_with_no_feed_url():
    with patch(
        "urllib.request.urlopen",
        return_value=_Response(_payload(_episode(feedUrl=""))),
    ):
        assert search_podcasts("old time radio") == []


def test_skips_a_result_with_no_name():
    with patch(
        "urllib.request.urlopen",
        return_value=_Response(_payload(_episode(collectionName="", trackName=""))),
    ):
        assert search_podcasts("old time radio") == []


def test_description_uses_singular_episode_for_one():
    with patch(
        "urllib.request.urlopen",
        return_value=_Response(_payload(_episode(trackCount=1))),
    ):
        results = search_podcasts("old time radio")
    assert results[0].description.endswith("1 episode")


def test_description_omits_missing_fields_gracefully():
    with patch(
        "urllib.request.urlopen",
        return_value=_Response(
            _payload(_episode(artistName="", primaryGenreName="", trackCount=None))
        ),
    ):
        results = search_podcasts("old time radio")
    assert results[0].description == ""


def test_returns_nothing_when_unreachable():
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert search_podcasts("old time radio") == []
