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
    CONF_SELECTABLE_VALUE,
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_SOC,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
DATA_SCHEMA_BASE = vol.Schema(
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

    async def _fetch_selectable_values(self, api_key: str) -> list[str] | None:
        """Fetch selectable values from the API."""
        session = aiohttp.ClientSession()
        url = "https://nexa-api.sigma-solutions.eu/api/integration/get-meters"
        token = api_key
        try:
            async with session.post(
                url, data={"apiKey": token}, timeout=10
            ) as response:
                if response.status != 200:
                    response.raise_for_status()
                data = await response.json()
                selectable_values = [
                    item if isinstance(item, str) else item.get("name") for item in data
                ]
                return [value for value in selectable_values if value]
        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("Error connecting to API to fetch dropdown values: %s", err)
            return None
        except aiohttp.ClientResponseError as err:
            _LOGGER.error("API error fetching dropdown values: %s", err)
            return None
        except Exception as err:
            _LOGGER.exception("Unexpected error fetching dropdown values: %s", err)
            return None
        finally:
            await session.close()

    async def validate_input(self, hass, data: dict[str, Any]) -> dict[str, str]:
        """Validate the API key by trying to connect."""
        errors: dict[str, str] = {}
        session = aiohttp.ClientSession()
        test_url = "https://nexa-api.sigma-solutions.eu/validate_key"
        apiKey = data[CONF_API_KEY]
        try:
            async with session.get(
                test_url, data={"apikey": apiKey}, timeout=10
            ) as response:
                if response.status == 401:
                    _LOGGER.error("API key rejected by endpoint")
                    errors["API Token"] = "invalid_auth"
                    response.raise_for_status()
                _LOGGER.info("API key validated successfully")
        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("Cannot connect to API endpoint: %s", err)
            errors["base"] = "cannot_connect"
        except Exception as err:
            _LOGGER.exception("Unknown error occurred during API key validation")
            errors["base"] = "unknown"
        finally:
            await session.close()
        return errors

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step when user adds the integration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            validation_errors = await self.validate_input(self.hass, user_input)
            if not validation_errors:
                api_key = user_input.get(CONF_API_KEY)
                selectable_values = await self._fetch_selectable_values(api_key)
                if selectable_values is None:
                    errors["base"] = "cannot_connect_api_values"
                elif not selectable_values:
                    errors["base"] = "no_selectable_values"
                else:
                    self.flow_context["user_input"] = user_input
                    self.flow_context["selectable_values"] = selectable_values
                    return await self.async_step_select()
            else:
                errors = validation_errors

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA_BASE,
            errors=errors,
            description_placeholders="Configure your Billbuster integration.",
        )

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the selection of a value."""
        selectable_values = self.flow_context.get("selectable_values")
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_value = user_input.get(CONF_SELECTABLE_VALUE)
            if selected_value in selectable_values:
                return self.async_create_entry(
                    title="Inverter settings",
                    data={
                        **self.flow_context.get("user_input", {}),
                        CONF_SELECTABLE_VALUE: selected_value,
                    },
                )
            else:
                errors[CONF_SELECTABLE_VALUE] = "invalid_selection"

        if selectable_values:
            SELECT_SCHEMA = vol.Schema(
                {
                    vol.Required(CONF_SELECTABLE_VALUE): vol.In(selectable_values),
                }
            )
            return self.async_show_form(
                step_id="select", data_schema=SELECT_SCHEMA, errors=errors
            )
        else:
            return self.async_abort(reason="no_selectable_values")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


class CannotConnect(Exception):
    """Error to indicate there is a problem connecting."""
