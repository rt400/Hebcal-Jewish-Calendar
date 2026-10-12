"""Processes and cleans Hebcal API event items and holidays."""
import datetime
import unicodedata
from typing import Dict, Any

from .helpers import CoordinatorHelpers

class EventProcessor:
    """Helper class to clean, parse, and structure raw Hebcal API items."""

    def __init__(self, zmanim_calc, language: str = "he"):
        """Initialize with a ZmanimCalculator instance and language preference."""
        self.zmanim_calc = zmanim_calc
        self.language = language

    @staticmethod
    def clean_item_text(item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively strip Hebrew vowels (Nikud) from API textual data items 
        to ensure clean rendering in Home Assistant UI.
        """
        if not isinstance(item, dict):
            return item
            
        cleaned = {}
        for key, value in item.items():
            if isinstance(value, str):
                cleaned[key] = "".join(
                    c for c in unicodedata.normalize("NFD", value)
                    if not (0x0591 <= ord(c) <= 0x05C7)
                )
            elif isinstance(value, dict):
                cleaned[key] = EventProcessor.clean_item_text(value)
            elif isinstance(value, list):
                cleaned[key] = [
                    EventProcessor.clean_item_text(v) if isinstance(v, (dict, list, str)) else v
                    for v in value
                ]
            else:
                cleaned[key] = value
        return cleaned

    def process_hebcal_item(self, item: Dict[str, Any], processed: Dict[str, Any]) -> None:
        """
        Process, categorize, and route individual items returned from the Hebcal API payload.
        Sets boolean flags for Home Assistant sensors (e.g., special_holiday).
        """
        if not item or not isinstance(item, dict):
            return

        category = item.get("category")
        if not category:
            return

        title_orig = item.get("title_orig", "")
        title = item.get("title", "")
        
        # Ensure date string is standardized to max 19 chars (YYYY-MM-DDTHH:MM:SS)
        if "date" in item:
            item["date"] = item["date"][:19]
            
        item_date = item.get("date", "")
        
        # Determine if the current API event falls on today's date
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        is_today = item_date.startswith(today_str)

        # ---------------------------------------------------------
        # BUG FIX: Properly flag special holidays (like Rosh Chodesh) 
        # so HA sensors know to display them when they occur today.
        # ---------------------------------------------------------
        if is_today and category in ["holiday", "yomtov", "roshchodesh", "mevarchim"]:
            if "Rosh Hashana" in title_orig or "Rosh Hashana" in title or "ראש השנה" in title_orig:
                processed["rosh_hashana"] = True
            else:
                processed["special_holiday"] = True

        valid_categories = [
            "candles", "havdalah", "parashat", "yomtov", 
            "holiday", "omer", "roshchodesh", "mevarchim"
        ]
        
        if category in valid_categories:
            # Extract Parasha (Weekly Torah Portion) if the event falls on a Saturday
            if category == "parashat":
                try:
                    item_dt = datetime.datetime.fromisoformat(item_date).date()
                    if item_dt.weekday() == 5:  # Saturday
                        processed["parasha"] = title
                    elif not processed.get("parasha"):
                        processed["parasha"] = title
                except Exception:
                    pass

            # Inject calculated sunset boundaries for holidays missing explicit times
            if category in ["yomtov", "holiday"]:
                item["start"] = self.zmanim_calc.sunset_time_str(item_date, -1)
                item["end"] = self.zmanim_calc.sunset_time_str(item_date, 0)
                
                # Only register as a strict 'Yom Tov' (Work Prohibition) if flagged by the API
                if item.get("yomtov"):
                    processed["holidays"].append({
                        "name": title,
                        "date": item_date[:10],
                        "start": item.get("start"),
                        "end": item.get("end"),
                        "yomtov_in": None,
                        "yomtov_out": None
                    })
                    
            # Always append the valid item to the events array for the HA sensor
            processed["events"].append(item)

    def complete_missing_times(self, processed: Dict[str, Any], havdalah_minutes: int, candle_minutes: int) -> None:
        """
        Scan the processed events array and fill in missing candle lighting 
        and havdalah times for holidays and shabbat using the local offline calculator.
        """
        now = datetime.datetime.now()
        events_to_add = {}

        def add_manual(dt_obj: datetime.datetime, cat: str):
            """Helper to append locally calculated fallback events."""
            key = (dt_obj.isoformat(), cat)
            if key not in events_to_add:
                events_to_add[key] = True
                self._add_manual_event(processed, cat, dt_obj, havdalah_minutes)

        api_candles = {}
        api_havdalahs = {}
        
        # Map existing API events for quick lookup
        for ev in processed.get("events", []):
            cat = ev.get("category")
            if cat not in ["candles", "havdalah"]:
                continue
                
            ev_date = ev.get("date", "")[:10]
            dt_obj = datetime.datetime.fromisoformat(ev["date"][:19])
            if cat == "candles":
                api_candles[ev_date] = dt_obj
            else:
                api_havdalahs[ev_date] = dt_obj

        # Process Yom Tov times
        sorted_holidays = sorted(processed.get("holidays", []), key=lambda h: h["date"])
        for i, holiday in enumerate(sorted_holidays):
            h_date = datetime.datetime.fromisoformat(holiday["date"][:10]).date()
            eve_date = h_date - datetime.timedelta(days=1)

            # Determine entry time
            y_in = api_candles.get(eve_date.isoformat()) or api_candles.get(h_date.isoformat())
            if y_in:
                holiday["yomtov_in"] = y_in
            else:
                y_in = self.zmanim_calc.get_offline_missing_time(h_date, "candles", -1)
                holiday["yomtov_in"] = y_in
                if y_in: 
                    add_manual(y_in, "candles")

            # Check for contiguous holidays (e.g., Diaspora 2-day Yom Tov)
            has_next_holiday = (i + 1 < len(sorted_holidays)) and \
                               (datetime.datetime.fromisoformat(sorted_holidays[i + 1]["date"][:10]).date() == h_date + datetime.timedelta(days=1))

            y_out = api_havdalahs.get(h_date.isoformat())

            # Determine exit time
            if y_out:
                holiday["yomtov_out"] = y_out
            elif has_next_holiday:
                next_in = api_candles.get(h_date.isoformat())
                if next_in:
                    holiday["yomtov_out"] = next_in
                else:
                    calc_out = self.zmanim_calc.get_offline_missing_time(h_date, "candles", 0)
                    holiday["yomtov_out"] = calc_out
                    if calc_out: 
                        add_manual(calc_out, "candles")
            else:
                calc_out = self.zmanim_calc.get_offline_missing_time(h_date, "havdalah", 0)
                holiday["yomtov_out"] = calc_out
                if calc_out: 
                    add_manual(calc_out, "havdalah")

        # Process Shabbat times
        shabbats = []
        if processed.get("events"):
            any_date = datetime.datetime.fromisoformat(processed["events"][0]["date"][:19]).date()
            days_to_friday = (4 - any_date.weekday()) % 7
            friday_date = any_date + datetime.timedelta(days=days_to_friday)
            saturday_date = friday_date + datetime.timedelta(days=1)

            # Determine Shabbat entry
            s_in = api_candles.get(friday_date.isoformat())
            if not s_in:
                s_in = self.zmanim_calc.get_offline_missing_time(friday_date, "candles", 0)
                if s_in: 
                    add_manual(s_in, "candles")

            # Determine Shabbat exit
            s_out = api_havdalahs.get(saturday_date.isoformat())
            if not s_out:
                sunday_date = saturday_date + datetime.timedelta(days=1)
                is_sunday_holiday = any(h["date"][:10] == sunday_date.isoformat() for h in processed.get("holidays", []))

                if is_sunday_holiday:
                    s_out = api_candles.get(saturday_date.isoformat())
                    if not s_out:
                        s_out = self.zmanim_calc.get_offline_missing_time(saturday_date, "candles", 0)
                        if s_out: 
                            add_manual(s_out, "candles")
                else:
                    s_out = self.zmanim_calc.get_offline_missing_time(saturday_date, "havdalah", 0)
                    if s_out: 
                        add_manual(s_out, "havdalah")

            if s_in and s_out:
                shabbats.append({"in": s_in, "out": s_out})

        # Identify active or next Shabbat
        if shabbats:
            active_shabbat = next((s for s in shabbats if s["in"] <= now <= s["out"]), None)
            if not active_shabbat:
                active_shabbat = next((s for s in shabbats if s["in"] > now), shabbats[-1])
            processed["shabbat_in"] = active_shabbat["in"]
            processed["shabbat_out"] = active_shabbat["out"]
        else:
            processed["shabbat_in"] = None
            processed["shabbat_out"] = None

        # Merge contiguous Yom Tovs based on temporal proximity (less than 3 hours gap)
        raw_yomtovs = [{"in": h["yomtov_in"], "out": h["yomtov_out"]} 
                       for h in processed.get("holidays", []) 
                       if h.get("yomtov_in") and h.get("yomtov_out")]
        raw_yomtovs.sort(key=lambda x: x["in"])
        
        merged_yomtovs = []
        current_yt = None
        for yt in raw_yomtovs:
            if not current_yt:
                current_yt = {"in": yt["in"], "out": yt["out"]}
            else:
                if (yt["in"] - current_yt["out"]).total_seconds() < 10800:
                    current_yt["out"] = max(current_yt["out"], yt["out"])
                else:
                    merged_yomtovs.append(current_yt)
                    current_yt = {"in": yt["in"], "out": yt["out"]}
        if current_yt:
            merged_yomtovs.append(current_yt)

        # Identify active or next Yom Tov
        if merged_yomtovs:
            active_yt = next((y for y in merged_yomtovs if y["in"] <= now <= y["out"]), None)
            if not active_yt:
                active_yt = next((y for y in merged_yomtovs if y["in"] > now), merged_yomtovs[-1])
            processed["yomtov_in"] = active_yt["in"]
            processed["yomtov_out"] = active_yt["out"]
        else:
            processed["yomtov_in"] = None
            processed["yomtov_out"] = None

    def _add_manual_event(self, processed: Dict[str, Any], event_type: str, event_time: datetime.datetime, havdalah_minutes: int) -> None:
        """
        Append locally calculated fallback events (Havdalah/Candles) to the events array 
        with localized text based on the user's language settings.
        """
        is_hebrew = CoordinatorHelpers.is_hebrew(self.language)

        if event_type == "havdalah":
            title = "הבדלה - ידני" if is_hebrew else "Havdalah - Manual"
            hebrew_text = f"הבדלה - {havdalah_minutes} דקות"
        else:
            title = "הדלקת נרות - ידני" if is_hebrew else "Candle lighting - Manual"
            hebrew_text = "הדלקת נרות"
            
        processed["events"].append({
            "className": event_type,
            "hebrew": hebrew_text,
            "date": event_time.isoformat(),
            "allDay": False,
            "title": title,
        })
