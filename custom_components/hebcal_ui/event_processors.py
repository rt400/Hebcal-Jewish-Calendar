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
    """
    if not item or not isinstance(item, dict):
        _LOGGER.debug("Skipping invalid item: %s", item)
        return

    category = item.get("category")
    if not category:
        _LOGGER.debug("Skipping item without category: %s", item.get("title", "Unknown"))
        return

    _LOGGER.debug("Processing item: %s (category: %s)", item.get("title", "Unknown"), category)

    if "events" not in processed:
        processed["events"] = []
    if "special_holiday" not in processed:
        processed["special_holiday"] = False

    title_orig = item.get("title_orig", "")
    if "Rosh Hashana" in title_orig:
        processed["rosh_hashana"] = True
        _LOGGER.debug("Identified Rosh Hashana event: %s", title_orig)

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
    try:
        date_time = datetime.datetime.fromisoformat(item["date"])
        weekday = date_time.weekday()  

        if weekday == 4:  
            processed["shabbat_in"] = date_time
            _LOGGER.debug("Added Shabbat candle lighting: %s", date_time)

            memo = item.get("memo", "")
            if "רֹאשׁ הַשָּׁנָה" in memo or "Rosh Hashana" in memo or "Yom Tov" in memo or "חג" in memo:
                if not processed.get("yomtov_in"):  
                    processed["yomtov_in"] = date_time
                _LOGGER.debug("Identified concurrent Yom Tov candle lighting: %s", date_time)

        elif weekday not in [4, 5]:  
            if not processed.get("yomtov_in"):
                processed["yomtov_in"] = date_time
                _LOGGER.debug("Added Yom Tov candle lighting: %s", date_time)
        elif weekday == 5:  
            processed["special_holiday"] = True
            _LOGGER.debug("Marked special holiday on Saturday: %s", item.get("title"))

        for holiday in processed.get("holidays", []):
            if holiday["date"] == (date_time.date() + timedelta(days=1)).isoformat():
                if not holiday.get("yomtov_in"):  
                    holiday["yomtov_in"] = date_time

        processed["events"].append(item)
    except (ValueError, KeyError) as err:
        _LOGGER.warning("Error processing candle lighting item: %s", err)

async def _process_havdalah(coordinator, item: dict[str, any], processed: dict[str, any]):
    try:
        date_time = datetime.datetime.fromisoformat(item["date"])
        weekday = date_time.weekday()

        if weekday == 5:  
            processed["shabbat_out"] = date_time
            processed["events"].append(item)
            _LOGGER.debug("Added Shabbat Havdalah: %s", date_time)
        elif weekday < 4 or weekday > 5:  
            processed["yomtov_out"] = date_time
            for holiday in processed.get("holidays", []):
                if holiday["date"] == date_time.date().isoformat():
                    holiday["yomtov_out"] = date_time
            processed["events"].append(item)
            _LOGGER.debug("Added Yom Tov Havdalah: %s", date_time)

    except (ValueError, KeyError) as err:
        _LOGGER.warning("Error processing Havdalah item: %s", err)

async def _process_parasha(coordinator, item: dict[str, any], processed: dict[str, any]):
    try:
        processed["parasha"] = item.get("title")
        processed["events"].append(item)
        _LOGGER.debug("Added Parasha: %s", item.get("title"))
    except Exception as err:
        _LOGGER.warning("Error processing Parasha item: %s", err)

async def _process_daily_zmanim(coordinator, item: dict[str, any], processed: dict[str, any]):
    """Process daily Zmanim (prayer times) data."""
    try:
        zmanim_data = _process_zmanim_helper(coordinator, item) 
        
        # NOTE: WE DO NOT OVERWRITE processed["zmanim"] HERE ANYMORE TO AVOID DESTROYING HDATE DATA
        # processed["zmanim"] = zmanim_data
        
        processed["events"].append(zmanim_data)
        _LOGGER.debug("Added daily Zmanim data to events")
    except Exception as err:
        _LOGGER.warning("Error processing Zmanim item: %s", err)

def _process_zmanim_helper(coordinator, item: Dict[str, Any]) -> Dict[str, str]:
    zmanim = {}
    try:
        for key in LANGUAGE_DATA[coordinator.language].get("zmanim", {}):
            if key in item:
                time_str = item[key][11:16]  
                if coordinator.use_12h_time:
                    temp_time = datetime.datetime.strptime(time_str, "%H:%M")
                    time_str = temp_time.strftime("%I:%M %p")
                localized_name = LANGUAGE_DATA[coordinator.language]["zmanim"][key]
                zmanim[localized_name] = time_str
        zmanim['title'] = 'day_zmanim'
    except Exception as err:
        _LOGGER.warning("Error processing Zmanim data: %s", err)
    return zmanim

async def _process_holiday_event(coordinator, item: dict[str, any], processed: dict[str, any]):
    try:
        item["start"] = coordinator.sunset_time(item["date"], -1) 
        item["end"] = coordinator.sunset_time(item["date"], 0)    
        processed["events"].append(item)

        if item.get("yomtov"):
            if "holidays" not in processed:
                processed["holidays"] = []
            holiday_info = {
                "name": item.get("title"),
                "date": item.get("date"),
                "start": item.get("start"),
                "end": item.get("end"),
                "yomtov_in": None, 
                "yomtov_out": None 
            }
            processed["holidays"].append(holiday_info)
            _LOGGER.debug("Added holiday to list: %s", item.get("title"))

        if item.get("category") == "omer":
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
