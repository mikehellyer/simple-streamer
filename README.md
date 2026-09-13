# Simple-Streamer

A simple internet radio and podcast player for Linux, macOS, and Windows.

## Status

Early scaffold. The Radio and Podcasts tabs each have 10 preset slots you can
assign a name + stream URL to (right-click a slot, or click an empty one).
Holding **F1** shows a legend overlaying the grid with what every slot is
tuned to. Playback goes through Qt's multimedia engine, so any direct
audio-stream URL works; podcast RSS-feed browsing isn't wired up yet.

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

- `src/simple_streamer/core/` — preset store and update checker; plain
  Python, no Qt dependency, covered by `tests/`.
- `src/simple_streamer/gui/` — the PySide6 window and widgets.
- `src/simple_streamer/app.py` — entry point.

## Updates

On startup the app checks the repo's latest GitHub Release in the
background and, if a newer version is published, shows a note in the status
bar — it never downloads or installs anything automatically. Unreachable
GitHub just means no note; it never blocks or errors the app.
