"""Search for a station or podcast's artwork, for the "Search for Image"
preset context-menu action.

Rather than scraping a general image search engine — which would need
either an API key we don't have or fragile, ToS-shaky HTML scraping —
this uses two purpose-built, free, keyless APIs that already exist to
answer exactly this question:

- Podcasts: the iTunes Search API, which returns each podcast's own
  official artwork.
- Radio: Radio-Browser (radio-browser.info), a community-maintained
  database of radio stations that stores a logo/favicon per station.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from simple_streamer.core.http import SSL_CONTEXT

REQUEST_TIMEOUT_SECONDS = 6
MAX_RESULTS = 8
DEFAULT_IMAGE_EXTENSION = ".png"

# For a user's own local file, picked via "Use Local Image…" — deliberately
# narrower than what a downloaded image is allowed to be (SVG/ICO included
# there), since those come from sources we already trust to serve an actual
# image; a user-picked file gets validated up front instead.
ALLOWED_LOCAL_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
MAX_LOCAL_IMAGE_BYTES = 5 * 1024 * 1024
LOCAL_IMAGE_SPEC_HINT = (
    "PNG, JPG, GIF, BMP, or WEBP · under 5 MB · a square image looks best"
)


@dataclass(frozen=True)
class ImageCandidate:
    title: str
    image_url: str


def search_images(category: str, query: str) -> list[ImageCandidate]:
    query = query.strip()
    if not query:
        return []
    if category == "podcasts":
        return _search_itunes(query)
    return _search_radio_browser(query)


def _search_itunes(query: str) -> list[ImageCandidate]:
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
        {"term": query, "media": "podcast", "limit": MAX_RESULTS}
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Simple-Streamer/1"})
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS, context=SSL_CONTEXT
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []

    candidates = []
    for item in payload.get("results", []):
        artwork = item.get("artworkUrl600") or item.get("artworkUrl100")
        name = item.get("collectionName") or item.get("artistName")
        if artwork and name:
            candidates.append(ImageCandidate(title=name, image_url=artwork))
    return candidates


def _search_radio_browser(query: str) -> list[ImageCandidate]:
    url = "https://de1.api.radio-browser.info/json/stations/search?" + urllib.parse.urlencode(
        {"name": query, "limit": MAX_RESULTS, "order": "votes", "reverse": "true"}
    )
    request = urllib.request.Request(
        url,
        headers={
            # radio-browser's usage policy asks every client to identify
            # itself with a descriptive user agent.
            "User-Agent": "Simple-Streamer/1 (+https://github.com/mikehellyer/simple-streamer)"
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS, context=SSL_CONTEXT
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []

    candidates = []
    for item in payload:
        favicon = (item.get("favicon") or "").strip()
        name = item.get("name")
        if favicon and name:
            candidates.append(ImageCandidate(title=name, image_url=favicon))
    return candidates


def download_image(url: str) -> Optional[bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "Simple-Streamer/1"})
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS, context=SSL_CONTEXT
        ) as response:
            return response.read()
    except OSError:
        return None


def guess_extension(url: str) -> str:
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    known = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp", ".svg"}
    return suffix if suffix in known else DEFAULT_IMAGE_EXTENSION


@dataclass(frozen=True)
class FetchedImage:
    title: str
    image_bytes: bytes
    extension: str


def validate_local_image(path: Path) -> Optional[str]:
    """Return an error message if `path` isn't a usable local image to
    import, or None if it's fine. Doesn't check the file actually decodes
    as an image — core has no Qt to check that with — just the cheap,
    Qt-free checks (extension, size) worth doing before that.
    """
    if path.suffix.lower() not in ALLOWED_LOCAL_IMAGE_EXTENSIONS:
        allowed = ", ".join(ext.lstrip(".").upper() for ext in ALLOWED_LOCAL_IMAGE_EXTENSIONS)
        return f"Unsupported file type “{path.suffix or path.name}”. Use one of: {allowed}."

    try:
        size = path.stat().st_size
    except OSError:
        return "Couldn't read that file."

    if size > MAX_LOCAL_IMAGE_BYTES:
        return (
            f"That file is {size / 1_048_576:.1f} MB — please use an image "
            f"under {MAX_LOCAL_IMAGE_BYTES // 1_048_576} MB."
        )

    return None


def search_and_fetch(category: str, query: str) -> list[FetchedImage]:
    """Search, then download every candidate's image — the one call this
    app's background-thread helper needs, so the GUI thread never blocks
    on either step.
    """
    fetched = []
    for candidate in search_images(category, query):
        image_bytes = download_image(candidate.image_url)
        if image_bytes:
            fetched.append(
                FetchedImage(
                    title=candidate.title,
                    image_bytes=image_bytes,
                    extension=guess_extension(candidate.image_url),
                )
            )
    return fetched
