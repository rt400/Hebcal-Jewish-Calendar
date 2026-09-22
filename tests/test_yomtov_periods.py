"""Yom Tov / Issur Melacha coverage for Tishrei 5787.

Tishrei 5787 is worth pinning because it exercises every awkward shape at once:

  * Rosh Hashana I on Shabbat (2026-09-12), a two-day Yom Tov entered from Shabbat
    with no Havdalah inside the window;
  * Yom Kippur on a Monday (2026-09-21), which puts 10 and 15 Tishrei in the same
    Sunday..Saturday window as the Saturday-night Sukkot onset;
  * Sukkot II ending on a Sunday (2026-09-27) in the same window that Shmini
    Atzeret begins on Saturday night (2026-10-03).

Each of those is a case where the single yomtov_in/yomtov_out pair has to choose,
and choosing wrongly leaves the sensors off during an actual Yom Tov.
"""
import asyncio
import datetime

import pytest

from conftest import (MODULES, FakeCoordinator, freeze, load_fixture, week_range)

processing = MODULES["processing"]

TIME_BEFORE_CHECK = TIME_AFTER_CHECK = 10


def evaluate(now, israel_mode=False, language="hebrew"):
    """Run one coordinator refresh at `now` and report the three sensor states."""
    start, end = week_range(now.date())
    items = load_fixture(start, end, language, israel_mode)
    freeze(now)
    coordinator = FakeCoordinator(israel_mode, language)
    data = asyncio.new_event_loop().run_until_complete(
        processing.process_data(coordinator, {"items": items}, {"times": {}}, {}))

    def active(kind):
        if kind == "issur":
            period = data.get("isur_melacha") or {}
            start_time, end_time = period.get("start"), period.get("end")
        else:
            start_time, end_time = data.get(f"{kind}_in"), data.get(f"{kind}_out")
            if start_time and end_time:
                start_time -= datetime.timedelta(minutes=TIME_BEFORE_CHECK)
                end_time += datetime.timedelta(minutes=TIME_AFTER_CHECK)
        if not start_time or not end_time:
            return False
        return start_time <= now <= end_time

    return data, {k: active(k) for k in ("shabbat", "yomtov", "issur")}


def dt(*args):
    return datetime.datetime(*args)


# (moment, description, expected issur_melacha)
ISSUR_CASES = [
    (dt(2026, 9, 11, 19, 30), "Rosh Hashana I eve (also Shabbat)", True),
    (dt(2026, 9, 12, 12, 0), "Rosh Hashana I (also Shabbat)", True),
    (dt(2026, 9, 12, 21, 0), "Rosh Hashana II begins", True),
    (dt(2026, 9, 13, 12, 0), "Rosh Hashana II", True),
    (dt(2026, 9, 13, 21, 0), "after Rosh Hashana havdalah", False),
    (dt(2026, 9, 16, 12, 0), "ordinary weekday", False),
    (dt(2026, 9, 21, 12, 0), "Yom Kippur", True),
    (dt(2026, 9, 23, 12, 0), "ordinary weekday", False),
    (dt(2026, 9, 25, 19, 30), "Sukkot I eve (also Shabbat)", True),
    (dt(2026, 9, 26, 12, 0), "Sukkot I (also Shabbat)", True),
    (dt(2026, 9, 26, 21, 0), "Sukkot II begins", True),
    (dt(2026, 9, 27, 12, 0), "Sukkot II", True),
    (dt(2026, 9, 27, 21, 0), "after Sukkot II havdalah", False),
    (dt(2026, 10, 3, 21, 0), "Simchat Torah begins", True),
    (dt(2026, 10, 4, 12, 0), "Simchat Torah", True),
    (dt(2026, 10, 4, 21, 0), "after Simchat Torah havdalah", False),
    (dt(2026, 10, 6, 12, 0), "ordinary weekday", False),
]


@pytest.mark.parametrize("language", ["hebrew", "english"])
@pytest.mark.parametrize("now,description,expected", ISSUR_CASES,
                         ids=[c[1].replace(" ", "-") for c in ISSUR_CASES])
def test_issur_melacha(now, description, expected, language):
    """Issur Melacha must be on for every moment work is prohibited, and off otherwise."""
    _data, state = evaluate(now, israel_mode=False, language=language)
    assert state["issur"] is expected, description


@pytest.mark.parametrize("language", ["hebrew", "english"])
def test_rosh_hashana_on_shabbat_keeps_its_period(language):
    """Regression: Rosh Hashana I on Shabbat must not lose its Yom Tov period.

    The Friday candle lighting sets yomtov_in while yomtov_out is still unknown,
    and the Saturday candle lighting sets special_holiday. Treating that shape as
    a free slot overwrites an in-progress Yom Tov and leaves yomtov_out unset,
    because the Rosh Hashana recompute then targets an ordinary Monday.
    """
    data, state = evaluate(dt(2026, 9, 12, 12, 0), israel_mode=False, language=language)

    assert data["yomtov_in"] is not None
    assert data["yomtov_out"] is not None, "yomtov_out was cleared and never replaced"
    assert data["yomtov_in"] < data["yomtov_out"], "inverted pair can never be active"
    assert data["yomtov_in"].date() == datetime.date(2026, 9, 11)
    assert state["yomtov"] is True


def test_yom_kippur_and_sukkot_share_a_window():
    """Yom Kippur must survive the Saturday-night Sukkot onset in the same window."""
    data, state = evaluate(dt(2026, 9, 21, 12, 0))
    assert state["yomtov"] is True
    assert data["yomtov_in"].date() == datetime.date(2026, 9, 20)
    assert data["yomtov_out"].date() == datetime.date(2026, 9, 21)


def test_sukkot_second_day_survives_shmini_atzeret_onset():
    """Sukkot II ends Sunday; Shmini Atzeret begins Saturday night, same window."""
    data, state = evaluate(dt(2026, 9, 27, 12, 0))
    assert state["yomtov"] is True
    assert data["yomtov_in"] < data["yomtov_out"], "inverted pair can never be active"
    assert data["yomtov_out"].date() == datetime.date(2026, 9, 27)


def test_data_path_distinguishes_the_two_schedules():
    """A two-day calendar yields Yom Tov on Sukkot II; a one-day calendar does not.

    This covers the data path only. Which calendar gets requested is decided by
    the `i=` mapping in coordinator.py and is covered by test_diaspora_handling.
    """
    _data, diaspora = evaluate(dt(2026, 9, 27, 12, 0), israel_mode=False)
    _data, israel = evaluate(dt(2026, 9, 27, 12, 0), israel_mode=True)
    assert diaspora["issur"] is True
    assert israel["issur"] is False


@pytest.mark.parametrize("now,description,_expected", ISSUR_CASES,
                         ids=[c[1].replace(" ", "-") for c in ISSUR_CASES])
def test_pair_is_never_inverted(now, description, _expected):
    """yomtov_in after yomtov_out makes `start <= now <= end` unsatisfiable."""
    data, _state = evaluate(now)
    if data.get("yomtov_in") and data.get("yomtov_out"):
        assert data["yomtov_in"] < data["yomtov_out"], description
