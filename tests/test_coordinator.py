"""Tests for the 50five DataUpdateCoordinator."""

import importlib
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

coordinator_mod = importlib.import_module("custom_components.50five.coordinator")
exceptions = importlib.import_module("custom_components.50five.exceptions")
models = importlib.import_module("custom_components.50five.models")

FiftyFiveCoordinator = coordinator_mod.FiftyFiveCoordinator
FiftyFiveAuthError = exceptions.FiftyFiveAuthError
FiftyFiveError = exceptions.FiftyFiveError
ActiveTransaction = models.ActiveTransaction
ChargeStation = models.ChargeStation

from .const import MOCK_MULTI_STATION_ID, MOCK_STATION_ID


async def test_coordinator_update_success(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
    mock_charge_stations: list[ChargeStation],
    mock_active_transaction: ActiveTransaction,
) -> None:
    """Test successful coordinator data update."""
    coordinator = FiftyFiveCoordinator(hass, mock_api_client)
    data = await coordinator._async_update_data()

    assert len(data) == 2
    assert MOCK_STATION_ID in data
    assert MOCK_MULTI_STATION_ID in data

    single_data = data[MOCK_STATION_ID]
    assert single_data.num_channels == 1
    assert single_data.station.name == "Home Charger Single"
    assert single_data.active_transaction == mock_active_transaction
    assert single_data.last_transaction is not None
    assert single_data.last_transaction.total_energy == 28.5

    multi_data = data[MOCK_MULTI_STATION_ID]
    assert multi_data.num_channels == 2
    assert multi_data.channels[1].global_status.value == "charging"
    assert multi_data.channels[2].global_status.value == "available"


async def test_coordinator_no_stations(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test coordinator behavior when no stations are returned."""
    mock_api_client.get_customer_charge_stations.return_value = []
    coordinator = FiftyFiveCoordinator(hass, mock_api_client)

    data = await coordinator._async_update_data()
    assert data == {}
    assert coordinator.charge_stations == []


async def test_coordinator_active_transaction_error_resilience(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
    mock_charge_stations: list[ChargeStation],
) -> None:
    """Test coordinator still succeeds when active transaction query fails."""
    mock_api_client.get_active_transaction.side_effect = FiftyFiveError("LMS timeout")
    coordinator = FiftyFiveCoordinator(hass, mock_api_client)

    data = await coordinator._async_update_data()
    assert len(data) == 2
    assert data[MOCK_STATION_ID].active_transaction is None


async def test_coordinator_auth_error(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test coordinator raises ConfigEntryAuthFailed on FiftyFiveAuthError."""
    mock_api_client.get_customer_charge_stations.side_effect = FiftyFiveAuthError("Token revoked")
    coordinator = FiftyFiveCoordinator(hass, mock_api_client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_api_error(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test coordinator raises UpdateFailed on FiftyFiveError."""
    mock_api_client.get_customer_charge_stations.side_effect = FiftyFiveError("Server error")
    coordinator = FiftyFiveCoordinator(hass, mock_api_client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_unexpected_error(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test coordinator raises UpdateFailed on unexpected exceptions."""
    mock_api_client.get_customer_charge_stations.side_effect = TypeError("Unexpected null")
    coordinator = FiftyFiveCoordinator(hass, mock_api_client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
