"""The schedule the coordinator requests, and the one it gives hdate.

These exercise `coordinator.py` directly rather than the data path, so the `i=`
mapping and the hdate flag are covered by something other than inspection.

The stored option is named `diaspora`, but setting it sends Hebcal `i=on`, which
selects the *Israel* schedule -- so it is really an "Israel mode" flag. That is
what the translations now say, and these tests pin the behaviour so the wording
and the code cannot drift apart again.
"""
import asyncio
import urllib.parse

import hdate
import pytest

from conftest import MODULES

coordinator_module = MODULES["coordinator"]
Coordinator = coordinator_module.HebcalDataUpdateCoordinator


class _FakeResponse:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    async def json(self):
        return {"items": []}


class _CapturingSession:
    """Records the URL the coordinator asks for."""

    def __init__(self):
        self.url = None

    def get(self, url, headers=None):
        self.url = url
        return _FakeResponse()


def _bare_coordinator(diaspora_mode):
    """A coordinator carrying only what _fetch_hebcal_data reads.

    __init__ needs a hass and a ConfigEntry, so bypass it.
    """
    coordinator = Coordinator.__new__(Coordinator)
    coordinator.diaspora_mode = diaspora_mode
    coordinator.tzeit_hakochavim = True
    coordinator.havdalah_minutes = 42
    coordinator.candle_minutes = 18
    coordinator.language = "english"
    coordinator.latitude = 40.7128
    coordinator.longitude = -74.0060
    coordinator.timezone = "America/New_York"
    return coordinator


def _requested_i(diaspora_mode):
    session = _CapturingSession()
    coordinator = _bare_coordinator(diaspora_mode)
    asyncio.new_event_loop().run_until_complete(
        coordinator._fetch_hebcal_data(session, "2026-09-27", "2026-10-03"))
    query = urllib.parse.parse_qs(urllib.parse.urlparse(session.url).query)
    return query["i"][0]


def test_option_set_requests_the_israel_calendar():
    """Setting the option sends i=on, which Hebcal reads as Israel."""
    assert _requested_i(True) == "on"


def test_option_unset_requests_the_diaspora_calendar():
    """Left unset -- the default -- the Diaspora calendar is requested."""
    assert _requested_i(False) == "off"


@pytest.mark.parametrize("diaspora_mode,expected_hdate_diaspora", [
    (False, True),    # Diaspora calendar requested -> hdate must agree
    (True, False),    # Israel calendar requested   -> hdate must agree
])
def test_hdate_agrees_with_the_requested_calendar(diaspora_mode, expected_hdate_diaspora):
    """The offline fallbacks must use the same schedule as the fetch.

    hdate returns no Saturday candle lighting on the Israel schedule, so a
    mismatch here silently loses the second day of Yom Tov.
    """
    location = hdate.Location(latitude=40.7128, longitude=-74.0060,
                              timezone="America/New_York",
                              diaspora=not diaspora_mode)
    assert location.diaspora is expected_hdate_diaspora


def test_israel_schedule_has_no_saturday_night_sukkot_onset():
    """Why the flag matters: the two schedules disagree about 2026-09-26."""
    common = dict(latitude=40.7128, longitude=-74.0060, timezone="America/New_York")
    israel = hdate.Zmanim(date=__import__("datetime").date(2026, 9, 26),
                          location=hdate.Location(diaspora=False, **common))
    diaspora = hdate.Zmanim(date=__import__("datetime").date(2026, 9, 26),
                            location=hdate.Location(diaspora=True, **common))
    assert israel.candle_lighting is None
    assert diaspora.candle_lighting is not None
