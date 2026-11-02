from datetime import datetime

import pytest

from simple_streamer.core.schedule import (
    Occurrence,
    ScheduleItem,
    ScheduleStore,
    WEEKDAYS,
    current_item,
    describe_days,
    next_start,
)

SIX = "https://example.com/6music"
R4 = "https://example.com/radio4"
R3 = "https://example.com/radio3"

# 2026-11-02 is a Monday.
MONDAY = (2026, 11, 2)
TUESDAY = (2026, 11, 3)
SATURDAY = (2026, 11, 7)


def at(day, hhmm):
    hours, minutes = map(int, hhmm.split(":"))
    return datetime(*day, hours, minutes)


def radio(label, url, start, end, days=WEEKDAYS, enabled=True):
    return ScheduleItem(list(days), start, "radio", label, url, end=end, enabled=enabled)


def podcast(label, day, start="14:00"):
    return ScheduleItem([day], start, "podcasts", label, f"https://example.com/{label}.rss")


@pytest.fixture
def weekday_routine():
    return [
        radio("Grimmy", SIX, "09:00", "10:00"),
        radio("Lauren Laverne", SIX, "10:00", "13:00"),
        radio("World at One", R4, "13:00", "13:45"),
        radio("Craig Charles", SIX, "13:45", "16:00"),
        radio("Radio 3", R3, "16:00", "17:00"),
        radio("PM", R4, "17:00", "17:30", enabled=False),
        podcast("More or Less", 0),
        podcast("Infinite Monkey Cage", 1),
    ]


def label_at(items, when, finished=frozenset()):
    item = current_item(items, when, set(finished))
    return item.label if item else None


def test_radio_slots_follow_the_clock(weekday_routine):
    assert label_at(weekday_routine, at(MONDAY, "08:59")) is None
    assert label_at(weekday_routine, at(MONDAY, "09:00")) == "Grimmy"
    assert label_at(weekday_routine, at(MONDAY, "11:20")) == "Lauren Laverne"
    assert label_at(weekday_routine, at(MONDAY, "13:44")) == "World at One"
    assert label_at(weekday_routine, at(MONDAY, "16:30")) == "Radio 3"


def test_nothing_after_the_last_slot_and_disabled_items_are_skipped(weekday_routine):
    assert label_at(weekday_routine, at(MONDAY, "17:05")) is None  # PM is unticked


def test_the_days_podcast_interrupts_the_afternoon_music(weekday_routine):
    assert label_at(weekday_routine, at(MONDAY, "13:50")) == "Craig Charles"
    assert label_at(weekday_routine, at(MONDAY, "14:00")) == "More or Less"
    assert label_at(weekday_routine, at(TUESDAY, "14:00")) == "Infinite Monkey Cage"


def test_music_resumes_once_the_episode_has_finished(weekday_routine):
    more_or_less = next(i for i in weekday_routine if i.label == "More or Less")
    done = {Occurrence(more_or_less.id, datetime(*MONDAY).date())}
    assert label_at(weekday_routine, at(MONDAY, "14:31"), done) == "Craig Charles"
    # …but finishing Monday's doesn't count for next Monday.
    assert label_at(weekday_routine, at((2026, 11, 9), "14:00"), done) == "More or Less"


def test_an_unfinished_podcast_appointment_doesnt_outlast_its_afternoon(weekday_routine):
    # Never got round to Monday's episode: by 4pm it's Radio 3's turn,
    # and switching the schedule on at 9pm must not start it either.
    assert label_at(weekday_routine, at(MONDAY, "16:00")) == "Radio 3"
    assert label_at(weekday_routine, at(MONDAY, "21:00")) is None


def test_a_lone_podcast_appointment_gets_a_bounded_window():
    items = [podcast("The News Quiz", 4, start="20:00")]
    friday = (2026, 11, 6)
    assert label_at(items, at(friday, "20:30")) == "The News Quiz"
    assert label_at(items, at(friday, "21:00")) is None


def test_weekday_items_dont_run_at_the_weekend(weekday_routine):
    assert label_at(weekday_routine, at(SATURDAY, "11:00")) is None


def test_next_start_finds_the_next_change(weekday_routine):
    when, item = next_start(weekday_routine, at(MONDAY, "11:20"))
    assert (when.hour, when.minute, item.label) == (13, 0, "World at One")
    # Friday evening rolls over the weekend to Monday morning.
    when, item = next_start(weekday_routine, at((2026, 11, 6), "18:00"))
    assert (when.date().isoformat(), item.label) == ("2026-11-09", "Grimmy")


def test_validate_rejects_bad_items():
    with pytest.raises(ValueError):
        radio("Backwards", SIX, "10:00", "09:00").validate()
    with pytest.raises(ValueError):
        ScheduleItem([], "10:00", "radio", "No days", SIX, end="11:00").validate()
    with pytest.raises(ValueError):
        radio("Bad time", SIX, "25:00", "26:00").validate()
    podcast("Fine without an end", 0).validate()


def test_describe_days():
    assert describe_days([0, 1, 2, 3, 4]) == "Mon–Fri"
    assert describe_days([5, 6]) == "Sat–Sun"
    assert describe_days([6, 0]) == "Mon, Sun"


def test_store_round_trips_and_skips_a_damaged_item(tmp_path):
    path = tmp_path / "schedule.json"
    store = ScheduleStore(path)
    store.items = [radio("Lauren Laverne", SIX, "10:00", "13:00"), podcast("More or Less", 0)]
    store.save()
    raw = path.read_text().replace('"start": "14:00"', '"start": "not a time"')
    path.write_text(raw)

    reloaded = ScheduleStore(path)

    assert [i.label for i in reloaded.items] == ["Lauren Laverne"]
    assert reloaded.items[0].id == store.items[0].id
