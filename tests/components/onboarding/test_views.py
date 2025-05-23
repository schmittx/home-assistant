"""Test the onboarding views."""

import asyncio
from collections.abc import AsyncGenerator
from http import HTTPStatus
from io import StringIO
import os
from typing import Any
from unittest.mock import ANY, DEFAULT, AsyncMock, MagicMock, Mock, patch

from hass_nabucasa.auth import CognitoAuth
from hass_nabucasa.const import STATE_CONNECTED
from hass_nabucasa.iot import CloudIoT
import pytest
from syrupy import SnapshotAssertion

from homeassistant.components import backup, onboarding
from homeassistant.components.cloud import DOMAIN as CLOUD_DOMAIN, CloudClient
from homeassistant.components.onboarding import const, views
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.backup import async_initialize_backup
from homeassistant.setup import async_setup_component

from . import mock_storage

from tests.common import (
    CLIENT_ID,
    CLIENT_REDIRECT_URI,
    MockUser,
    register_auth_provider,
)
from tests.test_util.aiohttp import AiohttpClientMocker
from tests.typing import ClientSessionGenerator


@pytest.fixture(autouse=True)
async def auth_active(hass: HomeAssistant) -> None:
    """Ensure auth is always active."""
    await register_auth_provider(hass, {"type": "homeassistant"})


@pytest.fixture(name="rpi")
async def rpi_fixture(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_supervisor
) -> None:
    """Mock core info with rpi."""
    aioclient_mock.get(
        "http://127.0.0.1/core/info",
        json={
            "result": "ok",
            "data": {"version_latest": "1.0.0", "machine": "raspberrypi3"},
        },
    )
    assert await async_setup_component(hass, "hassio", {})
    await hass.async_block_till_done()


@pytest.fixture(name="no_rpi")
async def no_rpi_fixture(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_supervisor
) -> None:
    """Mock core info with rpi."""
    aioclient_mock.get(
        "http://127.0.0.1/core/info",
        json={
            "result": "ok",
            "data": {"version_latest": "1.0.0", "machine": "odroid-n2"},
        },
    )
    assert await async_setup_component(hass, "hassio", {})
    await hass.async_block_till_done()


@pytest.fixture(name="mock_supervisor")
async def mock_supervisor_fixture(
    aioclient_mock: AiohttpClientMocker,
    store_info: AsyncMock,
    supervisor_is_connected: AsyncMock,
    resolution_info: AsyncMock,
) -> AsyncGenerator[None]:
    """Mock supervisor."""
    aioclient_mock.post("http://127.0.0.1/homeassistant/options", json={"result": "ok"})
    aioclient_mock.post("http://127.0.0.1/supervisor/options", json={"result": "ok"})
    aioclient_mock.get(
        "http://127.0.0.1/network/info",
        json={
            "result": "ok",
            "data": {
                "host_internet": True,
                "supervisor_internet": True,
            },
        },
    )
    with (
        patch.dict(os.environ, {"SUPERVISOR": "127.0.0.1"}),
        patch(
            "homeassistant.components.hassio.HassIO.get_info",
            return_value={},
        ),
        patch(
            "homeassistant.components.hassio.HassIO.get_host_info",
            return_value={},
        ),
        patch(
            "homeassistant.components.hassio.HassIO.get_supervisor_info",
            return_value={"diagnostics": True},
        ),
        patch(
            "homeassistant.components.hassio.HassIO.get_os_info",
            return_value={},
        ),
        patch(
            "homeassistant.components.hassio.HassIO.get_ingress_panels",
            return_value={"panels": {}},
        ),
        patch.dict(
            os.environ,
            {"SUPERVISOR_TOKEN": "123456"},
        ),
    ):
        yield


@pytest.fixture
def mock_default_integrations():
    """Mock the default integrations set up during onboarding."""
    with (
        patch("homeassistant.components.rpi_power.config_flow.new_under_voltage"),
        patch("homeassistant.components.rpi_power.binary_sensor.new_under_voltage"),
        patch("homeassistant.components.met.async_setup_entry", return_value=True),
        patch(
            "homeassistant.components.radio_browser.async_setup_entry",
            return_value=True,
        ),
        patch(
            "homeassistant.components.shopping_list.async_setup_entry",
            return_value=True,
        ),
    ):
        yield


async def test_onboarding_progress(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Test fetching progress."""
    mock_storage(hass_storage, {"done": ["hello"]})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client_no_auth()

    with patch.object(views, "STEPS", ["hello", "world"]):
        resp = await client.get("/api/onboarding")

    assert resp.status == 200
    data = await resp.json()
    assert len(data) == 2
    assert data[0] == {"step": "hello", "done": True}
    assert data[1] == {"step": "world", "done": False}


async def test_onboarding_user_already_done(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Test creating a new user when user step already done."""
    mock_storage(hass_storage, {"done": [views.STEP_USER]})

    with patch.object(onboarding, "STEPS", ["hello", "world"]):
        assert await async_setup_component(hass, "onboarding", {})
        await hass.async_block_till_done()

    client = await hass_client_no_auth()

    resp = await client.post(
        "/api/onboarding/users",
        json={
            "client_id": CLIENT_ID,
            "name": "Test Name",
            "username": "test-user",
            "password": "test-pass",
            "language": "en",
        },
    )

    assert resp.status == HTTPStatus.FORBIDDEN


async def test_onboarding_user(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client_no_auth: ClientSessionGenerator,
    area_registry: ar.AreaRegistry,
) -> None:
    """Test creating a new user."""
    # Create an existing area to mimic an integration creating an area
    # before onboarding is done.
    area_registry.async_create("Living Room")

    assert await async_setup_component(hass, "person", {})
    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    cur_users = len(await hass.auth.async_get_users())
    client = await hass_client_no_auth()

    resp = await client.post(
        "/api/onboarding/users",
        json={
            "client_id": CLIENT_ID,
            "name": "Test Name",
            "username": "test-user",
            "password": "test-pass",
            "language": "en",
        },
    )

    assert resp.status == 200
    assert const.STEP_USER in hass_storage[const.DOMAIN]["data"]["done"]

    data = await resp.json()
    assert "auth_code" in data

    users = await hass.auth.async_get_users()
    assert len(await hass.auth.async_get_users()) == cur_users + 1
    user = next((user for user in users if user.name == "Test Name"), None)
    assert user is not None
    assert len(user.credentials) == 1
    assert user.credentials[0].data["username"] == "test-user"
    assert len(hass.data["person"][1].async_items()) == 1

    # Validate refresh token 1
    resp = await client.post(
        "/auth/token",
        data={
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": data["auth_code"],
        },
    )

    assert resp.status == 200
    tokens = await resp.json()

    assert hass.auth.async_validate_access_token(tokens["access_token"]) is not None

    # Validate created areas
    assert len(area_registry.areas) == 3
    assert sorted(area.name for area in area_registry.async_list_areas()) == [
        "Bedroom",
        "Kitchen",
        "Living Room",
    ]


async def test_onboarding_user_invalid_name(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Test not providing name."""
    mock_storage(hass_storage, {"done": []})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client_no_auth()

    resp = await client.post(
        "/api/onboarding/users",
        json={
            "client_id": CLIENT_ID,
            "username": "test-user",
            "password": "test-pass",
            "language": "en",
        },
    )

    assert resp.status == 400


async def test_onboarding_user_race(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Test race condition on creating new user."""
    mock_storage(hass_storage, {"done": ["hello"]})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client_no_auth()

    resp1 = client.post(
        "/api/onboarding/users",
        json={
            "client_id": CLIENT_ID,
            "name": "Test 1",
            "username": "1-user",
            "password": "1-pass",
            "language": "en",
        },
    )
    resp2 = client.post(
        "/api/onboarding/users",
        json={
            "client_id": CLIENT_ID,
            "name": "Test 2",
            "username": "2-user",
            "password": "2-pass",
            "language": "es",
        },
    )

    res1, res2 = await asyncio.gather(resp1, resp2)

    assert sorted([res1.status, res2.status]) == [HTTPStatus.OK, HTTPStatus.FORBIDDEN]


async def test_onboarding_integration(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
) -> None:
    """Test finishing integration step."""
    mock_storage(hass_storage, {"done": [const.STEP_USER]})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()

    resp = await client.post(
        "/api/onboarding/integration",
        json={"client_id": CLIENT_ID, "redirect_uri": CLIENT_REDIRECT_URI},
    )

    assert resp.status == 200
    data = await resp.json()
    assert "auth_code" in data

    # Validate refresh token
    resp = await client.post(
        "/auth/token",
        data={
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": data["auth_code"],
        },
    )

    assert resp.status == 200
    assert const.STEP_INTEGRATION in hass_storage[const.DOMAIN]["data"]["done"]
    tokens = await resp.json()

    assert hass.auth.async_validate_access_token(tokens["access_token"]) is not None

    # Onboarding refresh token and new refresh token
    user = await hass.auth.async_get_user(hass_admin_user.id)
    assert len(user.refresh_tokens) == 2, user


async def test_onboarding_integration_missing_credential(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    hass_access_token: str,
) -> None:
    """Test that we fail integration step if user is missing credentials."""
    mock_storage(hass_storage, {"done": [const.STEP_USER]})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    refresh_token = hass.auth.async_validate_access_token(hass_access_token)
    refresh_token.credential = None

    client = await hass_client()

    resp = await client.post(
        "/api/onboarding/integration",
        json={"client_id": CLIENT_ID, "redirect_uri": CLIENT_REDIRECT_URI},
    )

    assert resp.status == 403


async def test_onboarding_integration_invalid_redirect_uri(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
) -> None:
    """Test finishing integration step."""
    mock_storage(hass_storage, {"done": [const.STEP_USER]})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()

    with patch(
        "homeassistant.components.auth.indieauth.fetch_redirect_uris", return_value=[]
    ):
        resp = await client.post(
            "/api/onboarding/integration",
            json={
                "client_id": CLIENT_ID,
                "redirect_uri": "http://invalid-redirect.uri",
            },
        )

    assert resp.status == 400

    # We will still mark the last step as done because there is nothing left.
    assert const.STEP_INTEGRATION in hass_storage[const.DOMAIN]["data"]["done"]

    # Only refresh token from onboarding should be there
    for user in await hass.auth.async_get_users():
        assert len(user.refresh_tokens) == 1, user


async def test_onboarding_integration_requires_auth(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Test finishing integration step."""
    mock_storage(hass_storage, {"done": [const.STEP_USER]})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client_no_auth()

    resp = await client.post(
        "/api/onboarding/integration", json={"client_id": CLIENT_ID}
    )

    assert resp.status == 401


async def test_onboarding_core_sets_up_met(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    mock_default_integrations,
) -> None:
    """Test finishing the core step."""
    mock_storage(hass_storage, {"done": [const.STEP_USER]})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()
    resp = await client.post("/api/onboarding/core_config")

    assert resp.status == 200

    await hass.async_block_till_done()
    assert len(hass.config_entries.async_entries("met")) == 1


async def test_onboarding_core_sets_up_shopping_list(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    mock_default_integrations,
) -> None:
    """Test finishing the core step set up the shopping list."""
    mock_storage(hass_storage, {"done": [const.STEP_USER]})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()
    resp = await client.post("/api/onboarding/core_config")

    assert resp.status == 200

    await hass.async_block_till_done()
    assert len(hass.config_entries.async_entries("shopping_list")) == 1


async def test_onboarding_core_sets_up_google_translate(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    mock_default_integrations,
) -> None:
    """Test finishing the core step sets up google translate."""
    mock_storage(hass_storage, {"done": [const.STEP_USER]})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()
    resp = await client.post("/api/onboarding/core_config")

    assert resp.status == 200

    await hass.async_block_till_done()
    assert len(hass.config_entries.async_entries("google_translate")) == 1


async def test_onboarding_core_sets_up_radio_browser(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    mock_default_integrations,
) -> None:
    """Test finishing the core step set up the radio browser."""
    mock_storage(hass_storage, {"done": [const.STEP_USER]})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()
    resp = await client.post("/api/onboarding/core_config")

    assert resp.status == 200

    await hass.async_block_till_done()
    assert len(hass.config_entries.async_entries("radio_browser")) == 1


async def test_onboarding_core_no_rpi_power(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    no_rpi,
    mock_default_integrations,
) -> None:
    """Test that the core step do not set up rpi_power on non RPi."""
    mock_storage(hass_storage, {"done": [const.STEP_USER]})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()

    resp = await client.post("/api/onboarding/core_config")

    assert resp.status == 200

    await hass.async_block_till_done()

    rpi_power_state = hass.states.get("binary_sensor.rpi_power_status")
    assert not rpi_power_state


async def test_onboarding_core_ensures_analytics_loaded(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    mock_default_integrations,
) -> None:
    """Test finishing the core step ensures analytics is ready."""
    mock_storage(hass_storage, {"done": [const.STEP_USER]})
    assert "analytics" not in hass.config.components

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()
    resp = await client.post("/api/onboarding/core_config")

    assert resp.status == 200

    await hass.async_block_till_done()
    assert "analytics" in hass.config.components


async def test_onboarding_analytics(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
) -> None:
    """Test finishing analytics step."""
    mock_storage(hass_storage, {"done": [const.STEP_USER]})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()

    resp = await client.post("/api/onboarding/analytics")

    assert resp.status == 200

    assert const.STEP_ANALYTICS in hass_storage[const.DOMAIN]["data"]["done"]

    resp = await client.post("/api/onboarding/analytics")
    assert resp.status == 403


async def test_onboarding_installation_type(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
) -> None:
    """Test returning installation type during onboarding."""
    mock_storage(hass_storage, {"done": []})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()

    with patch(
        "homeassistant.components.onboarding.views.async_get_system_info",
        return_value={"installation_type": "Home Assistant Core"},
    ):
        resp = await client.get("/api/onboarding/installation_type")

        assert resp.status == 200

        resp_content = await resp.json()
        assert resp_content["installation_type"] == "Home Assistant Core"


@pytest.mark.parametrize(
    ("method", "view", "kwargs"),
    [
        ("get", "installation_type", {}),
        ("get", "backup/info", {}),
        (
            "post",
            "backup/restore",
            {"json": {"backup_id": "abc123", "agent_id": "test"}},
        ),
        ("post", "backup/upload", {}),
    ],
)
async def test_onboarding_view_after_done(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    method: str,
    view: str,
    kwargs: dict[str, Any],
) -> None:
    """Test raising after onboarding."""
    mock_storage(hass_storage, {"done": [const.STEP_USER]})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()

    resp = await client.request(method, f"/api/onboarding/{view}", **kwargs)

    assert resp.status == 401


async def test_complete_onboarding(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """Test completing onboarding calls listeners."""
    listener_1 = Mock()
    onboarding.async_add_listener(hass, listener_1)
    listener_1.assert_not_called()

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    listener_2 = Mock()
    onboarding.async_add_listener(hass, listener_2)
    listener_2.assert_not_called()

    client = await hass_client()

    assert not onboarding.async_is_onboarded(hass)

    # Complete the user step
    resp = await client.post(
        "/api/onboarding/users",
        json={
            "client_id": CLIENT_ID,
            "name": "Test Name",
            "username": "test-user",
            "password": "test-pass",
            "language": "en",
        },
    )
    assert resp.status == 200
    assert not onboarding.async_is_onboarded(hass)
    listener_2.assert_not_called()

    # Complete the core config step
    resp = await client.post("/api/onboarding/core_config")
    assert resp.status == 200
    assert not onboarding.async_is_onboarded(hass)
    listener_2.assert_not_called()

    # Complete the integration step
    resp = await client.post(
        "/api/onboarding/integration",
        json={"client_id": CLIENT_ID, "redirect_uri": CLIENT_REDIRECT_URI},
    )
    assert resp.status == 200
    assert not onboarding.async_is_onboarded(hass)
    listener_2.assert_not_called()

    # Complete the analytics step
    resp = await client.post("/api/onboarding/analytics")
    assert resp.status == 200
    assert onboarding.async_is_onboarded(hass)
    listener_1.assert_not_called()  # Registered before the integration was setup
    listener_2.assert_called_once_with()

    listener_3 = Mock()
    onboarding.async_add_listener(hass, listener_3)
    listener_3.assert_called_once_with()


@pytest.mark.parametrize(
    ("method", "view", "kwargs"),
    [
        ("get", "backup/info", {}),
        (
            "post",
            "backup/restore",
            {"json": {"backup_id": "abc123", "agent_id": "test"}},
        ),
        ("post", "backup/upload", {}),
    ],
)
async def test_onboarding_backup_view_without_backup(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    method: str,
    view: str,
    kwargs: dict[str, Any],
) -> None:
    """Test interacting with backup wievs when backup integration is missing."""
    mock_storage(hass_storage, {"done": []})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()

    resp = await client.request(method, f"/api/onboarding/{view}", **kwargs)

    assert resp.status == 500
    assert await resp.json() == {"code": "backup_disabled"}


async def test_onboarding_backup_info(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    snapshot: SnapshotAssertion,
) -> None:
    """Test backup info."""
    mock_storage(hass_storage, {"done": []})

    assert await async_setup_component(hass, "onboarding", {})
    async_initialize_backup(hass)
    assert await async_setup_component(hass, "backup", {})
    await hass.async_block_till_done()

    client = await hass_client()

    backups = {
        "abc123": backup.ManagerBackup(
            addons=[backup.AddonInfo(name="Test", slug="test", version="1.0.0")],
            agents={
                "backup.local": backup.manager.AgentBackupStatus(protected=True, size=0)
            },
            backup_id="abc123",
            date="1970-01-01T00:00:00.000Z",
            database_included=True,
            extra_metadata={"instance_id": "abc123", "with_automatic_settings": True},
            folders=[backup.Folder.MEDIA, backup.Folder.SHARE],
            homeassistant_included=True,
            homeassistant_version="2024.12.0",
            name="Test",
            failed_agent_ids=[],
            with_automatic_settings=True,
        ),
        "def456": backup.ManagerBackup(
            addons=[],
            agents={
                "test.remote": backup.manager.AgentBackupStatus(protected=True, size=0)
            },
            backup_id="def456",
            date="1980-01-01T00:00:00.000Z",
            database_included=False,
            extra_metadata={
                "instance_id": "unknown_uuid",
                "with_automatic_settings": True,
            },
            folders=[backup.Folder.MEDIA, backup.Folder.SHARE],
            homeassistant_included=True,
            homeassistant_version="2024.12.0",
            name="Test 2",
            failed_agent_ids=[],
            with_automatic_settings=None,
        ),
    }

    with patch(
        "homeassistant.components.backup.manager.BackupManager.async_get_backups",
        return_value=(backups, {}),
    ):
        resp = await client.get("/api/onboarding/backup/info")

        assert resp.status == 200
        assert await resp.json() == snapshot


@pytest.mark.parametrize(
    ("params", "expected_kwargs"),
    [
        (
            {"backup_id": "abc123", "agent_id": "backup.local"},
            {
                "agent_id": "backup.local",
                "password": None,
                "restore_addons": None,
                "restore_database": True,
                "restore_folders": None,
                "restore_homeassistant": True,
            },
        ),
        (
            {
                "backup_id": "abc123",
                "agent_id": "backup.local",
                "password": "hunter2",
                "restore_addons": ["addon_1"],
                "restore_database": True,
                "restore_folders": ["media"],
            },
            {
                "agent_id": "backup.local",
                "password": "hunter2",
                "restore_addons": ["addon_1"],
                "restore_database": True,
                "restore_folders": [backup.Folder.MEDIA],
                "restore_homeassistant": True,
            },
        ),
        (
            {
                "backup_id": "abc123",
                "agent_id": "backup.local",
                "password": "hunter2",
                "restore_addons": ["addon_1", "addon_2"],
                "restore_database": False,
                "restore_folders": ["media", "share"],
            },
            {
                "agent_id": "backup.local",
                "password": "hunter2",
                "restore_addons": ["addon_1", "addon_2"],
                "restore_database": False,
                "restore_folders": [backup.Folder.MEDIA, backup.Folder.SHARE],
                "restore_homeassistant": True,
            },
        ),
    ],
)
async def test_onboarding_backup_restore(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    params: dict[str, Any],
    expected_kwargs: dict[str, Any],
) -> None:
    """Test restore backup."""
    mock_storage(hass_storage, {"done": []})

    assert await async_setup_component(hass, "onboarding", {})
    async_initialize_backup(hass)
    assert await async_setup_component(hass, "backup", {})
    await hass.async_block_till_done()

    client = await hass_client()

    with patch(
        "homeassistant.components.backup.manager.BackupManager.async_restore_backup",
    ) as mock_restore:
        resp = await client.post("/api/onboarding/backup/restore", json=params)
    assert resp.status == 200
    mock_restore.assert_called_once_with("abc123", **expected_kwargs)


@pytest.mark.parametrize(
    ("params", "restore_error", "expected_status", "expected_json", "restore_calls"),
    [
        # Missing agent_id
        (
            {"backup_id": "abc123"},
            None,
            400,
            {
                "message": "Message format incorrect: required key not provided @ data['agent_id']"
            },
            0,
        ),
        # Missing backup_id
        (
            {"agent_id": "backup.local"},
            None,
            400,
            {
                "message": "Message format incorrect: required key not provided @ data['backup_id']"
            },
            0,
        ),
        # Invalid restore_database
        (
            {
                "backup_id": "abc123",
                "agent_id": "backup.local",
                "restore_database": "yes_please",
            },
            None,
            400,
            {
                "message": "Message format incorrect: expected bool for dictionary value @ data['restore_database']"
            },
            0,
        ),
        # Invalid folder
        (
            {
                "backup_id": "abc123",
                "agent_id": "backup.local",
                "restore_folders": ["invalid"],
            },
            None,
            400,
            {
                "message": "Message format incorrect: expected Folder or one of 'share', 'addons/local', 'ssl', 'media' @ data['restore_folders'][0]"
            },
            0,
        ),
        # Wrong password
        (
            {"backup_id": "abc123", "agent_id": "backup.local"},
            backup.IncorrectPasswordError,
            400,
            {"code": "incorrect_password"},
            1,
        ),
        # Home Assistant error
        (
            {"backup_id": "abc123", "agent_id": "backup.local"},
            HomeAssistantError("Boom!"),
            400,
            {"code": "restore_failed", "message": "Boom!"},
            1,
        ),
    ],
)
async def test_onboarding_backup_restore_error(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    params: dict[str, Any],
    restore_error: Exception | None,
    expected_status: int,
    expected_json: str,
    restore_calls: int,
) -> None:
    """Test restore backup fails."""
    mock_storage(hass_storage, {"done": []})

    assert await async_setup_component(hass, "onboarding", {})
    async_initialize_backup(hass)
    assert await async_setup_component(hass, "backup", {})
    await hass.async_block_till_done()

    client = await hass_client()

    with patch(
        "homeassistant.components.backup.manager.BackupManager.async_restore_backup",
        side_effect=restore_error,
    ) as mock_restore:
        resp = await client.post("/api/onboarding/backup/restore", json=params)

    assert resp.status == expected_status
    assert await resp.json() == expected_json
    assert len(mock_restore.mock_calls) == restore_calls


@pytest.mark.parametrize(
    ("params", "restore_error", "expected_status", "expected_message", "restore_calls"),
    [
        # Unexpected error
        (
            {"backup_id": "abc123", "agent_id": "backup.local"},
            Exception("Boom!"),
            500,
            "500 Internal Server Error",
            1,
        ),
    ],
)
async def test_onboarding_backup_restore_unexpected_error(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    params: dict[str, Any],
    restore_error: Exception | None,
    expected_status: int,
    expected_message: str,
    restore_calls: int,
) -> None:
    """Test restore backup fails."""
    mock_storage(hass_storage, {"done": []})

    assert await async_setup_component(hass, "onboarding", {})
    async_initialize_backup(hass)
    assert await async_setup_component(hass, "backup", {})
    await hass.async_block_till_done()

    client = await hass_client()

    with patch(
        "homeassistant.components.backup.manager.BackupManager.async_restore_backup",
        side_effect=restore_error,
    ) as mock_restore:
        resp = await client.post("/api/onboarding/backup/restore", json=params)

    assert resp.status == expected_status
    assert (await resp.content.read()).decode().startswith(expected_message)
    assert len(mock_restore.mock_calls) == restore_calls


async def test_onboarding_backup_upload(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
) -> None:
    """Test upload backup."""
    mock_storage(hass_storage, {"done": []})

    assert await async_setup_component(hass, "onboarding", {})
    async_initialize_backup(hass)
    assert await async_setup_component(hass, "backup", {})
    await hass.async_block_till_done()

    client = await hass_client()

    with patch(
        "homeassistant.components.backup.manager.BackupManager.async_receive_backup",
        return_value="abc123",
    ) as mock_receive:
        resp = await client.post(
            "/api/onboarding/backup/upload?agent_id=backup.local",
            data={"file": StringIO("test")},
        )
    assert resp.status == 201
    assert await resp.json() == {"backup_id": "abc123"}
    mock_receive.assert_called_once_with(agent_ids=["backup.local"], contents=ANY)


@pytest.fixture(name="cloud")
async def cloud_fixture() -> AsyncGenerator[MagicMock]:
    """Mock the cloud object.

    See the real hass_nabucasa.Cloud class for how to configure the mock.
    """
    with patch(
        "homeassistant.components.cloud.Cloud", autospec=True
    ) as mock_cloud_class:
        mock_cloud = mock_cloud_class.return_value

        mock_cloud.auth = MagicMock(spec=CognitoAuth)
        mock_cloud.iot = MagicMock(
            spec=CloudIoT, last_disconnect_reason=None, state=STATE_CONNECTED
        )

        def set_up_mock_cloud(
            cloud_client: CloudClient, mode: str, **kwargs: Any
        ) -> DEFAULT:
            """Set up mock cloud with a mock constructor."""

            # Attributes set in the constructor with parameters.
            mock_cloud.client = cloud_client

            return DEFAULT

        mock_cloud_class.side_effect = set_up_mock_cloud

        # Attributes that we mock with default values.
        mock_cloud.id_token = None
        mock_cloud.is_logged_in = False

        yield mock_cloud


@pytest.fixture(name="setup_cloud")
async def setup_cloud_fixture(hass: HomeAssistant, cloud: MagicMock) -> None:
    """Fixture that sets up cloud."""
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, CLOUD_DOMAIN, {})
    await hass.async_block_till_done()


@pytest.mark.usefixtures("setup_cloud")
async def test_onboarding_cloud_forgot_password(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    cloud: MagicMock,
) -> None:
    """Test cloud forgot password."""
    mock_storage(hass_storage, {"done": []})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()

    mock_cognito = cloud.auth

    req = await client.post(
        "/api/onboarding/cloud/forgot_password", json={"email": "hello@bla.com"}
    )

    assert req.status == HTTPStatus.OK
    assert mock_cognito.async_forgot_password.call_count == 1


@pytest.mark.usefixtures("setup_cloud")
async def test_onboarding_cloud_login(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    cloud: MagicMock,
) -> None:
    """Test logging out from cloud."""
    mock_storage(hass_storage, {"done": []})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()
    req = await client.post(
        "/api/onboarding/cloud/login",
        json={"email": "my_username", "password": "my_password"},
    )

    assert req.status == HTTPStatus.OK
    data = await req.json()
    assert data == {"cloud_pipeline": None, "success": True}
    assert cloud.login.call_count == 1


@pytest.mark.usefixtures("setup_cloud")
async def test_onboarding_cloud_logout(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    cloud: MagicMock,
) -> None:
    """Test logging out from cloud."""
    mock_storage(hass_storage, {"done": []})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()
    req = await client.post("/api/onboarding/cloud/logout")

    assert req.status == HTTPStatus.OK
    data = await req.json()
    assert data == {"message": "ok"}
    assert cloud.logout.call_count == 1


@pytest.mark.usefixtures("setup_cloud")
async def test_onboarding_cloud_status(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    hass_client: ClientSessionGenerator,
    cloud: MagicMock,
) -> None:
    """Test logging out from cloud."""
    mock_storage(hass_storage, {"done": []})

    assert await async_setup_component(hass, "onboarding", {})
    await hass.async_block_till_done()

    client = await hass_client()
    req = await client.get("/api/onboarding/cloud/status")

    assert req.status == HTTPStatus.OK
    data = await req.json()
    assert data == {"logged_in": False}
