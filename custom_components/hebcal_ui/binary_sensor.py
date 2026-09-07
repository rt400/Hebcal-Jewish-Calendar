"""Binary sensor platform for Hebcal integration."""
import datetime
import logging
from typing import Any, Dict, Optional

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.event import async_track_point_in_time
 
from .const import (
    DOMAIN,
    VERSION,
    BINARY_SENSOR_TYPES,
    LANGUAGE_DATA,
    CONF_LANGUAGE,
    CONF_TIME_BEFORE_CHECK,
    CONF_TIME_AFTER_CHECK,
    DEFAULT_LANGUAGE,
    DEFAULT_TIME_BEFORE_CHECK,
    DEFAULT_TIME_AFTER_CHECK,
)
from .coordinator import HebcalDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hebcal binary sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    for sensor_type in BINARY_SENSOR_TYPES:
        entities.append(HebcalBinarySensor(coordinator, entry, sensor_type))
    
    async_add_entities(entities)
    entry.async_on_unload(
        entry.add_update_listener(options_update_listener)
    )
    
    _LOGGER.info("Added %d Hebcal binary sensors", len(entities))


async def options_update_listener(hass, entry):
    """Handle options updates by reloading the integration."""
    await hass.config_entries.async_reload(entry.entry_id)
    

class HebcalBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Hebcal binary sensor."""

    def __init__(
        self,
        coordinator: HebcalDataUpdateCoordinator,
        entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self.sensor_type = sensor_type
        
        sensor_config = BINARY_SENSOR_TYPES[sensor_type]
        english_entity_name = sensor_config["entity_id"]
        
        self._attr_unique_id = f"{entry.entry_id}_{english_entity_name}"
        self.entity_id = f"binary_sensor.hebcal_{english_entity_name}"
        
        self.language = entry.options.get(CONF_LANGUAGE, entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE))
        
        self._attr_name = sensor_config["name"][self.language]
        self._attr_icon = sensor_config["icon"]
        self._attr_device_class = sensor_config["device_class"]

        self.time_before_check = entry.options.get(
            CONF_TIME_BEFORE_CHECK, 
            entry.data.get(CONF_TIME_BEFORE_CHECK, DEFAULT_TIME_BEFORE_CHECK)
        )
        self.time_after_check = entry.options.get(
            CONF_TIME_AFTER_CHECK, 
            entry.data.get(CONF_TIME_AFTER_CHECK, DEFAULT_TIME_AFTER_CHECK)
        )
        
        self._timer_remover = None
        
    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information for grouping entities."""
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": "Hebcal Jewish Calendar",
            "manufacturer": "Yuval Mejahez",
            "model": "Hebcal Jewish Calendar",
            "sw_version": VERSION,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._schedule_future_update()

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_future_update()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._schedule_future_update()
        self.async_write_ha_state()

    def _cancel_future_update(self) -> None:
        if self._timer_remover:
            self._timer_remover()
            self._timer_remover = None

    @callback
    def _schedule_future_update(self) -> None:
        self._cancel_future_update()

        start_time, end_time = self._active_period
        if not start_time or not end_time:
            return

        now = datetime.datetime.now()
        next_update_time = None

        if now < start_time:
            next_update_time = start_time
        elif start_time <= now < end_time:
            next_update_time = end_time
        
        if next_update_time:
            self._timer_remover = async_track_point_in_time(
                self.hass, self._time_update_handler, next_update_time
            )

    @callback
    def _time_update_handler(self, now: datetime.datetime) -> None:
        self._schedule_future_update()
        self.async_write_ha_state()

    @property
    def is_on(self) -> Optional[bool]:
        if not self.coordinator.data:
            return None
        
        start_time, end_time = self._active_period
        if not start_time or not end_time:
            return False

        now = datetime.datetime.now()
        return start_time <= now <= end_time

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def _active_period(self) -> tuple[datetime.datetime | None, datetime.datetime | None]:
        if self.sensor_type == "is_shabbat":
            shabbat_in = self._ensure_datetime(self.coordinator.data.get("shabbat_in"))
            shabbat_out = self._ensure_datetime(self.coordinator.data.get("shabbat_out"))
            if not shabbat_in or not shabbat_out:
                return None, None
            start_time = shabbat_in - datetime.timedelta(minutes=self.time_before_check)
            end_time = shabbat_out + datetime.timedelta(minutes=self.time_after_check)
            return start_time, end_time
        
        if self.sensor_type == "is_yomtov":
            yomtov_in = self._ensure_datetime(self.coordinator.data.get("yomtov_in"))
            yomtov_out = self._ensure_datetime(self.coordinator.data.get("yomtov_out"))
            if not yomtov_in or not yomtov_out:
                return None, None
            start_time = yomtov_in - datetime.timedelta(minutes=self.time_before_check)
            end_time = yomtov_out + datetime.timedelta(minutes=self.time_after_check)
            return start_time, end_time

        if self.sensor_type == "issur_melacha":
            period = self.coordinator.isur_melacha_period
            start = self._ensure_datetime(period.get('start'))
            end = self._ensure_datetime(period.get('end'))
            return start, end
            
        return None, None

    # --- פונקציות עזר בטוחות לטיפול בתאריכים ---
    def _ensure_datetime(self, dt: Any) -> Optional[datetime.datetime]:
        """Ensure the variable is a datetime object."""
        if not dt: return None
        if isinstance(dt, datetime.datetime): return dt
        if isinstance(dt, str):
            try:
                if dt.endswith('Z'): return datetime.datetime.fromisoformat(dt[:-1] + '+00:00')
                return datetime.datetime.fromisoformat(dt)
            except (ValueError, TypeError):
                return None
        return None

    def _safe_strftime(self, dt: Any, format_str: str) -> str:
        """Safely format datetime that might be a string."""
        dt_obj = self._ensure_datetime(dt)
        if dt_obj: return dt_obj.strftime(format_str)
        return str(dt) if dt else ""

    def _safe_isoformat(self, dt: Any) -> str:
        """Safely isoformat datetime that might be a string."""
        dt_obj = self._ensure_datetime(dt)
        if dt_obj: return dt_obj.isoformat()
        return str(dt) if dt else ""
    # --------------------------------------------

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes based on sensor type."""
        if not self.coordinator.data:
            return {}
            
        attributes = {}
        
        try:
            if self.sensor_type == "is_shabbat":
                attributes.update(self._get_shabbat_attributes())
            elif self.sensor_type == "is_yomtov":
                attributes.update(self._get_yomtov_attributes())
            elif self.sensor_type == "issur_melacha":
                attributes.update(self._get_issur_melacha_attributes())
            
            update_time = self.coordinator.data.get("update_time", datetime.datetime.now())
            attributes["last_updated"] = self._safe_isoformat(update_time)
            attributes["time_before_check"] = self.time_before_check
            attributes["time_after_check"] = self.time_after_check
        except Exception as e:
            _LOGGER.error("Error generating attributes for %s: %s", self.entity_id, e)
            attributes["error"] = str(e)
            
        return attributes

    def _get_shabbat_attributes(self) -> Dict[str, Any]:
        attributes = {}
        
        shabbat_in = self.coordinator.data.get("shabbat_in")
        shabbat_out = self.coordinator.data.get("shabbat_out")
        
        if shabbat_in:
            attributes["shabbat_in"] = self._safe_isoformat(shabbat_in)
            attributes["candle_lighting"] = self._safe_strftime(shabbat_in, "%H:%M")
            attributes["candle_lighting_day"] = self._safe_strftime(shabbat_in, "%A")
            dt_in = self._ensure_datetime(shabbat_in)
            if dt_in:
                start_time = dt_in - datetime.timedelta(minutes=self.time_before_check)
                attributes["active_from"] = start_time.isoformat()
                attributes["active_from_time"] = start_time.strftime("%H:%M")
            
        if shabbat_out:
            attributes["shabbat_out"] = self._safe_isoformat(shabbat_out)
            attributes["havdalah"] = self._safe_strftime(shabbat_out, "%H:%M")
            attributes["havdalah_day"] = self._safe_strftime(shabbat_out, "%A")
            dt_out = self._ensure_datetime(shabbat_out)
            if dt_out:
                end_time = dt_out + datetime.timedelta(minutes=self.time_after_check)
                attributes["active_until"] = end_time.isoformat()
                attributes["active_until_time"] = end_time.strftime("%H:%M")
        
        parasha = self.coordinator.data.get("parasha")
        if parasha:
            attributes["parasha"] = parasha
        
        now = datetime.datetime.now()
        dt_out = self._ensure_datetime(shabbat_out)
        dt_in = self._ensure_datetime(shabbat_in)
        
        if self.is_on and dt_out:
            time_until_end = self.coordinator.get_time_until_event(dt_out)
            if time_until_end:
                attributes["time_until_havdalah"] = self.coordinator.format_time_delta(time_until_end)
                attributes["minutes_until_havdalah"] = int(time_until_end.total_seconds() / 60)
        elif not self.is_on and dt_in and dt_in > now:
            time_until_start = self.coordinator.get_time_until_event(dt_in)
            if time_until_start:
                attributes["time_until_candles"] = self.coordinator.format_time_delta(time_until_start)
                attributes["minutes_until_candles"] = int(time_until_start.total_seconds() / 60)
        
        if self.is_on:
            attributes["status_hebrew"] = "שבת קודש"
        else:
            attributes["status_hebrew"] = "יום חול"
            
        return attributes

    def _get_yomtov_attributes(self) -> Dict[str, Any]:
        attributes = {}
        
        yomtov_in = self.coordinator.data.get("yomtov_in")
        yomtov_out = self.coordinator.data.get("yomtov_out")
        
        if yomtov_in:
            attributes["yomtov_in"] = self._safe_isoformat(yomtov_in)
            attributes["candle_lighting"] = self._safe_strftime(yomtov_in, "%H:%M")
            attributes["candle_lighting_day"] = self._safe_strftime(yomtov_in, "%A")
            dt_in = self._ensure_datetime(yomtov_in)
            if dt_in:
                start_time = dt_in - datetime.timedelta(minutes=self.time_before_check)
                attributes["active_from"] = start_time.isoformat()
                attributes["active_from_time"] = start_time.strftime("%H:%M")
            
        if yomtov_out:
            attributes["yomtov_out"] = self._safe_isoformat(yomtov_out)
            attributes["havdalah"] = self._safe_strftime(yomtov_out, "%H:%M")
            attributes["havdalah_day"] = self._safe_strftime(yomtov_out, "%A")
            dt_out = self._ensure_datetime(yomtov_out)
            if dt_out:
                end_time = dt_out + datetime.timedelta(minutes=self.time_after_check)
                attributes["active_until"] = end_time.isoformat()
                attributes["active_until_time"] = end_time.strftime("%H:%M")
        
        yomtov_name = self.coordinator.data.get("yomtov_name")
        if yomtov_name:
            attributes["yomtov_name"] = yomtov_name
            attributes["holiday_name"] = yomtov_name
        
        if self.coordinator.data.get("rosh_hashana"):
            attributes["holiday_type"] = "Rosh Hashana (2 days)"
            attributes["special_notes"] = "Two-day holiday"
        elif self.coordinator.data.get("special_holiday"):
            attributes["holiday_type"] = "Special Holiday"
        else:
            attributes["holiday_type"] = "Regular Holiday"
        
        holiday_count = self.coordinator.data.get("holiday_count", 0)
        if holiday_count > 0:
            attributes["holiday_count"] = holiday_count
        
        now = datetime.datetime.now()
        dt_out = self._ensure_datetime(yomtov_out)
        dt_in = self._ensure_datetime(yomtov_in)
        
        if self.is_on and dt_out:
            time_until_end = self.coordinator.get_time_until_event(dt_out)
            if time_until_end:
                attributes["time_until_havdalah"] = self.coordinator.format_time_delta(time_until_end)
                attributes["minutes_until_havdalah"] = int(time_until_end.total_seconds() / 60)
        elif not self.is_on and dt_in and dt_in > now:
            time_until_start = self.coordinator.get_time_until_event(dt_in)
            if time_until_start:
                attributes["time_until_candles"] = self.coordinator.format_time_delta(time_until_start)
                attributes["minutes_until_candles"] = int(time_until_start.total_seconds() / 60)
        
        if self.is_on:
            attributes["status_hebrew"] = "יום טוב"
        else:
            attributes["status_hebrew"] = "יום חול"
            
        return attributes

    def _get_issur_melacha_attributes(self) -> Dict[str, Any]:
        attributes = {}
        period = self.coordinator.isur_melacha_period
        
        if period.get('start'):
            attributes["period_start"] = self._safe_isoformat(period['start'])
            attributes["period_start_time"] = self._safe_strftime(period['start'], "%H:%M")
            attributes["period_start_day"] = self._safe_strftime(period['start'], "%A")
            
        if period.get('end'):
            attributes["period_end"] = self._safe_isoformat(period['end'])
            attributes["period_end_time"] = self._safe_strftime(period['end'], "%H:%M")
            attributes["period_end_day"] = self._safe_strftime(period['end'], "%A")
        
        attributes["period_type"] = period.get('type', 'none')
        attributes["period_type_hebrew"] = self.coordinator.get_isur_melacha_type_description()
        attributes["duration_hours"] = period.get('duration_hours', 0)
        attributes["is_active"] = period.get('active', False)
        
        duration = period.get('duration_hours', 0)
        if duration > 0:
            if duration >= 24:
                days = int(duration // 24)
                hours = int(duration % 24)
                attributes["duration_formatted"] = f"{days} days, {hours} hours"
                attributes["duration_formatted_hebrew"] = f"{days} ימים, {hours} שעות"
            else:
                attributes["duration_formatted"] = f"{duration} hours"
                attributes["duration_formatted_hebrew"] = f"{duration} שעות"
        
        if self.is_on:
            time_until_end = self.coordinator.get_time_until_isur_melacha_end()
            if time_until_end:
                attributes["time_until_end"] = self.coordinator.format_time_delta(time_until_end)
                attributes["minutes_until_end"] = int(time_until_end.total_seconds() / 60)
        else:
            time_until_start = self.coordinator.get_time_until_isur_melacha_start()
            if time_until_start:
                attributes["time_until_start"] = self.coordinator.format_time_delta(time_until_start)
                attributes["minutes_until_start"] = int(time_until_start.total_seconds() / 60)
        
        attributes["shabbat_active"] = self.coordinator.is_shabbat_active
        attributes["yomtov_active"] = self.coordinator.is_yomtov_active
        
        shabbat_in = self.coordinator.data.get("shabbat_in")
        shabbat_out = self.coordinator.data.get("shabbat_out")
        yomtov_in = self.coordinator.data.get("yomtov_in")
        yomtov_out = self.coordinator.data.get("yomtov_out")
        
        if shabbat_in:
            attributes["shabbat_candles"] = self._safe_strftime(shabbat_in, "%H:%M")
        if shabbat_out:
            attributes["shabbat_havdalah"] = self._safe_strftime(shabbat_out, "%H:%M")
        if yomtov_in:
            attributes["yomtov_candles"] = self._safe_strftime(yomtov_in, "%H:%M")
        if yomtov_out:
            attributes["yomtov_havdalah"] = self._safe_strftime(yomtov_out, "%H:%M")
        
        attributes["status_hebrew"] = self.coordinator.format_isur_melacha_status()
        
        special_info = []
        if self.coordinator.data.get("rosh_hashana"): special_info.append("Rosh Hashana (2 days)")
        if self.coordinator.data.get("special_holiday"): special_info.append("Special Holiday")
        if special_info: attributes["special_cases"] = ", ".join(special_info)
        
        next_candles = self.coordinator.next_candle_lighting
        if next_candles:
            attributes["next_candle_lighting"] = self._safe_strftime(next_candles, "%A %H:%M")
            attributes["next_candle_lighting_full"] = self._safe_isoformat(next_candles)
            
        next_havdalah = self.coordinator.next_havdalah
        if next_havdalah:
            attributes["next_havdalah"] = self._safe_strftime(next_havdalah, "%A %H:%M")
            attributes["next_havdalah_full"] = self._safe_isoformat(next_havdalah)
        
        if self.is_on:
            attributes["work_status"] = "Prohibited"
            attributes["work_status_hebrew"] = "אסור לעשות מלאכה"
        else:
            attributes["work_status"] = "Permitted"
            attributes["work_status_hebrew"] = "מותר לעשות מלאכה"
            
        return attributes

    @property
    def icon(self) -> str:
        """Return dynamic icon based on sensor type and state."""
        if self.sensor_type == "issur_melacha":
            if self.is_on: return "mdi:hand-back-right-off"
            else: return "mdi:hand-back-right"
        return self._attr_icon
