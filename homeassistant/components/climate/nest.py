"""
Support for Nest thermostats.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/climate.nest/
"""
import logging

import voluptuous as vol

from homeassistant.components.nest import DATA_NEST
from homeassistant.components.climate import (
    STATE_AUTO, STATE_COOL, STATE_HEAT, STATE_IDLE, ClimateDevice,
    PLATFORM_SCHEMA, ATTR_TARGET_TEMP_HIGH, ATTR_TARGET_TEMP_LOW,
    ATTR_TEMPERATURE)
from homeassistant.const import (
    TEMP_CELSIUS, TEMP_FAHRENHEIT,
    CONF_SCAN_INTERVAL, STATE_ON, STATE_OFF, STATE_UNKNOWN)

DEPENDENCIES = ['nest']
_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_SCAN_INTERVAL):
        vol.All(vol.Coerce(int), vol.Range(min=1)),
})

STATE_ECO = 'eco'
STATE_HEAT_COOL = 'heat-cool'
STATE_HEATING = 'heating'
STATE_COOLING = 'cooling'


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Nest thermostat."""
    if discovery_info is None:
        return

    temp_unit = hass.config.units.temperature_unit

    add_devices(
        [NestThermostat(structure, device, temp_unit)
         for structure, device in hass.data[DATA_NEST].thermostats()],
        True
    )


class NestThermostat(ClimateDevice):
    """Representation of a Nest thermostat."""

    def __init__(self, structure, device, temp_unit):
        """Initialize the thermostat."""
        self._unit = temp_unit
        self.structure = structure
        self.device = device
        self._fan_list = [STATE_ON, STATE_AUTO]

        # Not all nest devices support cooling and heating remove unused
        self._operation_list = [STATE_OFF]

        # Add supported nest thermostat features
        if self.device.can_heat:
            self._operation_list.append(STATE_HEAT)

        if self.device.can_cool:
            self._operation_list.append(STATE_COOL)

        if self.device.can_heat and self.device.can_cool:
            self._operation_list.append(STATE_AUTO)

        self._operation_list.append(STATE_ECO)

        # feature of device
        self._has_fan = self.device.has_fan

        # data attributes
        self._away = None
        self._eco = None
        self._location = None
        self._name = None
        self._humidity = None
        self._target_temperature = None
        self._temperature = None
        self._temperature_scale = None
        self._operation_mode = None
        self._current_operation = None
        self._fan = None
        self._eco_temperature = None
        self._is_locked = None
        self._locked_temperature = None
        self._min_temperature = None
        self._max_temperature = None
        self._hvac_state = None

    @property
    def name(self):
        """Return the name of the nest, if any."""
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._temperature_scale

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._temperature

    @property
    def operation_mode(self):
        """Return current operation mode ie. auto, heat, cool, off."""
        if self._operation_mode in [STATE_HEAT, STATE_COOL, STATE_OFF,
                                    STATE_ECO]:
            return self._operation_mode
        elif self._operation_mode == STATE_HEAT_COOL:
            return STATE_AUTO
        return STATE_UNKNOWN

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        if self._current_operation in [STATE_OFF, STATE_IDLE]:
            return self._current_operation
        elif self._current_operation == STATE_HEATING:
            return STATE_HEAT
        elif self._current_operation == STATE_COOLING:
            return STATE_COOL
        elif self._current_operation == STATE_HEAT_COOL:
            return STATE_AUTO
        return STATE_UNKNOWN

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        if (self._operation_mode != STATE_HEAT_COOL and
                not self.is_away_mode_on):
            return self._target_temperature
        elif (self._operation_mode == STATE_HEAT_COOL and
              not self.is_away_mode_on):
            return ((self._target_temperature[0] +
                     self._target_temperature[1]) / 2)
        return None

    @property
    def target_temperature_low(self):
        """Return the lower bound temperature we try to reach."""
        if (self.is_away_mode_on or self._operation_mode == STATE_ECO) and \
                self._eco_temperature[0]:
            # eco_temperature is always a low, high tuple
            return self._eco_temperature[0]
        if self._operation_mode == STATE_HEAT_COOL:
            return self._target_temperature[0]
        return None

    @property
    def target_temperature_high(self):
        """Return the upper bound temperature we try to reach."""
        if (self.is_away_mode_on or self._operation_mode == STATE_ECO) and \
                self._eco_temperature[1]:
            # eco_temperature is always a low, high tuple
            return self._eco_temperature[1]
        if self._operation_mode == STATE_HEAT_COOL:
            return self._target_temperature[1]
        return None

    @property
    def is_away_mode_on(self):
        """Return if away mode is on."""
        return self._away

    @property
    def is_eco_mode_on(self):
        """Return if economy mode is on."""
        return self._eco

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        target_temp_low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        target_temp_high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        if self._operation_mode == STATE_HEAT_COOL:
            if target_temp_low is not None and target_temp_high is not None:
                temp = (target_temp_low, target_temp_high)
        else:
            temp = kwargs.get(ATTR_TEMPERATURE)
        _LOGGER.debug("Nest set_temperature-output-value=%s", temp)
        self.device.target = temp

    def set_operation_mode(self, operation_mode):
        """Set operation mode."""
        if operation_mode in [STATE_HEAT, STATE_COOL, STATE_OFF, STATE_ECO]:
            device_mode = operation_mode
        elif operation_mode == STATE_AUTO:
            device_mode = STATE_HEAT_COOL
        self.device.mode = device_mode

    @property
    def operation_list(self):
        """List of available operation modes."""
        return self._operation_list

    def turn_away_mode_on(self):
        """Turn away on."""
        self.structure.away = True

    def turn_away_mode_off(self):
        """Turn away off."""
        self.structure.away = False

    @property
    def current_fan_mode(self):
        """Return whether the fan is on."""
        if self._has_fan:
            # Return whether the fan is on
            return STATE_ON if self._fan else STATE_AUTO
        # No Fan available so disable slider
        return None

    @property
    def fan_list(self):
        """List of available fan modes."""
        return self._fan_list

    def set_fan_mode(self, fan):
        """Turn fan on/off."""
        self.device.fan = fan.lower()

    @property
    def min_temp(self):
        """Identify min_temp in Nest API or defaults if not available."""
        return self._min_temperature

    @property
    def max_temp(self):
        """Identify max_temp in Nest API or defaults if not available."""
        return self._max_temperature

    @property
    def current_humidity(self):
        """Return the current humidity."""
        return self._humidity

    def update(self):
        """Cache value from Python-nest."""
        self._location = self.device.where
        self._name = self.device.name
        self._humidity = self.device.humidity
        self._temperature = self.device.temperature
        self._operation_mode = self.device.mode
        self._current_operation = self.device.hvac_state
        self._target_temperature = self.device.target
        self._fan = self.device.fan
        self._away = self.structure.away == 'away'
        self._eco = self.device.has_leaf
        self._eco_temperature = self.device.eco_temperature
        self._locked_temperature = self.device.locked_temperature
        self._min_temperature = self.device.min_temperature
        self._max_temperature = self.device.max_temperature
        self._is_locked = self.device.is_locked
        self._hvac_state = self.device.hvac_state
        if self.device.temperature_scale == 'C':
            self._temperature_scale = TEMP_CELSIUS
        else:
            self._temperature_scale = TEMP_FAHRENHEIT
