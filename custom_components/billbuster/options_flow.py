import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
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
    CONF_SELECTABLE_VALUE,  # Define this in your const.py
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_SOC,
)

_LOGGER = logging.getLogger(__name__)


class OptionsFlowHandler(config_entries.OptionsFlow):
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

    async def validate_input(self, data: dict[str, Any]) -> dict[str, str]:
        """Validate the API key by trying to connect."""
        errors: dict[str, str] = {}
        session = aiohttp.ClientSession()
        test_url = "https://nexa-api.sigma-solutions.eu/api/integration/verify-token"
        token = data[CONF_API_KEY]
        try:
            async with session.post(test_url, data={"apiToken": token}) as resp:
                _LOGGER.info("Resp status is: %s", resp.status)
                if resp.status == 400:
                    _LOGGER.error("API key rejected by endpoint")
                    errors["API Token"] = "invalid_auth"
                    raise InvalidAuth("Invalid API key")
            _LOGGER.info("API key validated successfully (in options flow)")
        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("Cannot connect to API endpoint for validation: %s", err)
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            pass  # Errors already set
        except Exception:
            _LOGGER.exception("Unknown error occurred during API key validation")
            errors["base"] = "unknown"
        finally:
            await session.close()
        return errors

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self.validate_input(user_input)
            if not errors:
                return self.async_create_entry(data=user_input)

        current_api_key = self.config_entry.options.get(
            CONF_API_KEY, self.config_entry.data.get(CONF_API_KEY)
        )
        selectable_values = await self._fetch_selectable_values(current_api_key)

        if selectable_values is None:
            return self.async_abort(reason="cannot_connect_dropdown")  # Add translation
        elif not selectable_values:
            return self.async_abort(reason="no_selectable_values")  # Add translation

        options_schema = vol.Schema(
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
                vol.Required(
                    CONF_SELECTABLE_VALUE,
                    default=self.config_entry.options.get(
                        CONF_SELECTABLE_VALUE,
                        self.config_entry.data.get(CONF_SELECTABLE_VALUE),
                    ),
                ): vol.In(selectable_values),
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


class CannotConnect(Exception):
    """Error to indicate there is a problem connecting."""
