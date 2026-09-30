"""Handles local halachic times (Zmanim), sunset calculations, and missing event times."""
import datetime
from datetime import timedelta
import hdate
from hdate.translator import set_language
from hdate.zmanim import Zman

class ZmanimCalculator:
    """Helper class to encapsulate all Zmanim and astronomical calculations."""

    def __init__(self, offline_hebcal: hdate.Location, candle_minutes: int, havdalah_minutes: int):
        """Initialize the calculator with location and minute offsets."""
        self.offline_hebcal = offline_hebcal
        self.candle_minutes = candle_minutes
        self.havdalah_minutes = havdalah_minutes

    def fetch_zmanim_data(self, date: datetime.date) -> dict[str, datetime.datetime]:
        """Extract halachic times (Zmanim) locally via the hdate package for a given date."""
        processed_zmanim = {}
        raw_data = hdate.Zmanim(date=date, location=self.offline_hebcal).zmanim
        for k, v in raw_data.items():
            time_obj = self.zman_to_dict(v)
            if time_obj:
                processed_zmanim[k] = time_obj
        return processed_zmanim

    def fetch_hebrew_date(self, date: datetime.date) -> dict[str, str]:
        """Fetch corresponding Hebrew and English calendar date strings."""
        try:
            hdate_obj = hdate.HDateInfo(date)
            set_language("he")
            hebrew_date_str = str(hdate_obj).replace("ה' ", "ה")
            set_language("en")
            english_date_str = str(hdate_obj)
            return {"hebrew": hebrew_date_str, "english": english_date_str}
        except Exception:
            return {"hebrew": "", "english": ""}

    def get_sunset_time(self, date: datetime.date, day_offset: int = 0) -> datetime.datetime:
        """Calculate exact local sunset time for a specific date using hdate."""
        try:
            target_date = date + datetime.timedelta(days=day_offset)
            sunset_utc = hdate.Zmanim(date=target_date, location=self.offline_hebcal).zmanim.get("shkia").local
            if sunset_utc is None:
                return datetime.datetime.combine(target_date, datetime.time(18, 0))
            return sunset_utc.replace(tzinfo=None)
        except Exception:
            return datetime.datetime.combine(date, datetime.time(18, 0))

    def sunset_time_str(self, date_str: str, day_offset: int) -> str:
        """Calculate ISO formatted sunset time string with an optional day offset."""
        try:
            date = datetime.datetime.fromisoformat(date_str[:19]).date()
            sunset = self.get_sunset_time(date, day_offset)
            return sunset.isoformat()
        except Exception:
            return date_str

    def get_offline_missing_time(self, date: datetime.date | datetime.datetime, type_calculation: str,
                                 days_offset: int) -> datetime.datetime | None:
        """Calculate missing candle lighting or havdalah timestamps mathematically using sunset data."""
        target_date = (date.date() if isinstance(date, datetime.datetime) else date) + timedelta(days=days_offset)
        zmanim_obj = hdate.Zmanim(date=target_date, location=self.offline_hebcal)
        shkia_zman = zmanim_obj.zmanim.get("shkia")

        if not shkia_zman or not shkia_zman.local:
            return None

        shkia_local = shkia_zman.local

        if type_calculation == "havdalah":
            dt = shkia_local + timedelta(minutes=self.havdalah_minutes)
        elif type_calculation == "candles":
            dt = shkia_local - timedelta(minutes=self.candle_minutes)
        else:
            return None

        return dt.replace(tzinfo=None)

    @staticmethod
    def zman_to_dict(zman: Zman) -> datetime.datetime | None:
        """Convert a zman object into a timezone-naive local datetime object."""
        dt_utc = zman.utc
        if dt_utc is None:
            return None
        if dt_utc.tzinfo is None:
            from datetime import timezone
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        return dt_utc.astimezone(zman.timezone).replace(tzinfo=None)
