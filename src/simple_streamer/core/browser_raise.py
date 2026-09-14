"""Best-effort nudge to bring an already-running browser to the front.

Opening a URL (QDesktopServices.openUrl, which just calls xdg-open under
the hood on Linux) reliably gets a new tab opened in the browser, but
restoring/raising the window if it's minimized is the window manager's
job — some Linux desktop environments deliberately suppress that
("focus-stealing prevention") for a request that didn't come with a
proper activation token, which a plain xdg-open call doesn't carry. This
isn't something openUrl (or Qt) can force; macOS doesn't have the same
problem since its window-activation model works differently.

This tries `wmctrl`, a common Linux utility for exactly this, against a
handful of common browser identifiers. If wmctrl isn't installed, or
none of the names match, it just does nothing — never worse than before.
"""
from __future__ import annotations

import subprocess
import sys

_BROWSER_NAMES = ("microsoft-edge", "msedge", "firefox", "chromium", "google-chrome")


def try_raise_browser_window() -> None:
    if sys.platform != "linux":
        return
    for name in _BROWSER_NAMES:
        try:
            result = subprocess.run(
                ["wmctrl", "-a", name], capture_output=True, timeout=2
            )
        except (OSError, subprocess.TimeoutExpired):
            return  # wmctrl isn't installed (or something else went wrong) — give up quietly
        if result.returncode == 0:
            return  # found and raised a matching window
