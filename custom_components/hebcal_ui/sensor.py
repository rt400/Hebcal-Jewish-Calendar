"""Sensor platform for Hebcal integration."""
import datetime
import logging
import re
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    VERSION,
    SENSOR_TYPES,
    LANGUAGE_DATA,
    ZMANIM_TRANSLATIONS,
    HEBREW_WEEKDAY,
    OMER_DAYS,
    CONF_LANGUAGE,
    CONF_USE_12H_TIME,
    CONF_OMER_COUNT_TYPE,
    DEFAULT_LANGUAGE,
    DEFAULT_USE_12H_TIME,
    DEFAULT_OMER_COUNT_TYPE,
)
from .coordinator import HebcalDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hebcal sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    for sensor_type in SENSOR_TYPES:
        entities.append(HebcalSensor(coordinator, entry, sensor_type))
    
    async_add_entities(entities)
    entry.async_on_unload(
        entry.add_update_listener(options_update_listener)
    )

async def options_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


class HebcalSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Hebcal sensor."""

    def __init__(
        self,
        coordinator: HebcalDataUpdateCoordinator,
        entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self.sensor_type = sensor_type
        
        sensor_config = SENSOR_TYPES[sensor_type]
        english_entity_name = sensor_config["entity_id"]
        
        self._attr_unique_id = f"{entry.entry_id}_{english_entity_name}"
        self.entity_id = f"sensor.hebcal_{english_entity_name}"
        
        self.language = entry.options.get(CONF_LANGUAGE, entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE))
        
        self._attr_name = sensor_config["name"][self.language]
        self._attr_icon = sensor_config["icon"]
        self._attr_device_class = sensor_config["device_class"]
        self._attr_native_unit_of_measurement = sensor_config["unit"]
        
        self.use_12h_time = entry.options.get(CONF_USE_12H_TIME, entry.data.get(CONF_USE_12H_TIME, DEFAULT_USE_12H_TIME))
        self.omer_count_type = entry.options.get(CONF_OMER_COUNT_TYPE, entry.data.get(CONF_OMER_COUNT_TYPE, DEFAULT_OMER_COUNT_TYPE))
        
        self._timer_remover = None

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": "Hebcal Jewish Calendar",
            "manufacturer": "Yuval Mejahez",
            "model": "Hebcal Jewish Calendar",
            "sw_version": VERSION,
        }

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added to Home Assistant."""
        await super().async_added_to_hass()
        self._schedule_future_update()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity which will be removed from Home Assistant."""
        self._cancel_future_update()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._schedule_future_update()
        self.async_write_ha_state()

    def _cancel_future_update(self) -> None:
        """Cancel any scheduled update."""
        if self._timer_remover:
            self._timer_remover()
            self._timer_remover = None

    @callback
    def _schedule_future_update(self) -> None:
        """Schedule an update for the next relevant time for time-sensitive sensors."""
        self._cancel_future_update()

        if self.sensor_type not in ["hebrew_date", "omer_day", "event_name"]:
            return

        now = datetime.datetime.now()
        next_update_time = None

        if self.sensor_type in ["hebrew_date", "omer_day"]:
            sunset_today = self.coordinator.data.get("zmanim", {}).get("shkia")
            if sunset_today and sunset_today > now:
                next_update_time = sunset_today
            else:
                sunset_tomorrow = self.coordinator.data.get("zmanim_tomorrow", {}).get("shkia")
                if sunset_tomorrow:
                    next_update_time = sunset_tomorrow

        elif self.sensor_type == "event_name":
            events = self.coordinator.data.get("events", [])
            potential_updates = []
            for event in events:
                if "start" in event and "end" in event:
                    try:
                        start = datetime.datetime.fromisoformat(event["start"][:19])
                        end = datetime.datetime.fromisoformat(event["end"][:19])
                        if start > now: potential_updates.append(start)
                        if end > now: potential_updates.append(end)
                    except (ValueError, TypeError): continue
            if potential_updates:
                next_update_time = min(potential_updates)

        if next_update_time:
            self._timer_remover = async_track_point_in_time(self.hass, self._time_update_handler, next_update_time)

    @callback
    def _time_update_handler(self, now: datetime.datetime) -> None:
        """Handle a time-based update."""
        self._schedule_future_update()
        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return LANGUAGE_DATA[self.language]["no_info"]
        
        method_name = f"_get_{self.sensor_type}"
        if hasattr(self, method_name):
            return getattr(self, method_name)()
        
        return LANGUAGE_DATA[self.language]["no_info"]

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        if self.sensor_type == "zmanim":
            return self._get_zmanim_attributes()
            
        attributes = {}
        
        if self.sensor_type in ["shabbat_in", "shabbat_out", "yomtov_in", "yomtov_out"]:
            dt_val = self.coordinator.data.get(self.sensor_type)
            
            if isinstance(dt_val, str):
                try:
                    if dt_val.endswith('Z'):
                        dt_val = datetime.datetime.fromisoformat(dt_val[:-1] + '+00:00')
                    else:
                        dt_val = datetime.datetime.fromisoformat(dt_val)
                except (ValueError, TypeError):
                    pass
                    
            if isinstance(dt_val, datetime.datetime):
                if self.language == "hebrew":
                    attributes["תאריך_מלא"] = dt_val.strftime("%d/%m/%Y %H:%M")
                    attributes["תאריך"] = dt_val.strftime("%d/%m/%Y")
                    attributes["שעה"] = self._format_time(dt_val)
                else:
                    attributes["full_date"] = dt_val.strftime("%Y-%m-%d %H:%M")
                    attributes["date"] = dt_val.strftime("%Y-%m-%d")
                    attributes["time"] = self._format_time(dt_val)
                    
        return attributes

    def _get_shabbat_in(self) -> str:
        shabbat_in = self.coordinator.data.get("shabbat_in")
        if shabbat_in: return self._format_time(shabbat_in)
        return LANGUAGE_DATA[self.language]["no_info"]

    def _get_shabbat_out(self) -> str:
        shabbat_out = self.coordinator.data.get("shabbat_out")
        if shabbat_out: return self._format_time(shabbat_out)
        return LANGUAGE_DATA[self.language]["no_info"]

    def _get_yomtov_in(self) -> str:
        yomtov_in = self.coordinator.data.get("yomtov_in")
        yomtov_out = self.coordinator.data.get("yomtov_out")
        
        if yomtov_in:
            now = datetime.datetime.now()
            
            if yomtov_out:
                dt_out = yomtov_out if isinstance(yomtov_out, datetime.datetime) else datetime.datetime.fromisoformat(str(yomtov_out).replace('Z','+00:00')).replace(tzinfo=None)
                
                # בדיקה רק לפי התאריך (מתעלמים מהשעה), כדי שהמידע יישאר עד חצות
                if dt_out.date() >= now.date():
                    return self._format_time(yomtov_in)
            else:
                dt_in = yomtov_in if isinstance(yomtov_in, datetime.datetime) else datetime.datetime.fromisoformat(str(yomtov_in).replace('Z','+00:00')).replace(tzinfo=None)
                if dt_in.date() >= now.date():
                    return self._format_time(yomtov_in)
                    
        return LANGUAGE_DATA[self.language]["no_info"]

    def _get_yomtov_out(self) -> str:
        yomtov_out = self.coordinator.data.get("yomtov_out")
        
        if yomtov_out:
            now = datetime.datetime.now()
            dt_out = yomtov_out if isinstance(yomtov_out, datetime.datetime) else datetime.datetime.fromisoformat(str(yomtov_out).replace('Z','+00:00')).replace(tzinfo=None)
            
            # בדיקה רק לפי התאריך (מתעלמים מהשעה)
            if dt_out.date() >= now.date():
                return self._format_time(yomtov_out)
                
        return LANGUAGE_DATA[self.language]["no_info"]

    def _get_parasha(self) -> str:
        """Get Torah portion."""
        parasha = self.coordinator.data.get("parasha")
        
        # אם יש פרשה רגילה, נחזיר אותה
        if parasha:
            return parasha
            
        # אם אין פרשה (למשל כי זה שבת-חג), נחפש חג שנופל בדיוק על שבת
        shabbat_out = self.coordinator.data.get("shabbat_out")
        shabbat_date = None
        
        # חילוץ בטוח של התאריך של יום השבת
        if isinstance(shabbat_out, str):
            try:
                if shabbat_out.endswith('Z'):
                    shabbat_date = datetime.datetime.fromisoformat(shabbat_out[:-1] + '+00:00').date()
                else:
                    shabbat_date = datetime.datetime.fromisoformat(shabbat_out).date()
            except (ValueError, TypeError):
                pass
        elif isinstance(shabbat_out, datetime.datetime):
            shabbat_date = shabbat_out.date()
            
        # אם מצאנו את תאריך השבת, נעבור על כל החגים של השבוע
        if shabbat_date:
            holidays = self.coordinator.data.get("holidays", [])
            for holiday in holidays:
                holiday_date_str = holiday.get("date", "")
                
                # בודקים אם התאריך של החג זהה בדיוק לתאריך של השבת (10 התווים הראשונים = YYYY-MM-DD)
                if isinstance(holiday_date_str, str) and len(holiday_date_str) >= 10:
                    if holiday_date_str[:10] == shabbat_date.isoformat():
                        holiday_name = holiday.get("name", "")
                        
                        # מחזירים את התצוגה המבוקשת לפי השפה
                        if self.language == "hebrew":
                            return f"שבת ({holiday_name})"
                        else:
                            return f"Shabbat ({holiday_name})"
                            
        # גיבוי: אם לא נמצא חג שתואם לתאריך השבת, נחזיר "שבת מיוחדת"
        return LANGUAGE_DATA[self.language]["special_shabbat"]

    def _get_yomtov_name(self) -> str:
        """Get Yom Tov name."""
        holidays = self.coordinator.data.get("holidays", [])
        now = datetime.datetime.now()
        
        if holidays:
            for holiday in holidays:
                # חיפוש זמן סיום החג (צאת החג או השקיעה)
                end_time = holiday.get("yomtov_out") or holiday.get("end")
                
                # המרה בטוחה של זמן הסיום ל-datetime במידה והוא טקסט
                if isinstance(end_time, str):
                    try:
                        if end_time.endswith('Z'):
                            dt = datetime.datetime.fromisoformat(end_time[:-1] + '+00:00')
                        else:
                            dt = datetime.datetime.fromisoformat(end_time)
                        end_time = dt.replace(tzinfo=None)
                    except (ValueError, TypeError):
                        pass
                
                # מחזירים את החג הראשון שעוד לא נגמר (זמן הסיום שלו מאוחר מעכשיו)
                if isinstance(end_time, datetime.datetime) and end_time >= now:
                    return holiday.get("name", LANGUAGE_DATA[self.language]["no_info"])
                
                # גיבוי: אם לא הצלחנו למצוא שעת סיום מדויקת, נבדוק לפי התאריך הכללי
                elif not isinstance(end_time, datetime.datetime):
                    holiday_date_str = holiday.get("date", "")
                    if isinstance(holiday_date_str, str) and len(holiday_date_str) >= 10:
                        if holiday_date_str[:10] >= now.date().isoformat():
                            return holiday.get("name", LANGUAGE_DATA[self.language]["no_info"])
            
            # אם כל החגים ברשימה כבר עברו, החזר ערך ריק/אין מידע
            return LANGUAGE_DATA[self.language]["no_info"]

        # תמיכה לאחור במידה ו-yomtov_name מוגדר ישירות (ללא רשימה)
        yomtov_name = self.coordinator.data.get("yomtov_name")
        if yomtov_name: 
            return yomtov_name
            
        return LANGUAGE_DATA[self.language]["no_info"]

    def _get_omer_day(self) -> str:
        if not self.coordinator.data:
            return LANGUAGE_DATA[self.language]["no_omer"]

        now = datetime.datetime.now()
        sunset = self.coordinator.data.get("zmanim", {}).get("shkia")
        if isinstance(sunset, str):
            try: sunset = datetime.datetime.fromisoformat(sunset)
            except: pass

        target_date = now.date()
        if sunset and isinstance(sunset, datetime.datetime) and now > sunset:
            target_date += datetime.timedelta(days=1)

        day_num = None
        events = self.coordinator.data.get("events", [])
        for event in events:
            if event.get("category") == "omer":
                try:
                    event_date = datetime.datetime.fromisoformat(event["date"][:19]).date()
                    if event_date == target_date:
                        title = event.get("title", "")
                        match = re.search(r'(\d+)', title)
                        if match:
                            day_num = int(match.group(1))
                            break
                except (ValueError, TypeError):
                    continue

        if day_num and 1 <= day_num <= 49:
            return OMER_DAYS[self.omer_count_type].get(day_num, "")
        return LANGUAGE_DATA[self.language]["no_omer"]

    def _get_hebrew_date(self) -> str:
        now = datetime.datetime.now()
        zmanim = self.coordinator.data.get("zmanim", {})
        sunset = zmanim.get("shkia")
        if isinstance(sunset, str):
            try: sunset = datetime.datetime.fromisoformat(sunset)
            except: pass

        hebrew_date_data = self.coordinator.data.get("hebrew_date", {})
        date_to_show = None
        gregorian_date_for_weekday = datetime.date.today()

        if sunset and isinstance(sunset, datetime.datetime) and now > sunset:
            date_to_show = hebrew_date_data.get("tomorrow", {})
            gregorian_date_for_weekday += datetime.timedelta(days=1)
        else:
            date_to_show = hebrew_date_data.get("today", {})

        if not date_to_show:
            return LANGUAGE_DATA[self.language]["no_info"]

        if self.language == "hebrew":
            return date_to_show.get("hebrew", "")
        else:
            weekday = gregorian_date_for_weekday.strftime("%A")
            english_date = date_to_show.get("english", "")
            if not english_date: return LANGUAGE_DATA[self.language]["no_info"]
            return f"{weekday}, {english_date}"

    def _get_zmanim(self) -> str:
        today = datetime.date.today()
        if self.language == "hebrew":
            return f"זמנים הלכתיים עבור יום {today}"
        else:
            return f"Halachic times for {today}"

    def _get_zmanim_attributes(self) -> Dict[str, Any]:
        """Get Zmanim as attributes."""
        zmanim_data = self.coordinator.data.get("zmanim", {})
        
        if not isinstance(zmanim_data, dict):
            return {"error": "Zmanim data is not a valid dictionary"}
            
        attributes = {}
        try:
            for key, time_dt in zmanim_data.items():
                if time_dt:
                    formatted_time = self._format_time(time_dt)
                    
                    if key in ZMANIM_TRANSLATIONS:
                        translated_key = ZMANIM_TRANSLATIONS[key].get(self.language, key)
                        attributes[translated_key] = formatted_time
                    else:
                        attributes[key] = formatted_time
                        
            if not attributes:
                attributes["status"] = "No Zmanim available for today"
                
        except Exception as e:
            _LOGGER.error("Error generating zmanim attributes: %s", e)
            attributes["error_details"] = str(e)

        return attributes

    def _format_time(self, dt: Any) -> str:
        """Format datetime to time string safely."""
        if isinstance(dt, str):
            try:
                if dt.endswith('Z'): dt = datetime.datetime.fromisoformat(dt[:-1] + '+00:00')
                else: dt = datetime.datetime.fromisoformat(dt)
            except (ValueError, TypeError):
                return dt
                
        if isinstance(dt, datetime.datetime):
            if self.use_12h_time:
                return dt.strftime("%I:%M %p")
            else:
                return dt.strftime("%H:%M")
        return str(dt)
