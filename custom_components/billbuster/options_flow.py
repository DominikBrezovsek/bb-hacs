import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_API_KEY,
    CONF_INVERTER_IP,
    CONF_INVERTER_POWER,
    CONF_INVERTER_SERIAL,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_PEAK_CHARGE_POWER,
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_SOC,
)

_LOGGER = logging.getLogger(__name__)


class OptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_API_KEY,
                        default=self.config_entry.options.get(
                            CONF_API_KEY, self.config_entry.data.get(CONF_API_KEY)
                        ),
                    ): cv.string,
                    vol.Required(
                        CONF_INVERTER_IP,
                        default=self.config_entry.options.get(
                            CONF_INVERTER_IP,
                            self.config_entry.data.get(CONF_INVERTER_IP),
                        ),
                    ): cv.string,
                    vol.Required(
                        CONF_INVERTER_SERIAL,
                        default=self.config_entry.options.get(
                            CONF_INVERTER_SERIAL,
                            self.config_entry.data.get(CONF_INVERTER_SERIAL),
                        ),
                    ): vol.All(vol.Coerce(int)),
                    vol.Required(
                        CONF_INVERTER_POWER,
                        default=self.config_entry.options.get(
                            CONF_INVERTER_POWER,
                            self.config_entry.data.get(CONF_INVERTER_POWER),
                        ),
                    ): cv.positive_int,
                    vol.Required(
                        CONF_PEAK_CHARGE_POWER,
                        default=self.config_entry.options.get(
                            CONF_PEAK_CHARGE_POWER,
                            self.config_entry.data.get(CONF_PEAK_CHARGE_POWER),
                        ),
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_MIN_SOC,
                        default=self.config_entry.options.get(
                            CONF_MIN_SOC,
                            self.config_entry.data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC),
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                    vol.Optional(
                        CONF_MAX_SOC,
                        default=self.config_entry.options.get(
                            CONF_MAX_SOC,
                            self.config_entry.data.get(CONF_MAX_SOC, DEFAULT_MAX_SOC),
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                }
            ),
        )
