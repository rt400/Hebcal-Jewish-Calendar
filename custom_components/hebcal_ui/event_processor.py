"""Processes and cleans Hebcal API event items and holidays."""
import datetime
import unicodedata

class EventProcessor:
    """Helper class to clean, parse, and structure raw Hebcal API items."""

    def __init__(self, zmanim_calc):
        """Initialize with a ZmanimCalculator instance to calculate missing sunset/holiday times."""
        self.zmanim_calc = zmanim_calc

    @staticmethod
    def clean_item_text(item: dict[str, any]) -> dict[str, any]:
        """Strip Hebrew vowels (Nikud) and diacritics from API textual data items recursively."""
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

    def process_hebcal_item(self, item: dict[str, any], processed: dict[str, any]):
        """Process and categorize individual items returned from Hebcal API payload."""
        if not item or not isinstance(item, dict):
            return

        category = item.get("category")
        if not category:
            return

        title_orig = item.get("title_orig", "")
        title = item.get("title", "")
        if "Rosh Hashana" in title_orig or "Rosh Hashana" in title or "ראש השנה" in title_orig:
            processed["rosh_hashana"] = True

        if "date" in item:
            item["date"] = item["date"][:19]

        if category in ["candles", "havdalah", "parashat", "yomtov", "holiday", "omer", "roshchodesh", "mevarchim"]:
            if category == "parashat":
                try:
                    item_date = datetime.datetime.fromisoformat(item["date"][:19]).date()
                    if item_date.weekday() == 5:
                        processed["parasha"] = item.get("title")
                    elif not processed.get("parasha"):
                        processed["parasha"] = item.get("title")
                except Exception:
                    pass

            if category in ["yomtov", "holiday"]:
                item["start"] = self.zmanim_calc.sunset_time_str(item["date"], -1)
                item["end"] = self.zmanim_calc.sunset_time_str(item["date"], 0)
                if item.get("yomtov"):
                    processed["holidays"].append({
                        "name": item.get("title"),
                        "date": item.get("date")[:10],
                        "start": item.get("start"),
                        "end": item.get("end"),
                        "yomtov_in": None,
                        "yomtov_out": None
                    })
            processed["events"].append(item)

    def complete_missing_times(self, processed: dict[str, any], havdalah_minutes: int, candle_minutes: int):
        """Fill in missing candle lighting and havdalah times for holidays and shabbat."""
        now = datetime.datetime.now()
        events_to_add = {}

        def add_manual(dt: datetime.datetime, cat: str):
            key = (dt.isoformat(), cat)
            if key not in events_to_add:
                events_to_add[key] = True
                self._add_manual_event(processed, cat, dt, havdalah_minutes)

        api_candles = {}
        api_havdalahs = {}
        for ev in processed.get("events", []):
            cat = ev.get("category")
            if cat not in ["candles", "havdalah"]:
                continue
            ev_date = ev.get("date", "")[:10]
            dt = datetime.datetime.fromisoformat(ev["date"][:19])
            if cat == "candles":
                api_candles[ev_date] = dt
            else:
                api_havdalahs[ev_date] = dt

        sorted_holidays = sorted(processed.get("holidays", []), key=lambda h: h["date"])
        for i, holiday in enumerate(sorted_holidays):
            h_date = datetime.datetime.fromisoformat(holiday["date"][:10]).date()
            eve_date = h_date - datetime.timedelta(days=1)

            y_in = api_candles.get(eve_date.isoformat()) or api_candles.get(h_date.isoformat())
            if y_in:
                holiday["yomtov_in"] = y_in
            else:
                y_in = self.zmanim_calc.get_offline_missing_time(h_date, "candles", -1)
                holiday["yomtov_in"] = y_in
                if y_in: add_manual(y_in, "candles")

            has_next_holiday = (i + 1 < len(sorted_holidays)) and \
                               (datetime.datetime.fromisoformat(
                                   sorted_holidays[i + 1]["date"][:10]).date() == h_date + datetime.timedelta(days=1))

            y_out = api_havdalahs.get(h_date.isoformat())

            if y_out:
                holiday["yomtov_out"] = y_out
            elif has_next_holiday:
                next_in = api_candles.get(h_date.isoformat())
                if next_in:
                    holiday["yomtov_out"] = next_in
                else:
                    calc_out = self.zmanim_calc.get_offline_missing_time(h_date, "candles", 0)
                    holiday["yomtov_out"] = calc_out
                    if calc_out: add_manual(calc_out, "candles")
            else:
                calc_out = self.zmanim_calc.get_offline_missing_time(h_date, "havdalah", 0)
                holiday["yomtov_out"] = calc_out
                if calc_out: add_manual(calc_out, "havdalah")

        shabbats = []
        if processed.get("events"):
            any_date = datetime.datetime.fromisoformat(processed["events"][0]["date"][:19]).date()
            days_to_friday = (4 - any_date.weekday()) % 7
            friday_date = any_date + datetime.timedelta(days=days_to_friday)
            saturday_date = friday_date + datetime.timedelta(days=1)

            s_in = api_candles.get(friday_date.isoformat())
            if not s_in:
                s_in = self.zmanim_calc.get_offline_missing_time(friday_date, "candles", 0)
                if s_in: add_manual(s_in, "candles")

            s_out = api_havdalahs.get(saturday_date.isoformat())
            if not s_out:
                sunday_date = saturday_date + datetime.timedelta(days=1)
                is_sunday_holiday = any(
                    h["date"][:10] == sunday_date.isoformat() for h in processed.get("holidays", []))

                if is_sunday_holiday:
                    s_out = api_candles.get(saturday_date.isoformat())
                    if not s_out:
                        s_out = self.zmanim_calc.get_offline_missing_time(saturday_date, "candles", 0)
                        if s_out: add_manual(s_out, "candles")
                else:
                    s_out = self.zmanim_calc.get_offline_missing_time(saturday_date, "havdalah", 0)
                    if s_out: add_manual(s_out, "havdalah")

            if s_in and s_out:
                shabbats.append({"in": s_in, "out": s_out})

        merged_blocks = []
        current_block = None

        all_periods = [{"in": h["yomtov_in"], "out": h["yomtov_out"]} for h in processed.get("holidays", []) if
                       h.get("yomtov_in") and h.get("yomtov_out")]
        all_periods.extend(shabbats)
        all_periods.sort(key=lambda x: x["in"])

        for p in all_periods:
            if not current_block:
                current_block = {"in": p["in"], "out": p["out"]}
            else:
                if (p["in"] - current_block["out"]).total_seconds() < 10800:
                    current_block["out"] = max(current_block["out"], p["out"])
                else:
                    merged_blocks.append(current_block)
                    current_block = {"in": p["in"], "out": p["out"]}
        if current_block:
            merged_blocks.append(current_block)

        active_or_next = None
        for block in merged_blocks:
            if block["in"] <= now <= block["out"]:
                active_or_next = block
                break
            elif block["in"] > now and not active_or_next:
                active_or_next = block

        if not active_or_next and merged_blocks:
            active_or_next = merged_blocks[-1]

        if active_or_next:
            processed["yomtov_in"] = active_or_next["in"]
            processed["yomtov_out"] = active_or_next["out"]

        if shabbats:
            active_shabbat = next((s for s in shabbats if s["in"] <= now <= s["out"]), shabbats[-1])
            processed["shabbat_in"] = active_shabbat["in"]
            processed["shabbat_out"] = active_shabbat["out"]

    @staticmethod
    def _add_manual_event(processed: dict, event_type: str, event_time: datetime.datetime, havdalah_minutes: int):
        """Append manual backup events (candles or havdalah) to the event list."""
        if event_type == "havdalah":
            title = "הבדלה - ידני"
            hebrew = f"הבדלה - {havdalah_minutes} דקות"
        else:
            title = "הדלקת נרות - ידני"
            hebrew = "הדלקת נרות"
        processed["events"].append({
            "className": event_type,
            "hebrew": hebrew,
            "date": event_time.isoformat(),
            "allDay": False,
            "title": title,
        })
