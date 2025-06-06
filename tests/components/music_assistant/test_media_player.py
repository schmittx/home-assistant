"""Test Music Assistant media player entities."""

from unittest.mock import MagicMock, call

from music_assistant_models.constants import PLAYER_CONTROL_NONE
from music_assistant_models.enums import (
    EventType,
    MediaType,
    PlayerFeature,
    QueueOption,
)
from music_assistant_models.media_items import Track
import pytest
from syrupy.assertion import SnapshotAssertion
from syrupy.filters import paths

from homeassistant.components.media_player import (
    ATTR_GROUP_MEMBERS,
    ATTR_INPUT_SOURCE,
    ATTR_MEDIA_ENQUEUE,
    ATTR_MEDIA_REPEAT,
    ATTR_MEDIA_SEEK_POSITION,
    ATTR_MEDIA_SHUFFLE,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    SERVICE_CLEAR_PLAYLIST,
    SERVICE_JOIN,
    SERVICE_SELECT_SOURCE,
    SERVICE_UNJOIN,
    MediaPlayerEntityFeature,
)
from homeassistant.components.music_assistant.const import DOMAIN
from homeassistant.components.music_assistant.media_player import (
    ATTR_ALBUM,
    ATTR_ANNOUNCE_VOLUME,
    ATTR_ARTIST,
    ATTR_AUTO_PLAY,
    ATTR_MEDIA_ID,
    ATTR_MEDIA_TYPE,
    ATTR_RADIO_MODE,
    ATTR_SOURCE_PLAYER,
    ATTR_URL,
    ATTR_USE_PRE_ANNOUNCE,
    SERVICE_GET_QUEUE,
    SERVICE_PLAY_ANNOUNCEMENT,
    SERVICE_PLAY_MEDIA_ADVANCED,
    SERVICE_TRANSFER_QUEUE,
)
from homeassistant.config_entries import HomeAssistantError
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_MEDIA_NEXT_TRACK,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_MEDIA_PREVIOUS_TRACK,
    SERVICE_MEDIA_STOP,
    SERVICE_REPEAT_SET,
    SERVICE_SHUFFLE_SET,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    SERVICE_VOLUME_DOWN,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    SERVICE_VOLUME_UP,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .common import (
    setup_integration_from_fixtures,
    snapshot_music_assistant_entities,
    trigger_subscription_callback,
)

from tests.common import AsyncMock

MOCK_TRACK = Track(
    item_id="1",
    provider="library",
    name="Test Track",
    provider_mappings={},
)


async def test_media_player(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    music_assistant_client: MagicMock,
) -> None:
    """Test media player."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    snapshot_music_assistant_entities(
        hass, entity_registry, snapshot, Platform.MEDIA_PLAYER
    )


async def test_media_player_basic_actions(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player entity basic actions (play/stop/pause etc.)."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state
    for action, cmd in (
        (SERVICE_MEDIA_PLAY, "play"),
        (SERVICE_MEDIA_PAUSE, "pause"),
        (SERVICE_MEDIA_STOP, "stop"),
        (SERVICE_MEDIA_PREVIOUS_TRACK, "previous"),
        (SERVICE_MEDIA_NEXT_TRACK, "next"),
        (SERVICE_VOLUME_UP, "volume_up"),
        (SERVICE_VOLUME_DOWN, "volume_down"),
    ):
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            action,
            {
                ATTR_ENTITY_ID: entity_id,
            },
            blocking=True,
        )

        assert music_assistant_client.send_command.call_count == 1
        assert music_assistant_client.send_command.call_args == call(
            f"players/cmd/{cmd}", player_id=mass_player_id
        )
        music_assistant_client.send_command.reset_mock()


async def test_media_player_seek_action(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player entity seek action."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        "media_seek",
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_MEDIA_SEEK_POSITION: 100,
        },
        blocking=True,
    )

    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "players/cmd/seek", player_id=mass_player_id, position=100
    )


async def test_media_player_volume_set_action(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player entity volume_set action."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_VOLUME_SET,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_MEDIA_VOLUME_LEVEL: 0.5,
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "players/cmd/volume_set", player_id=mass_player_id, volume_level=50
    )


async def test_media_player_volume_mute_action(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player entity volume_mute action."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_VOLUME_MUTE,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_MEDIA_VOLUME_MUTED: True,
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "players/cmd/volume_mute", player_id=mass_player_id, muted=True
    )


async def test_media_player_turn_on_off_actions(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player entity turn_on/turn_off actions."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state
    for action, pwr in (
        (SERVICE_TURN_ON, True),
        (SERVICE_TURN_OFF, False),
    ):
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            action,
            {
                ATTR_ENTITY_ID: entity_id,
            },
            blocking=True,
        )
        assert music_assistant_client.send_command.call_count == 1
        assert music_assistant_client.send_command.call_args == call(
            "players/cmd/power", player_id=mass_player_id, powered=pwr
        )
        music_assistant_client.send_command.reset_mock()


async def test_media_player_shuffle_set_action(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player entity shuffle_set action."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_SHUFFLE_SET,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_MEDIA_SHUFFLE: True,
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "player_queues/shuffle", queue_id=mass_player_id, shuffle_enabled=True
    )


async def test_media_player_repeat_set_action(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player entity repeat_set action."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_REPEAT_SET,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_MEDIA_REPEAT: "one",
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "player_queues/repeat", queue_id=mass_player_id, repeat_mode="one"
    )


async def test_media_player_join_players_action(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player entity join_players action."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_JOIN,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_GROUP_MEMBERS: ["media_player.my_super_test_player_2"],
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "players/cmd/group_many",
        target_player=mass_player_id,
        child_player_ids=["00:00:00:00:00:02"],
    )
    # test again with invalid source player
    music_assistant_client.send_command.reset_mock()
    with pytest.raises(
        HomeAssistantError, match="Entity media_player.blah_blah not found"
    ):
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_JOIN,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_GROUP_MEMBERS: ["media_player.blah_blah"],
            },
            blocking=True,
        )


async def test_media_player_unjoin_player_action(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player entity unjoin player action."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_UNJOIN,
        {
            ATTR_ENTITY_ID: entity_id,
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "players/cmd/ungroup", player_id=mass_player_id
    )


async def test_media_player_clear_playlist_action(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player entity clear_playlist action."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_CLEAR_PLAYLIST,
        {
            ATTR_ENTITY_ID: entity_id,
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "player_queues/clear", queue_id=mass_player_id
    )


async def test_media_player_play_media_action(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player (advanced) play_media action."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state

    # test simple play_media call with URI as media_id and no media type
    await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY_MEDIA_ADVANCED,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_MEDIA_ID: "spotify://track/1234",
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "player_queues/play_media",
        queue_id=mass_player_id,
        media=["spotify://track/1234"],
        option=None,
        radio_mode=False,
        start_item=None,
    )

    # test simple play_media call with URI and enqueue specified
    music_assistant_client.send_command.reset_mock()
    await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY_MEDIA_ADVANCED,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_MEDIA_ID: "spotify://track/1234",
            ATTR_MEDIA_ENQUEUE: "add",
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "player_queues/play_media",
        queue_id=mass_player_id,
        media=["spotify://track/1234"],
        option=QueueOption.ADD,
        radio_mode=False,
        start_item=None,
    )

    # test basic play_media call with URL and radio mode specified
    music_assistant_client.send_command.reset_mock()
    await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY_MEDIA_ADVANCED,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_MEDIA_ID: "spotify://track/1234",
            ATTR_RADIO_MODE: True,
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "player_queues/play_media",
        queue_id=mass_player_id,
        media=["spotify://track/1234"],
        option=None,
        radio_mode=True,
        start_item=None,
    )

    # test play_media call with media id and media type specified
    music_assistant_client.send_command.reset_mock()
    music_assistant_client.music.get_item = AsyncMock(return_value=MOCK_TRACK)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY_MEDIA_ADVANCED,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_MEDIA_ID: "1",
            ATTR_MEDIA_TYPE: "track",
        },
        blocking=True,
    )
    assert music_assistant_client.music.get_item.call_count == 1
    assert music_assistant_client.music.get_item.call_args == call(
        MediaType.TRACK, "1", "library"
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "player_queues/play_media",
        queue_id=mass_player_id,
        media=[MOCK_TRACK.uri],
        option=None,
        radio_mode=False,
        start_item=None,
    )

    # test play_media call by name
    music_assistant_client.send_command.reset_mock()
    music_assistant_client.music.get_item_by_name = AsyncMock(return_value=MOCK_TRACK)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY_MEDIA_ADVANCED,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_MEDIA_ID: "test",
            ATTR_ARTIST: "artist",
            ATTR_ALBUM: "album",
        },
        blocking=True,
    )
    assert music_assistant_client.music.get_item_by_name.call_count == 1
    assert music_assistant_client.music.get_item_by_name.call_args == call(
        name="test",
        artist="artist",
        album="album",
        media_type=None,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "player_queues/play_media",
        queue_id=mass_player_id,
        media=[MOCK_TRACK.uri],
        option=None,
        radio_mode=False,
        start_item=None,
    )


async def test_media_player_play_announcement_action(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player play_announcement action."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state
    await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY_ANNOUNCEMENT,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_URL: "http://blah.com/announcement.mp3",
            ATTR_USE_PRE_ANNOUNCE: True,
            ATTR_ANNOUNCE_VOLUME: 50,
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "players/cmd/play_announcement",
        player_id=mass_player_id,
        url="http://blah.com/announcement.mp3",
        use_pre_announce=True,
        volume_level=50,
    )


async def test_media_player_transfer_queue_action(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player transfer_queu action."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    state = hass.states.get(entity_id)
    assert state
    await hass.services.async_call(
        DOMAIN,
        SERVICE_TRANSFER_QUEUE,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_SOURCE_PLAYER: "media_player.my_super_test_player_2",
            ATTR_AUTO_PLAY: True,
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "player_queues/transfer",
        source_queue_id="00:00:00:00:00:02",
        target_queue_id="00:00:00:00:00:01",
        auto_play=True,
        require_schema=25,
    )
    # test again with invalid source player
    music_assistant_client.send_command.reset_mock()
    with pytest.raises(HomeAssistantError, match="Source player not available."):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_TRANSFER_QUEUE,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_SOURCE_PLAYER: "media_player.blah_blah",
            },
            blocking=True,
        )
    # test again with no source player specified (which picks first playing playerqueue)
    music_assistant_client.send_command.reset_mock()
    await hass.services.async_call(
        DOMAIN,
        SERVICE_TRANSFER_QUEUE,
        {
            ATTR_ENTITY_ID: entity_id,
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "player_queues/transfer",
        source_queue_id="test_group_player_1",
        target_queue_id="00:00:00:00:00:01",
        auto_play=None,
        require_schema=25,
    )


async def test_media_player_get_queue_action(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
    snapshot: SnapshotAssertion,
) -> None:
    """Test media_player get_queue action."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_group_player_1"
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_QUEUE,
        {
            ATTR_ENTITY_ID: entity_id,
        },
        blocking=True,
        return_response=True,
    )
    # no call is made, this info comes from the cached queue data
    assert music_assistant_client.send_command.call_count == 0
    assert response == snapshot(exclude=paths(f"{entity_id}.elapsed_time"))


async def test_media_player_select_source_action(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test media_player entity select source action."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_SELECT_SOURCE,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_INPUT_SOURCE: "Line-In",
        },
        blocking=True,
    )
    assert music_assistant_client.send_command.call_count == 1
    assert music_assistant_client.send_command.call_args == call(
        "players/cmd/select_source", player_id=mass_player_id, source="linein"
    )


async def test_media_player_supported_features(
    hass: HomeAssistant,
    music_assistant_client: MagicMock,
) -> None:
    """Test if media_player entity supported features are cortrectly (re)mapped."""
    await setup_integration_from_fixtures(hass, music_assistant_client)
    entity_id = "media_player.test_player_1"
    mass_player_id = "00:00:00:00:00:01"
    state = hass.states.get(entity_id)
    assert state
    expected_features = (
        MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.SHUFFLE_SET
        | MediaPlayerEntityFeature.REPEAT_SET
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.CLEAR_PLAYLIST
        | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.MEDIA_ENQUEUE
        | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
        | MediaPlayerEntityFeature.SEEK
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.GROUPING
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SEARCH_MEDIA
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )
    assert state.attributes["supported_features"] == expected_features
    # remove power control capability from player, trigger subscription callback
    # and check if the supported features got updated
    music_assistant_client.players._players[
        mass_player_id
    ].power_control = PLAYER_CONTROL_NONE
    await trigger_subscription_callback(
        hass, music_assistant_client, EventType.PLAYER_CONFIG_UPDATED, mass_player_id
    )
    expected_features &= ~MediaPlayerEntityFeature.TURN_ON
    expected_features &= ~MediaPlayerEntityFeature.TURN_OFF
    state = hass.states.get(entity_id)
    assert state
    assert state.attributes["supported_features"] == expected_features

    # remove volume control capability from player, trigger subscription callback
    # and check if the supported features got updated
    music_assistant_client.players._players[
        mass_player_id
    ].volume_control = PLAYER_CONTROL_NONE
    await trigger_subscription_callback(
        hass, music_assistant_client, EventType.PLAYER_CONFIG_UPDATED, mass_player_id
    )
    expected_features &= ~MediaPlayerEntityFeature.VOLUME_SET
    expected_features &= ~MediaPlayerEntityFeature.VOLUME_STEP
    state = hass.states.get(entity_id)
    assert state
    assert state.attributes["supported_features"] == expected_features

    # remove mute control capability from player, trigger subscription callback
    # and check if the supported features got updated
    music_assistant_client.players._players[
        mass_player_id
    ].mute_control = PLAYER_CONTROL_NONE
    await trigger_subscription_callback(
        hass, music_assistant_client, EventType.PLAYER_CONFIG_UPDATED, mass_player_id
    )
    expected_features &= ~MediaPlayerEntityFeature.VOLUME_MUTE
    state = hass.states.get(entity_id)
    assert state
    assert state.attributes["supported_features"] == expected_features

    # remove grouping capability from player, trigger subscription callback
    # and check if the supported features got updated
    music_assistant_client.players._players[mass_player_id].supported_features.remove(
        PlayerFeature.SET_MEMBERS
    )
    await trigger_subscription_callback(
        hass, music_assistant_client, EventType.PLAYER_CONFIG_UPDATED, mass_player_id
    )
    expected_features &= ~MediaPlayerEntityFeature.GROUPING
    state = hass.states.get(entity_id)
    assert state
    assert state.attributes["supported_features"] == expected_features
