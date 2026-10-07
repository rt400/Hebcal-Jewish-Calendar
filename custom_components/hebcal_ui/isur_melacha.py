"""Calculates the Issur Melacha (work prohibition) period and manages related logic."""
import datetime
import logging
from typing import Dict, Any
from .helpers import CoordinatorHelpers

_LOGGER = logging.getLogger(__name__)

def calculate_isur_melacha_period(data: dict[str, any], language: str = "he") -> dict[str, any]:
    """Calculate comprehensive Issur Melacha period information natively localized."""
    is_hebrew = CoordinatorHelpers.is_hebrew(language)
    now = datetime.datetime.now()

    result = {
        "active": False,
        "start": None,
        "end": None,
        "type": "none",
        "type_description": "אין איסור מלאכה" if is_hebrew else "No Work Prohibition",
        "duration_hours": 0,
        "duration_formatted": "",
        "time_until_start": None,
        "time_until_end": None,
        "time_until_start_formatted": "",
        "time_until_end_formatted": "",
        "minutes_until_start": 0,
        "minutes_until_end": 0,
        "status_text": "אין איסור מלאכה" if is_hebrew else "No Work Prohibition",
        "work_status": "מותר" if is_hebrew else "Permitted",
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

    if shabbat_in:
        result["components"]["shabbat_times"]["candles"] = shabbat_in.isoformat()
        result["components"]["shabbat_times"]["candles_formatted"] = shabbat_in.strftime("%H:%M")
        result["components"]["shabbat_times"]["candles_day"] = CoordinatorHelpers.get_localized_day(shabbat_in, language)
    if shabbat_out:
        result["components"]["shabbat_times"]["havdalah"] = shabbat_out.isoformat()
        result["components"]["shabbat_times"]["havdalah_formatted"] = shabbat_out.strftime("%H:%M")
        result["components"]["shabbat_times"]["havdalah_day"] = CoordinatorHelpers.get_localized_day(shabbat_out, language)
    if yomtov_in:
        result["components"]["yomtov_times"]["candles"] = yomtov_in.isoformat()
        result["components"]["yomtov_times"]["candles_formatted"] = yomtov_in.strftime("%H:%M")
        result["components"]["yomtov_times"]["candles_day"] = CoordinatorHelpers.get_localized_day(yomtov_in, language)
    if yomtov_out:
        result["components"]["yomtov_times"]["havdalah"] = yomtov_out.isoformat()
        result["components"]["yomtov_times"]["havdalah_formatted"] = yomtov_out.strftime("%H:%M")
        result["components"]["yomtov_times"]["havdalah_day"] = CoordinatorHelpers.get_localized_day(yomtov_out, language)

    if shabbat_in and shabbat_out:
        result["components"]["shabbat_active"] = shabbat_in <= now <= shabbat_out
    if yomtov_in and yomtov_out:
        result["components"]["yomtov_active"] = yomtov_in <= now <= yomtov_out

    period_info = (
        _get_case_shabbat_through_yomtov(shabbat_in, yomtov_out, is_hebrew) or
        _get_case_yomtov_thursday_through_shabbat(yomtov_in, shabbat_out, is_hebrew) or
        _get_case_yomtov_friday_through_shabbat(yomtov_in, yomtov_out, shabbat_out, is_hebrew) or
        _get_individual_or_upcoming_period(now, shabbat_in, shabbat_out, yomtov_in, yomtov_out, is_hebrew)
    )

    period_start, period_end = None, None
    if period_info:
        period_start, period_end, period_type, type_desc, special_case = period_info
        result["type"] = period_type
        result["type_description"] = type_desc
        if special_case:
            result["special_cases"].append(special_case)

    if period_start and period_end:
        _populate_period_times(result, period_start, period_end, language)
        _populate_period_status(result, now, period_start, period_end, language)

    if data.get("rosh_hashana"):
        result["special_cases"].append("ראש השנה (יומיים)" if is_hebrew else "Rosh Hashana (2 days)")
    if data.get("special_holiday"):
        result["special_cases"].append("חג מיוחד" if is_hebrew else "Special Holiday")

    def get_next_event(data_dict, event_suffix):
        now_dt = datetime.datetime.now()
        candidates = []
        shabbat_event = data_dict.get(f"shabbat_{event_suffix}")
        if shabbat_event and shabbat_event > now_dt:
            candidates.append(shabbat_event)

        yomtov_event = data_dict.get(f"yomtov_{event_suffix}")
        if yomtov_event and yomtov_event > now_dt:
            candidates.append(yomtov_event)

        for h in data_dict.get("holidays", []):
            h_event = h.get(f"yomtov_{event_suffix}")
            if h_event and h_event > now_dt:
                candidates.append(h_event)

        return min(candidates) if candidates else None

    next_candles = get_next_event(data, "in")
    if next_candles:
        day_str = CoordinatorHelpers.get_localized_day(next_candles, language)
        result["next_events"]["candle_lighting"] = next_candles.isoformat()
        result["next_events"]["candle_lighting_formatted"] = f"{day_str} {next_candles.strftime('%H:%M')}"

    next_havdalah = get_next_event(data, "out")
    if next_havdalah:
        day_str = CoordinatorHelpers.get_localized_day(next_havdalah, language)
        result["next_events"]["havdalah"] = next_havdalah.isoformat()
        result["next_events"]["havdalah_formatted"] = f"{day_str} {next_havdalah.strftime('%H:%M')}"

    _LOGGER.debug("Issur Melacha calculation completed: %s", result["type"])
    return result

def _get_case_shabbat_through_yomtov(shabbat_in, yomtov_out, is_hebrew):
    if shabbat_in and yomtov_out and yomtov_out > shabbat_in and yomtov_out.weekday() == 6:
        desc = "שבת עד יום טוב (יום ראשון)" if is_hebrew else "Shabbat through Yom Tov (Sunday)"
        return shabbat_in, yomtov_out, "shabbat_through_yomtov", desc, "Yom Tov ending Sunday after Shabbat"
    return None

def _get_case_yomtov_thursday_through_shabbat(yomtov_in, shabbat_out, is_hebrew):
    if yomtov_in and shabbat_out and yomtov_in.weekday() == 3:
        desc = "יום טוב (חמישי) עד שבת" if is_hebrew else "Yom Tov (Thursday) through Shabbat"
        return yomtov_in, shabbat_out, "yomtov_thursday_through_shabbat", desc, "Yom Tov starting Thursday before Shabbat"
    return None

def _get_case_yomtov_friday_through_shabbat(yomtov_in, yomtov_out, shabbat_out, is_hebrew):
    if yomtov_in and shabbat_out and yomtov_in.weekday() == 3:
        desc = "יום טוב (שישי) עד שבת" if is_hebrew else "Yom Tov (Friday) through Shabbat"
        return yomtov_in, shabbat_out, "yomtov_through_shabbat_friday", desc, "Yom Tov on Friday before Shabbat"
    return None

def _get_individual_or_upcoming_period(now, shabbat_in, shabbat_out, yomtov_in, yomtov_out, is_hebrew):
    if shabbat_in and shabbat_out and shabbat_in <= now <= shabbat_out:
        desc = "שבת בלבד" if is_hebrew else "Shabbat Only"
        return shabbat_in, shabbat_out, "shabbat_only", desc, None
    if yomtov_in and yomtov_out and yomtov_in <= now <= yomtov_out:
        desc = "יום טוב בלבד" if is_hebrew else "Yom Tov Only"
        return yomtov_in, yomtov_out, "yomtov_only", desc, None

    upcoming_periods = []
    if shabbat_in and shabbat_out and shabbat_in > now:
        desc = "שבת הבא" if is_hebrew else "Upcoming Shabbat"
        upcoming_periods.append((shabbat_in, shabbat_out, "shabbat_upcoming", desc, None))
    if yomtov_in and yomtov_out and yomtov_in > now:
        desc = "יום טוב הבא" if is_hebrew else "Upcoming Yom Tov"
        upcoming_periods.append((yomtov_in, yomtov_out, "yomtov_upcoming", desc, None))

    if upcoming_periods:
        upcoming_periods.sort(key=lambda x: x[0])
        return upcoming_periods[0]
    return None

def _populate_period_times(result, period_start, period_end, language):
    result["start"] = period_start
    result["end"] = period_end
    result["start_formatted"] = period_start.strftime("%H:%M")
    result["end_formatted"] = period_end.strftime("%H:%M")
    result["start_day"] = CoordinatorHelpers.get_localized_day(period_start, language)
    result["end_day"] = CoordinatorHelpers.get_localized_day(period_end, language)

    duration = period_end - period_start
    duration_hours = round(duration.total_seconds() / 3600, 1)
    result["duration_hours"] = duration_hours
    result["duration_formatted"] = CoordinatorHelpers.format_time_delta(duration, language)

def _populate_period_status(result, now, period_start, period_end, language):
    is_hebrew = CoordinatorHelpers.is_hebrew(language)
    is_active = period_start <= now <= period_end
    result["active"] = is_active

    if is_active:
        time_until_end = period_end - now
        result["time_until_end"] = time_until_end.total_seconds()
        result["minutes_until_end"] = int(time_until_end.total_seconds() / 60)
        result["time_until_end_formatted"] = CoordinatorHelpers.format_time_delta(time_until_end, language)
        
        if is_hebrew:
            result["status_text"] = f"איסור מלאכה פעיל - נגמר בעוד {result['time_until_end_formatted']}"
            result["work_status"] = "אסור"
        else:
            result["status_text"] = f"Active - Ends in {result['time_until_end_formatted']}"
            result["work_status"] = "Prohibited"
    elif period_start > now:
        time_until_start = period_start - now
        result["time_until_start"] = time_until_start.total_seconds()
        result["minutes_until_start"] = int(time_until_start.total_seconds() / 60)
        result["time_until_start_formatted"] = CoordinatorHelpers.format_time_delta(time_until_start, language)
        
        if is_hebrew:
            result["status_text"] = f"איסור מלאכה מתחיל בעוד {result['time_until_start_formatted']}"
            result["work_status"] = "מותר"
        else:
            result["status_text"] = f"Starts in {result['time_until_start_formatted']}"
            result["work_status"] = "Permitted"
    else:
        result["status_text"] = "איסור מלאכה הסתיים" if is_hebrew else "Ended"
        result["work_status"] = "מותר" if is_hebrew else "Permitted"
