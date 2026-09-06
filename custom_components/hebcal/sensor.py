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
    # Reload the integration to apply changes to all entities
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
        
        # Important: Use constant English names for entity_id for stability
        sensor_config = SENSOR_TYPES[sensor_type]
        english_entity_name = sensor_config["entity_id"]  # This is the English name from const.py
        
        self._attr_unique_id = f"{entry.entry_id}_{english_entity_name}"
        # Force the English entity_id
        self.entity_id = f"sensor.hebcal_{english_entity_name}"
        
        # Get configuration for display name
        self.language = entry.options.get(CONF_LANGUAGE, entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE))
        
        # The display name can be in the user's chosen language
        self._attr_name = sensor_config["name"][self.language]
        self._attr_icon = sensor_config["icon"]
        self._attr_device_class = sensor_config["device_class"]
        self._attr_native_unit_of_measurement = sensor_config["unit"]
        
        # Get configuration
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
            "sw_version": "4.0.0",
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
        _LOGGER.debug("Coordinator update for %s", self.entity_id)
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
        if self.sensor_type == "zmanim":
            return self._get_zmanim_attributes()
        return {}

    def _get_shabbat_in(self) -> str:
        """Get Shabbat entrance time."""
        shabbat_in = self.coordinator.data.get("shabbat_in")
        if shabbat_in:
            return self._format_time(shabbat_in)
        return LANGUAGE_DATA[self.language]["no_info"]

    def _get_shabbat_out(self) -> str:
        """Get Shabbat exit time."""
        shabbat_out = self.coordinator.data.get("shabbat_out")
        if shabbat_out:
            return self._format_time(shabbat_out)
        return LANGUAGE_DATA[self.language]["no_info"]

    def _get_yomtov_in(self) -> str:
        """Get Yom Tov entrance time."""
        yomtov_in = self.coordinator.data.get("yomtov_in")
        if yomtov_in:
            today = datetime.datetime.now().date()
            if yomtov_in.date() >= today:
                return self._format_time(yomtov_in)
        return LANGUAGE_DATA[self.language]["no_info"]

    def _get_yomtov_out(self) -> str:
        """Get Yom Tov exit time."""
        yomtov_out = self.coordinator.data.get("yomtov_out")
        if yomtov_out:
            today = datetime.datetime.now().date()
            if yomtov_out.date() >= today:
                return self._format_time(yomtov_out)
        return LANGUAGE_DATA[self.language]["no_info"]

    def _get_parasha(self) -> str:
        """Get Torah portion."""
        parasha = self.coordinator.data.get("parasha")
        if parasha:
            return parasha
        return LANGUAGE_DATA[self.language]["special_shabbat"]

    def _get_yomtov_name(self) -> str:
        """Get Yom Tov name."""
        yomtov_name = self.coordinator.data.get("yomtov_name")
        if yomtov_name:
            return yomtov_name
        return LANGUAGE_DATA[self.language]["no_info"]

    def _get_event_name(self) -> str:
        """Get current event name."""
        today = datetime.datetime.now()
        
        # Check for current holidays
        events = self.coordinator.data.get("events", [])
        for event in events:
            if "start" in event and "end" in event:
                start = datetime.datetime.fromisoformat(event["start"][:19])
                end = datetime.datetime.fromisoformat(event["end"][:19])
                if start <= today <= end:
                    return event.get("title", "")
        
        # Return current weekday
        if self.language == "hebrew":
            return HEBREW_WEEKDAY.get(today.isoweekday(), "")
        else:
            return today.strftime("%A")

    def _get_omer_day(self) -> str:
        """Get Omer count."""
        if not self.coordinator.data:
            return LANGUAGE_DATA[self.language]["no_omer"]

        now = datetime.datetime.now()
        sunset = self.coordinator.data.get("zmanim", {}).get("shkia")

        target_date = now.date()
        if sunset and now > sunset:
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
        """Get Hebrew date based on sunset, as the Jewish day starts in the evening."""
        now = datetime.datetime.now()
        zmanim = self.coordinator.data.get("zmanim", {})
        sunset = zmanim.get("shkia")

        hebrew_date_data = self.coordinator.data.get("hebrew_date", {})
        date_to_show = None
        gregorian_date_for_weekday = datetime.date.today()

        # Determine which day's date to show
        if sunset and now > sunset:
            # After sunset, it's the next Hebrew day
            date_to_show = hebrew_date_data.get("tomorrow", {})
            gregorian_date_for_weekday += datetime.timedelta(days=1)
        else:
            # Before sunset, it's the current Hebrew day
            date_to_show = hebrew_date_data.get("today", {})

        if not date_to_show:
            return LANGUAGE_DATA[self.language]["no_info"]

        if self.language == "hebrew":
            # The Hebrew string from hdate already includes the day of the week
            return date_to_show.get("hebrew", "")
        else:
            # The English string from hdate does not, so we add it.
            weekday = gregorian_date_for_weekday.strftime("%A")
            english_date = date_to_show.get("english", "")
            if not english_date:
                return LANGUAGE_DATA[self.language]["no_info"]
            return f"{weekday}, {english_date}"

    def _get_zmanim(self) -> str:
        """Get Zmanim description."""
        today = datetime.date.today()
        if self.language == "hebrew":
            return f"זמנים הלכתיים עבור יום {today}"
        else:
            return f"Halachic times for {today}"

    def _get_zmanim_attributes(self) -> Dict[str, Any]:
        """Get Zmanim as attributes."""
        zmanim_data = self.coordinator.data.get("zmanim", {})
        
        attributes = {}
        for key, time_dt in zmanim_data.items():
            # נבדוק שיש תרגום לשם ושיש שעה
            if key in ZMANIM_TRANSLATIONS and time_dt:
                formatted_time = self._format_time(time_dt)
                translated_key = ZMANIM_TRANSLATIONS[key][self.language]
                attributes[translated_key] = formatted_time

        return attributes

    def _format_time(self, dt: datetime.datetime) -> str:
        """Format datetime to time string."""
        if self.use_12h_time:
            return dt.strftime("%I:%M %p")
        else:
            return dt.strftime("%H:%M")

    def _format_time_string(self, time_str: str) -> str:
        """Format time string according to 12h/24h preference."""
        if self.use_12h_time:
            try:
                dt = datetime.datetime.strptime(time_str, "%H:%M")
                return dt.strftime("%I:%M %p")
            except ValueError:
                return time_str
        return time_str
