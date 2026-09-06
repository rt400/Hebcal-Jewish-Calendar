"""
Hebcal Jewish Calendar Integration for Home Assistant.
"""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, UPDATE_INTERVAL
from .coordinator import HebcalDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hebcal from a config entry."""
    # Check if migration is needed
    if entry.version < 2:  # If the version is old
        await async_migrate_entry(hass, entry)
    
    coordinator = HebcalDataUpdateCoordinator(hass, entry)
    
    await coordinator.async_config_entry_first_refresh()
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry to new format."""
    _LOGGER.info("Migrating Hebcal config entry from version %s", config_entry.version)
    
    new_data = {**config_entry.data}
    new_options = {**config_entry.options}
    
    if config_entry.version == 1:
        # Migration from version 1 to version 2
        # Here you can add data format changes if needed
        _LOGGER.info("Migrating from version 1 to 2")
        
        # Example: if you changed configuration key names
        # if "old_key" in new_data:
        #     new_data["new_key"] = new_data.pop("old_key")
    
    # Update the config entry
    hass.config_entries.async_update_entry(
        config_entry,
        data=new_data,
        options=new_options,
        version=2,  # The new version
    )
    
    _LOGGER.info("Migration completed successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok
