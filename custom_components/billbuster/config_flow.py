import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.billbuster.options_flow import OptionsFlowHandler
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
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
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): cv.string,
        vol.Required(CONF_INVERTER_IP): cv.string,
        vol.Required(CONF_INVERTER_SERIAL): cv.string,
        vol.Required(CONF_INVERTER_POWER): cv.positive_int,
        vol.Required(CONF_PEAK_CHARGE_POWER): cv.positive_int,
        vol.Optional(CONF_MIN_SOC, default=DEFAULT_MIN_SOC): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=100)
        ),
        vol.Optional(CONF_MAX_SOC, default=DEFAULT_MAX_SOC): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=100)
        ),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for BillBuster."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step when user adds the integration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await self.validate_input(user_input)
            except InvalidAuth:
                errors["API Token"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            if not errors:
                _LOGGER.info("API key is valid, creating config entry")

                await self.async_set_unique_id(user_input[CONF_API_KEY])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Inverter settings",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
            description_placeholders="Configure your Billbuster integration.",
        )

    async def validate_input(self, data: dict[str, Any]) -> None:
        """Validate the API key by trying to connect."""

        session = aiohttp.ClientSession()
        test_url = "https://nexa-api.sigma-solutions.eu/api/integration/verify-token"
        token = data[CONF_API_KEY]
        try:
            async with session.post(test_url, data={"apiToken": token}) as resp:
                if resp.status == 400:
                    _LOGGER.error("API key rejected by endpoint")
                    resp.raise_for_status()
                _LOGGER.info("API key validated successfully")
                _LOGGER.info("Response code: %s", resp.status)
        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("Cannot connect to API endpoint: %s", err)
            raise CannotConnect("Cannot connect to the API endpoint")
        except Exception as err:
            _LOGGER.exception("Unknown error occurred during API key validation")
            raise err  # Re-raise other unexpected errors
        finally:
            await session.close()

    async def async_step_options(self, user_input=None):
        """Handle an options flow."""
        if user_input is not None:
            return self.async_create_entry(title="Inverter settings", data=user_input)

        return self.async_show_form(
            step_id="options",
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

    @staticmethod
    @callback
    def async_get_options_flow(configEntry):
        """Create the options flow."""
        return OptionsFlowHandler()


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


class CannotConnect(Exception):
    """Error to indicate there is a problem connecting."""
