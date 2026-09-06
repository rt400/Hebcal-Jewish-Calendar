"""Config flow for Hebcal Jewish Calendar integration."""
import logging
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_TIME_ZONE
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_LANGUAGE,
    CONF_HAVDALAH_MINUTES,
    CONF_TIME_BEFORE_CHECK,
    CONF_TIME_AFTER_CHECK,
    CONF_JERUSALEM_CANDLE,
    CONF_TZEIT_HAKOCHAVIM,
    CONF_DIASPORA,
    CONF_USE_12H_TIME,
    CONF_OMER_COUNT_TYPE,
    DEFAULT_LANGUAGE,
    DEFAULT_HAVDALAH_MINUTES,
    DEFAULT_TIME_BEFORE_CHECK,
    DEFAULT_TIME_AFTER_CHECK,
    DEFAULT_JERUSALEM_CANDLE,
    DEFAULT_TZEIT_HAKOCHAVIM,
    DEFAULT_DIASPORA,
    DEFAULT_USE_12H_TIME,
    DEFAULT_OMER_COUNT_TYPE,
)

_LOGGER = logging.getLogger(__name__)

LANGUAGE_CHOICES = {
    "hebrew": "Hebrew - עברית (Native Hebrew event names)",
    "english": "English (Transliterated event names)",
}

OMER_COUNT_TYPE_MAP = {
    "omer_count_yemenite": 0,
    "omer_count_ashkenazi_sephardic": 1,
}

OMER_COUNT_TYPE_REVERSE_MAP = {
    0: "omer_count_yemenite",
    1: "omer_count_ashkenazi_sephardic",
}


class HebcalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle configuration flow for Hebcal Jewish Calendar integration."""

    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self) -> None:
        self.data: Dict[str, Any] = {}

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        if user_input is not None:
            self.data.update(user_input)
            return await self.async_step_location()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LANGUAGE, default=DEFAULT_LANGUAGE
                    ): vol.In(LANGUAGE_CHOICES),
                }
            ),
        )

    async def async_step_location(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        errors: Dict[str, str] = {}

        if user_input is not None:
            try:
                latitude = float(user_input[CONF_LATITUDE])
                longitude = float(user_input[CONF_LONGITUDE])

                if not (-90 <= latitude <= 90):
                    errors[CONF_LATITUDE] = "invalid_latitude"
                elif not (-180 <= longitude <= 180):
                    errors[CONF_LONGITUDE] = "invalid_longitude"
                else:
                    self.data.update(user_input)
                    return await self.async_step_settings()

            except (ValueError, TypeError):
                errors["base"] = "invalid_coordinates"

        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LATITUDE, default=self.hass.config.latitude
                    ): cv.latitude,
                    vol.Required(
                        CONF_LONGITUDE, default=self.hass.config.longitude
                    ): cv.longitude,
                    vol.Required(
                        CONF_TIME_ZONE, default=str(self.hass.config.time_zone)
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_settings(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        if user_input is not None:
            if CONF_OMER_COUNT_TYPE in user_input:
                user_input[CONF_OMER_COUNT_TYPE] = OMER_COUNT_TYPE_MAP[
                    user_input[CONF_OMER_COUNT_TYPE]
                ]

            self.data.update(user_input)

            unique_id = f"{self.data[CONF_LATITUDE]}_{self.data[CONF_LONGITUDE]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            title = (
                "Hebcal - לוח השנה העברי"
                if self.data[CONF_LANGUAGE] == "hebrew"
                else "Hebcal Jewish Calendar"
            )

            return self.async_create_entry(title=title, data=self.data)

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_HAVDALAH_MINUTES,
                        default=DEFAULT_HAVDALAH_MINUTES,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
                    vol.Optional(
                        CONF_TIME_BEFORE_CHECK,
                        default=DEFAULT_TIME_BEFORE_CHECK,
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
                    vol.Optional(
                        CONF_TIME_AFTER_CHECK,
                        default=DEFAULT_TIME_AFTER_CHECK,
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
                    vol.Optional(
                        CONF_JERUSALEM_CANDLE,
                        default=DEFAULT_JERUSALEM_CANDLE,
                    ): bool,
                    vol.Optional(
                        CONF_TZEIT_HAKOCHAVIM,
                        default=DEFAULT_TZEIT_HAKOCHAVIM,
                    ): bool,
                    vol.Optional(
                        CONF_DIASPORA,
                        default=DEFAULT_DIASPORA,
                    ): bool,
                    vol.Optional(
                        CONF_USE_12H_TIME,
                        default=DEFAULT_USE_12H_TIME,
                    ): bool,
                    vol.Optional(
                        CONF_OMER_COUNT_TYPE,
                        default=OMER_COUNT_TYPE_REVERSE_MAP[
                            DEFAULT_OMER_COUNT_TYPE
                        ],
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(OMER_COUNT_TYPE_MAP.keys()),
                            translation_key="omer_count_type",
                        )
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "HebcalOptionsFlowHandler":
        return HebcalOptionsFlowHandler()


class HebcalOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Hebcal integration."""

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        if user_input is not None:
            if CONF_OMER_COUNT_TYPE in user_input:
                user_input[CONF_OMER_COUNT_TYPE] = OMER_COUNT_TYPE_MAP[
                    user_input[CONF_OMER_COUNT_TYPE]
                ]
            return self.async_create_entry(title="", data=user_input)

        def get_value(key, default):
            return self.config_entry.options.get(
                key, self.config_entry.data.get(key, default)
            )

        current_omer = get_value(
            CONF_OMER_COUNT_TYPE, DEFAULT_OMER_COUNT_TYPE
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LANGUAGE,
                        default=get_value(CONF_LANGUAGE, DEFAULT_LANGUAGE),
                    ): vol.In(LANGUAGE_CHOICES),
                    vol.Optional(
                        CONF_HAVDALAH_MINUTES,
                        default=get_value(
                            CONF_HAVDALAH_MINUTES,
                            DEFAULT_HAVDALAH_MINUTES,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
                    vol.Optional(
                        CONF_TIME_BEFORE_CHECK,
                        default=get_value(
                            CONF_TIME_BEFORE_CHECK,
                            DEFAULT_TIME_BEFORE_CHECK,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
                    vol.Optional(
                        CONF_TIME_AFTER_CHECK,
                        default=get_value(
                            CONF_TIME_AFTER_CHECK,
                            DEFAULT_TIME_AFTER_CHECK,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
                    vol.Optional(
                        CONF_JERUSALEM_CANDLE,
                        default=get_value(
                            CONF_JERUSALEM_CANDLE,
                            DEFAULT_JERUSALEM_CANDLE,
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_TZEIT_HAKOCHAVIM,
                        default=get_value(
                            CONF_TZEIT_HAKOCHAVIM,
                            DEFAULT_TZEIT_HAKOCHAVIM,
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_DIASPORA,
                        default=get_value(
                            CONF_DIASPORA, DEFAULT_DIASPORA
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_USE_12H_TIME,
                        default=get_value(
                            CONF_USE_12H_TIME,
                            DEFAULT_USE_12H_TIME,
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_OMER_COUNT_TYPE,
                        default=OMER_COUNT_TYPE_REVERSE_MAP.get(
                            current_omer,
                            "omer_count_ashkenazi_sephardic",
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(OMER_COUNT_TYPE_MAP.keys()),
                            translation_key="omer_count_type",
                        )
                    ),
                }
            ),
        )
