"""Functions for processing specific Hebcal calendar items."""
import datetime
import logging
import re
from datetime import timedelta
from typing import Dict, Any

from .const import LANGUAGE_DATA

_LOGGER = logging.getLogger(__name__)

async def process_hebcal_item(coordinator, item: dict[str, any], processed: dict[str, any]):
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
        coordinator: The HebcalDataUpdateCoordinator instance.
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
            await _process_candle_lighting(coordinator, item, processed)
        elif category == "havdalah":
            await _process_havdalah(coordinator, item, processed)
        elif category == "parashat":
            await _process_parasha(coordinator, item, processed)
        elif category == "day_zmanim":
            await _process_daily_zmanim(coordinator, item, processed)
        elif category in ["yomtov", "holiday", "omer", "roshchodesh", "mevarchim"]:
            await _process_holiday_event(coordinator, item, processed)
        else:
            _LOGGER.debug("Unhandled category: %s", category)

    except Exception as err:
        _LOGGER.warning("Error processing item %s: %s", item.get("title", "Unknown"), err)

async def _process_candle_lighting(coordinator, item: dict[str, any], processed: dict[str, any]):
    """
    Process candle lighting times for Shabbat and Yom Tov.

    Logic:
    - Friday candles = Shabbat entry
    - Non-Friday/Saturday candles = Yom Tov entry
    - Saturday candles = Special holiday (marked but not processed as entry)

    Args:
        coordinator: The HebcalDataUpdateCoordinator instance.
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

async def _process_havdalah(coordinator, item: dict[str, any], processed: dict[str, any]):
    """
    Process Havdalah times for Shabbat and Yom Tov.

    Logic:
    - Saturday Havdalah = Shabbat exit
    - Other days Havdalah = Yom Tov exit

    Args:
        coordinator: The HebcalDataUpdateCoordinator instance.
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

async def _process_parasha(coordinator, item: dict[str, any], processed: dict[str, any]):
    """
    Process Torah reading (Parashat) information.

    Args:
        coordinator: The HebcalDataUpdateCoordinator instance.
        item: Parasha item from API
        processed: Data dictionary to update
    """
    try:
        processed["parasha"] = item.get("title")
        processed["events"].append(item)
        _LOGGER.debug("Added Parasha: %s", item.get("title"))
    except Exception as err:
        _LOGGER.warning("Error processing Parasha item: %s", err)

async def _process_daily_zmanim(coordinator, item: dict[str, any], processed: dict[str, any]):
    """
    Process daily Zmanim (prayer times) data.

    Args:
        coordinator: The HebcalDataUpdateCoordinator instance.
        item: Zmanim item from API
        processed: Data dictionary to update
    """
    try:
        zmanim_data = _process_zmanim_helper(coordinator, item) # Call helper function
        processed["zmanim"] = zmanim_data
        processed["events"].append(zmanim_data)
        _LOGGER.debug("Added daily Zmanim data")
    except Exception as err:
        _LOGGER.warning("Error processing Zmanim item: %s", err)

def _process_zmanim_helper(coordinator, item: Dict[str, Any]) -> Dict[str, str]:
    """
    Helper to process Zmanim (daily prayer times) data with time format conversion.

    Converts 24-hour format to 12-hour format if user preference is set.

    Args:
        coordinator: The HebcalDataUpdateCoordinator instance.
        item: Raw Zmanim item from API

    Returns:
        Processed Zmanim dictionary with formatted times
    """
    zmanim = {}

    try:
        # Process each Zmanim time according to language configuration
        for key in LANGUAGE_DATA[coordinator.language][4]:
            if key in item:
                time_str = item[key][11:16]  # Extract HH:MM from ISO datetime

                if coordinator.use_12h_time:
                    # Convert to 12-hour format with AM/PM
                    temp_time = datetime.datetime.strptime(time_str, "%H:%M")
                    time_str = temp_time.strftime("%I:%M %p")

                # Use localized name for the Zmanim
                localized_name = LANGUAGE_DATA[coordinator.language][4][key]
                zmanim[localized_name] = time_str

        zmanim['title'] = 'day_zmanim'
        _LOGGER.debug("Processed %d Zmanim times", len(zmanim) - 1)  # -1 for title

    except Exception as err:
        _LOGGER.warning("Error processing Zmanim data: %s", err)

    return zmanim

async def _process_holiday_event(coordinator, item: dict[str, any], processed: dict[str, any]):
    """
    Process holiday and special events.

    Adds sunset-based start/end times for proper event duration.

    Args:
        coordinator: The HebcalDataUpdateCoordinator instance.
        item: Holiday item from API
        processed: Data dictionary to update
    """
    try:
        # Add sunset times for event duration
        item["start"] = coordinator.sunset_time(item["date"], -1)  # Previous day sunset
        item["end"] = coordinator.sunset_time(item["date"], 0)     # Same day sunset
        processed["events"].append(item)

        # If it's a major holiday, add it to our list of holidays for the week
        if item.get("yomtov"):
            holiday_info = {
                "name": item.get("title"),
                "date": item.get("date"),
                "start": item.get("start"),
                "end": item.get("end"),
                "yomtov_in": None, # Will be populated by candle lighting
                "yomtov_out": None # Will be populated by havdalah
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
