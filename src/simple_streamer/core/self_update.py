"""Downloading and launching an update, once the user has asked for it.

Simple-Streamer never does this on its own — check_for_update() only ever
notifies. Everything here only runs after an explicit "Update" click.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

DOWNLOAD_TIMEOUT_SECONDS = 30


def _installer_suffix() -> str:
    if sys.platform == "win32":
        return ".exe"
    if sys.platform == "darwin":
        return ".dmg"
    return ".deb"


def find_asset_for_this_platform(assets: list[tuple[str, str]]) -> Optional[str]:
    """Return the download URL of the release asset built for this OS, if any."""
    suffix = _installer_suffix()
    for name, download_url in assets:
        if name.lower().endswith(suffix):
            return download_url
    return None


def download_asset(url: str) -> Optional[Path]:
    """Download a release asset to a fresh temp directory. None on failure."""
    filename = url.rsplit("/", 1)[-1] or "simple-streamer-update"
    dest_dir = Path(tempfile.mkdtemp(prefix="simple-streamer-update-"))
    dest_path = dest_dir / filename

    request = urllib.request.Request(url, headers={"User-Agent": "Simple-Streamer/1"})
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            with open(dest_path, "wb") as out_file:
                shutil.copyfileobj(response, out_file)
    except OSError:
        return None
    return dest_path


def launch_installer(path: Path) -> bool:
    """Hand the downloaded installer off to the OS. True if it was launched."""
    try:
        if sys.platform == "win32":
            subprocess.Popen([str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        return False
    return True
