"""Tests for the 50five number platform."""

import importlib
from unittest.mock import AsyncMock

from homeassistant.components.number import ATTR_VALUE, DOMAIN as NUMBER_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .const import MOCK_STATION_ID

FiftyFiveApiError = importlib.import_module(
    "custom_components.50five.exceptions"
).FiftyFiveApiError


async def test_hcc_tariff_number_is_not_added_for_belgian_provider_category(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test the HCC tariff control is omitted for the Shell BE app variants."""
    mock_api_client.provider_category = "BE"
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        NUMBER_DOMAIN,
        "50five",
        f"{MOCK_STATION_ID}_hcc_tariff",
    )
    assert entity_id is None


async def test_hcc_tariff_number_is_not_added_when_provider_category_is_unknown(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test the HCC tariff control is omitted when edit eligibility is unknown."""
    mock_api_client.provider_category = None
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        NUMBER_DOMAIN,
        "50five",
        f"{MOCK_STATION_ID}_hcc_tariff",
    )
    assert entity_id is None


async def test_hcc_tariff_number_updates_and_refreshes_value(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test setting the HCC tariff and displaying the backend value."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        NUMBER_DOMAIN,
        "50five",
        f"{MOCK_STATION_ID}_hcc_tariff",
    )
    assert entity_id is not None
    registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "0.3"
    assert state.attributes["unit_of_measurement"] == "€/kWh"
    assert state.attributes["min"] == 0.05
    assert state.attributes["max"] == 0.75

    async def update_backend(station_id: str, tariff: float) -> bool:
        stations = mock_api_client.get_customer_charge_stations.return_value
        station_index, station = next(
            (index, station)
            for index, station in enumerate(stations)
            if station.id == station_id
        )
        assert station.hcc is not None
        stations[station_index] = station.model_copy(
            update={"hcc": station.hcc.model_copy(update={"hcc_tariff": tariff})}
        )
        return True

    mock_api_client.update_hcc_tariff.side_effect = update_backend

    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {
            "entity_id": entity_id,
            ATTR_VALUE: 0.42,
        },
        blocking=True,
    )

    mock_api_client.update_hcc_tariff.assert_awaited_once_with(
        MOCK_STATION_ID, 0.42
    )
    updated_state = hass.states.get(entity_id)
    assert updated_state is not None
    assert updated_state.state == "0.42"


async def test_hcc_tariff_number_uses_mobile_app_fallback_range(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test fallback limits are the app's raw, excluding-VAT range."""
    mock_api_client.get_reimbursement_tariff_range.return_value = None
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id(
        NUMBER_DOMAIN,
        "50five",
        f"{MOCK_STATION_ID}_hcc_tariff",
    )
    assert entity_id is not None
    registry = er.async_get(hass)
    registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["min"] == 0.0001
    assert state.attributes["max"] == 0.67


async def test_hcc_tariff_number_falls_back_on_range_api_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test number setup falls back to default range on FiftyFiveError."""
    mock_api_client.get_reimbursement_tariff_range.side_effect = FiftyFiveApiError(
        "temporary error"
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id(
        NUMBER_DOMAIN,
        "50five",
        f"{MOCK_STATION_ID}_hcc_tariff",
    )
    assert entity_id is not None
