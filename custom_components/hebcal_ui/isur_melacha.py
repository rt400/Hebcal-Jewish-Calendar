import datetime
from typing import Dict, Any

def calculate_isur_melacha_period(data: Dict[str, Any], language: str = "he") -> Dict[str, Any]:
    """
    Calculates the Issur Melacha (Work Prohibition) period.
    Dynamically merges Shabbat and Yom Tov if they overlap or are contiguous 
    (e.g., 2 days of Yom Tov going directly into Shabbat, commonly seen in the Diaspora).
    """
    # Fetch the current local time without timezone info (naive datetime)
    now = datetime.datetime.now().replace(tzinfo=None)

    def _make_naive(dt):
        """
        Helper function to clean up datetime objects.
        Converts strings to datetime and strips timezone information to 
        prevent comparison errors between aware and naive datetime objects.
        """
        if not dt: return None
        if isinstance(dt, str):
            try:
                dt = datetime.datetime.fromisoformat(dt.replace('Z', '+00:00'))
            except Exception:
                return None
        return dt.replace(tzinfo=None)

    # Extract and clean entry (in) and exit (out) times for both Shabbat and Yom Tov
    si = _make_naive(data.get("shabbat_in"))
    so = _make_naive(data.get("shabbat_out"))
    yi = _make_naive(data.get("yomtov_in"))
    yo = _make_naive(data.get("yomtov_out"))

    # Initialize the base structure of the output dictionary
    # This matches the schema expected by the Home Assistant sensor attributes
    result = {
        "active": False,
        "start": None,
        "end": None,
        "type": "none",
        "type_description": "אין איסור מלאכה קרוב" if language == "he" else "No upcoming Issur Melacha",
        "duration_hours": 0,
        "duration_formatted": "",
        "time_until_start": None,
        "time_until_end": None,
        "time_until_start_formatted": "",
        "time_until_end_formatted": "",
        "minutes_until_start": None,
        "minutes_until_end": None,
        "status_text": "אין איסור מלאכה באופק" if language == "he" else "No Issur Melacha in sight",
        "work_status": "מותר" if language == "he" else "Allowed",
        "components": {
            "shabbat_active": False,
            "yomtov_active": False,
            "shabbat_times": {},
            "yomtov_times": {}
        },
        "special_cases": [],
        "next_events": {
            "candle_lighting": None,
            "candle_lighting_formatted": "",
            "havdalah": None,
            "havdalah_formatted": ""
        }
    }

    def _get_time_props(dt_in, dt_out, lang):
        """
        Helper function to format individual start/end times and their corresponding weekdays.
        """
        days_he = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
        days_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        res = {}
        if dt_in:
            res["candles"] = dt_in.isoformat()
            res["candles_formatted"] = dt_in.strftime("%H:%M")
            res["candles_day"] = days_he[dt_in.weekday()] if lang == "he" else days_en[dt_in.weekday()]
        else:
            res["candles"] = None
            res["candles_formatted"] = ""
            res["candles_day"] = ""
            
        if dt_out:
            res["havdalah"] = dt_out.isoformat()
            res["havdalah_formatted"] = dt_out.strftime("%H:%M")
            res["havdalah_day"] = days_he[dt_out.weekday()] if lang == "he" else days_en[dt_out.weekday()]
        else:
            res["havdalah"] = None
            res["havdalah_formatted"] = ""
            res["havdalah_day"] = ""
        return res

    # Populate raw component times for debugging and specific UI displays
    result["components"]["shabbat_times"] = _get_time_props(si, so, language)
    result["components"]["yomtov_times"] = _get_time_props(yi, yo, language)

    # Build the initial list of available time intervals
    intervals = []
    if si and so:
        intervals.append({'type': 'shabbat_only', 'start': si, 'end': so})
    if yi and yo:
        intervals.append({'type': 'yomtov_only', 'start': yi, 'end': yo})

    # If neither Shabbat nor Yom Tov exists in the current data range, return the empty default
    if not intervals:
        return result

    # Step 1: Sort intervals chronologically based on their start times
    intervals.sort(key=lambda x: x['start'])

    # Step 2: Merge contiguous or overlapping blocks (Interval Merging Algorithm)
    # This prevents the system from splitting contiguous holidays (e.g., Wed-Fri Yom Tov leading into Fri-Sat Shabbat)
    merged = []
    for current in intervals:
        if not merged:
            merged.append(current)
        else:
            prev = merged[-1]
            # If the current interval starts before or exactly when the previous one ends, merge them!
            if current['start'] <= prev['end']:
                # Extend the end time to the maximum of both blocks
                prev['end'] = max(prev['end'], current['end'])
                # If we are merging a Yom Tov and a Shabbat, update the block type
                if prev['type'] != current['type']:
                    prev['type'] = 'shabbat_and_yomtov'
            else:
                # If there is a gap between intervals, append it as a new distinct block
                merged.append(current)

    # Step 3: Identify the active interval (if currently inside one) or the next upcoming interval
    target_interval = None
    is_active = False
    
    # Check if we are currently inside any of the merged blocks
    for m in merged:
        if m['start'] <= now <= m['end']:
            target_interval = m
            is_active = True
            break
    
    # If not currently active, find the nearest future block
    if not target_interval:
        for m in merged:
            if m['start'] > now:
                target_interval = m
                break
    
    # If all events are in the past, return the empty default
    if not target_interval:
        return result

    # Extract final calculated boundaries and type
    t_start = target_interval['start']
    t_end = target_interval['end']
    t_type = target_interval['type']

    result["active"] = is_active
    result["start"] = t_start.isoformat()
    result["end"] = t_end.isoformat()
    result["type"] = t_type

    # Step 4: Generate custom descriptions and flag special geographic cases
    if t_type == 'shabbat_only':
        result["type_description"] = "שבת בלבד" if language == "he" else "Shabbat Only"
    elif t_type == 'yomtov_only':
        result["type_description"] = "יום טוב בלבד" if language == "he" else "Yom Tov Only"
    else:
        result["type_description"] = "שבת ויום טוב (רצוף)" if language == "he" else "Shabbat & Yom Tov (Contiguous)"
        # Append diagnostic tags to help users understand why the holiday is unusually long
        if data.get("diaspora", False) or "diaspora" in str(data).lower():
             result["special_cases"].append("diaspora_contiguous")
        else:
             result["special_cases"].append("israel_contiguous")

    # Step 5: Calculate total duration of the targeted block
    duration = t_end - t_start
    result["duration_hours"] = round(duration.total_seconds() / 3600.0, 1)
    result["duration_formatted"] = _format_td(duration, language)

    # Step 6: Calculate real-time countdowns and generate localized status text
    if is_active:
        until_end = t_end - now
        result["time_until_end"] = until_end.total_seconds()
        result["time_until_end_formatted"] = _format_td(until_end, language)
        result["minutes_until_end"] = int(until_end.total_seconds() // 60)
        result["work_status"] = "אסור" if language == "he" else "Forbidden"
        status_t = f"איסור מלאכה פעיל\nנגמר בעוד {result['time_until_end_formatted']}" if language == "he" else f"Active\nEnds in {result['time_until_end_formatted']}"
        result["status_text"] = status_t
    else:
        until_start = t_start - now
        result["time_until_start"] = until_start.total_seconds()
        result["time_until_start_formatted"] = _format_td(until_start, language)
        result["minutes_until_start"] = int(until_start.total_seconds() // 60)
        result["work_status"] = "מותר" if language == "he" else "Allowed"
        status_t = f"מתחיל בעוד {result['time_until_start_formatted']}" if language == "he" else f"Starts in {result['time_until_start_formatted']}"
        result["status_text"] = status_t

    # Step 7: Determine real-time active components inside a merged block
    # Helps the UI show exactly what is currently happening (e.g., it's Friday night, so both might technically be active)
    if is_active:
        result["components"]["shabbat_active"] = (si and so and si <= now <= so) or False
        result["components"]["yomtov_active"] = (yi and yo and yi <= now <= yo) or False

    # Step 8: Calculate precise 'next events' for the unified block
    # Candle Lighting: The very next candle lighting time that hasn't passed yet.
    # Note: Even in a contiguous block, there might be a secondary candle lighting (e.g., lighting Shabbat candles on Friday night during Yom Tov).
    future_candles = [dt for dt in [si, yi] if dt and dt > now]
    next_candle = min(future_candles) if future_candles else None
    
    # Havdalah: Strictly the end time of the entire merged block. 
    # Ensures no false havdalah triggers in the middle of a contiguous holiday.
    next_havdalah = t_end

    def _format_dt_event(dt, lang):
        """Helper function to format event strings combining the day name and time."""
        if not dt: return ""
        days_he = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
        days_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        day = days_he[dt.weekday()] if lang == "he" else days_en[dt.weekday()]
        return f"{day} {dt.strftime('%H:%M')}"

    # Assign calculated next events to the final payload
    result["next_events"]["candle_lighting"] = next_candle.isoformat() if next_candle else None
    result["next_events"]["candle_lighting_formatted"] = _format_dt_event(next_candle, language) if next_candle else ""
    
    result["next_events"]["havdalah"] = next_havdalah.isoformat() if next_havdalah else None
    result["next_events"]["havdalah_formatted"] = _format_dt_event(next_havdalah, language) if next_havdalah else ""

    return result

def _format_td(td: datetime.timedelta, language: str) -> str:
    """
    Helper function to format timedelta objects into human-readable strings (Days, Hours, Minutes).
    """
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    parts = []
    if language == "he":
        if days > 0:
            if days == 1: parts.append("יום אחד")
            elif days == 2: parts.append("יומיים")
            else: parts.append(f"{days} ימים")
        if hours > 0:
            if hours == 1: parts.append("שעה אחת")
            elif hours == 2: parts.append("שעתיים")
            else: parts.append(f"{hours} שעות")
        if minutes > 0:
            if minutes == 1: parts.append("דקה אחת")
            else: parts.append(f"{minutes} דקות")
    else:
        if days > 0: parts.append(f"{days} {'day' if days == 1 else 'days'}")
        if hours > 0: parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
        if minutes > 0: parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
        
    return ", ".join(parts) if parts else "0 דקות" if language == "he" else "0 minutes"
