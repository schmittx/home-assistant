"""DataUpdateCoordinator for the Adax component."""

import logging
from typing import Any, cast

from adax import Adax
from adax_local import Adax as AdaxLocal

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, CONF_PASSWORD, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import ACCOUNT_ID, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


type AdaxConfigEntry = ConfigEntry[AdaxCloudCoordinator | AdaxLocalCoordinator]


class AdaxCloudCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator for updating data to and from Adax (cloud)."""

    def __init__(self, hass: HomeAssistant, entry: AdaxConfigEntry) -> None:
        """Initialize the Adax coordinator used for Cloud mode."""
        super().__init__(
            hass,
            config_entry=entry,
            logger=_LOGGER,
            name="AdaxCloud",
            update_interval=SCAN_INTERVAL,
        )

        self.adax_data_handler = Adax(
            entry.data[ACCOUNT_ID],
            entry.data[CONF_PASSWORD],
            websession=async_get_clientsession(hass),
        )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from the Adax."""
        try:
            if hasattr(self.adax_data_handler, "fetch_rooms_info"):
                rooms = await self.adax_data_handler.fetch_rooms_info() or []
                _LOGGER.debug("fetch_rooms_info returned: %s", rooms)
            else:
                _LOGGER.debug("fetch_rooms_info method not available, using get_rooms")
                rooms = []

            if not rooms:
                _LOGGER.debug(
                    "No rooms from fetch_rooms_info, trying get_rooms as fallback"
                )
                rooms = await self.adax_data_handler.get_rooms() or []
                _LOGGER.debug("get_rooms fallback returned: %s", rooms)

            if not rooms:
                raise UpdateFailed("No rooms available from Adax API")

        except OSError as e:
            raise UpdateFailed(f"Error communicating with API: {e}") from e

        for room in rooms:
            room["energyWh"] = int(room.get("energyWh", 0))

        return {r["id"]: r for r in rooms}


class AdaxLocalCoordinator(DataUpdateCoordinator[dict[str, Any] | None]):
    """Coordinator for updating data to and from Adax (local)."""

    def __init__(self, hass: HomeAssistant, entry: AdaxConfigEntry) -> None:
        """Initialize the Adax coordinator used for Local mode."""
        super().__init__(
            hass,
            config_entry=entry,
            logger=_LOGGER,
            name="AdaxLocal",
            update_interval=SCAN_INTERVAL,
        )

        self.adax_data_handler = AdaxLocal(
            entry.data[CONF_IP_ADDRESS],
            entry.data[CONF_TOKEN],
            websession=async_get_clientsession(hass, verify_ssl=False),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the Adax."""
        if result := await self.adax_data_handler.get_status():
            return cast(dict[str, Any], result)
        raise UpdateFailed("Got invalid status from device")
