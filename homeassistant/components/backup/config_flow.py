"""Config flow for Home Assistant Backup integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class BackupConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Home Assistant Backup."""

    VERSION = 1

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        return self.async_create_entry(title="Backup", data={})
