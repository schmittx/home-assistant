"""Tests for the AirGradient select platform."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from airgradient import AirGradientConnectionError, AirGradientError, Config
from freezegun.api import FrozenDateTimeFactory
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.airgradient.const import DOMAIN
from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_OPTION, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from . import setup_integration

from tests.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_load_fixture,
    snapshot_platform,
)


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_all_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    airgradient_devices: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test all entities."""
    with patch("homeassistant.components.airgradient.PLATFORMS", [Platform.SELECT]):
        await setup_integration(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_setting_value(
    hass: HomeAssistant,
    mock_airgradient_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setting value."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: "select.airgradient_configuration_source",
            ATTR_OPTION: "local",
        },
        blocking=True,
    )
    mock_airgradient_client.set_configuration_control.assert_called_once_with("local")
    assert mock_airgradient_client.get_config.call_count == 2


async def test_cloud_creates_no_number(
    hass: HomeAssistant,
    mock_cloud_airgradient_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test cloud configuration control."""
    with patch("homeassistant.components.airgradient.PLATFORMS", [Platform.SELECT]):
        await setup_integration(hass, mock_config_entry)

    assert len(hass.states.async_all()) == 1

    mock_cloud_airgradient_client.get_config.return_value = Config.from_json(
        await async_load_fixture(hass, "get_config_local.json", DOMAIN)
    )

    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert len(hass.states.async_all()) == 7

    mock_cloud_airgradient_client.get_config.return_value = Config.from_json(
        await async_load_fixture(hass, "get_config_cloud.json", DOMAIN)
    )

    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert len(hass.states.async_all()) == 1


@pytest.mark.parametrize(
    ("exception", "error_message"),
    [
        (
            AirGradientConnectionError("Something happened"),
            "An error occurred while communicating with the Airgradient device: Something happened",
        ),
        (
            AirGradientError("Something else happened"),
            "An unknown error occurred while communicating with the Airgradient device: Something else happened",
        ),
    ],
)
async def test_exception_handling(
    hass: HomeAssistant,
    mock_airgradient_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    exception: Exception,
    error_message: str,
) -> None:
    """Test exception handling."""
    await setup_integration(hass, mock_config_entry)

    mock_airgradient_client.set_configuration_control.side_effect = exception
    with pytest.raises(HomeAssistantError, match=error_message):
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {
                ATTR_ENTITY_ID: "select.airgradient_configuration_source",
                ATTR_OPTION: "local",
            },
            blocking=True,
        )
