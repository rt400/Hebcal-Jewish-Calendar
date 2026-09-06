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
    """
    Set up Hebcal binary sensors from a config entry.
    
    Creates binary sensors for Shabbat, Yom Tov, and Issur Melacha status
    based on the coordinator data.
    
    Args:
        hass: Home Assistant instance
        entry: Configuration entry
        async_add_entities: Callback to add entities
    """
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
    """
    Handle options updates by reloading the integration.
    
    This ensures that configuration changes (like language or time buffers)
    are applied to all entities.
    
    Args:
        hass: Home Assistant instance
        entry: Configuration entry that was updated
    """
    await hass.config_entries.async_reload(entry.entry_id)
    

class HebcalBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """
    Representation of a Hebcal binary sensor.
    
    This class handles all types of Hebcal binary sensors including:
    - Shabbat status
    - Yom Tov status  
    - Issur Melacha (prohibition of work) status
    """

    def __init__(
        self,
        coordinator: HebcalDataUpdateCoordinator,
        entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        """
        Initialize the binary sensor.
        
        Args:
            coordinator: Data update coordinator
            entry: Configuration entry
            sensor_type: Type of sensor (is_shabbat, is_yomtov, issur_melacha)
        """
        super().__init__(coordinator)
        self.entry = entry
        self.sensor_type = sensor_type
        
        # Use consistent English entity names for stability
        sensor_config = BINARY_SENSOR_TYPES[sensor_type]
        english_entity_name = sensor_config["entity_id"]
        
        self._attr_unique_id = f"{entry.entry_id}_{english_entity_name}"
        # Force English entity ID for consistency
        self.entity_id = f"binary_sensor.hebcal_{english_entity_name}"
        
        # Get language configuration for display names
        self.language = entry.options.get(CONF_LANGUAGE, entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE))
        
        # Display name can be in user's chosen language
        self._attr_name = sensor_config["name"][self.language]
        self._attr_icon = sensor_config["icon"]
        self._attr_device_class = sensor_config["device_class"]

        # Get time buffer configuration
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
        """
        Return device information for grouping entities.
        
        Returns:
            Device information dictionary
        """
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
        """Schedule an update for the next relevant time."""
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
            _LOGGER.debug(
                "Scheduling next update for %s at %s",
                self.entity_id,
                next_update_time,
            )
            self._timer_remover = async_track_point_in_time(
                self.hass, self._time_update_handler, next_update_time
            )

    @callback
    def _time_update_handler(self, now: datetime.datetime) -> None:
        """Handle a time-based update."""
        _LOGGER.debug("Time-based update for %s at %s", self.entity_id, now)
        self._schedule_future_update()
        self.async_write_ha_state()

    @property
    def is_on(self) -> Optional[bool]:
        """
        Return true if the binary sensor is on.
        
        Dynamically calls the appropriate method based on sensor type.
        
        Returns:
            True if sensor condition is met, False otherwise, None if no data
        """
        if not self.coordinator.data:
            return None
        
        start_time, end_time = self._active_period
        if not start_time or not end_time:
            return False

        now = datetime.datetime.now()
        return start_time <= now <= end_time

    @property
    def available(self) -> bool:
        """
        Return if entity is available.
        
        Returns:
            True if coordinator has successfully updated data
        """
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def _active_period(self) -> tuple[datetime.datetime | None, datetime.datetime | None]:
        """Get the start and end time for the sensor's active period."""
        if self.sensor_type == "is_shabbat":
            shabbat_in = self.coordinator.data.get("shabbat_in")
            shabbat_out = self.coordinator.data.get("shabbat_out")
            if not shabbat_in or not shabbat_out:
                return None, None
            start_time = shabbat_in - datetime.timedelta(minutes=self.time_before_check)
            end_time = shabbat_out + datetime.timedelta(minutes=self.time_after_check)
            return start_time, end_time
        
        if self.sensor_type == "is_yomtov":
            yomtov_in = self.coordinator.data.get("yomtov_in")
            yomtov_out = self.coordinator.data.get("yomtov_out")
            if not yomtov_in or not yomtov_out:
                return None, None
            start_time = yomtov_in - datetime.timedelta(minutes=self.time_before_check)
            end_time = yomtov_out + datetime.timedelta(minutes=self.time_after_check)
            return start_time, end_time

        if self.sensor_type == "issur_melacha":
            period = self.coordinator.isur_melacha_period
            return period.get('start'), period.get('end')
            
        return None, None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """
        Return additional state attributes based on sensor type.
        
        Provides detailed information relevant to each sensor type
        including times, names, and status information.
        
        Returns:
            Dictionary of additional attributes
        """
        if not self.coordinator.data:
            return {}
            
        attributes = {}
        
        if self.sensor_type == "is_shabbat":
            attributes.update(self._get_shabbat_attributes())
        elif self.sensor_type == "is_yomtov":
            attributes.update(self._get_yomtov_attributes())
        elif self.sensor_type == "issur_melacha":
            attributes.update(self._get_issur_melacha_attributes())
        
        # Add common attributes
        attributes["last_updated"] = self.coordinator.data.get("update_time", datetime.datetime.now()).isoformat()
        attributes["time_before_check"] = self.time_before_check
        attributes["time_after_check"] = self.time_after_check
        
        return attributes

    def _get_shabbat_attributes(self) -> Dict[str, Any]:
        """
        Get Shabbat-specific attributes.
        
        Returns:
            Dictionary with Shabbat times, Parasha, and status information
        """
        attributes = {}
        
        # Shabbat times
        shabbat_in = self.coordinator.data.get("shabbat_in")
        shabbat_out = self.coordinator.data.get("shabbat_out")
        
        if shabbat_in:
            attributes["shabbat_in"] = shabbat_in.isoformat()
            attributes["candle_lighting"] = shabbat_in.strftime("%H:%M")
            attributes["candle_lighting_day"] = shabbat_in.strftime("%A")
            start_time = shabbat_in - datetime.timedelta(minutes=self.time_before_check)
            attributes["active_from"] = start_time.isoformat()
            attributes["active_from_time"] = start_time.strftime("%H:%M")
            
        if shabbat_out:
            attributes["shabbat_out"] = shabbat_out.isoformat()
            attributes["havdalah"] = shabbat_out.strftime("%H:%M")
            attributes["havdalah_day"] = shabbat_out.strftime("%A")
            end_time = shabbat_out + datetime.timedelta(minutes=self.time_after_check)
            attributes["active_until"] = end_time.isoformat()
            attributes["active_until_time"] = end_time.strftime("%H:%M")
        
        # Parasha information
        parasha = self.coordinator.data.get("parasha")
        if parasha:
            attributes["parasha"] = parasha
        
        # Time calculations
        now = datetime.datetime.now()
        if self.is_on and shabbat_out:
            time_until_end = self.coordinator.get_time_until_event(shabbat_out)
            if time_until_end:
                attributes["time_until_havdalah"] = self.coordinator.format_time_delta(time_until_end)
                attributes["minutes_until_havdalah"] = int(time_until_end.total_seconds() / 60)
        elif not self.is_on and shabbat_in and shabbat_in > now:
            time_until_start = self.coordinator.get_time_until_event(shabbat_in)
            if time_until_start:
                attributes["time_until_candles"] = self.coordinator.format_time_delta(time_until_start)
                attributes["minutes_until_candles"] = int(time_until_start.total_seconds() / 60)
        
        # Status in Hebrew
        if self.is_on:
            attributes["status_hebrew"] = "שבת קודש"
        else:
            attributes["status_hebrew"] = "יום חול"
            
        return attributes

    def _get_yomtov_attributes(self) -> Dict[str, Any]:
        """
        Get Yom Tov-specific attributes.
        
        Returns:
            Dictionary with Yom Tov times, holiday names, and status information
        """
        attributes = {}
        
        # Yom Tov times
        yomtov_in = self.coordinator.data.get("yomtov_in")
        yomtov_out = self.coordinator.data.get("yomtov_out")
        
        if yomtov_in:
            attributes["yomtov_in"] = yomtov_in.isoformat()
            attributes["candle_lighting"] = yomtov_in.strftime("%H:%M")
            attributes["candle_lighting_day"] = yomtov_in.strftime("%A")
            start_time = yomtov_in - datetime.timedelta(minutes=self.time_before_check)
            attributes["active_from"] = start_time.isoformat()
            attributes["active_from_time"] = start_time.strftime("%H:%M")
            
        if yomtov_out:
            attributes["yomtov_out"] = yomtov_out.isoformat()
            attributes["havdalah"] = yomtov_out.strftime("%H:%M")
            attributes["havdalah_day"] = yomtov_out.strftime("%A")
            end_time = yomtov_out + datetime.timedelta(minutes=self.time_after_check)
            attributes["active_until"] = end_time.isoformat()
            attributes["active_until_time"] = end_time.strftime("%H:%M")
        
        # Holiday information
        yomtov_name = self.coordinator.data.get("yomtov_name")
        if yomtov_name:
            attributes["yomtov_name"] = yomtov_name
            attributes["holiday_name"] = yomtov_name
        
        # Special holiday flags
        if self.coordinator.data.get("rosh_hashana"):
            attributes["holiday_type"] = "Rosh Hashana (2 days)"
            attributes["special_notes"] = "Two-day holiday"
        elif self.coordinator.data.get("special_holiday"):
            attributes["holiday_type"] = "Special Holiday"
        else:
            attributes["holiday_type"] = "Regular Holiday"
        
        # Holiday count
        holiday_count = self.coordinator.data.get("holiday_count", 0)
        if holiday_count > 0:
            attributes["holiday_count"] = holiday_count
        
        # Time calculations
        now = datetime.datetime.now()
        if self.is_on and yomtov_out:
            time_until_end = self.coordinator.get_time_until_event(yomtov_out)
            if time_until_end:
                attributes["time_until_havdalah"] = self.coordinator.format_time_delta(time_until_end)
                attributes["minutes_until_havdalah"] = int(time_until_end.total_seconds() / 60)
        elif not self.is_on and yomtov_in and yomtov_in > now:
            time_until_start = self.coordinator.get_time_until_event(yomtov_in)
            if time_until_start:
                attributes["time_until_candles"] = self.coordinator.format_time_delta(time_until_start)
                attributes["minutes_until_candles"] = int(time_until_start.total_seconds() / 60)
        
        # Status in Hebrew
        if self.is_on:
            attributes["status_hebrew"] = "יום טוב"
        else:
            attributes["status_hebrew"] = "יום חול"
            
        return attributes

    def _get_issur_melacha_attributes(self) -> Dict[str, Any]:
        """
        Get Issur Melacha-specific attributes.
        
        Provides comprehensive information about work prohibition periods,
        including extended periods that combine Shabbat and Yom Tov.
        
        Returns:
            Dictionary with detailed Issur Melacha information
        """
        attributes = {}
        period = self.coordinator.isur_melacha_period
        
        # Basic period information
        if period['start']:
            attributes["period_start"] = period['start'].isoformat()
            attributes["period_start_time"] = period['start'].strftime("%H:%M")
            attributes["period_start_day"] = period['start'].strftime("%A")
            
        if period['end']:
            attributes["period_end"] = period['end'].isoformat()
            attributes["period_end_time"] = period['end'].strftime("%H:%M")
            attributes["period_end_day"] = period['end'].strftime("%A")
        
        # Period details
        attributes["period_type"] = period['type']
        attributes["period_type_hebrew"] = self.coordinator.get_isur_melacha_type_description()
        attributes["duration_hours"] = period['duration_hours']
        attributes["is_active"] = period['active']
        
        # Duration formatting
        if period['duration_hours'] > 0:
            if period['duration_hours'] >= 24:
                days = int(period['duration_hours'] // 24)
                hours = int(period['duration_hours'] % 24)
                attributes["duration_formatted"] = f"{days} days, {hours} hours"
                attributes["duration_formatted_hebrew"] = f"{days} ימים, {hours} שעות"
            else:
                attributes["duration_formatted"] = f"{period['duration_hours']} hours"
                attributes["duration_formatted_hebrew"] = f"{period['duration_hours']} שעות"
        
        # Time calculations
        now = datetime.datetime.now()
        if self.is_on:
            # Currently active - show time until end
            time_until_end = self.coordinator.get_time_until_isur_melacha_end()
            if time_until_end:
                attributes["time_until_end"] = self.coordinator.format_time_delta(time_until_end)
                attributes["minutes_until_end"] = int(time_until_end.total_seconds() / 60)
        else:
            # Not active - show time until start
            time_until_start = self.coordinator.get_time_until_isur_melacha_start()
            if time_until_start:
                attributes["time_until_start"] = self.coordinator.format_time_delta(time_until_start)
                attributes["minutes_until_start"] = int(time_until_start.total_seconds() / 60)
        
        # Individual component status
        attributes["shabbat_active"] = self.coordinator.is_shabbat_active
        attributes["yomtov_active"] = self.coordinator.is_yomtov_active
        
        # Individual times for reference
        shabbat_in = self.coordinator.data.get("shabbat_in")
        shabbat_out = self.coordinator.data.get("shabbat_out")
        yomtov_in = self.coordinator.data.get("yomtov_in")
        yomtov_out = self.coordinator.data.get("yomtov_out")
        
        if shabbat_in:
            attributes["shabbat_candles"] = shabbat_in.strftime("%H:%M")
        if shabbat_out:
            attributes["shabbat_havdalah"] = shabbat_out.strftime("%H:%M")
        if yomtov_in:
            attributes["yomtov_candles"] = yomtov_in.strftime("%H:%M")
        if yomtov_out:
            attributes["yomtov_havdalah"] = yomtov_out.strftime("%H:%M")
        
        # Detailed status
        attributes["status_hebrew"] = self.coordinator.format_isur_melacha_status()
        
        # Special cases information
        special_info = []
        if self.coordinator.data.get("rosh_hashana"):
            special_info.append("Rosh Hashana (2 days)")
        if self.coordinator.data.get("special_holiday"):
            special_info.append("Special Holiday")
        
        if special_info:
            attributes["special_cases"] = ", ".join(special_info)
        
        # Next events for planning
        next_candles = self.coordinator.next_candle_lighting
        if next_candles:
            attributes["next_candle_lighting"] = next_candles.strftime("%A %H:%M")
            attributes["next_candle_lighting_full"] = next_candles.isoformat()
            
        next_havdalah = self.coordinator.next_havdalah
        if next_havdalah:
            attributes["next_havdalah"] = next_havdalah.strftime("%A %H:%M")
            attributes["next_havdalah_full"] = next_havdalah.isoformat()
        
        # Work status
        if self.is_on:
            attributes["work_status"] = "Prohibited"
            attributes["work_status_hebrew"] = "אסור לעשות מלאכה"
        else:
            attributes["work_status"] = "Permitted"
            attributes["work_status_hebrew"] = "מותר לעשות מלאכה"
            
        return attributes

    @property
    def icon(self) -> str:
        """
        Return dynamic icon based on sensor type and state.
        
        Provides visual feedback for the current status of each sensor.
        
        Returns:
            Material Design icon string
        """
        if self.sensor_type == "issur_melacha":
            # Dynamic icon for Issur Melacha based on state
            if self.is_on:
                return "mdi:hand-back-right-off"  # Work prohibited
            else:
                return "mdi:hand-back-right"      # Work allowed
        
        # Use default icon from configuration for other sensors
        return self._attr_icon
