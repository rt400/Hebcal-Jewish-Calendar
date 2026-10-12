"""Data update coordinator for Hebcal integration."""
import asyncio
import datetime
from datetime import timedelta
import json
import logging
import socket
from typing import Dict, Any

import aiofiles
import aiohttp
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
from .event_processor import EventProcessor
from .helpers import CoordinatorHelpers
from .offline_engine import OfflineJewishCalendar

_LOGGER = logging.getLogger(__name__)


class HebcalDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching, caching, and processing Hebcal data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        try:
            super().__init__(
                hass,
                _LOGGER,
                name=DOMAIN,
                update_interval=UPDATE_INTERVAL,
            )
        except RuntimeError:
            import homeassistant.helpers.update_coordinator as uc
            uc.DataUpdateCoordinator.__init__(self, hass, _LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)

        self.entry = entry
        self.config_path = hass.config.path(f"custom_components/{DOMAIN}/")

        self.local_timezone = None
        self.last_full_update = None
        self.last_date_checked = None
        self.daily_update_listener = None
        self.is_first_update = True
        self.retry_count = 0
        self.max_retries = 3

        # Load user configuration parameters
        self.latitude = entry.data[CONF_LATITUDE]
        self.longitude = entry.data[CONF_LONGITUDE]
        self.timezone = entry.data[CONF_TIME_ZONE]

        self.havdalah_minutes = self._get_config_value(CONF_HAVDALAH_MINUTES, DEFAULT_HAVDALAH_MINUTES)
        self.candle_minutes = 40 if self._get_config_value(CONF_JERUSALEM_CANDLE, DEFAULT_JERUSALEM_CANDLE) else 18
        self.tzeit_hakochavim = self._get_config_value(CONF_TZEIT_HAKOCHAVIM, DEFAULT_TZEIT_HAKOCHAVIM)
        self.diaspora_mode = self._get_config_value(CONF_DIASPORA, DEFAULT_DIASPORA)
        self.language = self._get_config_value(CONF_LANGUAGE, DEFAULT_LANGUAGE)

        # Allow user to force the integration to run strictly via the local offline engine
        self.is_offline_only = self._get_config_value("offline_mode", False)

        # Initialize the local offline calculation engine (Fallback / Offline-only)
        self.offline_engine = OfflineJewishCalendar(
            latitude=self.latitude,
            longitude=self.longitude,
            timezone=self.timezone,
            diaspora=self.diaspora_mode,
            candle_minutes=self.candle_minutes,
            havdalah_minutes=self.havdalah_minutes,
            language=self.language
        )

        # Initialize the online components (Zmanim calculation and Event Processor)
        from .zmanim_calculator import ZmanimCalculator
        import hdate
        offline_loc = hdate.Location(
            latitude=self.latitude, 
            longitude=self.longitude, 
            timezone=self.timezone,
            diaspora=self.diaspora_mode
        )
        self.zmanim_calc = ZmanimCalculator(offline_loc, self.candle_minutes, self.havdalah_minutes)
        self.event_processor = EventProcessor(self.zmanim_calc, self.language)

    def _get_config_value(self, key: str, default: Any) -> Any:
        """Retrieve a configuration value, prioritizing options over initial data."""
        return self.entry.options.get(key, self.entry.data.get(key, default))

    async def async_setup(self) -> None:
        """Set up the coordinator, schedule daily updates, and perform the initial data fetch."""
        _LOGGER.info("Setting up Hebcal coordinator")
        self._schedule_daily_update()
        await self._perform_initial_update()

    def _schedule_daily_update(self) -> None:
        """Schedule a background task to refresh data at midnight every day."""
        if self.daily_update_listener:
            self.daily_update_listener()
        self.daily_update_listener = async_track_time_change(
            self.hass, self._daily_update_callback, hour=0, minute=0, second=0
        )

    async def _daily_update_callback(self, now: datetime.datetime) -> None:
        """Callback triggered at midnight to enforce a data refresh."""
        self.retry_count = 0
        await self.async_request_refresh()

    async def _perform_initial_update(self) -> None:
        """Trigger the first data fetch upon integration load."""
        self.is_first_update = True
        self.retry_count = 0
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """
        Main update logic:
        1. Calculate 40 days of offline data in the background (as a safety net).
        2. If 'offline_mode' is True, skip API and map offline data directly.
        3. Attempt to fetch live data from the Hebcal API.
        4. If the API fails (network error, timeout), fallback to the local offline engine seamlessly.
        """
        now = datetime.datetime.now()
        today = now.date()

        # Step 1: Build the offline database in the background for 40 days ahead
        offline_db = {}
        try:
            offline_db = await self.hass.async_add_executor_job(
                self.offline_engine.build_local_database, today, 40
            )
            await self._save_offline_db_to_file(offline_db)
        except Exception as e:
            _LOGGER.debug("Failed to build offline DB in the background: %s", e)

        needs_full_update = self._needs_full_update(today, now)

        # Prevent unnecessary rapid API calls if a full update isn't required yet
        if not needs_full_update and not self.is_first_update and self.data:
            self.data["update_time"] = datetime.datetime.now()
            return self.data

        # Step 2: Handle strict offline mode
        if self.is_offline_only and offline_db:
            _LOGGER.debug("Operating in OFFLINE-ONLY mode. Using local engine.")
            mapped_data = self._map_offline_to_ha(offline_db, today, now)
            await self._save_data_to_file(mapped_data)
            return mapped_data

        # Step 3: Attempt to fetch data from Hebcal API
        try:
            data = await self._full_api_update(today)
            self.retry_count = 0
            self.is_first_update = False
            return data

        # Step 4: Fallback to the Offline engine if the network or API fails
        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError, Exception) as err:
            _LOGGER.warning("Hebcal API unavailable (%s). Falling back to OFFLINE engine!", err)
            if offline_db:
                mapped_data = self._map_offline_to_ha(offline_db, today, now)
                await self._save_data_to_file(mapped_data)
                return mapped_data
            else:
                try:
                    # Last resort: load stale data from the local JSON cache
                    return await self._load_data_from_file()
                except Exception:
                    raise UpdateFailed("All updates and fallbacks failed. Cannot retrieve Hebcal data.")

    def _map_offline_to_ha(self, offline_db: dict, today: datetime.date, now: datetime.datetime) -> dict:
        """
        Mapper Function:
        Translates the structural output of the independent OfflineJewishCalendar
        into the exact dictionary format expected by the Home Assistant sensors.
        """
        tomorrow = today + timedelta(days=1)
        # Strip timezone info to prevent comparison crashes between aware and naive datetimes
        now_naive = now.replace(tzinfo=None)

        processed = {
            "update_time": now,
            "shabbat_in": None,
            "shabbat_out": None,
            "yomtov_in": None,
            "yomtov_out": None,
            "parasha": None,
            "events": [],
            "hebrew_date": {"today": {}, "tomorrow": {}},
            "zmanim": {},
            "zmanim_tomorrow": {},
            "holidays": [],
            "rosh_hashana": False,
            "special_holiday": False,
            "data_source": "offline_engine"
        }

        # Map daily Zmanim and Hebrew Dates
        for day in offline_db.get("days", []):
            try:
                day_dt = datetime.date.fromisoformat(day["date"])
                if day_dt == today:
                    processed["zmanim"] = day.get("zmanim", {})
                    processed["hebrew_date"]["today"] = {"hebrew": day.get("hebrew_date"), "english": ""}
                    holiday_text = day.get("holiday") or ""
                    
                    if holiday_text:
                        # הוספת האירוע למערך שהחיישן קורא (פותר את באג ראש חודש/אירועים)
                        for event_name in holiday_text.split(", "):
                            if event_name not in processed["events"]:
                                processed["events"].append(event_name)
                                
                        # Check for specific major holidays
                        if "ראש השנה" in holiday_text or "Rosh Hashana" in holiday_text:
                            processed["rosh_hashana"] = True
                        else:
                            processed["special_holiday"] = True
                        
                elif day_dt == tomorrow:
                    processed["zmanim_tomorrow"] = day.get("zmanim", {})
                    processed["hebrew_date"]["tomorrow"] = {"hebrew": day.get("hebrew_date"), "english": ""}
            except Exception:
                pass

        # Map upcoming Shabbat times and Parasha
        for shabbat in offline_db.get("shabbatot", []):
            if not shabbat.get("entry") or not shabbat.get("exit"): 
                continue
            try:
                # Strip timezones from the parsed ISO strings to match `now_naive`
                s_in = datetime.datetime.fromisoformat(shabbat["entry"].replace('Z', '+00:00')).replace(tzinfo=None)
                s_out = datetime.datetime.fromisoformat(shabbat["exit"].replace('Z', '+00:00')).replace(tzinfo=None)
                
                # We only care about the *next* or *current* Shabbat
                if s_out >= now_naive:
                    processed["shabbat_in"] = s_in
                    processed["shabbat_out"] = s_out
                    processed["parasha"] = shabbat.get("name")
                    break
            except Exception:
                pass

        # Map upcoming Yom Tov (Holidays)
        for hol in offline_db.get("holidays", []):
            if not hol.get("entry") or not hol.get("exit"): 
                continue
            try:
                # Strip timezones
                h_in = datetime.datetime.fromisoformat(hol["entry"].replace('Z', '+00:00')).replace(tzinfo=None)
                h_out = datetime.datetime.fromisoformat(hol["exit"].replace('Z', '+00:00')).replace(tzinfo=None)
                
                processed["holidays"].append({
                    "name": hol.get("name"),
                    "date": hol.get("start_date"),
                    "yomtov_in": h_in,
                    "yomtov_out": h_out
                })
                
                # Set the primary Yom Tov sensors to the nearest upcoming holiday
                if h_out >= now_naive and not processed["yomtov_in"]:
                    processed["yomtov_in"] = h_in
                    processed["yomtov_out"] = h_out
            except Exception:
                pass

        # Finally, calculate the Issur Melacha (Work Prohibition) period using the mapped data
        processed["isur_melacha"] = calculate_isur_melacha_period(processed, self.language)
        return processed

    def _needs_full_update(self, today: datetime.date, now: datetime.datetime) -> bool:
        """Determine if a full API request is necessary based on elapsed time or date change."""
        if not self.data or not self.last_full_update: 
            return True
        if self.last_date_checked != today: 
            return True
        if now - self.last_full_update > FULL_UPDATE_INTERVAL: 
            return True
        return False

    async def _full_api_update(self, today: datetime.date) -> dict[str, Any]:
        """Fetch primary data directly from the Hebcal API over the network."""
        self.last_full_update = datetime.datetime.now()
        self.last_date_checked = today

        await self._set_local_timezone()
        start_date, end_date = self._get_date_range(today)

        timeout = aiohttp.ClientTimeout(total=20)

        # Critical Fix: Bypass aiohttp's internal DNS resolver bug on Windows/IPv6 environments
        # by forcing it to use the OS's native threaded resolver and IPv4.
        resolver = aiohttp.ThreadedResolver()
        connector = aiohttp.TCPConnector(resolver=resolver, family=socket.AF_INET)

        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            # Construct the static, safe Hebcal URL
            i_param = "off" if self.diaspora_mode else "on"
            lg_param = "h" if CoordinatorHelpers.is_hebrew(self.language) else "a"

            url = (
                f"https://www.hebcal.com/hebcal/?v=1&cfg=json&maj=on&min=on&nx=on&mf=on&ss=on&mod=on&s=on&c=on&o=on"
                f"&geo=pos&lg={lg_param}&start={start_date}&end={end_date}"
                f"&latitude={self.latitude}&longitude={self.longitude}&tzid={self.timezone}&b={self.candle_minutes}&i={i_param}"
            )

            # Append Havdalah offset if Tzeit Hakochavim calculation is disabled
            if not self.tzeit_hakochavim and self.havdalah_minutes:
                url += f"&m={self.havdalah_minutes}"

            _LOGGER.info("Fetching data from Hebcal API: %s", url)

            headers = {"User-Agent": f"HomeAssistant-Hebcal/{VERSION}"}
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                hebcal_data = await response.json()
                hebcal_data["request_url"] = url
                
                # Clean up Hebrew text encoding/formatting issues directly from the JSON
                if "items" in hebcal_data:
                    hebcal_data["items"] = [EventProcessor.clean_item_text(item) for item in hebcal_data["items"]]

            # Calculate local Zmanim and Hebrew Dates using the online integration's calculator
            zmanim_today = self.zmanim_calc.fetch_zmanim_data(today)
            tomorrow = today + datetime.timedelta(days=1)
            zmanim_tomorrow = self.zmanim_calc.fetch_zmanim_data(tomorrow)

            hebrew_date_data = {
                "today": self.zmanim_calc.fetch_hebrew_date(today),
                "tomorrow": self.zmanim_calc.fetch_hebrew_date(tomorrow),
            }

            # Initialize the processed data template
            processed = {
                "request_url": url,
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
                "data_source": "online_api"
            }

            # Map the parsed API events into the local data structure
            for item in hebcal_data.get("items", []):
                self.event_processor.process_hebcal_item(item, processed)

            # Ensure any missing candle lighting or havdalah times are populated
            self.event_processor.complete_missing_times(processed, self.havdalah_minutes, self.candle_minutes)
            
            # Calculate Issur Melacha based on the fully mapped API data
            processed["isur_melacha"] = calculate_isur_melacha_period(processed, self.language)

            # Cache the successful API fetch to the disk
            await self._save_data_to_file(processed)
            return processed

    async def _set_local_timezone(self) -> None:
        """Resolve and set the local timezone utilizing Home Assistant's zone info."""
        try:
            self.local_timezone = await async_get_time_zone(self.timezone)
        except Exception:
            self.local_timezone = None

    def _get_date_range(self, date: datetime.date) -> tuple[datetime.date, datetime.date]:
        """Calculate the current week's boundaries (Sunday to Sunday) for the API request."""
        days_since_sunday = date.isoweekday() % 7
        start_date = date - datetime.timedelta(days=days_since_sunday)
        end_date = start_date + datetime.timedelta(days=8)
        return start_date, end_date

    async def _save_data_to_file(self, data: dict[str, Any]) -> None:
        """Cache the compiled HA sensor data to a local JSON file."""
        try:
            import os
            os.makedirs(self.config_path, exist_ok=True)
            file_path = f"{self.config_path}hebcal_data_{self.entry.entry_id}.json"
            serializable_data = CoordinatorHelpers.make_serializable(data)
            async with aiofiles.open(file_path, "w", encoding="utf-8") as file:
                await file.write(json.dumps(serializable_data, ensure_ascii=False, indent=2))
        except Exception as e:
            _LOGGER.debug("Failed to save HA data cache: %s", e)

    async def _load_data_from_file(self) -> dict[str, Any]:
        """Load fallback HA sensor data from the local JSON cache."""
        try:
            file_path = f"{self.config_path}hebcal_data_{self.entry.entry_id}.json"
            async with aiofiles.open(file_path, "r", encoding="utf-8") as file:
                content = await file.read()
                data = json.loads(content)
            return CoordinatorHelpers.deserialize_data(data)
        except Exception:
            raise

    async def _save_offline_db_to_file(self, offline_db: dict) -> None:
        """Save the raw Offline Engine database to a JSON file for debugging and transparency."""
        try:
            import os
            os.makedirs(self.config_path, exist_ok=True)
            file_path = f"{self.config_path}hebcal_offline_db_{self.entry.entry_id}.json"
            async with aiofiles.open(file_path, "w", encoding="utf-8") as file:
                await file.write(json.dumps(offline_db, ensure_ascii=False, indent=2))
        except Exception as e:
            _LOGGER.debug("Failed to save offline DB file: %s", e)

    async def async_shutdown(self) -> None:
        """Cleanup task listeners upon coordinator shutdown."""
        if self.daily_update_listener:
            self.daily_update_listener()
            self.daily_update_listener = None
        await super().async_shutdown()

    @property
    def is_shabbat_active(self) -> bool:
        """Check if it is currently Shabbat based on localized boundaries."""
        if not self.data: return False
        now = datetime.datetime.now()
        shabbat_in = self.data.get("shabbat_in")
        shabbat_out = self.data.get("shabbat_out")
        if shabbat_in and shabbat_out: 
            return shabbat_in <= now <= shabbat_out
        return False

    @property
    def is_yomtov_active(self) -> bool:
        """Check if it is currently Yom Tov based on localized boundaries."""
        if not self.data: return False
        now = datetime.datetime.now()
        yomtov_in = self.data.get("yomtov_in")
        yomtov_out = self.data.get("yomtov_out")
        
        # Check specific mapped holidays
        for holiday in self.data.get("holidays", []):
            if holiday.get("yomtov_in") and holiday.get("yomtov_out"):
                if holiday["yomtov_in"] <= now <= holiday["yomtov_out"]: 
                    return True
                    
        # Check global flags
        if yomtov_in and yomtov_out: 
            return yomtov_in <= now <= yomtov_out
        return False

    @property
    def next_candle_lighting(self) -> datetime.datetime | None:
        """Retrieve the datetime of the absolute nearest future candle lighting event."""
        if not self.data: return None
        now = datetime.datetime.now()
        candidates = []
        if self.data.get("shabbat_in") and self.data["shabbat_in"] > now: 
            candidates.append(self.data["shabbat_in"])
        if self.data.get("yomtov_in") and self.data["yomtov_in"] > now: 
            candidates.append(self.data["yomtov_in"])
        for h in self.data.get("holidays", []):
            if h.get("yomtov_in") and h["yomtov_in"] > now: 
                candidates.append(h["yomtov_in"])
                
        return min(candidates) if candidates else None

    @property
    def next_havdalah(self) -> datetime.datetime | None:
        """Retrieve the datetime of the absolute nearest future havdalah event."""
        if not self.data: return None
        now = datetime.datetime.now()
        candidates = []
        if self.data.get("shabbat_out") and self.data["shabbat_out"] > now: 
            candidates.append(self.data["shabbat_out"])
        if self.data.get("yomtov_out") and self.data["yomtov_out"] > now: 
            candidates.append(self.data["yomtov_out"])
        for h in self.data.get("holidays", []):
            if h.get("yomtov_out") and h["yomtov_out"] > now: 
                candidates.append(h["yomtov_out"])
                
        return min(candidates) if candidates else None

    def get_time_until_event(self, event_time: datetime.datetime | None) -> timedelta | None:
        """Calculate the remaining duration until a specific datetime."""
        if not event_time: return None
        now = datetime.datetime.now()
        if event_time <= now: return None
        return event_time - now

    def format_time_delta(self, delta: timedelta) -> str:
        """Format a timedelta object into a localized human-readable string."""
        return CoordinatorHelpers.format_time_delta(delta, self.language)

    @property
    def isur_melacha_period(self) -> Dict[str, Any]:
        """Fetch the pre-calculated Issur Melacha payload."""
        if not self.data or "isur_melacha" not in self.data:
            return {'active': False, 'start': None, 'end': None, 'type': 'no_data', 'duration_hours': 0}
        return self.data["isur_melacha"]

    def get_time_until_isur_melacha_start(self) -> timedelta | None:
        seconds = self.isur_melacha_period.get('time_until_start')
        return timedelta(seconds=seconds) if seconds and seconds > 0 else None

    def get_time_until_isur_melacha_end(self) -> timedelta | None:
        seconds = self.isur_melacha_period.get('time_until_end')
        return timedelta(seconds=seconds) if seconds and seconds > 0 else None

    def format_isur_melacha_status(self) -> str:
        return self.isur_melacha_period.get('status_text', 'Unknown')

    def get_isur_melacha_type_description(self) -> str:
        return self.isur_melacha_period.get('type_description', 'Unknown')
