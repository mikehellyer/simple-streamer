import subprocess
from unittest.mock import patch, MagicMock

from simple_streamer.core.browser_raise import try_raise_browser_window


def test_does_nothing_off_linux():
    with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_run:
        try_raise_browser_window()
    mock_run.assert_not_called()


def test_stops_at_the_first_matching_browser():
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        matched = args[2] == "firefox"
        return MagicMock(returncode=0 if matched else 1)

    with patch("sys.platform", "linux"), patch("subprocess.run", side_effect=fake_run):
        try_raise_browser_window()

    assert [c[2] for c in calls] == ["microsoft-edge", "msedge", "firefox"]


def test_gives_up_quietly_when_wmctrl_is_not_installed():
    with patch("sys.platform", "linux"), patch(
        "subprocess.run", side_effect=FileNotFoundError("wmctrl not found")
    ) as mock_run:
        try_raise_browser_window()  # must not raise
    assert mock_run.call_count == 1


def test_gives_up_quietly_on_timeout():
    with patch("sys.platform", "linux"), patch(
        "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="wmctrl", timeout=2)
    ):
        try_raise_browser_window()  # must not raise


def test_gives_up_quietly_when_no_browser_matches():
    with patch("sys.platform", "linux"), patch(
        "subprocess.run", return_value=MagicMock(returncode=1)
    ) as mock_run:
        try_raise_browser_window()
    assert mock_run.call_count == 5  # tried every known browser name, found none
