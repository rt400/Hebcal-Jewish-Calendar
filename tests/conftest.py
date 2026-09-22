"""Test harness for the Hebcal data path.

The integration's data path (`processing`, `event_processors`, `isur_melacha`) is
pure apart from two inputs: the Hebcal calendar JSON and the offline `hdate`
calculations. Both are deterministic here -- calendar responses are recorded in
`tests/fixtures/`, and `hdate` is the version pinned in `manifest.json` -- so the
tests need no network and no Home Assistant.
"""
import datetime
import importlib.abc
import importlib.util
import json
import pathlib
import sys
import types
from datetime import timedelta

import hdate
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "hebcal_ui"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

# Fixtures were recorded at this location, with b=18.
LAT, LON, TZ = 40.7128, -74.0060, "America/New_York"


def _is_dunder(name):
    return name.startswith("__") and name.endswith("__")


class _StubMeta(type):
    """Metaclass for stub classes: synthesises attributes and allows subscripting.

    Covers `Platform.SENSOR` (class attribute access) and
    `DataUpdateCoordinator[dict[str, any]]` (generic subscripting) alike.
    """

    def __getattr__(cls, name):
        if _is_dunder(name):
            raise AttributeError(name)
        value = _StubMeta(name, (), {})
        setattr(cls, name, value)
        return value

    def __getitem__(cls, item):
        return cls


class _Permissive(types.ModuleType):
    """Stands in for Home Assistant: any attribute resolves to a throwaway class."""

    def __getattr__(self, name):
        # Dunders must stay absent: the import machinery probes __path__ and
        # friends, and handing it a class breaks module resolution.
        if _is_dunder(name):
            raise AttributeError(name)
        value = _StubMeta(name, (), {"__init__": lambda self, *a, **kw: None})
        setattr(self, name, value)
        return value


_STUB_ROOTS = ("homeassistant", "aiohttp", "aiofiles", "aiozoneinfo", "voluptuous")


class _StubFinder(importlib.abc.MetaPathFinder):
    """Resolves any import under _STUB_ROOTS to a permissive stub module.

    A fixed list of submodule names goes stale every time the integration imports
    something new from Home Assistant, so synthesise them on demand instead.
    """

    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root not in _STUB_ROOTS:
            return None
        return importlib.util.spec_from_loader(fullname, _StubLoader())


class _StubLoader(importlib.abc.Loader):
    def create_module(self, spec):
        module = _Permissive(spec.name)
        module.__path__ = []          # make every stub a package
        return module

    def exec_module(self, module):
        return None


def _install_stubs():
    sys.meta_path.insert(0, _StubFinder())


def _load_component():
    package = types.ModuleType("hebcal_ui")
    package.__path__ = [str(COMPONENT)]
    sys.modules["hebcal_ui"] = package
    loaded = {}
    for name in ("const", "isur_melacha", "event_processors", "processing",
                 "coordinator", "__init__"):
        spec = importlib.util.spec_from_file_location(
            f"hebcal_ui.{name}", COMPONENT / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"hebcal_ui.{name}"] = module
        setattr(package, name, module)
        spec.loader.exec_module(module)
        loaded[name] = module
    return loaded


_install_stubs()
MODULES = _load_component()


class FakeCoordinator:
    """The subset of HebcalDataUpdateCoordinator that the data path calls.

    `get_offline_missing_time` and `sunset_time` mirror coordinator.py; keeping
    them here rather than importing the coordinator avoids pulling in aiohttp and
    the Home Assistant config-entry machinery.
    """

    def __init__(self, israel_mode, language="hebrew"):
        # The integration's attribute is named diaspora_mode, but setting it sends
        # Hebcal i=on, which selects the Israel schedule. Tests say israel_mode so
        # the intent stays readable; hdate then takes its negation.
        self.latitude, self.longitude, self.timezone = LAT, LON, TZ
        self.diaspora_mode = israel_mode
        self.candle_minutes = 18
        self.language = language
        self.use_12h_time = False
        self.next_candle_lighting = None
        self.next_havdalah = None
        self.offline_hebcal = hdate.Location(
            latitude=LAT, longitude=LON, timezone=TZ, diaspora=not israel_mode)

    def get_offline_missing_time(self, date, type_calculation, days):
        target = date + timedelta(days=days)
        zmanim = hdate.Zmanim(date=target.date(), location=self.offline_hebcal)
        value = None
        if type_calculation == "havdalah":
            value = zmanim.havdalah
            if value is None:
                value = (zmanim.zmanim.get("tset_hakohavim_shabbat").local
                         if target.weekday() == 4 else zmanim.candle_lighting)
        elif type_calculation == "candles":
            value = zmanim.candle_lighting
        return value.replace(tzinfo=None) if value is not None else None

    def get_sunset_time(self, date, day_offset=0):
        target = date + timedelta(days=day_offset)
        return hdate.Zmanim(date=target,
                            location=self.offline_hebcal).zmanim.get("shkia").local

    def sunset_time(self, date_str, day_offset):
        date = datetime.datetime.fromisoformat(date_str[:19]).date()
        return self.get_sunset_time(date, day_offset).isoformat()

    def format_time_delta(self, delta):
        return str(delta)


def week_range(date):
    """Sunday..Saturday window, matching coordinator._get_week_range."""
    start = date - timedelta(days=(date.weekday() + 1) % 7)
    return start, start + timedelta(days=6)


def load_fixture(start, end, language, israel_mode):
    lg = "h" if language == "hebrew" else "s"
    i = "on" if israel_mode else "off"
    path = FIXTURES / f"hebcal_{start}_{end}_lg-{lg}_i-{i}.json"
    if not path.exists():
        pytest.skip(f"no recorded fixture: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def freeze(now):
    """Pin datetime.date.today() and datetime.datetime.now() in the data path."""
    class _Date(datetime.date):
        @classmethod
        def today(cls):
            return now.date()

    class _DateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    shim = types.SimpleNamespace(date=_Date, datetime=_DateTime, timedelta=timedelta)
    for module in ("processing", "isur_melacha", "event_processors"):
        MODULES[module].datetime = shim
