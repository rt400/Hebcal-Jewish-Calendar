"""Data update coordinator for Hebcal integration."""
import asyncio
import datetime
from datetime import timedelta
import json
import logging
from typing import Dict, Any, Coroutine
import re

import aiofiles
import aiohttp
import hdate
from hdate.translator import set_language
from aiozoneinfo import async_get_time_zone
from hdate.zmanim import Zman
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_TIME_ZONE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.event import async_track_time_change
from .const import (
    DOMAIN,
    UPDATE_INTERVAL,
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

_LOGGER = logging.getLogger(__name__)


class HebcalDataUpdateCoordinator(DataUpdateCoordinator[dict[str, any]]):
    """
    Class to manage fetching and processing Hebcal data.

    This coordinator handles:
    - Fetching data from Hebcal API (calendar events, zmanim, Hebrew dates)
    - Processing and structuring the data for Home Assistant entities
    - Smart caching and retry mechanisms
    - Daily automatic updates and manual refresh capabilities
    - Backup data storage for offline functionality
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """
        Initialize the Hebcal data coordinator.

        Args:
            hass: Home Assistant instance
            entry: Configuration entry containing user settings
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )

        # Core configuration
        self.entry = entry
        self.config_path = hass.config.path(f"custom_components/{DOMAIN}/")

        # State tracking
        self.local_timezone = None
        self.last_full_update = None
        self.last_date_checked = None
        self.daily_update_listener = None
        self.is_first_update = True

        # Retry mechanism configuration
        self.retry_count = 0
        self.max_retries = 5
        self.retry_intervals = [60, 300, 900, 1800, 3600]  # Progressive delays: 1min, 5min, 15min, 30min, 1hour

        # Location settings
        self.latitude = entry.data[CONF_LATITUDE]
        self.longitude = entry.data[CONF_LONGITUDE]
        self.timezone = entry.data[CONF_TIME_ZONE]

        # User preferences (with fallbacks from entry.data to entry.options)
        self.havdalah_minutes = self._get_config_value(CONF_HAVDALAH_MINUTES, DEFAULT_HAVDALAH_MINUTES)
        self.time_before_check = self._get_config_value(CONF_TIME_BEFORE_CHECK, DEFAULT_TIME_BEFORE_CHECK)
        self.time_after_check = self._get_config_value(CONF_TIME_AFTER_CHECK, DEFAULT_TIME_AFTER_CHECK)
        self.jerusalem_candle = self._get_config_value(CONF_JERUSALEM_CANDLE, DEFAULT_JERUSALEM_CANDLE)
        self.tzeit_hakochavim = self._get_config_value(CONF_TZEIT_HAKOCHAVIM, DEFAULT_TZEIT_HAKOCHAVIM)
        self.diaspora_mode = self._get_config_value(CONF_DIASPORA, DEFAULT_DIASPORA)
        self.use_12h_time = self._get_config_value(CONF_USE_12H_TIME, DEFAULT_USE_12H_TIME)
        self.omer_count_type = self._get_config_value(CONF_OMER_COUNT_TYPE, DEFAULT_OMER_COUNT_TYPE)
        self.language = self._get_config_value(CONF_LANGUAGE, DEFAULT_LANGUAGE)

        # Calculated settings
        self.candle_minutes = 40 if self.jerusalem_candle else 18
        self.offline_hebcal = hdate.Location(latitude=self.latitude, longitude=self.longitude, timezone=self.timezone)

    async def async_setup(self) -> None:
        """
        Set up the coordinator with initial configuration.

        This method:
        1. Schedules daily updates at midnight
        2. Performs initial data fetch
        """
        _LOGGER.info("Setting up Hebcal coordinator")

        # Schedule daily update at midnight
        self._schedule_daily_update()

        # Perform initial update
        await self._perform_initial_update()

    def _schedule_daily_update(self) -> None:
        """
        Schedule automatic daily update at midnight.

        This ensures fresh data is available each day and handles
        date transitions properly.
        """
        if self.daily_update_listener:
            self.daily_update_listener()

        self.daily_update_listener = async_track_time_change(
            self.hass,
            self._daily_update_callback,
            hour=0,
            minute=0,
            second=0
        )
        _LOGGER.debug("Daily update scheduled for midnight")

    async def _daily_update_callback(self, now: datetime.datetime):
        """
        Callback executed at midnight for daily updates.

        Args:
            now: Current datetime (provided by Home Assistant)
        """
        _LOGGER.info("Performing scheduled daily update at midnight")
        self.retry_count = 0  # Reset retry count for daily update
        await self.async_request_refresh()

    async def _perform_initial_update(self):
        """
        Perform initial update on startup or integration installation.

        This ensures data is available immediately after setup.
        """
        _LOGGER.info("Performing initial update on startup")
        self.is_first_update = True
        self.retry_count = 0
        await self.async_request_refresh()

    def _get_config_value(self, key: str, default: any) -> any:
        """
        Get configuration value with fallback hierarchy.

        Priority: entry.options > entry.data > default

        Args:
            key: Configuration key to retrieve
            default: Default value if key not found

        Returns:
            Configuration value
        """
        return self.entry.options.get(key, self.entry.data.get(key, default))

    async def _async_update_data(self) -> dict[str, any]:
        """
        Main update logic with smart caching and retry mechanism.

        This method determines whether to perform a full API update
        or use cached data based on various conditions.

        Returns:
            Processed Hebcal data dictionary

        Raises:
            UpdateFailed: When update fails and no cached data available
        """
        now = datetime.datetime.now()
        today = now.date()

        try:
            # Determine update strategy
            needs_full_update = self._needs_full_update(today, now)

            if needs_full_update or self.is_first_update:
                _LOGGER.info("Performing full API update (retry count: %d)", self.retry_count)
                data = await self._full_api_update(today)
                self.retry_count = 0  # Reset retry count on success
                self.is_first_update = False
                return data
            else:
                # Use cached data with minimal processing
                _LOGGER.debug("Using cached data with local calculations")
                return await self._quick_local_update()

        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as err:
            _LOGGER.warning("Network error during update (attempt %d/%d): %s",
                            self.retry_count + 1, self.max_retries, err)
            return await self._handle_network_error()
        except Exception as err:
            _LOGGER.error("Unexpected error during update: %s", err)
            return await self._handle_general_error()

    async def _handle_network_error(self) -> dict[str, any]:
        """
        Handle network errors with progressive retry logic.

        Strategy:
        1. Try to load cached data first
        2. Schedule retry if within retry limits
        3. Fail gracefully if max retries exceeded

        Returns:
            Cached data if available

        Raises:
            UpdateFailed: When no cached data and retries exhausted
        """
        # Attempt to load cached data
        try:
            cached_data = await self._load_data_from_file()
            if cached_data:
                _LOGGER.info("Using cached data due to network error")
                # Schedule retry if we haven't exceeded max retries
                if self.retry_count < self.max_retries:
                    self._schedule_retry()
                return cached_data
        except Exception as cache_err:
            _LOGGER.warning("Could not load cached data: %s", cache_err)

        # Handle retry logic
        if self.retry_count < self.max_retries:
            self._schedule_retry()
            raise UpdateFailed(f"Network error, retry scheduled in {self.retry_intervals[self.retry_count]} seconds")
        else:
            # Max retries exceeded - reset for next cycle
            _LOGGER.error("Max retries exceeded, will try again at next scheduled update")
            self.retry_count = 0
            raise UpdateFailed("Network unavailable and max retries exceeded")

    async def _handle_general_error(self) -> dict[str, any]:
        """
        Handle general (non-network) errors.

        Returns:
            Cached data if available

        Raises:
            UpdateFailed: When no cached data available
        """
        try:
            cached_data = await self._load_data_from_file()
            if cached_data:
                _LOGGER.info("Using cached data due to processing error")
                return cached_data
        except Exception:
            pass

        raise UpdateFailed("Update failed and no cached data available")

    def _schedule_retry(self):
        """
        Schedule a retry attempt with progressive delay.

        Uses exponential backoff strategy to avoid overwhelming
        the API during outages.
        """
        if self.retry_count < self.max_retries:
            retry_delay = self.retry_intervals[self.retry_count]
            self.retry_count += 1

            _LOGGER.info("Scheduling retry %d/%d in %d seconds",
                         self.retry_count, self.max_retries, retry_delay)

            async def retry_update(_):
                await self.async_request_refresh()

            self.hass.loop.call_later(retry_delay, lambda: asyncio.create_task(retry_update(None)))

    def _needs_full_update(self, today: datetime.date, now: datetime.datetime):
        """
        Determine if a full API update is required.

        Full update is needed when:
        1. No data exists (first run)
        2. Date has changed (new day)
        3. More than 6 hours since last update
        4. Near important Shabbat/Yom Tov times

        Args:
            today: Current date
            now: Current datetime

        Returns:
            True if full update needed, False otherwise
        """
        # No data at all
        if not self.data or not self.last_full_update:
            _LOGGER.debug("Full update needed: No existing data")
            return True

        # New day has passed
        if self.last_date_checked != today:
            _LOGGER.debug("Full update needed: New day detected")
            return True

        return False

    async def _full_api_update(self, today: datetime.date) -> dict[str, any]:
        """
        Perform complete update with API calls and data processing.

        Process:
        1. Set local timezone
        2. Calculate date range (current week)
        3. Fetch data from 3 Hebcal APIs
        4. Process and structure the data
        5. Save to cache file

        Args:
            today: Current date for calculations

        Returns:
            Fully processed Hebcal data
        """
        _LOGGER.debug("Starting full API update")

        # Update tracking timestamps
        self.last_full_update = datetime.datetime.now()
        self.last_date_checked = today

        # Set up timezone and date range
        await self._set_local_timezone()
        start_date, end_date = self._get_week_range(today)

        # Fetch all required data with timeout protection
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            _LOGGER.debug("Fetching Hebcal calendar data")
            hebcal_data = await self._fetch_hebcal_data(session, start_date, end_date)

            _LOGGER.debug("Fetching Zmanim data")
            zmanim_today = self._fetch_zmanim_data(today)

        _LOGGER.debug("Fetching Hebrew date data for today and tomorrow")
        tomorrow = today + datetime.timedelta(days=1)
        zmanim_tomorrow = self._fetch_zmanim_data(tomorrow)
        hebrew_date_today = self._fetch_hebrew_date(today)
        hebrew_date_tomorrow = self._fetch_hebrew_date(tomorrow)
        hebrew_date_data = {
            "today": hebrew_date_today,
            "tomorrow": hebrew_date_tomorrow,
        }

        # Process the raw data
        _LOGGER.debug("Processing fetched data")
        processed_data = await self._process_data(hebcal_data, zmanim_today, zmanim_tomorrow, hebrew_date_data)

        # Save to cache for offline use
        await self._save_data_to_file(processed_data)

        _LOGGER.info("Full API update completed successfully")
        return processed_data

    async def _quick_local_update(self) -> dict[str, any]:
        """
        Quick update using existing cached data.

        This method updates only the timestamp and performs
        minimal local calculations without API calls.

        Returns:
            Updated cached data or triggers full update if no cache
        """
        if self.data:
            # Update timestamp to show data freshness
            self.data["update_time"] = datetime.datetime.now()
            _LOGGER.debug("Quick local update completed")
            return self.data
        else:
            # No cached data available - must do full update
            _LOGGER.debug("No cached data found, performing full update")
            return await self._full_api_update(datetime.date.today())

    async def _set_local_timezone(self):
        """
        Initialize the local timezone object for datetime conversions.

        This is used to convert UTC times from APIs to local time.
        """
        try:
            self.local_timezone = await async_get_time_zone(self.timezone)
            _LOGGER.debug("Local timezone set to: %s", self.timezone)
        except Exception as err:
            _LOGGER.warning("Could not set timezone %s: %s", self.timezone, err)
            self.local_timezone = None

    def _get_week_range(self, date: datetime.date):
        """
        Calculate the current week range (Sunday to Saturday).

        This ensures we fetch data for the entire Jewish week,
        which starts on Sunday.

        Args:
            date: Reference date for calculation

        Returns:
            Tuple of (start_date, end_date) for the week
        """
        days_since_sunday = date.isoweekday() % 7
        start_date = date - datetime.timedelta(days=days_since_sunday)
        end_date = start_date + datetime.timedelta(days=6)

        _LOGGER.debug("Week range: %s to %s", start_date, end_date)
        return start_date, end_date

    async def _fetch_hebcal_data(
            self, session: aiohttp.ClientSession, start_date: datetime.date, end_date: datetime.date
    ) -> dict[str, any]:
        """
        Fetch calendar data from Hebcal API.

        This includes Shabbat times, holidays, Torah readings, etc.

        Args:
            session: HTTP session for requests
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Raw Hebcal calendar data
        """
        diaspora = "on" if self.diaspora_mode else "off"
        language_code = LANGUAGE_DATA[self.language]["code"]

        # Choose URL based on Havdalah calculation preference
        if self.tzeit_hakochavim:
            url = HEBCAL_DATE_URL.format(
                language_code, start_date, end_date,
                self.latitude, self.longitude, self.timezone,
                self.candle_minutes, diaspora
            )
        else:
            url = HEBCAL_DATE_URL_HAVDALAH.format(
                language_code, start_date, end_date,
                self.latitude, self.longitude, self.timezone,
                self.havdalah_minutes, self.candle_minutes, diaspora
            )

        _LOGGER.debug("Fetching from URL: %s", url)
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.json()

    def _fetch_zmanim_data(self, date: datetime.date) -> dict[str, datetime.datetime]:
        """
        Fetch daily prayer times (Zmanim) from the local hdate library.

        Args:
            date: Date for Zmanim calculation

        Returns:
            A dictionary mapping internal zmanim names to their datetime objects.
        """
        processed_zmanim = {}
        raw_data = hdate.Zmanim(date=date, location=self.offline_hebcal).zmanim
        for k, v in raw_data.items():
            time_obj = self.zman_to_dict(v)
            if time_obj:
                processed_zmanim[k] = time_obj
        return processed_zmanim

    def _fetch_hebrew_date(self, date: datetime.date) -> dict[str, str]:
        """
        Fetch Hebrew date conversion from the local hdate library.

        Args:
            date: Gregorian date to convert

        Returns:
            A dictionary containing the Hebrew date.
        """
        try:
            # Create a single HDateInfo object to get both Hebrew and English dates.
            # Create an HDate object from the Gregorian date.
            hdate_obj = hdate.HDateInfo(date)
            hebrew_date_str = str(hdate_obj).replace("ה' ", "ה")
            set_language("en")
            english_date_str = str(hdate_obj)
            return {"hebrew": hebrew_date_str, "english": english_date_str}
        except Exception as e:
            _LOGGER.warning("Could not fetch Hebrew date using hdate.HDateInfo: %s. This might be due to a library version issue.", e)
            return {"hebrew": "", "english": ""}

    async def _process_data(
            self, hebcal_data: Dict[str, Any], zmanim_today: Dict[str, Any], zmanim_tomorrow: Dict[str, Any], hebrew_date_data: Dict[str, Any]
    ) -> dict[str, any]:
        """
        Process raw API data into structured format for Home Assistant.

        This method:
        1. Creates the base data structure
        2. Processes each Hebcal calendar item
        3. Completes missing candle/Havdalah times
        4. Structures data for entity consumption

        Args:
            hebcal_data: Raw calendar data from Hebcal
            zmanim_today: Raw Zmanim data for today
            zmanim_tomorrow: Raw Zmanim data for tomorrow
            hebrew_date_data: Raw Hebrew date data from Hebcal

        Returns:
            Structured data dictionary for Home Assistant entities
        """
        _LOGGER.debug("Processing raw API data")

        # Initialize the processed data structure
        processed = {
            "update_time": datetime.datetime.now(),
            "shabbat_in": None,
            "shabbat_out": None,
            "yomtov_in": None,
            "yomtov_out": None,  # Kept for backward compatibility / simple cases
            "parasha": None,
            "events": [],
            "omer_day": None,
            "hebrew_date": hebrew_date_data,
            "zmanim": zmanim_today,
            "zmanim_tomorrow": zmanim_tomorrow,
            "holidays": [],  # New list to store multiple holidays
            "rosh_hashana": False,
            "special_holiday": False,
        }

        # Process each calendar item
        for item in hebcal_data.get("items", []):
            await self._process_hebcal_item(item, processed)

        # Complete any missing candle lighting or Havdalah times
        await self._complete_missing_times(processed)

        # Calculate Issur Melacha period
        processed["isur_melacha"] = self._calculate_isur_melacha_period(processed)

        _LOGGER.debug("Data processing completed. Found %d events", len(processed["events"]))
        return processed

    def sunset_time(self, date_str: str, day_offset: int) -> str:
        """
        Calculate sunset time for a given date with day offset.

        Used for adding start/end times to holiday events.

        Args:
            date_str: ISO format date string
            day_offset: Days to add/subtract (-1 for previous day, 0 for same day)

        Returns:
            ISO format datetime string of sunset
        """
        try:
            date = datetime.datetime.fromisoformat(date_str[:19]).date()
            sunset = self.get_sunset_time(date, day_offset)
            return sunset.isoformat()
        except Exception as err:
            _LOGGER.warning("Could not calculate sunset time for %s: %s", date_str, err)
            return date_str  # Fallback to original date

    def _add_manual_event(self, processed: dict, event_type: str, event_time: datetime.datetime):
        """Helper to add a manually calculated event to the list."""
        if event_type == "havdalah":
            title = "הבדלה - ידני"
            hebrew = "הבדלה - 42 דקות"
        else:  # candles
            title = "הדלקת נרות - ידני"
            hebrew = "הדלקת נרות"
        processed["events"].append({
            "className": event_type,
            "hebrew": hebrew,
            "date": event_time.isoformat(),
            "allDay": False,
            "title": title,
        })
        _LOGGER.debug("Added manual %s event at %s", event_type, event_time)

    async def _complete_missing_times(self, processed: dict[str, any]):
        """
        Complete missing candle lighting and Havdalah times using calculations.

        This handles cases where the API doesn't provide complete time pairs,
        such as:
        - Shabbat entry without exit (or vice versa)
        - Yom Tov entry without exit (or vice versa)
        - Special holidays that fall on Shabbat

        Args:
            processed: Data dictionary to modify with calculated times
        """
        _LOGGER.debug("Completing missing Shabbat/Yom Tov times")

        # Handle missing Shabbat times
        if processed.get("shabbat_in") and not processed.get("shabbat_out"):
            # Has Shabbat entry but no exit - calculate Havdalah time
            shabbat_out = self.get_offline_missing_time(
                processed["shabbat_in"],
                "havdalah",
                1
            )
            if shabbat_out:
                processed["shabbat_out"] = shabbat_out
                self._add_manual_event(processed, "havdalah", shabbat_out)

                # Handle special holiday that starts after Shabbat
                # This logic is for a holiday that BEGINS on Saturday night.
                # We must check that yomtov_in was not already set for a holiday that began on Friday.
                if processed.get("special_holiday") and not processed.get("yomtov_in"):
                    # This condition is now met only when a holiday truly starts after Shabbat.
                    yomtov_in_calculated = self.get_offline_missing_time(
                        processed["shabbat_in"],
                        "candles",
                        1
                    )
                    if yomtov_in_calculated:
                        processed["yomtov_in"] = yomtov_in_calculated
                        self._add_manual_event(processed, "candles", yomtov_in_calculated)

        elif not processed.get("shabbat_in") and processed.get("shabbat_out"):
            # Has Shabbat exit but no entry - calculate candle lighting time
            shabbat_in = self.get_offline_missing_time(
                processed["shabbat_out"],
                "candles",
                -1  # Candle lighting is the day before Havdalah
            )
            if shabbat_in:
                processed["shabbat_in"] = shabbat_in
                self._add_manual_event(processed, "candles", shabbat_in)

        # Handle missing Yom Tov times
        if processed.get("yomtov_in") and not processed.get("yomtov_out"):
            # Has Yom Tov entry but no exit - calculate based on holiday type
            if processed.get("rosh_hashana"):
                # Rosh Hashana is 2 days
                yomtov_out = self.get_offline_missing_time(
                    processed["yomtov_in"],
                    "havdalah",
                    2
                )
                if yomtov_out: _LOGGER.debug("Calculated Rosh Hashana end (2 days): %s", yomtov_out)
            else:
                # Regular holiday is 1 day
                yomtov_out = self.get_offline_missing_time(
                    processed["yomtov_in"],
                    "havdalah",
                    1
                )
                if yomtov_out: _LOGGER.debug("Calculated regular Yom Tov end (1 day): %s", yomtov_out)

            if yomtov_out:
                processed["yomtov_out"] = yomtov_out
                self._add_manual_event(processed, "havdalah", yomtov_out)

        elif not processed.get("yomtov_in") and processed.get("yomtov_out"):
            # Has Yom Tov exit but no entry - calculate candle lighting time
            if processed.get("rosh_hashana"):
                # Rosh Hashana is 2 days
                yomtov_in = self.get_offline_missing_time(
                    processed["yomtov_out"], "candles", -2
                )
                _LOGGER.debug("Calculated Rosh Hashana start (-2 days): %s", yomtov_in)
            else:
                # Regular holiday is 1 day
                yomtov_in = self.get_offline_missing_time(
                    processed["yomtov_out"], "candles", -1
                )
                _LOGGER.debug("Calculated regular Yom Tov start (-1 day): %s", yomtov_in)

            if yomtov_in:
                processed["yomtov_in"] = yomtov_in
                self._add_manual_event(processed, "candles", yomtov_in)

    def _process_zmanim(self, item: Dict[str, Any]) -> Dict[str, str]:
        """
        Process Zmanim (daily prayer times) data with time format conversion.

        Converts 24-hour format to 12-hour format if user preference is set.

        Args:
            item: Raw Zmanim item from API

        Returns:
            Processed Zmanim dictionary with formatted times
        """
        zmanim = {}

        try:
            # Process each Zmanim time according to language configuration
            for key in LANGUAGE_DATA[self.language][4]:
                if key in item:
                    time_str = item[key][11:16]  # Extract HH:MM from ISO datetime

                    if self.use_12h_time:
                        # Convert to 12-hour format with AM/PM
                        temp_time = datetime.datetime.strptime(time_str, "%H:%M")
                        time_str = temp_time.strftime("%I:%M %p")

                    # Use localized name for the Zmanim
                    localized_name = LANGUAGE_DATA[self.language][4][key]
                    zmanim[localized_name] = time_str

            zmanim['title'] = 'day_zmanim'
            _LOGGER.debug("Processed %d Zmanim times", len(zmanim) - 1)  # -1 for title

        except Exception as err:
            _LOGGER.warning("Error processing Zmanim data: %s", err)

        return zmanim

    async def _process_hebcal_item(self, item: dict[str, any], processed: dict[str, any]):
        """
        Process a single Hebcal calendar item with complete logic.

        This method handles different types of calendar items:
        - Candle lighting times (Shabbat/Yom Tov entry)
        - Havdalah times (Shabbat/Yom Tov exit)
        - Torah readings (Parashat)
        - Holidays and special events
        - Daily Zmanim
        - Omer counting

        Args:
            item: Single calendar item from Hebcal API
            processed: Data dictionary to update with processed information
        """
        if not item or not isinstance(item, dict):
            _LOGGER.debug("Skipping invalid item: %s", item)
            return

        category = item.get("category")
        if not category:
            _LOGGER.debug("Skipping item without category: %s", item.get("title", "Unknown"))
            return

        _LOGGER.debug("Processing item: %s (category: %s)", item.get("title", "Unknown"), category)

        # Initialize missing keys if needed
        if "events" not in processed:
            processed["events"] = []
        if "special_holiday" not in processed:
            processed["special_holiday"] = False

        # Identify Rosh Hashana for special 2-day handling
        # Use title_orig for reliable English matching
        title_orig = item.get("title_orig", "")
        if "Rosh Hashana" in title_orig:
            processed["rosh_hashana"] = True
            _LOGGER.debug("Identified Rosh Hashana event: %s", title_orig)

        # Clean up date format (truncate to 19 characters for ISO format)
        if "date" in item:
            item["date"] = item["date"][:19]

        try:
            if category == "candles":
                await self._process_candle_lighting(item, processed)
            elif category == "havdalah":
                await self._process_havdalah(item, processed)
            elif category == "parashat":
                await self._process_parasha(item, processed)
            elif category in ["yomtov", "holiday", "omer", "roshchodesh", "mevarchim"]:
                await self._process_holiday_event(item, processed)
            else:
                _LOGGER.debug("Unhandled category: %s", category)

        except Exception as err:
            _LOGGER.warning("Error processing item %s: %s", item.get("title", "Unknown"), err)

    async def _process_candle_lighting(self, item: dict[str, any], processed: dict[str, any]):
        """
        Process candle lighting times for Shabbat and Yom Tov.

        Logic:
        - Friday candles = Shabbat entry
        - Non-Friday/Saturday candles = Yom Tov entry
        - Saturday candles = Special holiday (marked but not processed as entry)

        Args:
            item: Candle lighting item from API
            processed: Data dictionary to update
        """
        try:
            date_time = datetime.datetime.fromisoformat(item["date"])
            weekday = date_time.weekday()  # 0=Monday, 4=Friday, 5=Saturday

            # The check_candles_time function was too restrictive and prevented future events
            # from being processed. We should trust the API data for the requested week.

            if weekday == 4:  # Friday
                processed["shabbat_in"] = date_time
                _LOGGER.debug("Added Shabbat candle lighting: %s", date_time)

                # Check if it's also a holiday (like Rosh Hashana on Erev Shabbat)
                memo = item.get("memo", "")
                if "רֹאשׁ הַשָּׁנָה" in memo or "Rosh Hashana" in memo or "Yom Tov" in memo or "חג" in memo:
                    if not processed.get("yomtov_in"):  # Check to avoid overwriting
                        processed["yomtov_in"] = date_time
                    _LOGGER.debug("Identified concurrent Yom Tov candle lighting: %s", date_time)

            elif weekday not in [4, 5]:  # Not Friday or Saturday
                # Only set yomtov_in if it hasn't been set yet for this update cycle
                # This prevents overwriting the start time for multi-day holidays like Rosh Hashana
                if not processed.get("yomtov_in"):
                    processed["yomtov_in"] = date_time
                    _LOGGER.debug("Added Yom Tov candle lighting: %s", date_time)
            elif weekday == 5:  # Saturday
                # This is a special case, like a holiday starting after Shabbat.
                # We don't set yomtov_in here, but mark it for other logic to handle.
                processed["special_holiday"] = True
                _LOGGER.debug("Marked special holiday on Saturday: %s", item.get("title"))

            # Associate candle lighting with the correct holiday in the list (which is on the next day)
            for holiday in processed["holidays"]:
                if holiday["date"] == (date_time.date() + timedelta(days=1)).isoformat():
                    if not holiday.get("yomtov_in"):  # Only set if not already set for this specific holiday
                        holiday["yomtov_in"] = date_time

            processed["events"].append(item)
        except (ValueError, KeyError) as err:
            _LOGGER.warning("Error processing candle lighting item: %s", err)

    async def _process_havdalah(self, item: dict[str, any], processed: dict[str, any]):
        """
        Process Havdalah times for Shabbat and Yom Tov.

        Logic:
        - Saturday Havdalah = Shabbat exit
        - Other days Havdalah = Yom Tov exit

        Args:
            item: Havdalah item from API
            processed: Data dictionary to update
        """
        try:
            date_time = datetime.datetime.fromisoformat(item["date"])
            weekday = date_time.weekday()

            if weekday == 5:  # Saturday
                processed["shabbat_out"] = date_time
                processed["events"].append(item)
                _LOGGER.debug("Added Shabbat Havdalah: %s", date_time)
            elif weekday < 4 or weekday > 5:  # Not Friday-Saturday
                processed["yomtov_out"] = date_time
                # Find the corresponding holiday in the list and update its end time
                # We match by checking if the havdalah is on the same day as the holiday date
                for holiday in processed["holidays"]:
                    if holiday["date"] == date_time.date().isoformat():
                        holiday["yomtov_out"] = date_time
                processed["events"].append(item)
                _LOGGER.debug("Added Yom Tov Havdalah: %s", date_time)

        except (ValueError, KeyError) as err:
            _LOGGER.warning("Error processing Havdalah item: %s", err)

    async def _process_parasha(self, item: dict[str, any], processed: dict[str, any]):
        """
        Process Torah reading (Parashat) information.

        Args:
            item: Parasha item from API
            processed: Data dictionary to update
        """
        try:
            processed["parasha"] = item.get("title")
            processed["events"].append(item)
            _LOGGER.debug("Added Parasha: %s", item.get("title"))
        except Exception as err:
            _LOGGER.warning("Error processing Parasha item: %s", err)

    async def _process_holiday_event(self, item: dict[str, any], processed: dict[str, any]):
        """
        Process holiday and special events.

        Adds sunset-based start/end times for proper event duration.

        Args:
            item: Holiday item from API
            processed: Data dictionary to update
        """
        try:
            # Add sunset times for event duration
            item["start"] = self.sunset_time(item["date"], -1)  # Previous day sunset
            item["end"] = self.sunset_time(item["date"], 0)  # Same day sunset
            processed["events"].append(item)

            # If it's a major holiday, add it to our list of holidays for the week
            if item.get("yomtov"):
                holiday_info = {
                    "name": item.get("title"),
                    "date": item.get("date"),
                    "start": item.get("start"),
                    "end": item.get("end"),
                    "yomtov_in": None,  # Will be populated by candle lighting
                    "yomtov_out": None  # Will be populated by havdalah
                }
                processed["holidays"].append(holiday_info)
                _LOGGER.debug("Added holiday to list: %s", item.get("title"))

            # Store Omer count if it's an Omer day
            if item.get("category") == "omer":
                # Extract day number from title (e.g., "15th day of the Omer")
                title = item.get("title", "")
                try:
                    match = re.search(r'(\d+)', title)
                    if match:
                        processed["omer_day"] = int(match.group(1))
                except Exception:
                    pass

            _LOGGER.debug("Added holiday event: %s", item.get("title"))

        except Exception as err:
            _LOGGER.warning("Error processing holiday item: %s", err)

    async def _save_data_to_file(self, data: dict[str, any]):
        """
        Save processed data to backup file for offline functionality.

        The data is serialized to JSON format with datetime objects
        converted to ISO strings for storage.

        Args:
            data: Processed data dictionary to save
        """
        try:
            import os
            os.makedirs(self.config_path, exist_ok=True)

            file_path = f"{self.config_path}hebcal_data_{self.entry.entry_id}.json"

            # Convert datetime objects to strings for JSON serialization
            serializable_data = self._make_serializable(data)

            async with aiofiles.open(file_path, "w", encoding="utf-8") as file:
                await file.write(json.dumps(serializable_data, ensure_ascii=False, indent=2))

            _LOGGER.debug("Data saved to cache file: %s", file_path)
        except Exception as err:
            _LOGGER.warning("Could not save backup data to file: %s", err)

    async def _load_data_from_file(self) -> dict[str, any]:
        """
        Load processed data from backup file.

        Converts stored ISO date strings back to datetime objects
        for proper functionality.

        Returns:
            Deserialized data dictionary

        Raises:
            FileNotFoundError: When no cache file exists
            Exception: For other file/parsing errors
        """
        try:
            file_path = f"{self.config_path}hebcal_data_{self.entry.entry_id}.json"

            async with aiofiles.open(file_path, "r", encoding="utf-8") as file:
                content = await file.read()
                data = json.loads(content)

            # Convert string dates back to datetime objects
            deserialized_data = self._deserialize_data(data)
            _LOGGER.debug("Data loaded from cache file: %s", file_path)
            return deserialized_data

        except FileNotFoundError:
            _LOGGER.debug("No cache file found at: %s", file_path)
            raise
        except Exception as err:
            _LOGGER.warning("Could not load backup data from file: %s", err)
            raise

    def _make_serializable(self, data: dict[str, any]) -> dict[str, any]:
        """
        Convert datetime objects to strings for JSON serialization.

        Args:
            data: Data dictionary potentially containing datetime objects

        Returns:
            Serializable dictionary with datetime objects as ISO strings
        """
        serializable = {}
        for key, value in data.items():
            if isinstance(value, datetime.datetime):
                serializable[key] = value.isoformat()
            elif isinstance(value, datetime.date):
                serializable[key] = value.isoformat()
            elif isinstance(value, list):
                serializable[key] = [
                    self._make_serializable(item) if isinstance(item, dict) else item
                    for item in value
                ]
            elif isinstance(value, dict):
                serializable[key] = self._make_serializable(value)
            else:
                serializable[key] = value
        return serializable

    def _deserialize_data(self, data: dict[str, any]) -> dict[str, any]:
        """
        Recursively convert ISO date strings in a dictionary back to datetime objects.

        Args:
            data: Serialized data dictionary

        Returns:
            Deserialized dictionary with datetime objects restored
        """
        if not isinstance(data, dict):
            return data

        deserialized = {}
        # Keys that are known to hold datetime strings
        datetime_keys = {"update_time", "shabbat_in", "shabbat_out", "yomtov_in", "yomtov_out", "start", "end",
                         "calculation_time", "date"}

        for key, value in data.items():
            if key in datetime_keys and isinstance(value, str) and value:
                try:
                    # Handle both 'Z' suffix and regular isoformat
                    if value.endswith('Z'):
                        deserialized[key] = datetime.datetime.fromisoformat(value[:-1] + '+00:00')
                    else:
                        deserialized[key] = datetime.datetime.fromisoformat(value)
                except (ValueError, TypeError) as err:
                    _LOGGER.debug("Could not deserialize key '%s' with value '%s' as datetime: %s", key, value, err)
                    deserialized[key] = value
            elif isinstance(value, dict):
                deserialized[key] = self._deserialize_data(value)  # Recurse for nested dicts
            elif isinstance(value, list):
                # Recurse for items in list
                deserialized[key] = [self._deserialize_data(item) if isinstance(item, dict) else item for item in value]
            else:
                deserialized[key] = value
        return deserialized

    def _get_fallback_data(self) -> dict[str, any]:
        """
        Generate minimal fallback data when all else fails.

        This ensures entities don't break completely during
        extended outages or configuration issues.

        Returns:
            Basic data structure with safe defaults
        """
        return {
            "update_time": datetime.datetime.now(),
            "shabbat_in": None,
            "shabbat_out": None,
            "yomtov_in": None,
            "yomtov_out": None,
            "parasha": None,
            "holidays": [],
            "omer_day": None,
            "hebrew_date": {},
            "zmanim": {},
            "rosh_hashana": False,
            "special_holiday": False,
        }

    def get_sunset_time(self, date: datetime.date, day_offset: int = 0) -> datetime.datetime:
        """
        Calculate sunset time for a specific date with optional offset.

        Uses Home Assistant's built-in astral calculations for accuracy.

        Args:
            date: Base date for calculation
            day_offset: Days to add/subtract (0 = same day, -1 = previous day, +1 = next day)

        Returns:
            Local sunset datetime
        """
        try:
            target_date = date + datetime.timedelta(days=day_offset)
            sunset_utc = hdate.Zmanim(date=target_date, location=self.offline_hebcal).zmanim.get("shkia").local
            if sunset_utc is None:
                _LOGGER.warning("Could not calculate sunset for %s", target_date)
                # Fallback to approximate sunset time (6 PM)
                return datetime.datetime.combine(target_date, datetime.time(18, 0))

            return sunset_utc.replace(tzinfo=None) if sunset_utc is not None else None

        except Exception as err:
            _LOGGER.warning("Error calculating sunset time for %s: %s", date, err)
            # Fallback to approximate sunset time
            return datetime.datetime.combine(date, datetime.time(18, 0))

    async def async_shutdown(self):
        """
        Clean shutdown of the coordinator.

        Cancels scheduled updates and cleans up resources
        to prevent memory leaks.
        """
        _LOGGER.info("Shutting down Hebcal coordinator")

        # Cancel daily update listener
        if self.daily_update_listener:
            self.daily_update_listener()
            self.daily_update_listener = None
            _LOGGER.debug("Daily update listener cancelled")

        # Call parent shutdown
        await super().async_shutdown()
        _LOGGER.debug("Coordinator shutdown completed")

    @property
    def is_shabbat_active(self) -> bool:
        """
        Check if Shabbat is currently active.

        Returns:
            True if current time is between Shabbat entry and exit
        """
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
        """
        Check if Yom Tov is currently active.

        Returns:
            True if current time is between Yom Tov entry and exit
        """
        if not self.data:
            return False

        now = datetime.datetime.now()
        yomtov_in = self.data.get("yomtov_in")
        yomtov_out = self.data.get("yomtov_out")

        # New logic: check all holidays in the list
        for holiday in self.data.get("holidays", []):
            if holiday.get("yomtov_in") and holiday.get("yomtov_out"):
                if holiday["yomtov_in"] <= now <= holiday["yomtov_out"]:
                    return True
        if yomtov_in and yomtov_out:
            return yomtov_in <= now <= yomtov_out
        return False

    @property
    def next_candle_lighting(self) -> datetime.datetime | None:
        """
        Get the next upcoming candle lighting time.

        Returns:
            Next candle lighting datetime or None if not available
        """
        if not self.data:
            return None

        now = datetime.datetime.now()
        candidates = []

        # Check Shabbat candles
        shabbat_in = self.data.get("shabbat_in")
        if shabbat_in and shabbat_in > now:
            candidates.append(shabbat_in)

        # Check Yom Tov candles
        yomtov_in = self.data.get("yomtov_in")
        if yomtov_in and yomtov_in > now:
            candidates.append(yomtov_in)

        # New logic: check all holidays in the list
        for holiday in self.data.get("holidays", []):
            if holiday.get("yomtov_in") and holiday["yomtov_in"] > now:
                candidates.append(holiday["yomtov_in"])

        return min(candidates) if candidates else None

    @property
    def next_havdalah(self) -> datetime.datetime | None:
        """
        Get the next upcoming Havdalah time.

        Returns:
            Next Havdalah datetime or None if not available
        """
        if not self.data:
            return None

        now = datetime.datetime.now()
        candidates = []

        # Check Shabbat Havdalah
        shabbat_out = self.data.get("shabbat_out")
        if shabbat_out and shabbat_out > now:
            candidates.append(shabbat_out)

        # Check Yom Tov Havdalah
        yomtov_out = self.data.get("yomtov_out")
        if yomtov_out and yomtov_out > now:
            candidates.append(yomtov_out)

        # New logic: check all holidays in the list
        for holiday in self.data.get("holidays", []):
            if holiday.get("yomtov_out") and holiday["yomtov_out"] > now:
                candidates.append(holiday["yomtov_out"])

        return min(candidates) if candidates else None

    def get_time_until_event(self, event_time: datetime.datetime | None) -> timedelta | None:
        """
        Calculate time remaining until a specific event.

        Args:
            event_time: Target event datetime

        Returns:
            Time delta until event or None if event_time is None/past
        """
        if not event_time:
            return None

        now = datetime.datetime.now()
        if event_time <= now:
            return None

        return event_time - now

    def format_time_delta(self, delta: timedelta) -> str:
        """
        Format a time delta into human-readable string.

        Args:
            delta: Time delta to format

        Returns:
            Formatted string like "2 hours, 15 minutes"
        """
        if not delta:
            return "Unknown"

        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        parts = []
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

        return ", ".join(parts) if parts else "Less than a minute"

    def _calculate_isur_melacha_period(self, data: dict[str, any]) -> dict[str, any]:
        """
        Calculate comprehensive Issur Melacha period information.

        This method determines when work is prohibited according to Jewish law,
        including complex scenarios where Shabbat and Yom Tov overlap or are consecutive.

        Args:
            data: Processed data containing Shabbat and Yom Tov times

        Returns:
            Dictionary with complete Issur Melacha information for JSON storage
        """
        now = datetime.datetime.now()

        # Initialize result structure
        result = {
            "active": False,
            "start": None,
            "end": None,
            "type": "none",
            "type_hebrew": "אין איסור מלאכה",
            "duration_hours": 0,
            "duration_formatted": "",
            "duration_formatted_hebrew": "",
            "time_until_start": None,
            "time_until_end": None,
            "time_until_start_formatted": "",
            "time_until_end_formatted": "",
            "minutes_until_start": 0,
            "minutes_until_end": 0,
            "status_hebrew": "אין איסור מלאכה",
            "work_status": "Permitted",
            "work_status_hebrew": "מותר",
            "components": {
                "shabbat_active": False,
                "yomtov_active": False,
                "shabbat_times": {},
                "yomtov_times": {},
            },
            "special_cases": [],
            "next_events": {},
            "calculation_time": now.isoformat(),
        }

        shabbat_in = data.get("shabbat_in")
        shabbat_out = data.get("shabbat_out")
        yomtov_in = data.get("yomtov_in")
        yomtov_out = data.get("yomtov_out")

        _LOGGER.debug("Calculating Issur Melacha - Shabbat: %s to %s, Yom Tov: %s to %s",
                      shabbat_in, shabbat_out, yomtov_in, yomtov_out)

        # Add component times for reference
        if shabbat_in:
            result["components"]["shabbat_times"]["candles"] = shabbat_in.isoformat()
            result["components"]["shabbat_times"]["candles_formatted"] = shabbat_in.strftime("%H:%M")
            result["components"]["shabbat_times"]["candles_day"] = shabbat_in.strftime("%A")
        if shabbat_out:
            result["components"]["shabbat_times"]["havdalah"] = shabbat_out.isoformat()
            result["components"]["shabbat_times"]["havdalah_formatted"] = shabbat_out.strftime("%H:%M")
            result["components"]["shabbat_times"]["havdalah_day"] = shabbat_out.strftime("%A")
        if yomtov_in:
            result["components"]["yomtov_times"]["candles"] = yomtov_in.isoformat()
            result["components"]["yomtov_times"]["candles_formatted"] = yomtov_in.strftime("%H:%M")
            result["components"]["yomtov_times"]["candles_day"] = yomtov_in.strftime("%A")
        if yomtov_out:
            result["components"]["yomtov_times"]["havdalah"] = yomtov_out.isoformat()
            result["components"]["yomtov_times"]["havdalah_formatted"] = yomtov_out.strftime("%H:%M")
            result["components"]["yomtov_times"]["havdalah_day"] = yomtov_out.strftime("%A")

        # Check individual component status
        if shabbat_in and shabbat_out:
            result["components"]["shabbat_active"] = shabbat_in <= now <= shabbat_out
        if yomtov_in and yomtov_out:
            result["components"]["yomtov_active"] = yomtov_in <= now <= yomtov_out

        # Determine the combined Issur Melacha period using helper functions
        period_info = (
                self._get_case_shabbat_through_yomtov(shabbat_in, yomtov_out) or
                self._get_case_yomtov_thursday_through_shabbat(yomtov_in, shabbat_out) or
                self._get_case_yomtov_friday_through_shabbat(yomtov_in, yomtov_out, shabbat_out) or
                self._get_individual_or_upcoming_period(now, shabbat_in, shabbat_out, yomtov_in, yomtov_out)
        )

        period_start, period_end = None, None
        if period_info:
            period_start, period_end, period_type, type_hebrew, special_case = period_info
            result["type"] = period_type
            result["type_hebrew"] = type_hebrew
            if special_case:
                result["special_cases"].append(special_case)

        if period_start and period_end:
            self._populate_period_times(result, period_start, period_end)
            self._populate_period_status(result, now, period_start, period_end)

        # Add special case information
        if data.get("rosh_hashana"):
            result["special_cases"].append("Rosh Hashana (2 days)")
        if data.get("special_holiday"):
            result["special_cases"].append("Special Holiday")

        # Add next events information
        next_candles = self.next_candle_lighting
        if next_candles:
            result["next_events"]["candle_lighting"] = next_candles.isoformat()
            result["next_events"]["candle_lighting_formatted"] = next_candles.strftime("%A %H:%M")

        next_havdalah = self.next_havdalah
        if next_havdalah:
            result["next_events"]["havdalah"] = next_havdalah.isoformat()
            result["next_events"]["havdalah_formatted"] = next_havdalah.strftime("%A %H:%M")

        _LOGGER.debug("Issur Melacha calculation completed: %s", result["type"])
        return result

    def _get_case_shabbat_through_yomtov(self, shabbat_in, yomtov_out):
        """Case 1: Yom Tov ends on Sunday, creating a continuous period from Shabbat."""
        if shabbat_in and yomtov_out and yomtov_out > shabbat_in and yomtov_out.weekday() == 6:  # Sunday
            _LOGGER.debug("Issur Melacha Case: Shabbat through Yom Tov ending Sunday")
            return (
                shabbat_in,
                yomtov_out,
                "shabbat_through_yomtov",
                "שבת עד יום טוב (יום ראשון)",
                "Yom Tov ending Sunday after Shabbat",
            )
        return None

    def _get_case_yomtov_thursday_through_shabbat(self, yomtov_in, shabbat_out):
        """Case 2: Yom Tov starts on Thursday, creating a continuous period into Shabbat."""
        if yomtov_in and shabbat_out and yomtov_in.weekday() == 3:  # Thursday
            _LOGGER.debug("Issur Melacha Case: Yom Tov Thursday through Shabbat")
            return (
                yomtov_in,
                shabbat_out,
                "yomtov_thursday_through_shabbat",
                "יום טוב (חמישי) עד שבת",
                "Yom Tov starting Thursday before Shabbat",
            )
        return None

    def _get_case_yomtov_friday_through_shabbat(self, yomtov_in, yomtov_out, shabbat_out):
        """Case 3: Yom Tov ends on Friday, creating a continuous period into Shabbat."""
        # This case is for a 1-day Yom Tov on Friday. Candle lighting (yomtov_in) is on Thursday.
        if yomtov_in and shabbat_out and yomtov_in.weekday() == 3:  # Thursday
            _LOGGER.debug("Issur Melacha Case: Yom Tov on Friday through Shabbat")
            return (
                yomtov_in,
                shabbat_out,
                "yomtov_through_shabbat_friday",
                "יום טוב (שישי) עד שבת",
                "Yom Tov on Friday before Shabbat",
            )
        return None

    def _get_individual_or_upcoming_period(self, now, shabbat_in, shabbat_out, yomtov_in, yomtov_out):
        """Handle individual active periods or find the next upcoming period."""
        # Check for currently active individual periods
        if shabbat_in and shabbat_out and shabbat_in <= now <= shabbat_out:
            return shabbat_in, shabbat_out, "shabbat_only", "שבת בלבד", None
        if yomtov_in and yomtov_out and yomtov_in <= now <= yomtov_out:
            return yomtov_in, yomtov_out, "yomtov_only", "יום טוב בלבד", None

        # Find the earliest upcoming period
        upcoming_periods = []
        if shabbat_in and shabbat_out and shabbat_in > now:
            upcoming_periods.append((shabbat_in, shabbat_out, "shabbat_upcoming", "שבת הבא", None))
        if yomtov_in and yomtov_out and yomtov_in > now:
            upcoming_periods.append((yomtov_in, yomtov_out, "yomtov_upcoming", "יום טוב הבא", None))

        if upcoming_periods:
            upcoming_periods.sort(key=lambda x: x[0])
            return upcoming_periods[0]

        return None

    def _populate_period_times(self, result, period_start, period_end):
        """Populate the result dict with start/end times and duration."""
        result["start"] = period_start
        result["end"] = period_end
        result["start_formatted"] = period_start.strftime("%H:%M")
        result["end_formatted"] = period_end.strftime("%H:%M")
        result["start_day"] = period_start.strftime("%A")
        result["end_day"] = period_end.strftime("%A")

        duration = period_end - period_start
        duration_hours = round(duration.total_seconds() / 3600, 1)
        result["duration_hours"] = duration_hours

        if duration_hours >= 24:
            days = int(duration_hours // 24)
            hours = int(duration_hours % 24)
            result["duration_formatted"] = f"{days} days, {hours} hours"
            result["duration_formatted_hebrew"] = f"{days} ימים, {hours} שעות"
        else:
            result["duration_formatted"] = f"{duration_hours:.1f} hours"
            result["duration_formatted_hebrew"] = f"{duration_hours:.1f} שעות"

    def _populate_period_status(self, result, now, period_start, period_end):
        """Populate the result dict with active status and time until start/end."""
        is_active = period_start <= now <= period_end
        result["active"] = is_active

        if is_active:
            time_until_end = period_end - now
            result["time_until_end"] = time_until_end.total_seconds()
            result["minutes_until_end"] = int(time_until_end.total_seconds() / 60)
            result["time_until_end_formatted"] = self.format_time_delta(time_until_end)
            result["status_hebrew"] = f"איסור מלאכה פעיל - נגמר בעוד {result['time_until_end_formatted']}"
            result["work_status"] = "Prohibited"
            result["work_status_hebrew"] = "אסור"
        elif period_start > now:
            time_until_start = period_start - now
            result["time_until_start"] = time_until_start.total_seconds()
            result["minutes_until_start"] = int(time_until_start.total_seconds() / 60)
            result["time_until_start_formatted"] = self.format_time_delta(time_until_start)
            result["status_hebrew"] = f"איסור מלאכה מתחיל בעוד {result['time_until_start_formatted']}"
            result["work_status"] = "Permitted"
            result["work_status_hebrew"] = "מותר"
        else:  # Period has passed
            result["status_hebrew"] = "איסור מלאכה הסתיים"
            result["work_status"] = "Permitted"
            result["work_status_hebrew"] = "מותר"

    # Update existing functions to use JSON data:

    @property
    def isur_melacha_period(self) -> Dict[str, Any]:
        """
        Get Isur Melacha period information from stored JSON data.

        Returns:
            Dictionary containing comprehensive Isur Melacha information
        """
        if not self.data or "isur_melacha" not in self.data:
            return {
                'active': False,
                'start': None,
                'end': None,
                'type': 'no_data',
                'duration_hours': 0
            }

        return self.data["isur_melacha"]

    @property
    def isur_melacha_active(self) -> bool:
        """
        Check if Isur Melacha is currently active.

        Returns:
            True if work is currently forbidden according to Jewish law
        """
        period = self.isur_melacha_period
        return period.get('active', False)

    @property
    def isur_melacha_start(self) -> datetime.datetime | None:
        """
        Get the start time of the current/next Isur Melacha period.

        Returns:
            Start datetime of Isur Melacha period or None
        """
        period = self.isur_melacha_period
        start_dt = period.get('start')
        if isinstance(start_dt, datetime.datetime):
            return start_dt
        return None

    @property
    def isur_melacha_end(self) -> datetime.datetime | None:
        """
        Get the end time of the current/next Isur Melacha period.

        Returns:
            End datetime of Isur Melacha period or None
        """
        period = self.isur_melacha_period
        end_dt = period.get('end')
        if isinstance(end_dt, datetime.datetime):
            return end_dt
        return None

    @property
    def isur_melacha_type(self) -> str:
        """
        Get the type description of the current Isur Melacha period.

        Returns:
            String describing the type of prohibition period
        """
        period = self.isur_melacha_period
        return period.get('type', 'none')

    @property
    def isur_melacha_duration(self) -> float:
        """
        Get the total duration of the Isur Melacha period in hours.

        Returns:
            Duration in hours (float)
        """
        period = self.isur_melacha_period
        return period.get('duration_hours', 0)

    def get_time_until_isur_melacha_start(self) -> timedelta | None:
        """
        Calculate time remaining until Isur Melacha period starts.

        Returns:
            Time delta until start or None if already active/no period
        """
        period = self.isur_melacha_period
        seconds = period.get('time_until_start')
        if seconds and seconds > 0:
            return timedelta(seconds=seconds)
        return None

    def get_time_until_isur_melacha_end(self) -> timedelta | None:
        """
        Calculate time remaining until Isur Melacha period ends.

        Returns:
            Time delta until end or None if not active/no period
        """
        period = self.isur_melacha_period
        seconds = period.get('time_until_end')
        if seconds and seconds > 0:
            return timedelta(seconds=seconds)
        return None

    def format_isur_melacha_status(self) -> str:
        """
        Format a human-readable status of the Isur Melacha period.

        Returns:
            Formatted status string in Hebrew
        """
        period = self.isur_melacha_period
        return period.get('status_hebrew', 'אין איסור מלאכה')

    def get_isur_melacha_type_description(self) -> str:
        """
        Get Hebrew description of the Isur Melacha period type.

        Returns:
            Hebrew description of the period type
        """
        period = self.isur_melacha_period
        return period.get('type_hebrew', 'אין איסור מלאכה')

    def get_offline_missing_time(self, date: datetime.datetime, type_calculation: str,
                                 days: int) -> datetime.datetime | None:
        """
        Calculate offline missing time for a specific date and type of calculation.

        Args:
            date: The base date for calculation
            type_calculation: The type of calculation ('havdalah' or 'candles')
            days: Offset in days (positive or negative)

        Returns:
            A tz-naive datetime of the calculated time, or None if not available
        """
        target_date = date + timedelta(days=days)
        zmanim = hdate.Zmanim(date=target_date.date(), location=self.offline_hebcal)

        dt = None
        if type_calculation == "havdalah":
            dt = zmanim.havdalah
            # fallback - if havdalah is not available, try candle lighting
            if dt is None:
                if target_date.weekday() == 4:
                    dt = zmanim.zmanim.get("tset_hakohavim_shabbat").local
                else:
                    dt = zmanim.candle_lighting

        elif type_calculation == "candles":
            dt = zmanim.candle_lighting

        # Remove tzinfo if time is found
        return dt.replace(tzinfo=None) if dt is not None else None

    def zman_to_dict(self, zman: Zman) -> datetime.datetime | None:
        """
        Convert a Zman object to a naive datetime in the local timezone.

        This function takes a Zman object (which might be timezone-aware or naive UTC)
        and converts it to a timezone-naive datetime object in the local timezone
        configured for the integration. This ensures consistency for display and
        comparison within Home Assistant, which typically operates with naive datetimes
        in the system's local timezone.

        Args:
            zman: The Zman object from the hdate library. This object contains
                  both the UTC datetime (`zman.utc`) and the target timezone
                  (`zman.timezone`).


        Returns:
            A naive datetime object representing the zman in the correct local time.
        """
        dt_utc = zman.utc  # Can be tz-naive or tz-aware in UTC

        # Guard against None from hdate for zmanim that don't occur (e.g. at high latitudes)
        if dt_utc is None:
            _LOGGER.debug("Skipping zman with no time value (dt_utc is None)")
            return None

        # If tz-naive, make it tz-aware in UTC
        if dt_utc.tzinfo is None:
            from datetime import timezone
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        # Convert to the location's timezone and make it naive for consistency
        return dt_utc.astimezone(zman.timezone).replace(tzinfo=None)