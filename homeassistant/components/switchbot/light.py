"""Switchbot integration light platform."""

from __future__ import annotations

from typing import Any, cast

import switchbot
from switchbot import ColorMode as SwitchBotColorMode

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SwitchbotConfigEntry, SwitchbotDataUpdateCoordinator
from .entity import SwitchbotEntity, exception_handler

SWITCHBOT_COLOR_MODE_TO_HASS = {
    SwitchBotColorMode.RGB: ColorMode.RGB,
    SwitchBotColorMode.COLOR_TEMP: ColorMode.COLOR_TEMP,
}

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwitchbotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switchbot light."""
    async_add_entities([SwitchbotLightEntity(entry.runtime_data)])


class SwitchbotLightEntity(SwitchbotEntity, LightEntity):
    """Representation of switchbot light bulb."""

    _device: switchbot.SwitchbotBaseLight
    _attr_name = None

    def __init__(self, coordinator: SwitchbotDataUpdateCoordinator) -> None:
        """Initialize the Switchbot light."""
        super().__init__(coordinator)
        device = self._device
        self._attr_max_color_temp_kelvin = device.max_temp
        self._attr_min_color_temp_kelvin = device.min_temp
        self._attr_supported_color_modes = {
            SWITCHBOT_COLOR_MODE_TO_HASS[mode] for mode in device.color_modes
        }
        self._async_update_attrs()

    @callback
    def _async_update_attrs(self) -> None:
        """Handle updating _attr values."""
        device = self._device
        self._attr_is_on = self._device.on
        self._attr_brightness = max(0, min(255, round(device.brightness * 2.55)))
        if device.color_mode == SwitchBotColorMode.COLOR_TEMP:
            self._attr_color_temp_kelvin = device.color_temp
            self._attr_color_mode = ColorMode.COLOR_TEMP
            return
        self._attr_rgb_color = device.rgb
        self._attr_color_mode = ColorMode.RGB

    @exception_handler
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Instruct the light to turn on."""
        brightness = round(
            cast(int, kwargs.get(ATTR_BRIGHTNESS, self.brightness)) / 255 * 100
        )

        if (
            self.supported_color_modes
            and ColorMode.COLOR_TEMP in self.supported_color_modes
            and ATTR_COLOR_TEMP_KELVIN in kwargs
        ):
            kelvin = max(2700, min(6500, kwargs[ATTR_COLOR_TEMP_KELVIN]))
            await self._device.set_color_temp(brightness, kelvin)
            return
        if ATTR_RGB_COLOR in kwargs:
            rgb = kwargs[ATTR_RGB_COLOR]
            await self._device.set_rgb(brightness, rgb[0], rgb[1], rgb[2])
            return
        if ATTR_BRIGHTNESS in kwargs:
            await self._device.set_brightness(brightness)
            return
        await self._device.turn_on()

    @exception_handler
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Instruct the light to turn off."""
        await self._device.turn_off()
