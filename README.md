# Simple-Streamer

A simple internet radio and podcast player for Linux, macOS, and Windows.

## Status

The Radio and Podcasts tabs each have 20 preset slots you can assign a name +
URL to (right-click a slot, or click an empty one) — Radio ships with BBC,
talkSPORT, LBC, Planet Rock, Manx Radio, and Sportsnet 590 as starter presets,
and Podcasts ships with a few shows. Holding **F1** shows a legend overlaying
the grid with what every slot is tuned to. Playback goes through Qt's
multimedia engine: Radio slots take a direct stream URL, Podcast slots take
an RSS feed URL and always play whatever that show's latest episode is.

## Development setup

```bash
python3 -m venv venv
source venv/bin/activate   # on Windows: venv\Scripts\activate
pip install -e ".[dev]" 2>/dev/null || pip install -r requirements-dev.txt
```

Run the app:

```bash
python -m simple_streamer.app
```

Run the tests (core logic only — no display required):

```bash
pytest
```

## Project layout

- `src/simple_streamer/core/` — preset store, podcast/pls resolvers, and the
  update checker; plain Python, no Qt dependency, covered by `tests/`.
- `src/simple_streamer/gui/` — the PySide6 window and widgets.
- `src/simple_streamer/app.py` — entry point.
- `packaging/` — the PyInstaller spec and per-OS installer scripts (see
  Releasing, below).

## Updates

On startup the app checks the repo's latest GitHub Release in the
background and, if a newer version is published, shows a note in the status
bar — it never downloads or installs anything automatically. Unreachable
GitHub just means no note; it never blocks or errors the app.

## Releasing

1. Bump `__version__` in `src/simple_streamer/__init__.py`.
2. Commit, then tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. The [release workflow](.github/workflows/release.yml) builds all three
   platforms and attaches the installers to a GitHub Release for that tag:
   - **Windows**: PyInstaller → Inno Setup → `Simple-Streamer-X.Y.Z-Windows-Setup.exe`
   - **macOS**: PyInstaller → `.app` → `Simple-Streamer-X.Y.Z-macOS.dmg`
   - **Linux**: PyInstaller → `simple-streamer_X.Y.Z_amd64.deb`

To build one platform's installer locally (must run on that OS):

```bash
pip install -r requirements-dev.txt
pyinstaller --noconfirm packaging/pyinstaller/simple-streamer.spec
# then, per platform:
bash packaging/macos/build-dmg.sh      # macOS
bash packaging/linux/build-deb.sh      # Linux
iscc packaging/windows/installer.iss   # Windows (Inno Setup installed)
```
