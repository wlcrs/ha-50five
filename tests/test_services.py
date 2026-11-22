"""Tests for 50five services."""

from datetime import UTC, datetime
import importlib
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

const = importlib.import_module("custom_components.50five.const")
init_mod = importlib.import_module("custom_components.50five")
services_mod = importlib.import_module("custom_components.50five.services")

DOMAIN = const.DOMAIN
async_setup = init_mod.async_setup
_resolve_fiftyfive_target = services_mod._resolve_fiftyfive_target

from .const import MOCK_CARD_ID, MOCK_STATION_ID


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


async def test_services_raise_validation_error_when_no_valid_targets(
    hass: HomeAssistant,
) -> None:
    """Test services raise ServiceValidationError when no valid targets match."""
    await async_setup(hass, {})

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "start_charging",
            {"entity_id": "switch.non_existent"},
            blocking=True,
        )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "stop_charging",
            {"entity_id": "switch.non_existent"},
            blocking=True,
        )


async def test_service_start_charging_sets_coordinator_optimistic_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test 50five.start_charging sets optimistic state for the matching card switch."""
    await async_setup(hass, {})
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    card1_entity = "switch.office_charger_dual_ch_2_charge_with_card_nl_50f_123456_7"
    card2_entity = "switch.office_charger_dual_ch_2_charge_with_card_nl_50f_999999_9"
    assert hass.states.get(card1_entity).state == "off"
    assert hass.states.get(card2_entity).state == "off"

    # Calling start_charging on card1_entity with explicit card_id for card 2 turns on card 2 only
    await hass.services.async_call(
        DOMAIN,
        "start_charging",
        {"entity_id": card1_entity, "card_id": "NL-50F-999999-9"},
        blocking=True,
    )
    assert hass.states.get(card2_entity).state == "on"
    assert hass.states.get(card1_entity).state == "off"

    # Calling start_charging targeting card1_entity without card_id uses card 1
    await hass.services.async_call(
        DOMAIN,
        "start_charging",
        {"entity_id": card1_entity},
        blocking=True,
    )
    assert hass.states.get(card1_entity).state == "on"
    assert hass.states.get(card2_entity).state == "off"


async def test_resolve_target_with_underscore_in_spot_id(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test _resolve_fiftyfive_target handles spot_ids containing _ch<N>_."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = mock_config_entry.runtime_data
    spot_id = "station_ch2_test"
    coordinator.data[spot_id] = coordinator.data[MOCK_STATION_ID]

    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        f"{spot_id}_charging",
        config_entry=mock_config_entry,
    )
    resolved = _resolve_fiftyfive_target(hass, entry.entity_id)
    assert resolved is not None
    _, resolved_spot_id, _ = resolved
    assert resolved_spot_id == spot_id


async def _setup_with_target_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> str:
    """Set up integration and return a target entity ID."""
    mock_config_entry.add_to_hass(hass)
    assert await async_setup(hass, {}) is True
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    ent_reg = er.async_get(hass)
    return next(
        e.entity_id
        for e in er.async_entries_for_config_entry(ent_reg, mock_config_entry.entry_id)
    )


async def test_get_transactions_service(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test get_transactions service passes normalized date_from/date_to and serializes items."""
    target_entity = await _setup_with_target_entity(hass, mock_config_entry)
    mock_api_client.get_charge_station_transactions_page.reset_mock()

    date_from = "2026-10-20T14:35:20+00:00"
    date_to = "2026-11-19T14:35:20+00:00"

    result = await hass.services.async_call(
        DOMAIN,
        "get_transactions",
        {
            "limit": 3,
            "date_from": date_from,
            "date_to": date_to,
            "page": 1,
        },
        target={"entity_id": target_entity},
        blocking=True,
        return_response=True,
    )

    mock_api_client.get_charge_station_transactions_page.assert_awaited_once_with(
        MOCK_STATION_ID,
        date_from=datetime(2026, 10, 20, 14, 35, 20, tzinfo=UTC),
        date_to=datetime(2026, 11, 19, 14, 35, 20, tzinfo=UTC),
        items_per_page=3,
        page=1,
    )
    assert result is not None
    assert result["page"] == 1
    assert result["has_next"] is False
    assert "transactions" in result
    assert len(result["transactions"]) == 1
    tx = result["transactions"][0]
    assert tx["id"] == "tx_last_1"
    assert tx["station_id"] == MOCK_STATION_ID
    assert tx["currency"] == "EUR"


async def test_get_transactions_service_default_dates(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test get_transactions forwards None dates when omitted."""
    target_entity = await _setup_with_target_entity(hass, mock_config_entry)
    mock_api_client.get_charge_station_transactions_page.reset_mock()

    await hass.services.async_call(
        DOMAIN,
        "get_transactions",
        {"limit": 5},
        target={"entity_id": target_entity},
        blocking=True,
        return_response=True,
    )

    mock_api_client.get_charge_station_transactions_page.assert_awaited_once_with(
        MOCK_STATION_ID,
        date_from=None,
        date_to=None,
        items_per_page=5,
        page=1,
    )


async def test_get_transactions_service_naive_datetimes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test naive datetimes from the HA datetime selector use HA's default timezone."""
    target_entity = await _setup_with_target_entity(hass, mock_config_entry)
    mock_api_client.get_charge_station_transactions_page.reset_mock()

    orig_tz = dt_util.get_default_time_zone()
    try:
        await hass.config.async_set_time_zone("Europe/Amsterdam")
        await hass.services.async_call(
            DOMAIN,
            "get_transactions",
            {
                "date_from": "2026-10-20 14:00:00",  # CEST (+02:00) -> 12:00 UTC
                "date_to": "2026-11-10 14:00:00",    # CET  (+01:00) -> 13:00 UTC
            },
            target={"entity_id": target_entity},
            blocking=True,
            return_response=True,
        )
    finally:
        dt_util.set_default_time_zone(orig_tz)

    mock_api_client.get_charge_station_transactions_page.assert_awaited_once_with(
        MOCK_STATION_ID,
        date_from=datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC),
        date_to=datetime(2026, 11, 10, 13, 0, 0, tzinfo=UTC),
        items_per_page=5,
        page=1,
    )


async def test_get_transactions_service_invalid_date_range(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test get_transactions raises ServiceValidationError when date_from > date_to."""
    target_entity = await _setup_with_target_entity(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            "get_transactions",
            {
                "date_from": "2026-11-19T14:35:20+00:00",
                "date_to": "2026-11-18T14:35:20+00:00",
            },
            target={"entity_id": target_entity},
            blocking=True,
            return_response=True,
        )
    assert exc_info.value.translation_key == "invalid_date_range"


async def test_get_transactions_service_date_range_too_long(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test get_transactions raises ServiceValidationError when span exceeds 1 month."""
    target_entity = await _setup_with_target_entity(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            "get_transactions",
            {
                "date_from": "2026-10-19T14:35:20+00:00",
                "date_to": "2026-11-19T14:35:21+00:00",
            },
            target={"entity_id": target_entity},
            blocking=True,
            return_response=True,
        )
    assert exc_info.value.translation_key == "date_range_too_long"


async def test_get_transactions_service_no_valid_targets(
    hass: HomeAssistant,
) -> None:
    """Test get_transactions raises ServiceValidationError on invalid targets."""
    assert await async_setup(hass, {}) is True

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "get_transactions",
            {"limit": 5},
            target={"entity_id": "sensor.nonexistent_entity"},
            blocking=True,
            return_response=True,
        )
