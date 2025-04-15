from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .inverter_logic import DeyeInverter

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=15)


class BillBusterCoordinator(DataUpdateCoordinator):
    """Coordinates updates for the BillBuster integration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.inverter = DeyeInverter(hass, entry)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({entry.title})",
            update_interval=UPDATE_INTERVAL,
        )

    async def _async_update_data(self):
        """Fetch data and update the inverter schedule."""
        _LOGGER.info("Running scheduled inverter update")
        try:
            success = await self.inverter.async_run_schedule_update()
            if not success:
                _LOGGER.warning(
                    "Inverter schedule update did not complete successfully"
                )
                return {"last_update_status": "failed"}

            _LOGGER.info("Inverter schedule update completed successfully")
            self.update_interval = self.inverter.next_run
            _LOGGER.info("Next run scheduled at" + self.update_interval)
            return {
                "last_update_status": "success",
                "timestamp": self.last_update_success_time,
            }

        except Exception as err:
            _LOGGER.exception(
                "Error communicating with inverter during scheduled update"
            )
            raise UpdateFailed(f"Error updating inverter schedule: {err}") from err

    async def update_from_config_entry(self, entry: ConfigEntry):
        """Update coordinator with new config entry data."""
        self.inverter.update_from_config_entry(entry=entry)
        _LOGGER.debug("Coordinator updated with new config: %s", entry.options)
