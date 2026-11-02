"""A weekly listening schedule: which preset to play when.

Radio items run from a start time to an end time on the chosen days.
Podcast items are listening appointments: at their start time the newest
unfinished episode plays, and once it ends whatever radio is scheduled at
that moment takes over again.

When items overlap, the one that started most recently wins — so a 2pm
podcast appointment interrupts a 1:45–4pm radio slot, and the radio comes
back when the episode finishes.

Items remember the station itself (label + URL), not a slot number, so
moving or renaming presets doesn't break the schedule (see
MainWindow._find_preset_for). The schedule's on/off state isn't stored
here: it's off every time the app starts.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
WEEKDAYS = (0, 1, 2, 3, 4)
WEEKEND = (5, 6)
# A podcast appointment with no later item and no radio slot around it
# still has to stop counting as "on now" at some point — otherwise
# switching the schedule on late in the evening would start that
# afternoon's episode.
PODCAST_FALLBACK_WINDOW_MINUTES = 60


def parse_time(text: str) -> int:
    """'13:45' -> minutes after midnight."""
    hours, _, minutes = text.partition(":")
    value = int(hours) * 60 + int(minutes)
    if not 0 <= value < 24 * 60:
        raise ValueError(f"not a time of day: {text!r}")
    return value


def format_time(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def describe_days(days: list[int]) -> str:
    chosen = sorted(set(days))
    if chosen == list(range(7)):
        return "Every day"
    if chosen == list(WEEKDAYS):
        return "Mon–Fri"
    if chosen == list(WEEKEND):
        return "Sat–Sun"
    return ", ".join(DAY_NAMES[d] for d in chosen)


@dataclass
class ScheduleItem:
    days: list[int]  # 0 = Monday … 6 = Sunday
    start: str  # "HH:MM"
    category: str  # "radio" or "podcasts"
    label: str
    url: str
    end: str = ""  # "HH:MM"; radio items only
    note: str = ""
    enabled: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def start_minutes(self) -> int:
        return parse_time(self.start)

    @property
    def end_minutes(self) -> int:
        return parse_time(self.end)

    def validate(self) -> None:
        """Raise ValueError describing the first problem, if any."""
        if self.category not in ("radio", "podcasts"):
            raise ValueError("Choose a preset to play.")
        if not self.days or not all(0 <= d <= 6 for d in self.days):
            raise ValueError("Choose at least one day.")
        start = parse_time(self.start)
        if self.category == "radio" and parse_time(self.end) <= start:
            raise ValueError("The end time has to be after the start time (same day).")
        if not self.url:
            raise ValueError("Choose a preset to play.")


@dataclass(frozen=True)
class Occurrence:
    """One day's run of an item — a podcast appointment is finished per day."""

    item_id: str
    day: date


def current_item(
    items: list[ScheduleItem], now: datetime, finished: set[Occurrence]
) -> Optional[ScheduleItem]:
    """The item that should be playing at `now`, or None for nothing."""
    minutes = now.hour * 60 + now.minute
    todays = [i for i in items if i.enabled and now.weekday() in i.days]
    candidates = []
    for item in todays:
        if item.start_minutes > minutes:
            continue
        if item.category == "radio":
            if minutes < item.end_minutes:
                candidates.append(item)
        elif Occurrence(item.id, now.date()) not in finished:
            if minutes < _podcast_window_end(item, todays):
                candidates.append(item)
    # Latest start wins; on a tie, the podcast appointment.
    return max(
        candidates,
        key=lambda i: (i.start_minutes, i.category == "podcasts"),
        default=None,
    )


def _podcast_window_end(item: ScheduleItem, todays: list[ScheduleItem]) -> int:
    """When a not-yet-finished podcast appointment stops being "on now":
    the next item starting after it, or the end of the radio slot it
    interrupts, whichever comes first.
    """
    start = item.start_minutes
    limits = [i.start_minutes for i in todays if i.start_minutes > start]
    limits += [
        i.end_minutes
        for i in todays
        if i.category == "radio" and i.start_minutes <= start < i.end_minutes
    ]
    return min(limits, default=start + PODCAST_FALLBACK_WINDOW_MINUTES)


def next_start(items: list[ScheduleItem], now: datetime) -> Optional[tuple[datetime, ScheduleItem]]:
    """The next time an enabled item starts, within the coming week."""
    today = now.replace(second=0, microsecond=0)
    minutes = now.hour * 60 + now.minute
    for offset in range(8):
        day = today + timedelta(days=offset)
        starts = sorted(
            (i for i in items if i.enabled and day.weekday() in i.days),
            key=lambda i: i.start_minutes,
        )
        for item in starts:
            if offset == 0 and item.start_minutes <= minutes:
                continue
            at = day.replace(hour=item.start_minutes // 60, minute=item.start_minutes % 60)
            return at, item
    return None


def sorted_items(items: list[ScheduleItem]) -> list[ScheduleItem]:
    """Display order: by first day, then start time."""
    return sorted(items, key=lambda i: (min(i.days, default=7), i.start_minutes, i.label))


def item_to_dict(item: ScheduleItem) -> dict:
    return asdict(item)


def item_from_dict(raw) -> ScheduleItem:
    """Build and validate an item from saved/exported data; ValueError if unusable."""
    try:
        item = ScheduleItem(
            days=[int(d) for d in raw["days"]],
            start=str(raw["start"]),
            category=str(raw["category"]),
            label=str(raw.get("label", "")),
            url=str(raw["url"]),
            end=str(raw.get("end", "")),
            note=str(raw.get("note", "")),
            enabled=bool(raw.get("enabled", True)),
            id=str(raw.get("id") or uuid.uuid4().hex),
        )
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("not a schedule item") from exc
    item.validate()
    return item


class ScheduleStore:
    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or Path(user_config_dir("Simple-Streamer")) / "schedule.json"
        self.items: list[ScheduleItem] = []
        self.load()

    @property
    def exists(self) -> bool:
        return self._config_path.exists()

    def load(self) -> None:
        if not self._config_path.exists():
            return
        try:
            data = json.loads(self._config_path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        items = []
        for raw in data.get("items", []) if isinstance(data, dict) else []:
            try:
                items.append(item_from_dict(raw))
            except ValueError:
                continue  # skip one bad item rather than lose the schedule
        self.items = items

    def save(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"items": [item_to_dict(item) for item in self.items]}
        self._config_path.write_text(json.dumps(data, indent=2))
