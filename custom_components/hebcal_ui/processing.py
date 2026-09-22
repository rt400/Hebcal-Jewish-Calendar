"""Data processing functions for the Hebcal integration."""
import datetime
import logging
from datetime import timedelta
from typing import Dict, Any

from . import isur_melacha, event_processors
from .const import LANGUAGE_DATA # Still needed for _process_zmanim which is now in event_processors

_LOGGER = logging.getLogger(__name__)

async def process_data(
    coordinator, hebcal_data: Dict[str, Any], zmanim_data: Dict[str, Any], hebrew_date_data: Dict[str, Any]
) -> dict[str, any]:
    """
    Process raw API data into structured format for Home Assistant.

    This method:
    1. Creates the base data structure
    2. Processes each Hebcal calendar item
    3. Completes missing candle/Havdalah times
    4. Structures data for entity consumption

    Args:
        coordinator: The HebcalDataUpdateCoordinator instance.
        hebcal_data: Raw calendar data from Hebcal
        zmanim_data: Raw Zmanim data from Hebcal
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
        "yomtov_out": None, # Kept for backward compatibility / simple cases
        "parasha": None,
        "events": [],
        "omer_day": None,
        "hebrew_date": hebrew_date_data,
        "zmanim": zmanim_data.get("times", {}),
        "holidays": [], # New list to store multiple holidays
        "rosh_hashana": False,
        "special_holiday": False,
    }

    # Process each calendar item
    for item in hebcal_data.get("items", []): # Pass coordinator to event_processors
        await event_processors.process_hebcal_item(coordinator, item, processed)

    # Complete any missing candle lighting or Havdalah times
    await _complete_missing_times(coordinator, processed)

    # Calculate Issur Melacha period
    processed["isur_melacha"] = isur_melacha.calculate_isur_melacha_period(coordinator, processed)

    _LOGGER.debug("Data processing completed. Found %d events", len(processed["events"]))
    return processed

def _add_manual_event(processed: dict, event_type: str, event_time: datetime.datetime):
    """Helper to add a manually calculated event to the list."""
    if event_type == "havdalah":
        title = "הבדלה - ידני"
        hebrew = "הבדלה - 42 דקות"
    else: # candles
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

def _yomtov_slot_is_free(processed: dict[str, any]) -> bool:
    """True when the Yom Tov slot holds nothing that still matters.

    A single Sunday..Saturday window can contain two distinct Yom Tov onsets, so the
    slot can be neither overwritten unconditionally (which loses the first) nor never
    overwritten (which loses the second).

    A yomtov_in with no yomtov_out is an open period whose end has not been derived
    yet -- this runs before the pairing block below -- so it must never be treated as
    free, or a Yom Tov in progress is discarded.
    """
    yomtov_out = processed.get("yomtov_out")
    if yomtov_out is not None:
        return yomtov_out < datetime.datetime.now()
    return processed.get("yomtov_in") is None

async def _complete_missing_times(coordinator, processed: dict[str, any]):
    """
    Complete missing candle lighting and Havdalah times using calculations.

    This handles cases where the API doesn't provide complete time pairs,
    such as:
    - Shabbat entry without exit (or vice versa)
    - Yom Tov entry without exit (or vice versa)
    - Special holidays that fall on Shabbat

    Args:
        coordinator: The HebcalDataUpdateCoordinator instance.
        processed: Data dictionary to modify with calculated times
    """
    _LOGGER.debug("Completing missing Shabbat/Yom Tov times")

    # Handle missing Shabbat times
    if processed.get("shabbat_in") and not processed.get("shabbat_out"):
        # Has Shabbat entry but no exit - calculate Havdalah time
        shabbat_out = coordinator.get_offline_missing_time(
            processed["shabbat_in"],
            "havdalah",
            1
        )
        if shabbat_out:
            processed["shabbat_out"] = shabbat_out
            _add_manual_event(processed, "havdalah", shabbat_out)

            # Handle special holiday that starts after Shabbat
            # This logic is for a holiday that BEGINS on Saturday night.
            # We must check that yomtov_in was not already set for a holiday that began on Friday.
            if processed.get("special_holiday") and _yomtov_slot_is_free(processed):
                # This condition is now met only when a holiday truly starts after Shabbat.
                yomtov_in_calculated = coordinator.get_offline_missing_time(
                    processed["shabbat_in"],
                    "candles",
                    1
                )
                if yomtov_in_calculated:
                    processed["yomtov_in"] = yomtov_in_calculated
                    # the previous pair, if any, is spent; let the block below
                    # derive a matching end for the onset just claimed
                    processed["yomtov_out"] = None
                    _add_manual_event(processed, "candles", yomtov_in_calculated)

    elif not processed.get("shabbat_in") and processed.get("shabbat_out"):
        # Has Shabbat exit but no entry - calculate candle lighting time
        shabbat_in = coordinator.get_offline_missing_time(
            processed["shabbat_out"],
            "candles",
            -1 # Candle lighting is the day before Havdalah
        )
        if shabbat_in:
            processed["shabbat_in"] = shabbat_in
            _add_manual_event(processed, "candles", shabbat_in)

    # Handle missing Yom Tov times
    if processed.get("yomtov_in") and not processed.get("yomtov_out"):
        # Has Yom Tov entry but no exit - calculate based on holiday type
        yomtov_out = None
        if processed.get("rosh_hashana"):
            # Rosh Hashana is 2 days
            yomtov_out = coordinator.get_offline_missing_time(
                processed["yomtov_in"],
                "havdalah",
                2
            )
            if yomtov_out: _LOGGER.debug("Calculated Rosh Hashana end (2 days): %s", yomtov_out)
        else:
            # Regular holiday is 1 day
            yomtov_out = coordinator.get_offline_missing_time(
                processed["yomtov_in"],
                "havdalah",
                1
            )
            if yomtov_out: _LOGGER.debug("Calculated regular Yom Tov end (1 day): %s", yomtov_out)

        if yomtov_out:
            processed["yomtov_out"] = yomtov_out
            _add_manual_event(processed, "havdalah", yomtov_out)

    elif not processed.get("yomtov_in") and processed.get("yomtov_out"):
        # Has Yom Tov exit but no entry - calculate candle lighting time
        yomtov_in = None
        if processed.get("rosh_hashana"):
            # Rosh Hashana is 2 days
            yomtov_in = coordinator.get_offline_missing_time(
                processed["yomtov_out"], "candles", -2
            )
            _LOGGER.debug("Calculated Rosh Hashana start (-2 days): %s", yomtov_in)
        else:
            # Regular holiday is 1 day
            yomtov_in = coordinator.get_offline_missing_time(
                processed["yomtov_out"], "candles", -1
            )
            _LOGGER.debug("Calculated regular Yom Tov start (-1 day): %s", yomtov_in)

        if yomtov_in:
            processed["yomtov_in"] = yomtov_in
            _add_manual_event(processed, "candles", yomtov_in)
