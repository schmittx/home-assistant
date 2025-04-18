"""A entity class for Bravia TV integration."""

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_MANUFACTURER, DOMAIN
from .coordinator import BraviaTVCoordinator


class BraviaTVEntity(CoordinatorEntity[BraviaTVCoordinator]):
    """BraviaTV entity class."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BraviaTVCoordinator,
        unique_id: str,
        model: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)

        self._attr_unique_id = unique_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            manufacturer=ATTR_MANUFACTURER,
            model=model,
            name=f"{ATTR_MANUFACTURER} {model}",
        )
        if coordinator.client.mac is not None:
            self._attr_device_info["connections"] = {
                (CONNECTION_NETWORK_MAC, coordinator.client.mac)
            }
