"""Define fixtures for Bosch Alarm tests."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

from bosch_alarm_mode2.panel import Area
from bosch_alarm_mode2.utils import Observable
import pytest

from homeassistant.components.bosch_alarm.const import (
    CONF_INSTALLER_CODE,
    CONF_USER_CODE,
    DOMAIN,
)
from homeassistant.const import CONF_HOST, CONF_MODEL, CONF_PASSWORD, CONF_PORT

from tests.common import MockConfigEntry


@pytest.fixture(
    params=[
        "solution_3000",
        "amax_3000",
        "b5512",
    ]
)
def model(request: pytest.FixtureRequest) -> Generator[str]:
    """Return every device."""
    return request.param


@pytest.fixture
def extra_config_entry_data(
    model: str, model_name: str, config_flow_data: dict[str, Any]
) -> dict[str, Any]:
    """Return extra config entry data."""
    return {CONF_MODEL: model_name} | config_flow_data


@pytest.fixture
def config_flow_data(model: str) -> dict[str, Any]:
    """Return extra config entry data."""
    if model == "solution_3000":
        return {CONF_USER_CODE: "1234"}
    if model == "amax_3000":
        return {CONF_INSTALLER_CODE: "1234", CONF_PASSWORD: "1234567890"}
    if model == "b5512":
        return {CONF_PASSWORD: "1234567890"}
    pytest.fail("Invalid model")


@pytest.fixture
def model_name(model: str) -> str | None:
    """Return extra config entry data."""
    return {
        "solution_3000": "Solution 3000",
        "amax_3000": "AMAX 3000",
        "b5512": "B5512 (US1B)",
    }.get(model)


@pytest.fixture
def serial_number(model: str) -> str | None:
    """Return extra config entry data."""
    if model == "solution_3000":
        return "1234567890"
    return None


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "homeassistant.components.bosch_alarm.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def area() -> Generator[Area]:
    """Define a mocked area."""
    mock = AsyncMock(spec=Area)
    mock.name = "Area1"
    mock.status_observer = AsyncMock(spec=Observable)
    mock.is_triggered.return_value = False
    mock.is_disarmed.return_value = True
    mock.is_arming.return_value = False
    mock.is_pending.return_value = False
    mock.is_part_armed.return_value = False
    mock.is_all_armed.return_value = False
    return mock


@pytest.fixture
def mock_panel(
    area: AsyncMock, model_name: str, serial_number: str | None
) -> Generator[AsyncMock]:
    """Define a fixture to set up Bosch Alarm."""
    with (
        patch(
            "homeassistant.components.bosch_alarm.Panel", autospec=True
        ) as mock_panel,
        patch("homeassistant.components.bosch_alarm.config_flow.Panel", new=mock_panel),
    ):
        client = mock_panel.return_value
        client.areas = {1: area}
        client.model = model_name
        client.firmware_version = "1.0.0"
        client.serial_number = serial_number
        client.connection_status_observer = AsyncMock(spec=Observable)
        yield client


@pytest.fixture
def mock_config_entry(
    extra_config_entry_data: dict[str, Any], serial_number: str | None
) -> MockConfigEntry:
    """Mock config entry for bosch alarm."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=serial_number,
        entry_id="01JQ917ACKQ33HHM7YCFXYZX51",
        data={
            CONF_HOST: "0.0.0.0",
            CONF_PORT: 7700,
            CONF_MODEL: "bosch_alarm_test_data.model",
        }
        | extra_config_entry_data,
    )
