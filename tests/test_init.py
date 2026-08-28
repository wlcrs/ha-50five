"""Tests for the 50five integration initialization, lifecycle, and services."""

import importlib
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

const = importlib.import_module("custom_components.50five.const")
coordinator_mod = importlib.import_module("custom_components.50five.coordinator")
init_mod = importlib.import_module("custom_components.50five")

CONF_ACCESS_TOKEN = const.CONF_ACCESS_TOKEN
CONF_CARD_ID = const.CONF_CARD_ID
CONF_CUSTOMER_ID = const.CONF_CUSTOMER_ID
CONF_DEVICE_ID = const.CONF_DEVICE_ID
CONF_TOKEN_EXPIRES_AT = const.CONF_TOKEN_EXPIRES_AT
DOMAIN = const.DOMAIN
FiftyFiveCoordinator = coordinator_mod.FiftyFiveCoordinator
async_setup = init_mod.async_setup
_resolve_fiftyfive_target = init_mod._resolve_fiftyfive_target

from .const import (
    MOCK_CARD_ID,
    MOCK_PASSWORD,
    MOCK_STATION_ID,
    MOCK_USERNAME,
)


async def test_async_setup(hass: HomeAssistant) -> None:
    """Test async_setup registers services."""
    assert await async_setup(hass, {}) is True
    assert hass.services.has_service(DOMAIN, "start_charging")
    assert hass.services.has_service(DOMAIN, "stop_charging")


async def test_setup_and_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test setup and unload of a config entry."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert isinstance(mock_config_entry.runtime_data, FiftyFiveCoordinator)

    # Test unload
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_entry_generates_device_id(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test setup entry generates device_id if missing."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_USERNAME,
        data={
            CONF_USERNAME: MOCK_USERNAME,
            CONF_PASSWORD: MOCK_PASSWORD,
            CONF_ACCESS_TOKEN: "mock_token",
            CONF_CARD_ID: MOCK_CARD_ID,
        },
        entry_id="test_entry_no_device",
        unique_id=f"{DOMAIN}_{MOCK_USERNAME}",
        version=2,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert CONF_DEVICE_ID in entry.data
    assert len(entry.data[CONF_DEVICE_ID]) > 0


async def test_token_refreshed_callback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test token refresh callback updates config entry data."""
    mock_config_entry.add_to_hass(hass)

    captured_callbacks = []

    def mock_client_init(*args, **kwargs):
        captured_callbacks.append(kwargs.get("on_token_refreshed"))
        client = AsyncMock()
        client.username = MOCK_USERNAME
        client.authenticate = AsyncMock(return_value=True)
        client.get_customer_charge_stations = AsyncMock(return_value=[])
        client.get_active_transaction = AsyncMock(return_value=None)
        return client

    with patch.object(
        init_mod, "FiftyFiveApiClient", side_effect=mock_client_init
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert len(captured_callbacks) > 0
    on_token_refreshed = captured_callbacks[0]
    assert on_token_refreshed is not None

    # Simulate token refreshed callback
    on_token_refreshed("new_token_123", "2030-01-01T00:00:00Z", "cust_new_456")

    assert mock_config_entry.data[CONF_ACCESS_TOKEN] == "new_token_123"
    assert mock_config_entry.data[CONF_TOKEN_EXPIRES_AT] == "2030-01-01T00:00:00Z"
    assert mock_config_entry.data[CONF_CUSTOMER_ID] == "cust_new_456"


async def test_update_options_listener(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test options update triggers reload."""
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    with patch.object(
        hass.config_entries, "async_reload", return_value=True
    ) as mock_reload:
        hass.config_entries.async_update_entry(
            mock_config_entry,
            options={CONF_CARD_ID: "NL-50F-NEW-1"},
        )
        await hass.async_block_till_done()
        mock_reload.assert_called_once_with(mock_config_entry.entry_id)


async def test_services_start_stop_charging(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test 50five.start_charging and 50five.stop_charging custom services."""
    await async_setup(hass, {})
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # The charging switch should have been created
    entity_id = "switch.home_charger_single_charge_with_card_nl_50f_123456_7"
    state = hass.states.get(entity_id)
    assert state is not None

    # Call start_charging service with specific card_id
    await hass.services.async_call(
        DOMAIN,
        "start_charging",
        {"entity_id": entity_id, "card_id": "CUSTOM-CARD-99"},
        blocking=True,
    )
    mock_api_client.start_charging.assert_called_with(
        MOCK_STATION_ID, "ch_999_1", "CUSTOM-CARD-99"
    )

    # Call stop_charging service
    await hass.services.async_call(
        DOMAIN,
        "stop_charging",
        {"entity_id": entity_id},
        blocking=True,
    )
    mock_api_client.stop_charging.assert_called_with(MOCK_STATION_ID, "ch_999_1")


async def test_services_target_resolution_edge_cases(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test service call handling with invalid or missing targets."""
    await async_setup(hass, {})
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # 1. Non-existent entity
    target = _resolve_fiftyfive_target(hass, "switch.non_existent")
    assert target is None

    # 2. Entity from another config entry / registry entry without config_entry_id
    entity_registry = er.async_get(hass)
    orphan_entry = entity_registry.async_get_or_create(
        "switch", DOMAIN, "orphan_unique_id"
    )
    target = _resolve_fiftyfive_target(hass, orphan_entry.entity_id)
    assert target is None

    # 3. Entry without runtime_data
    no_runtime_entry = MockConfigEntry(domain=DOMAIN, entry_id="no_runtime", version=2)
    no_runtime_entry.add_to_hass(hass)
    entity_no_runtime = entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        "unique_no_runtime",
        config_entry=no_runtime_entry,
    )
    assert _resolve_fiftyfive_target(hass, entity_no_runtime.entity_id) is None

    # 4. Empty unique_id / spot_id resolve failure
    entity_empty_id = entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        "",
        config_entry=mock_config_entry,
    )
    assert _resolve_fiftyfive_target(hass, entity_empty_id.entity_id) is None


async def test_services_with_device_id_target(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test 50five.start_charging and 50five.stop_charging targeting a device."""
    from homeassistant.helpers import device_registry as dr

    await async_setup(hass, {})
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get("sensor.home_charger_single_status")
    assert entity is not None
    assert entity.device_id is not None
    device_id = entity.device_id

    # Call start_charging with device_id and default card fallback
    mock_api_client.start_charging.reset_mock()
    await hass.services.async_call(
        DOMAIN,
        "start_charging",
        {"device_id": [device_id]},
        blocking=True,
    )
    mock_api_client.start_charging.assert_called_once_with(
        MOCK_STATION_ID, "ch_999_1", MOCK_CARD_ID
    )

    # Call stop_charging with device_id
    mock_api_client.stop_charging.reset_mock()
    await hass.services.async_call(
        DOMAIN,
        "stop_charging",
        {"device_id": [device_id]},
        blocking=True,
    )
    mock_api_client.stop_charging.assert_called_once_with(MOCK_STATION_ID, "ch_999_1")


async def test_services_with_sensor_entity_target(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test 50five.start_charging targeting a sensor entity resolves channel ID properly."""
    await async_setup(hass, {})
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Target the station status sensor
    sensor_id = "sensor.home_charger_single_status"
    assert hass.states.get(sensor_id) is not None

    mock_api_client.start_charging.reset_mock()
    await hass.services.async_call(
        DOMAIN,
        "start_charging",
        {"entity_id": sensor_id},
        blocking=True,
    )
    mock_api_client.start_charging.assert_called_once_with(
        MOCK_STATION_ID, "ch_999_1", MOCK_CARD_ID
    )

