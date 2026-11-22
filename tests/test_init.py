"""Tests for the 50five integration initialization and lifecycle."""

import importlib
from unittest.mock import AsyncMock, patch

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

from .const import (
    MOCK_CARD_ID,
    MOCK_PASSWORD,
    MOCK_STATION_ID,
    MOCK_USERNAME,
)


async def test_async_setup(hass: HomeAssistant) -> None:
    """Test async_setup registers services."""
    from homeassistant.core import SupportsResponse

    assert await async_setup(hass, {}) is True
    assert hass.services.has_service(DOMAIN, "start_charging")
    assert hass.services.has_service(DOMAIN, "stop_charging")
    assert hass.services.has_service(DOMAIN, "get_transactions")
    assert (
        hass.services.supports_response(DOMAIN, "get_transactions")
        is SupportsResponse.ONLY
    )


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

    with patch.object(init_mod, "FiftyFiveApiClient", side_effect=mock_client_init):
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


async def test_setup_entry_removes_legacy_hcc_enabled_sensor(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test legacy sensor.*_hcc_enabled entity is removed on setup."""
    mock_config_entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    legacy = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{MOCK_STATION_ID}_hcc_enabled",
        config_entry=mock_config_entry,
    )

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert ent_reg.async_get(legacy.entity_id) is None
    assert (
        ent_reg.async_get_entity_id(
            "binary_sensor", DOMAIN, f"{MOCK_STATION_ID}_hcc_enabled"
        )
        is not None
    )


async def test_setup_entry_removes_legacy_and_unchecked_card_switches(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test legacy single charging switches and unchecked card switches are removed on setup."""
    mock_config_entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    legacy_single = ent_reg.async_get_or_create(
        "switch",
        DOMAIN,
        f"{MOCK_STATION_ID}_charging",
        config_entry=mock_config_entry,
    )
    unchecked_card = ent_reg.async_get_or_create(
        "switch",
        DOMAIN,
        f"{MOCK_STATION_ID}_charging_NL-50F-UNCHECKED",
        config_entry=mock_config_entry,
    )

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert ent_reg.async_get(legacy_single.entity_id) is None
    assert ent_reg.async_get(unchecked_card.entity_id) is None
    assert (
        ent_reg.async_get_entity_id(
            "switch", DOMAIN, f"{MOCK_STATION_ID}_charging_{MOCK_CARD_ID}"
        )
        is not None
    )


async def test_migrate_entry_v2_1_to_v2_2(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test legacy CONF_CARD_ID is migrated to CONF_CARD_IDS at minor_version 2."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_USERNAME,
        data={
            CONF_USERNAME: MOCK_USERNAME,
            CONF_PASSWORD: MOCK_PASSWORD,
            CONF_ACCESS_TOKEN: "mock_token",
            CONF_CARD_ID: MOCK_CARD_ID,
        },
        options={CONF_CARD_ID: "NL-50F-999999-9"},
        entry_id="migrate_v2_1",
        unique_id=f"{DOMAIN}_{MOCK_USERNAME}",
        version=2,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == 2
    assert CONF_CARD_ID not in entry.data
    assert entry.data[const.CONF_CARD_IDS] == [MOCK_CARD_ID]
    assert CONF_CARD_ID not in entry.options
    assert entry.options[const.CONF_CARD_IDS] == ["NL-50F-999999-9"]


async def test_remove_entry_deletes_active_cards_store(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test removing a config entry deletes its persisted active cards storage."""
    from homeassistant.helpers.storage import Store

    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    removed_keys: list[str] = []
    orig_remove = Store.async_remove

    async def _track_remove(self: Store) -> None:
        removed_keys.append(self.key)
        await orig_remove(self)

    with patch.object(Store, "async_remove", _track_remove):
        await hass.config_entries.async_remove(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert (
        coordinator_mod.active_cards_store_key(mock_config_entry.entry_id)
        in removed_keys
    )


async def test_async_setup_registers_frontend_card(hass: HomeAssistant) -> None:
    """Test async_setup registers the static JS card when hass.http is present."""
    mock_http = AsyncMock()
    hass.http = mock_http  # type: ignore[assignment]
    try:
        with patch.object(init_mod, "add_extra_js_url") as mock_add_js:
            assert await async_setup(hass, {}) is True
    finally:
        hass.http = None  # type: ignore[assignment]

    mock_http.async_register_static_paths.assert_awaited_once()
    static_configs = mock_http.async_register_static_paths.await_args.args[0]
    assert len(static_configs) == 1
    assert static_configs[0].url_path == init_mod.FRONTEND_CARD_URL
    assert static_configs[0].path.endswith("fiftyfive-transactions-card.js")
    mock_add_js.assert_called_once_with(hass, init_mod.FRONTEND_CARD_URL)
