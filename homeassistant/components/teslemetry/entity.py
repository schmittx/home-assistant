"""Teslemetry parent entity class."""

from abc import abstractmethod
from typing import Any

from propcache.api import cached_property
from tesla_fleet_api.const import Scope
from tesla_fleet_api.teslemetry import EnergySite, Vehicle
from teslemetry_stream import Signal

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    TeslemetryEnergyHistoryCoordinator,
    TeslemetryEnergySiteInfoCoordinator,
    TeslemetryEnergySiteLiveCoordinator,
    TeslemetryVehicleDataCoordinator,
)
from .helpers import wake_up_vehicle
from .models import TeslemetryEnergyData, TeslemetryVehicleData


class TeslemetryRootEntity(Entity):
    """Parent class for all Teslemetry entities."""

    _attr_has_entity_name = True
    scoped: bool
    api: Vehicle | EnergySite

    def raise_for_scope(self, scope: Scope):
        """Raise an error if a scope is not available."""
        if not self.scoped:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="missing_scope",
                translation_placeholders={"scope": scope},
            )


class TeslemetryEntity(
    TeslemetryRootEntity,
    CoordinatorEntity[
        TeslemetryVehicleDataCoordinator
        | TeslemetryEnergyHistoryCoordinator
        | TeslemetryEnergySiteLiveCoordinator
        | TeslemetryEnergySiteInfoCoordinator
    ],
):
    """Parent class for all Teslemetry Coordinator entities."""

    def __init__(
        self,
        coordinator: TeslemetryVehicleDataCoordinator
        | TeslemetryEnergyHistoryCoordinator
        | TeslemetryEnergySiteLiveCoordinator
        | TeslemetryEnergySiteInfoCoordinator,
        key: str,
    ) -> None:
        """Initialize common aspects of a Teslemetry entity."""
        super().__init__(coordinator)
        self.key = key
        self._attr_translation_key = self.key
        self._async_update_attrs()

    @property
    def available(self) -> bool:
        """Return if sensor is available."""
        return self.coordinator.last_update_success and self._attr_available

    @property
    def _value(self) -> Any | None:
        """Return a specific value from coordinator data."""
        return self.coordinator.data.get(self.key)

    def get(self, key: str, default: Any | None = None) -> Any | None:
        """Return a specific value from coordinator data."""
        return self.coordinator.data.get(key, default)

    def get_number(self, key: str, default: float) -> float:
        """Return a specific number from coordinator data."""
        if isinstance(value := self.coordinator.data.get(key), (int, float)):
            return value
        return default

    @property
    def is_none(self) -> bool:
        """Return if the value is a literal None."""
        return self.get(self.key, False) is None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._async_update_attrs()
        self.async_write_ha_state()

    @abstractmethod
    def _async_update_attrs(self) -> None:
        """Update the attributes of the entity."""


class TeslemetryVehicleEntity(TeslemetryEntity):
    """Parent class for Teslemetry Vehicle entities."""

    _last_update: int = 0
    api: Vehicle
    vehicle: TeslemetryVehicleData

    def __init__(
        self,
        data: TeslemetryVehicleData,
        key: str,
    ) -> None:
        """Initialize common aspects of a Teslemetry entity."""

        self.api = data.api
        self.vehicle = data
        self._attr_unique_id = f"{data.vin}-{key}"
        self._attr_device_info = data.device
        super().__init__(data.coordinator, key)

    @property
    def _value(self) -> Any | None:
        """Return a specific value from coordinator data."""
        return self.coordinator.data.get(self.key)

    async def wake_up_if_asleep(self) -> None:
        """Wake up the vehicle if its asleep."""
        await wake_up_vehicle(self.vehicle)


class TeslemetryEnergyLiveEntity(TeslemetryEntity):
    """Parent class for Teslemetry Energy Site Live entities."""

    api: EnergySite

    def __init__(
        self,
        data: TeslemetryEnergyData,
        key: str,
    ) -> None:
        """Initialize common aspects of a Teslemetry Energy Site Live entity."""

        assert data.live_coordinator

        self.api = data.api
        self._attr_unique_id = f"{data.id}-{key}"
        self._attr_device_info = data.device

        super().__init__(data.live_coordinator, key)


class TeslemetryEnergyInfoEntity(TeslemetryEntity):
    """Parent class for Teslemetry Energy Site Info Entities."""

    api: EnergySite

    def __init__(
        self,
        data: TeslemetryEnergyData,
        key: str,
    ) -> None:
        """Initialize common aspects of a Teslemetry Energy Site Info entity."""

        self.api = data.api
        self._attr_unique_id = f"{data.id}-{key}"
        self._attr_device_info = data.device

        super().__init__(data.info_coordinator, key)


class TeslemetryEnergyHistoryEntity(TeslemetryEntity):
    """Parent class for Teslemetry Energy History Entities."""

    def __init__(
        self,
        data: TeslemetryEnergyData,
        key: str,
    ) -> None:
        """Initialize common aspects of a Teslemetry Energy Site Info entity."""

        assert data.history_coordinator

        self.api = data.api
        self._attr_unique_id = f"{data.id}-{key}"
        self._attr_device_info = data.device

        super().__init__(data.history_coordinator, key)


class TeslemetryWallConnectorEntity(TeslemetryEntity):
    """Parent class for Teslemetry Wall Connector Entities."""

    _attr_has_entity_name = True
    api: EnergySite

    def __init__(
        self,
        data: TeslemetryEnergyData,
        din: str,
        key: str,
    ) -> None:
        """Initialize common aspects of a Teslemetry entity."""

        assert data.live_coordinator

        self.api = data.api
        self.din = din
        self._attr_unique_id = f"{data.id}-{din}-{key}"

        # Find the model from the info coordinator
        model: str | None = None
        for wc in data.info_coordinator.data.get("components_wall_connectors", []):
            if wc["din"] == din:
                model = wc.get("part_name")
                break

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, din)},
            manufacturer="Tesla",
            configuration_url="https://teslemetry.com/console",
            name="Wall Connector",
            via_device=(DOMAIN, str(data.id)),
            serial_number=din.split("-")[-1],
            model=model,
        )

        super().__init__(data.live_coordinator, key)

    @property
    def _value(self) -> int:
        """Return a specific wall connector value from coordinator data."""
        return (
            self.coordinator.data.get("wall_connectors", {})
            .get(self.din, {})
            .get(self.key)
        )

    @property
    def exists(self) -> bool:
        """Return True if it exists in the wall connector coordinator data."""
        return self.key in self.coordinator.data.get("wall_connectors", {}).get(
            self.din, {}
        )


class TeslemetryVehicleStreamEntity(TeslemetryRootEntity):
    """Parent class for Teslemetry Vehicle Stream entities."""

    def __init__(
        self, data: TeslemetryVehicleData, key: str, streaming_key: Signal | None = None
    ) -> None:
        """Initialize common aspects of a Teslemetry entity."""
        self.streaming_key = streaming_key
        self.vehicle = data

        self.api = data.api
        self.stream = data.stream
        self.vin = data.vin
        self.add_field = data.stream.get_vehicle(self.vin).add_field

        self._attr_translation_key = key
        self._attr_unique_id = f"{data.vin}-{key}"
        self._attr_device_info = data.device

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        if self.streaming_key:
            self.async_on_remove(
                self.stream.async_add_listener(
                    self._handle_stream_update,
                    {"vin": self.vin, "data": {self.streaming_key: None}},
                )
            )
            self.vehicle.config_entry.async_create_background_task(
                self.hass,
                self.add_field(self.streaming_key),
                f"Adding field {self.streaming_key.value} to {self.vehicle.vin}",
            )

    def _handle_stream_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from the stream."""
        self._async_value_from_stream(data["data"][self.streaming_key])
        self.async_write_ha_state()

    def _async_value_from_stream(self, value: Any) -> None:
        """Update the entity with the latest value from the stream."""
        raise NotImplementedError

    @cached_property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.stream.connected
