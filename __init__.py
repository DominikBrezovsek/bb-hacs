# custom_components/billbuster/__init__.py

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_entry_flow, config_validation as cv

from .const import DOMAIN
from .coordinator import BillBusterCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BillBuster from a config entry."""
    _LOGGER.info("Setting up BillBuster entry: %s", entry.title)

    coordinator = BillBusterCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    _LOGGER.info("BillBuster entry %s setup complete", entry.title)

    async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry):
        """Handle options update."""

        _LOGGER.debug("Config entry updated: %s", entry.options)
        await coordinator.update_from_config_entry(entry)
        await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading BillBuster entry: %s", entry.title)

    if entry.entry_id in hass.data.get(DOMAIN, {}):
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Coordinator removed from hass data")

    _LOGGER.info("BillBuster entry %s unloaded", entry.title)
    return True
