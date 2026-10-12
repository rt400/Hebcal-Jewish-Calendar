"""Offline calculation engine for the Hebcal integration using the hdate library."""
import datetime as dt
import logging
from typing import Dict, Any, Optional, List

from hdate import HDateInfo, Location, Zmanim
from hdate.holidays import HolidayTypes
from hdate.parasha import Parasha
from hdate.translator import set_language

_LOGGER = logging.getLogger(__name__)


class OfflineJewishCalendar:
    """
    A standalone, offline calculation engine for Jewish calendar events, 
    Shabbat times, holidays, and daily Zmanim. Does not require internet access.
    """

    def __init__(
        self,
        latitude: float,
        longitude: float,
        timezone: str,
        diaspora: bool,
        candle_minutes: int,
        havdalah_minutes: int,
        language: str
    ):
        # Initialize the geographic location for accurate astronomical calculations
        self.location = Location(
            name="HA_Local_Instance",
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
            diaspora=diaspora,
        )
        self.candle_minutes = candle_minutes
        self.havdalah_minutes = havdalah_minutes

        # Dynamically set the output language based on HA configuration
        lang_code = "he" if language.lower() in ["he", "hebrew", "עברית"] else "en"
        try:
            set_language(lang_code)
        except Exception as e:
            _LOGGER.warning("Could not set hdate language, falling back to default: %s", e)

    def _extract_datetime(self, obj: Any, base_date: dt.date) -> Optional[dt.datetime]:
        """
        Helper method to safely extract a standard datetime object from various 
        hdate returned formats (which can sometimes mix datetime, time, or custom objects).
        """
        if obj is None:
            return None
        if isinstance(obj, dt.datetime):
            return obj
        if isinstance(obj, dt.time):
            return dt.datetime.combine(base_date, obj)

        # Iterate over common attributes hdate uses to store the actual time value
        for attr in ['dt', 'datetime', 'time', 'local']:
            if hasattr(obj, attr):
                val = getattr(obj, attr)
                if isinstance(val, dt.datetime):
                    return val
                if isinstance(val, dt.time):
                    return dt.datetime.combine(base_date, val)
                    
        return None

    def get_info(self, day: dt.date) -> HDateInfo:
        """Fetch general Hebrew calendar info (Parasha, Hebrew date, etc.) for a specific date."""
        try:
            return HDateInfo(day, diaspora=self.location.diaspora)
        except TypeError:
            return HDateInfo(day)

    def get_zmanim(self, day: dt.date) -> Zmanim:
        """Calculate daily Zmanim for a specific date based on the configured coordinates."""
        return Zmanim(
            date=day,
            location=self.location,
            candle_lighting_offset=self.candle_minutes,
            havdalah_offset=self.havdalah_minutes,
        )

    def get_candle_lighting(self, day: dt.date) -> Optional[str]:
        """Return the ISO formatted candle lighting time, if applicable."""
        zmanim_data = self.get_zmanim(day)
        extracted_time = self._extract_datetime(zmanim_data.candle_lighting, day)
        return extracted_time.isoformat() if extracted_time else None

    def get_havdalah(self, day: dt.date) -> Optional[str]:
        """Return the ISO formatted havdalah time, if applicable."""
        zmanim_data = self.get_zmanim(day)
        extracted_time = self._extract_datetime(zmanim_data.havdalah, day)
        return extracted_time.isoformat() if extracted_time else None

    def get_holiday_names(self, info: HDateInfo) -> str:
        """Extract and join holiday names into a single string."""
        return ", ".join(str(h) for h in info.holidays)

    def process_daily_data(self, day: dt.date) -> Dict[str, Any]:
        """Compile basic daily calendar and Zmanim information."""
        info = self.get_info(day)
        zmanim_data = self.get_zmanim(day)

        # Normalize zmanim keys to match the integration's expected standard
        normalized_zmanim = {}
        if hasattr(zmanim_data, 'zmanim') and isinstance(zmanim_data.zmanim, dict):
            key_mapping = {
                "shkia": "sunset",
                "netz": "sunrise",
                "alot_hashachar": "alotHaShachar"
            }
            
            for key, val in zmanim_data.zmanim.items():
                extracted = self._extract_datetime(val, day)
                if extracted:
                    final_key = key_mapping.get(key, key)
                    normalized_zmanim[final_key] = extracted.isoformat()

        return {
            "date": day.isoformat(),
            "weekday": str(info.hdate.dow()),
            "hebrew_date": str(info.hdate),
            "holiday": self.get_holiday_names(info) or None,
            "zmanim": normalized_zmanim,
        }

    def process_shabbat(self, saturday: dt.date) -> Dict[str, Any]:
        """Generate entry and exit data for a given Shabbat."""
        info = self.get_info(saturday)
        friday = saturday - dt.timedelta(days=1)

        # Determine the name (Parasha or special Shabbat)
        if getattr(info, 'parasha_obj', None) is not Parasha.NONE and getattr(info, 'parasha', None):
            name = f"פרשת {info.parasha}" if "פרשת" not in str(info.parasha) else str(info.parasha)
        else:
            h_names = self.get_holiday_names(info)
            name = f"שבת {h_names}" if h_names else "שבת קודש"

        exit_time = self.get_havdalah(saturday)
        
        return {
            "name": name,
            "date": saturday.isoformat(),
            "hebrew_date": str(info.hdate),
            "entry": self.get_candle_lighting(friday),
            "exit": exit_time,
            "note": None if exit_time else "Contiguous holiday / No immediate havdalah",
        }

    def process_holiday(self, first_day: dt.date) -> Dict[str, Any]:
        """
        Group contiguous holiday days (e.g., Diaspora 2-day Yom Tov) into a single event block.
        """
        holiday_days = [first_day]
        
        # Scan forward to group contiguous Yom Tov days
        while getattr(self.get_info(holiday_days[-1] + dt.timedelta(days=1)), 'is_yom_tov', False):
            holiday_days.append(holiday_days[-1] + dt.timedelta(days=1))

        # Collect unique holiday names across the grouped days
        names = []
        for current_day in holiday_days:
            for h in self.get_info(current_day).holidays:
                if getattr(h, 'type', None) == HolidayTypes.YOM_TOV and str(h) not in names:
                    names.append(str(h))

        # Determine the physical end boundary of the holiday block
        last_day_info = self.get_info(holiday_days[-1])
        last_hdate = getattr(last_day_info, 'last_day', None)
        end_date = last_hdate.gdate if last_hdate else holiday_days[-1]

        return {
            "name": ", ".join(names),
            "start_date": holiday_days[0].isoformat(),
            "end_date": end_date.isoformat(),
            "hebrew_date": str(self.get_info(holiday_days[0]).hdate),
            "entry": self.get_candle_lighting(holiday_days[0] - dt.timedelta(days=1)),
            "exit": self.get_havdalah(end_date),
        }

    def build_local_database(self, start: dt.date, days_ahead: int = 40) -> Dict[str, Any]:
        """
        Main execution method: Builds a structured, in-memory database of all 
        daily parameters, Shabbatot, and Holidays for the specified date range.
        Default is 40 days to ensure a full month overlap for HA calendars.
        """
        days_data: List[Dict[str, Any]] = []
        shabbatot: List[Dict[str, Any]] = []
        holidays: List[Dict[str, Any]] = []
        
        current_day = start
        end_date = start + dt.timedelta(days=days_ahead)

        while current_day <= end_date:
            # 1. Process standard daily data
            days_data.append(self.process_daily_data(current_day))

            # 2. Process Shabbat boundaries (Triggered on Saturday)
            if current_day.weekday() == 5:
                shabbatot.append(self.process_shabbat(current_day))

            # 3. Process Yom Tov blocks (Triggered on the first day of a holiday)
            yesterday = current_day - dt.timedelta(days=1)
            is_yom_tov_today = getattr(self.get_info(current_day), 'is_yom_tov', False)
            is_yom_tov_yesterday = getattr(self.get_info(yesterday), 'is_yom_tov', False)
            
            if is_yom_tov_today and not is_yom_tov_yesterday:
                holidays.append(self.process_holiday(current_day))

            current_day += dt.timedelta(days=1)

        return {
            "location": self.location.name,
            "range": {
                "start": start.isoformat(), 
                "end": end_date.isoformat()
            },
            "shabbatot": shabbatot,
            "holidays": holidays,
            "days": days_data,
        }
