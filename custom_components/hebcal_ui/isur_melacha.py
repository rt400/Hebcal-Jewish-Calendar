"""Calculates the Issur Melacha (work prohibition) period and manages related logic."""
import datetime
import logging
from datetime import timedelta

_LOGGER = logging.getLogger(__name__)

def calculate_isur_melacha_period(coordinator, data: dict[str, any]) -> dict[str, any]:
    """Calculate comprehensive Issur Melacha period information."""
    now = datetime.datetime.now()

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

    if shabbat_in and shabbat_out:
        result["components"]["shabbat_active"] = shabbat_in <= now <= shabbat_out
    if yomtov_in and yomtov_out:
        result["components"]["yomtov_active"] = yomtov_in <= now <= yomtov_out

    period_info = (
        _get_case_shabbat_through_yomtov(shabbat_in, yomtov_out) or
        _get_case_yomtov_thursday_through_shabbat(yomtov_in, shabbat_out) or
        _get_case_yomtov_friday_through_shabbat(yomtov_in, yomtov_out, shabbat_out) or
        _get_individual_or_upcoming_period(now, shabbat_in, shabbat_out, yomtov_in, yomtov_out)
    )

    period_start, period_end = None, None
    if period_info:
        period_start, period_end, period_type, type_hebrew, special_case = period_info
        result["type"] = period_type
        result["type_hebrew"] = type_hebrew
        if special_case:
            result["special_cases"].append(special_case)

    if period_start and period_end:
        _populate_period_times(result, period_start, period_end)
        _populate_period_status(result, now, period_start, period_end, coordinator.format_time_delta)

    if data.get("rosh_hashana"):
        result["special_cases"].append("Rosh Hashana (2 days)")
    if data.get("special_holiday"):
        result["special_cases"].append("Special Holiday")

    next_candles = coordinator.next_candle_lighting
    if next_candles:
        result["next_events"]["candle_lighting"] = next_candles.isoformat()
        result["next_events"]["candle_lighting_formatted"] = next_candles.strftime("%A %H:%M")

    next_havdalah = coordinator.next_havdalah
    if next_havdalah:
        result["next_events"]["havdalah"] = next_havdalah.isoformat()
        result["next_events"]["havdalah_formatted"] = next_havdalah.strftime("%A %H:%M")

    return result

def _get_case_shabbat_through_yomtov(shabbat_in, yomtov_out):
    if shabbat_in and yomtov_out and yomtov_out > shabbat_in and yomtov_out.weekday() == 6:
        return shabbat_in, yomtov_out, "shabbat_through_yomtov", "שבת עד יום טוב (יום ראשון)", "Yom Tov ending Sunday after Shabbat"
    return None

def _get_case_yomtov_thursday_through_shabbat(yomtov_in, shabbat_out):
    if yomtov_in and shabbat_out and yomtov_in.weekday() == 3:
        return yomtov_in, shabbat_out, "yomtov_thursday_through_shabbat", "יום טוב (חמישי) עד שבת", "Yom Tov starting Thursday before Shabbat"
    return None

def _get_case_yomtov_friday_through_shabbat(yomtov_in, yomtov_out, shabbat_out):
    if yomtov_in and shabbat_out and yomtov_in.weekday() == 3:
        return yomtov_in, shabbat_out, "yomtov_through_shabbat_friday", "יום טוב (שישי) עד שבת", "Yom Tov on Friday before Shabbat"
    return None

def _get_individual_or_upcoming_period(now, shabbat_in, shabbat_out, yomtov_in, yomtov_out):
    if shabbat_in and shabbat_out and shabbat_in <= now <= shabbat_out:
        return shabbat_in, shabbat_out, "shabbat_only", "שבת בלבד", None
    if yomtov_in and yomtov_out and yomtov_in <= now <= yomtov_out:
        return yomtov_in, yomtov_out, "yomtov_only", "יום טוב בלבד", None

    upcoming_periods = []
    if shabbat_in and shabbat_out and shabbat_in > now:
        upcoming_periods.append((shabbat_in, shabbat_out, "shabbat_upcoming", "שבת הבא", None))
    if yomtov_in and yomtov_out and yomtov_in > now:
        upcoming_periods.append((yomtov_in, yomtov_out, "yomtov_upcoming", "יום טוב הבא", None))

    if upcoming_periods:
        upcoming_periods.sort(key=lambda x: x[0])
        return upcoming_periods[0]
    return None

def _populate_period_times(result, period_start, period_end):
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

def _populate_period_status(result, now, period_start, period_end, format_time_delta_func):
    is_active = period_start <= now <= period_end
    result["active"] = is_active

    if is_active:
        time_until_end = period_end - now
        result["time_until_end"] = time_until_end.total_seconds()
        result["minutes_until_end"] = int(time_until_end.total_seconds() / 60)
        result["time_until_end_formatted"] = format_time_delta_func(time_until_end)
        result["status_hebrew"] = f"איסור מלאכה פעיל - נגמר בעוד {result['time_until_end_formatted']}"
        result["work_status"] = "Prohibited"
        result["work_status_hebrew"] = "אסור"
    elif period_start > now:
        time_until_start = period_start - now
        result["time_until_start"] = time_until_start.total_seconds()
        result["minutes_until_start"] = int(time_until_start.total_seconds() / 60)
        result["time_until_start_formatted"] = format_time_delta_func(time_until_start)
        result["status_hebrew"] = f"איסור מלאכה מתחיל בעוד {result['time_until_start_formatted']}"
        result["work_status"] = "Permitted"
        result["work_status_hebrew"] = "מותר"
    else:
        result["status_hebrew"] = "איסור מלאכה הסתיים"
        result["work_status"] = "Permitted"
        result["work_status_hebrew"] = "מותר"
