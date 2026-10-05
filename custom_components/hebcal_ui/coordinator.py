"""Data update coordinator for Hebcal integration."""
import asyncio
import datetime
from datetime import timedelta
import json
import logging
from typing import Dict, Any

import aiofiles
import aiohttp
import hdate
from aiozoneinfo import async_get_time_zone

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_TIME_ZONE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.event import async_track_time_change

from .const import (
    DOMAIN,
    VERSION,
    UPDATE_INTERVAL,
    FULL_UPDATE_INTERVAL,
    CONF_HAVDALAH_MINUTES,
    CONF_TIME_BEFORE_CHECK,
    CONF_TIME_AFTER_CHECK,
    CONF_JERUSALEM_CANDLE,
    CONF_TZEIT_HAKOCHAVIM,
    CONF_DIASPORA,
    CONF_USE_12H_TIME,
    CONF_OMER_COUNT_TYPE,
    CONF_LANGUAGE,
    HEBCAL_DATE_URL,
    HEBCAL_DATE_URL_HAVDALAH,
    LANGUAGE_DATA,
    DEFAULT_HAVDALAH_MINUTES,
    DEFAULT_TIME_BEFORE_CHECK,
    DEFAULT_TIME_AFTER_CHECK,
    DEFAULT_JERUSALEM_CANDLE,
    DEFAULT_TZEIT_HAKOCHAVIM,
    DEFAULT_DIASPORA,
    DEFAULT_USE_12H_TIME,
    DEFAULT_OMER_COUNT_TYPE,
    DEFAULT_LANGUAGE,
)

from .isur_melacha import calculate_isur_melacha_period
from .zmanim_calculator import ZmanimCalculator
from .event_processor import EventProcessor
from .helpers import CoordinatorHelpers

_LOGGER = logging.getLogger(__name__)


class HebcalDataUpdateCoordinator(DataUpdateCoordinator[dict[str, any]]):
    """Class to manage fetching, caching, and processing Hebcal data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the coordinator with configurations and helper instances."""
        try:
            super().__init__(
                hass,
                _LOGGER,
                name=DOMAIN,
                update_interval=UPDATE_INTERVAL,
            )
        except RuntimeError:
            import homeassistant.helpers.update_coordinator as uc
            uc.DataUpdateCoordinator.__init__(
                self,
                hass,
                _LOGGER,
                name=DOMAIN,
                update_interval=UPDATE_INTERVAL,
            )

        self.entry = entry
        self.config_path = hass.config.path(f"custom_components/{DOMAIN}/")

        self.local_timezone = None
        self.last_full_update = None
        self.last_date_checked = None
        self.daily_update_listener = None
        self.is_first_update = True

        self.retry_count = 0
        self.max_retries = 5
        self.retry_intervals = [60, 300, 900, 1800, 3600]

        self.latitude = entry.data[CONF_LATITUDE]
        self.longitude = entry.data[CONF_LONGITUDE]
        self.timezone = entry.data[CONF_TIME_ZONE]

        self.havdalah_minutes = self._get_config_value(CONF_HAVDALAH_MINUTES, DEFAULT_HAVDALAH_MINUTES)
        self.time_before_check = self._get_config_value(CONF_TIME_BEFORE_CHECK, DEFAULT_TIME_BEFORE_CHECK)
        self.time_after_check = self._get_config_value(CONF_TIME_AFTER_CHECK, DEFAULT_TIME_AFTER_CHECK)
        self.jerusalem_candle = self._get_config_value(CONF_JERUSALEM_CANDLE, DEFAULT_JERUSALEM_CANDLE)
        self.tzeit_hakochavim = self._get_config_value(CONF_TZEIT_HAKOCHAVIM, DEFAULT_TZEIT_HAKOCHAVIM)
        self.diaspora_mode = self._get_config_value(CONF_DIASPORA, DEFAULT_DIASPORA)
        self.use_12h_time = self._get_config_value(CONF_USE_12H_TIME, DEFAULT_USE_12H_TIME)
        self.omer_count_type = self._get_config_value(CONF_OMER_COUNT_TYPE, DEFAULT_OMER_COUNT_TYPE)
        self.language = self._get_config_value(CONF_LANGUAGE, DEFAULT_LANGUAGE)

        self.candle_minutes = 40 if self.jerusalem_candle else 18

        self.offline_hebcal = hdate.Location(
            latitude=self.latitude,
            longitude=self.longitude,
            timezone=self.timezone,
            diaspora=self.diaspora_mode
        )

        # Initialize helper modules
        self.zmanim_calc = ZmanimCalculator(self.offline_hebcal, self.candle_minutes, self.havdalah_minutes)
        self.event_processor = EventProcessor(self.zmanim_calc)

    async def async_setup(self) -> None:
        """Set up the coordinator, schedule daily refreshes, and trigger initial update."""
        _LOGGER.info("Setting up Hebcal coordinator")
        self._schedule_daily_update()
        await self._perform_initial_update()

    def _schedule_daily_update(self) -> None:
        """Schedule a routine background update at midnight every day."""
        if self.daily_update_listener:
            self.daily_update_listener()

        self.daily_update_listener = async_track_time_change(
            self.hass,
            self._daily_update_callback,
            hour=0,
            minute=0,
            second=0
        )

    async def _daily_update_callback(self, now: datetime.datetime):
        """Reset retry counters and request data refresh upon midnight trigger."""
        self.retry_count = 0
        await self.async_request_refresh()

    async def _perform_initial_update(self):
        """Perform the first data synchronization."""
        self.is_first_update = True
        self.retry_count = 0
        await self.async_request_refresh()

    def _get_config_value(self, key: str, default: any) -> any:
        """Retrieve a specific configuration value from options or data entries."""
        return self.entry.options.get(key, self.entry.data.get(key, default))

    async def _async_update_data(self) -> dict[str, any]:
        """Fetch data from API if needed, otherwise fallback to cache or quick update."""
        now = datetime.datetime.now()
        today = now.date()

        try:
            needs_full_update = self._needs_full_update(today, now)
            if needs_full_update or self.is_first_update:
                data = await self._full_api_update(today)
                self.retry_count = 0
                self.is_first_update = False
                return data
            else:
                return await self._quick_local_update()
        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError):
            return await self._handle_network_error()
        except Exception:
            return await self._handle_general_error()

    async def _handle_network_error(self) -> dict[str, any]:
        """Handle network failures by attempting to load from local cache files."""
        try:
            cached_data = await self._load_data_from_file()
            if cached_data:
                if self.retry_count < self.max_retries:
                    self._schedule_retry()
                return cached_data
        except Exception:
            pass

        if self.retry_count < self.max_retries:
            self._schedule_retry()
            raise UpdateFailed(f"Network error, retry scheduled in {self.retry_intervals[self.retry_count]} seconds")
        else:
            self.retry_count = 0
            raise UpdateFailed("Network unavailable and max retries exceeded")

    async def _handle_general_error(self) -> dict[str, any]:
        """Handle general errors by trying to serve cached data."""
        try:
            cached_data = await self._load_data_from_file()
            if cached_data:
                return cached_data
        except Exception:
            pass
        raise UpdateFailed("Update failed and no cached data available")

    def _schedule_retry(self):
        """Schedule a background retry attempt using exponential intervals."""
        if self.retry_count < self.max_retries:
            retry_delay = self.retry_intervals[self.retry_count]
            self.retry_count += 1

            async def retry_update(_):
                await self.async_request_refresh()

            self.hass.loop.call_later(retry_delay, lambda: asyncio.create_task(retry_update(None)))

    def _needs_full_update(self, today: datetime.date, now: datetime.datetime):
        """Determine whether a full HTTP API query is required."""
        if not self.data or not self.last_full_update:
            return True
        if self.last_date_checked != today:
            return True
        if now - self.last_full_update > FULL_UPDATE_INTERVAL:
            return True
        return False

    async def _full_api_update(self, today: datetime.date) -> dict[str, any]:
        """Perform a full fetch cycle from Hebcal API and local Zmanim engine."""
        self.last_full_update = datetime.datetime.now()
        self.last_date_checked = today

        await self._set_local_timezone()
        start_date, end_date = self._get_date_range(today)

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            hebcal_data = await self._fetch_hebcal_data(session, start_date, end_date)
            zmanim_today = self.zmanim_calc.fetch_zmanim_data(today)

        tomorrow = today + datetime.timedelta(days=1)
        zmanim_tomorrow = self.zmanim_calc.fetch_zmanim_data(tomorrow)
        hebrew_date_today = self.zmanim_calc.fetch_hebrew_date(today)
        hebrew_date_tomorrow = self.zmanim_calc.fetch_hebrew_date(tomorrow)
        hebrew_date_data = {
            "today": hebrew_date_today,
            "tomorrow": hebrew_date_tomorrow,
        }

        processed_data = await self._process_data(hebcal_data, zmanim_today, zmanim_tomorrow, hebrew_date_data)
        await self._save_data_to_file(processed_data)
        return processed_data

    async def _quick_local_update(self) -> dict[str, any]:
        """Perform a fast local state update without hitting the external web API."""
        if self.data:
            self.data["update_time"] = datetime.datetime.now()
            return self.data
        else:
            return await self._full_api_update(datetime.datetime.now().date())

    async def _set_local_timezone(self):
        """Resolve and assign local timezone object."""
        try:
            self.local_timezone = await async_get_time_zone(self.timezone)
        except Exception:
            self.local_timezone = None

    def _get_date_range(self, date: datetime.date):
        """Calculate date range padding from Sunday to Sunday."""
        days_since_sunday = date.isoweekday() % 7
        start_date = date - datetime.timedelta(days=days_since_sunday)
        end_date = start_date + datetime.timedelta(days=8)
        return start_date, end_date

    async def _fetch_hebcal_data(
            self, session: aiohttp.ClientSession, start_date: datetime.date, end_date: datetime.date
    ) -> dict[str, any]:
        """Download raw JSON event payloads from the official Hebcal web service."""
        diaspora_param = "off" if self.diaspora_mode else "on"
        language_code = LANGUAGE_DATA[self.language]["code"]

        if self.tzeit_hakochavim:
            url = HEBCAL_DATE_URL.format(
                language_code, start_date, end_date,
                self.latitude, self.longitude, self.timezone,
                self.candle_minutes, diaspora_param
            )
        else:
            url = HEBCAL_DATE_URL_HAVDALAH.format(
                language_code, start_date, end_date,
                self.latitude, self.longitude, self.timezone,
                self.havdalah_minutes, self.candle_minutes, diaspora_param
            )

        headers = {"User-Agent": f"HomeAssistant-Hebcal/{VERSION}"}
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            data = await response.json()
            data["request_url"] = url
            if "items" in data:
                data["items"] = [EventProcessor.clean_item_text(item) for item in data["items"]]
            return data

    async def _process_data(
            self, hebcal_data: Dict[str, Any], zmanim_today: Dict[str, Any], zmanim_tomorrow: Dict[str, Any],
            hebrew_date_data: Dict[str, Any]
    ) -> dict[str, any]:
        """Process raw API data and compile a structured dictionary ready for Home Assistant."""
        processed = {
            "request_url": hebcal_data.get("request_url", ""),
            "update_time": datetime.datetime.now(),
            "shabbat_in": None,
            "shabbat_out": None,
            "yomtov_in": None,
            "yomtov_out": None,
            "parasha": None,
            "events": [],
            "omer_day": None,
            "hebrew_date": hebrew_date_data,
            "zmanim": zmanim_today,
            "zmanim_tomorrow": zmanim_tomorrow,
            "holidays": [],
            "rosh_hashana": False,
            "special_holiday": False,
            "raw_items": hebcal_data.get("items", []),
        }

        for item in hebcal_data.get("items", []):
            self.event_processor.process_hebcal_item(item, processed)

        self.event_processor.complete_missing_times(processed, self.havdalah_minutes, self.candle_minutes)
        processed["isur_melacha"] = calculate_isur_melacha_period(self, processed)
        return processed

    async def _save_data_to_file(self, data: dict[str, any]):
        """Save processed state dictionary locally as a JSON cache file."""
        try:
            import os
            os.makedirs(self.config_path, exist_ok=True)
            file_path = f"{self.config_path}hebcal_data_{self.entry.entry_id}.json"
            serializable_data = CoordinatorHelpers.make_serializable(data)
            async with aiofiles.open(file_path, "w", encoding="utf-8") as file:
                await file.write(json.dumps(serializable_data, ensure_ascii=False, indent=2))
        except Exception:
            pass

    async def _load_data_from_file(self) -> dict[str, any]:
        """Load and deserialize state dictionary from the local JSON cache file."""
        try:
            file_path = f"{self.config_path}hebcal_data_{self.entry.entry_id}.json"
            async with aiofiles.open(file_path, "r", encoding="utf-8") as file:
                content = await file.read()
                data = json.loads(content)
            return CoordinatorHelpers.deserialize_data(data)
        except FileNotFoundError:
            raise
        except Exception:
            raise

    async def async_shutdown(self):
        """Clean up background listeners upon coordinator shutdown."""
        if self.daily_update_listener:
            self.daily_update_listener()
            self.daily_update_listener = None
        await super().async_shutdown()

    @property
    def is_shabbat_active(self) -> bool:
        """Check if Shabbat is currently active."""
        if not self.data:
            return False
        now = datetime.datetime.now()
        shabbat_in = self.data.get("shabbat_in")
        shabbat_out = self.data.get("shabbat_out")
        if shabbat_in and shabbat_out:
            return shabbat_in <= now <= shabbat_out
        return False

    @property
    def is_yomtov_active(self) -> bool:
        """Check if Yom Tov is currently active."""
        if not self.data:
            return False
        now = datetime.datetime.now()
        yomtov_in = self.data.get("yomtov_in")
        yomtov_out = self.data.get("yomtov_out")

        for holiday in self.data.get("holidays", []):
            if holiday.get("yomtov_in") and holiday.get("yomtov_out"):
                if holiday["yomtov_in"] <= now <= holiday["yomtov_out"]:
                    return True
        if yomtov_in and yomtov_out:
            return yomtov_in <= now <= yomtov_out
        return False

    @property
    def next_candle_lighting(self) -> datetime.datetime | None:
        """Find the next upcoming candle lighting datetime."""
        if not self.data:
            return None
        now = datetime.datetime.now()
        candidates = []

        shabbat_in = self.data.get("shabbat_in")
        if shabbat_in and shabbat_in > now:
            candidates.append(shabbat_in)

        yomtov_in = self.data.get("yomtov_in")
        if yomtov_in and yomtov_in > now:
            candidates.append(yomtov_in)

        for holiday in self.data.get("holidays", []):
            if holiday.get("yomtov_in") and holiday["yomtov_in"] > now:
                candidates.append(holiday["yomtov_in"])

        return min(candidates) if candidates else None

    @property
    def next_havdalah(self) -> datetime.datetime | None:
        """Find the next upcoming havdalah datetime."""
        if not self.data:
            return None
        now = datetime.datetime.now()
        candidates = []

        shabbat_out = self.data.get("shabbat_out")
        if shabbat_out and shabbat_out > now:
            candidates.append(shabbat_out)

        yomtov_out = self.data.get("yomtov_out")
        if yomtov_out and yomtov_out > now:
            candidates.append(yomtov_out)

        for holiday in self.data.get("holidays", []):
            if holiday.get("yomtov_out") and holiday["yomtov_out"] > now:
                candidates.append(holiday["yomtov_out"])

        return min(candidates) if candidates else None

    def get_time_until_event(self, event_time: datetime.datetime | None) -> timedelta | None:
        """Calculate time duration until a specific future event."""
        if not event_time:
            return None
        now = datetime.datetime.now()
        if event_time <= now:
            return None
        return event_time - now

    def format_time_delta(self, delta: timedelta) -> str:
        """Format a timedelta object into a readable English string representation."""
        return CoordinatorHelpers.format_time_delta(delta)
        
    @property
    def isur_melacha_period(self) -> Dict[str, Any]:
        """Return the complete isur melacha period dictionary."""
        if not self.data or "isur_melacha" not in self.data:
            return {'active': False, 'start': None, 'end': None, 'type': 'no_data', 'duration_hours': 0}
        return self.data["isur_melacha"]

    @property
    def isur_melacha_active(self) -> bool:
        """Return whether isur melacha is currently active."""
        period = self.isur_melacha_period
        return period.get('active', False)

    @property
    def isur_melacha_start(self) -> datetime.datetime | None:
        """Return the start datetime of the isur melacha period."""
        period = self.isur_melacha_period
        start_dt = period.get('start')
        return start_dt if isinstance(start_dt, datetime.datetime) else None

    @property
    def isur_melacha_end(self) -> datetime.datetime | None:
        """Return the end datetime of the isur melacha period."""
        period = self.isur_melacha_period
        end_dt = period.get('end')
        return end_dt if isinstance(end_dt, datetime.datetime) else None

    @property
    def isur_melacha_type(self) -> str:
        """Return the type of the isur melacha period."""
        period = self.isur_melacha_period
        return period.get('type', 'none')

    @property
    def isur_melacha_duration(self) -> float:
        """Return the duration of the isur melacha period in hours."""
        period = self.isur_melacha_period
        return period.get('duration_hours', 0)

    def get_time_until_isur_melacha_start(self) -> timedelta | None:
        """Calculate time until the next isur melacha starts."""
        period = self.isur_melacha_period
        seconds = period.get('time_until_start')
        return timedelta(seconds=seconds) if seconds and seconds > 0 else None

    def get_time_until_isur_melacha_end(self) -> timedelta | None:
        """Calculate time until the current isur melacha ends."""
        period = self.isur_melacha_period
        seconds = period.get('time_until_end')
        return timedelta(seconds=seconds) if seconds and seconds > 0 else None

    def format_isur_melacha_status(self) -> str:
        """Return the formatted Hebrew status of the isur melacha period."""
        period = self.isur_melacha_period
        return period.get('status_hebrew', 'אין איסור מלאכה')

    def get_isur_melacha_type_description(self) -> str:
        """Return the Hebrew description of the isur melacha type."""
        period = self.isur_melacha_period
        return period.get('type_hebrew', 'אין איסור מלאכה')
