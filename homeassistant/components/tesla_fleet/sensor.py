"""Sensor platform for Tesla Fleet integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from itertools import chain
from typing import cast

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util
from homeassistant.util.variance import ignore_variance

from . import TeslaFleetConfigEntry
from .const import ENERGY_HISTORY_FIELDS, TeslaFleetState
from .entity import (
    TeslaFleetEnergyHistoryEntity,
    TeslaFleetEnergyInfoEntity,
    TeslaFleetEnergyLiveEntity,
    TeslaFleetVehicleEntity,
    TeslaFleetWallConnectorEntity,
)
from .models import TeslaFleetEnergyData, TeslaFleetVehicleData

PARALLEL_UPDATES = 0

CHARGE_STATES = {
    "Starting": "starting",
    "Charging": "charging",
    "Stopped": "stopped",
    "Complete": "complete",
    "Disconnected": "disconnected",
    "NoPower": "no_power",
}

SHIFT_STATES = {"P": "p", "D": "d", "R": "r", "N": "n"}


@dataclass(frozen=True, kw_only=True)
class TeslaFleetSensorEntityDescription(SensorEntityDescription):
    """Describes Tesla Fleet Sensor entity."""

    value_fn: Callable[[StateType], StateType] = lambda x: x


VEHICLE_DESCRIPTIONS: tuple[TeslaFleetSensorEntityDescription, ...] = (
    TeslaFleetSensorEntityDescription(
        key="charge_state_charging_state",
        options=list(CHARGE_STATES.values()),
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda value: CHARGE_STATES.get(cast(str, value)),
    ),
    TeslaFleetSensorEntityDescription(
        key="charge_state_battery_level",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
    ),
    TeslaFleetSensorEntityDescription(
        key="charge_state_usable_battery_level",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="charge_state_charge_energy_added",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=1,
    ),
    TeslaFleetSensorEntityDescription(
        key="charge_state_charger_power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
    ),
    TeslaFleetSensorEntityDescription(
        key="charge_state_charger_voltage",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    TeslaFleetSensorEntityDescription(
        key="charge_state_charger_actual_current",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    TeslaFleetSensorEntityDescription(
        key="charge_state_charge_rate",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    TeslaFleetSensorEntityDescription(
        key="charge_state_conn_charge_cable",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="charge_state_fast_charger_type",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="charge_state_battery_range",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.MILES,
        device_class=SensorDeviceClass.DISTANCE,
        suggested_display_precision=1,
    ),
    TeslaFleetSensorEntityDescription(
        key="charge_state_est_battery_range",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.MILES,
        device_class=SensorDeviceClass.DISTANCE,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="charge_state_ideal_battery_range",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.MILES,
        device_class=SensorDeviceClass.DISTANCE,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="drive_state_speed",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        entity_registry_enabled_default=False,
        value_fn=lambda value: value or 0,
    ),
    TeslaFleetSensorEntityDescription(
        key="drive_state_power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda value: value or 0,
    ),
    TeslaFleetSensorEntityDescription(
        key="drive_state_shift_state",
        options=list(SHIFT_STATES.values()),
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda x: SHIFT_STATES.get(str(x), "p"),
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="vehicle_state_odometer",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfLength.MILES,
        device_class=SensorDeviceClass.DISTANCE,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="vehicle_state_tpms_pressure_fl",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        suggested_unit_of_measurement=UnitOfPressure.PSI,
        device_class=SensorDeviceClass.PRESSURE,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="vehicle_state_tpms_pressure_fr",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        suggested_unit_of_measurement=UnitOfPressure.PSI,
        device_class=SensorDeviceClass.PRESSURE,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="vehicle_state_tpms_pressure_rl",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        suggested_unit_of_measurement=UnitOfPressure.PSI,
        device_class=SensorDeviceClass.PRESSURE,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="vehicle_state_tpms_pressure_rr",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        suggested_unit_of_measurement=UnitOfPressure.PSI,
        device_class=SensorDeviceClass.PRESSURE,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="climate_state_inside_temp",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        suggested_display_precision=1,
    ),
    TeslaFleetSensorEntityDescription(
        key="climate_state_outside_temp",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        suggested_display_precision=1,
    ),
    TeslaFleetSensorEntityDescription(
        key="climate_state_driver_temp_setting",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="climate_state_passenger_temp_setting",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="drive_state_active_route_traffic_minutes_delay",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="drive_state_active_route_energy_at_arrival",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="drive_state_active_route_miles_to_arrival",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.MILES,
        device_class=SensorDeviceClass.DISTANCE,
    ),
)


@dataclass(frozen=True, kw_only=True)
class TeslaFleetTimeEntityDescription(SensorEntityDescription):
    """Describes Tesla Fleet Sensor entity."""

    variance: int


VEHICLE_TIME_DESCRIPTIONS: tuple[TeslaFleetTimeEntityDescription, ...] = (
    TeslaFleetTimeEntityDescription(
        key="charge_state_minutes_to_full_charge",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        variance=4,
    ),
    TeslaFleetTimeEntityDescription(
        key="drive_state_active_route_minutes_to_arrival",
        device_class=SensorDeviceClass.TIMESTAMP,
        variance=1,
    ),
)

ENERGY_LIVE_DESCRIPTIONS: tuple[TeslaFleetSensorEntityDescription, ...] = (
    TeslaFleetSensorEntityDescription(
        key="solar_power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
    ),
    TeslaFleetSensorEntityDescription(
        key="energy_left",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    TeslaFleetSensorEntityDescription(
        key="total_pack_energy",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="percentage_charged",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        suggested_display_precision=2,
        value_fn=lambda value: value or 0,
    ),
    TeslaFleetSensorEntityDescription(
        key="battery_power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
    ),
    TeslaFleetSensorEntityDescription(
        key="load_power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
    ),
    TeslaFleetSensorEntityDescription(
        key="grid_power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
    ),
    TeslaFleetSensorEntityDescription(
        key="grid_services_power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
    ),
    TeslaFleetSensorEntityDescription(
        key="generator_power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
        entity_registry_enabled_default=False,
    ),
    TeslaFleetSensorEntityDescription(
        key="island_status",
        options=[
            "island_status_unknown",
            "on_grid",
            "off_grid",
            "off_grid_unintentional",
            "off_grid_intentional",
        ],
        device_class=SensorDeviceClass.ENUM,
    ),
)

WALL_CONNECTOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="wall_connector_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="wall_connector_fault_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="wall_connector_power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
    ),
    SensorEntityDescription(
        key="vin",
    ),
)

ENERGY_HISTORY_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = tuple(
    SensorEntityDescription(
        key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=(
            key.startswith("total") or key == "grid_energy_imported"
        ),
    )
    for key in ENERGY_HISTORY_FIELDS
)

ENERGY_INFO_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="vpp_backup_reserve_percent",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(key="version"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaFleetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Tesla Fleet sensor platform from a config entry."""
    async_add_entities(
        chain(
            (  # Add vehicles
                TeslaFleetVehicleSensorEntity(vehicle, description)
                for vehicle in entry.runtime_data.vehicles
                for description in VEHICLE_DESCRIPTIONS
            ),
            (  # Add vehicles time sensors
                TeslaFleetVehicleTimeSensorEntity(vehicle, description)
                for vehicle in entry.runtime_data.vehicles
                for description in VEHICLE_TIME_DESCRIPTIONS
            ),
            (  # Add energy site live
                TeslaFleetEnergyLiveSensorEntity(energysite, description)
                for energysite in entry.runtime_data.energysites
                for description in ENERGY_LIVE_DESCRIPTIONS
                if description.key in energysite.live_coordinator.data
                or description.key == "percentage_charged"
            ),
            (  # Add energy site history
                TeslaFleetEnergyHistorySensorEntity(energysite, description)
                for energysite in entry.runtime_data.energysites
                for description in ENERGY_HISTORY_DESCRIPTIONS
                if energysite.info_coordinator.data.get("components_battery")
                or energysite.info_coordinator.data.get("components_solar")
            ),
            (  # Add wall connectors
                TeslaFleetWallConnectorSensorEntity(energysite, wc["din"], description)
                for energysite in entry.runtime_data.energysites
                for wc in energysite.info_coordinator.data.get(
                    "components_wall_connectors", []
                )
                if "din" in wc
                for description in WALL_CONNECTOR_DESCRIPTIONS
            ),
            (  # Add energy site info
                TeslaFleetEnergyInfoSensorEntity(energysite, description)
                for energysite in entry.runtime_data.energysites
                for description in ENERGY_INFO_DESCRIPTIONS
                if description.key in energysite.info_coordinator.data
            ),
        )
    )


class TeslaFleetVehicleSensorEntity(TeslaFleetVehicleEntity, RestoreSensor):
    """Base class for Tesla Fleet vehicle metric sensors."""

    entity_description: TeslaFleetSensorEntityDescription

    def __init__(
        self,
        data: TeslaFleetVehicleData,
        description: TeslaFleetSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        super().__init__(data, description.key)

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        if self.coordinator.data.get("state") != TeslaFleetState.ONLINE:
            if (sensor_data := await self.async_get_last_sensor_data()) is not None:
                self._attr_native_value = sensor_data.native_value

    def _async_update_attrs(self) -> None:
        """Update the attributes of the sensor."""
        if self.has:
            self._attr_native_value = self.entity_description.value_fn(self._value)
        else:
            self._attr_native_value = None


class TeslaFleetVehicleTimeSensorEntity(TeslaFleetVehicleEntity, SensorEntity):
    """Base class for Tesla Fleet vehicle time sensors."""

    entity_description: TeslaFleetTimeEntityDescription

    def __init__(
        self,
        data: TeslaFleetVehicleData,
        description: TeslaFleetTimeEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        self._get_timestamp = ignore_variance(
            func=lambda value: dt_util.now() + timedelta(minutes=value),
            ignored_variance=timedelta(minutes=description.variance),
        )

        super().__init__(data, description.key)

    def _async_update_attrs(self) -> None:
        """Update the attributes of the sensor."""
        self._attr_available = isinstance(self._value, int | float) and self._value > 0
        if self._attr_available:
            self._attr_native_value = self._get_timestamp(self._value)


class TeslaFleetEnergyLiveSensorEntity(TeslaFleetEnergyLiveEntity, SensorEntity):
    """Base class for Tesla Fleet energy site metric sensors."""

    entity_description: TeslaFleetSensorEntityDescription

    def __init__(
        self,
        data: TeslaFleetEnergyData,
        description: TeslaFleetSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        super().__init__(data, description.key)

    def _async_update_attrs(self) -> None:
        """Update the attributes of the sensor."""
        self._attr_native_value = self.entity_description.value_fn(self._value)


class TeslaFleetEnergyHistorySensorEntity(TeslaFleetEnergyHistoryEntity, SensorEntity):
    """Base class for Tesla Fleet energy site metric sensors."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        data: TeslaFleetEnergyData,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        super().__init__(data, description.key)

    def _async_update_attrs(self) -> None:
        """Update the attributes of the sensor."""
        self._attr_native_value = self._value


class TeslaFleetWallConnectorSensorEntity(TeslaFleetWallConnectorEntity, SensorEntity):
    """Base class for Tesla Fleet energy site metric sensors."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        data: TeslaFleetEnergyData,
        din: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        super().__init__(
            data,
            din,
            description.key,
        )

    def _async_update_attrs(self) -> None:
        """Update the attributes of the sensor."""
        self._attr_available = not self.is_none
        self._attr_native_value = self._value


class TeslaFleetEnergyInfoSensorEntity(TeslaFleetEnergyInfoEntity, SensorEntity):
    """Base class for Tesla Fleet energy site metric sensors."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        data: TeslaFleetEnergyData,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        super().__init__(data, description.key)

    def _async_update_attrs(self) -> None:
        """Update the attributes of the sensor."""
        self._attr_available = not self.is_none
        self._attr_native_value = self._value
