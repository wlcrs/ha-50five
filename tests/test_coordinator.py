"""Tests for the 50five DataUpdateCoordinator."""

import importlib
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mock_charge_stations: list[ChargeStation],
    mock_active_transaction: ActiveTransaction,
) -> None:
    """Test successful coordinator data update."""
    coordinator = FiftyFiveCoordinator(hass, mock_config_entry, mock_api_client)
    assert coordinator.config_entry is mock_config_entry
    data = await coordinator._async_update_data()

    assert len(data) == 2
    assert MOCK_STATION_ID in data
    assert MOCK_MULTI_STATION_ID in data

    single_data = data[MOCK_STATION_ID]
    assert single_data.num_channels == 1
    assert single_data.station.name == "Home Charger Single"
    assert single_data.active_transaction == mock_active_transaction
    assert single_data.station.last_transaction is not None
    assert single_data.station.last_transaction.total_energy == 28.5

    multi_data = data[MOCK_MULTI_STATION_ID]
    assert multi_data.num_channels == 2
    assert multi_data.channels[1].status.value == "charging"
    assert multi_data.channels[2].status.value == "available"


async def test_coordinator_no_stations(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test coordinator behavior when no stations are returned."""
    mock_api_client.get_customer_charge_stations.return_value = []
    coordinator = FiftyFiveCoordinator(hass, mock_config_entry, mock_api_client)

    data = await coordinator._async_update_data()
    assert data == {}
    assert coordinator.charge_stations == []


async def test_coordinator_active_transaction_error_resilience(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mock_charge_stations: list[ChargeStation],
) -> None:
    """Test coordinator still succeeds when active transaction query fails."""
    mock_api_client.get_active_transaction.side_effect = FiftyFiveError("LMS timeout")
    coordinator = FiftyFiveCoordinator(hass, mock_config_entry, mock_api_client)

    data = await coordinator._async_update_data()
    assert len(data) == 2
    assert data[MOCK_STATION_ID].active_transaction is None


async def test_coordinator_auth_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test coordinator raises ConfigEntryAuthFailed on FiftyFiveAuthError."""
    mock_api_client.get_customer_charge_stations.side_effect = FiftyFiveAuthError(
        "Token revoked"
    )
    coordinator = FiftyFiveCoordinator(hass, mock_config_entry, mock_api_client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_api_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test coordinator raises UpdateFailed on FiftyFiveError."""
    mock_api_client.get_customer_charge_stations.side_effect = FiftyFiveError(
        "Server error"
    )
    coordinator = FiftyFiveCoordinator(hass, mock_config_entry, mock_api_client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_unexpected_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test coordinator raises UpdateFailed on unexpected exceptions."""
    mock_api_client.get_customer_charge_stations.side_effect = TypeError(
        "Unexpected null"
    )
    coordinator = FiftyFiveCoordinator(hass, mock_config_entry, mock_api_client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_completed_transactions_error_resilience(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mock_charge_stations: list[ChargeStation],
) -> None:
    """Test coordinator still succeeds when completed transactions query fails."""
    stations_without_tx = [
        st.model_copy(update={"transactions": None}) for st in mock_charge_stations
    ]
    mock_api_client.get_customer_charge_stations.return_value = stations_without_tx
    mock_api_client.get_charge_station_transactions.side_effect = FiftyFiveError(
        "Cannot read properties of undefined (reading 'country')"
    )
    coordinator = FiftyFiveCoordinator(hass, mock_config_entry, mock_api_client)

    data = await coordinator._async_update_data()
    assert len(data) == 2
    assert data[MOCK_STATION_ID].station.last_transaction is None


async def test_coordinator_completed_transactions_fetch_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mock_charge_stations: list[ChargeStation],
) -> None:
    """Test coordinator attaches fetched completed transactions."""
    stations_without_tx = [
        st.model_copy(update={"transactions": None}) for st in mock_charge_stations
    ]
    mock_api_client.get_customer_charge_stations.return_value = stations_without_tx
    mock_api_client.get_charge_station_transactions.return_value = mock_charge_stations[
        0
    ].transactions.items
    coordinator = FiftyFiveCoordinator(hass, mock_config_entry, mock_api_client)

    data = await coordinator._async_update_data()
    assert len(data) == 2
    assert data[MOCK_STATION_ID].station.last_transaction is not None
    assert data[MOCK_STATION_ID].station.last_transaction.total_energy == 28.5


async def test_coordinator_scopes_active_transaction_by_channel_id(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mock_active_transaction,
) -> None:
    """Test active_transaction is attached only to the station owning its channelId."""
    mock_api_client.get_active_transaction.return_value = (
        mock_active_transaction.model_copy(update={"channel_id": "ch_888_1"})
    )
    coordinator = FiftyFiveCoordinator(hass, mock_config_entry, mock_api_client)

    data = await coordinator._async_update_data()
    assert data[MOCK_STATION_ID].active_transaction is None
    assert data[MOCK_MULTI_STATION_ID].active_transaction is not None


async def test_coordinator_fetches_charge_cards_and_active_transaction_details(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mock_charge_cards,
) -> None:
    """Test coordinator fetches account cards and active transaction details."""
    from .const import MOCK_CARD_ID, MOCK_GET_TRANSACTION_RESPONSE

    active_details = models.CompletedTransaction.model_validate(
        MOCK_GET_TRANSACTION_RESPONSE["getTransaction"]
    )
    mock_api_client.get_transaction.return_value = active_details

    coordinator = FiftyFiveCoordinator(hass, mock_config_entry, mock_api_client)
    data = await coordinator._async_update_data()

    assert coordinator.charge_cards == mock_charge_cards
    mock_api_client.get_transaction.assert_awaited_once_with("tx_active_1")
    assert data[MOCK_STATION_ID].active_transaction_details == active_details
    assert MOCK_CARD_ID in data[MOCK_STATION_ID].get_backend_active_card_ids(1)

    # Repeating poll with same transaction_id reuses cached details without another API call
    data2 = await coordinator._async_update_data()
    assert mock_api_client.get_transaction.await_count == 1
    assert data2[MOCK_STATION_ID].active_transaction_details == active_details

    # New transaction_id triggers a fresh get_transaction lookup
    mock_api_client.get_active_transaction.return_value = (
        mock_api_client.get_active_transaction.return_value.model_copy(
            update={"transaction_id": "tx_active_2"}
        )
    )
    await coordinator._async_update_data()
    assert mock_api_client.get_transaction.await_count == 2
    mock_api_client.get_transaction.assert_awaited_with("tx_active_2")

    # Ending active transaction clears cached details
    mock_api_client.get_active_transaction.return_value = None
    data3 = await coordinator._async_update_data()
    assert data3[MOCK_STATION_ID].active_transaction_details is None


async def test_coordinator_degrades_gracefully_when_cards_or_tx_details_fail(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test coordinator succeeds when get_charge_cards or get_transaction fails."""
    mock_api_client.get_charge_cards.side_effect = FiftyFiveError("Cards failed")
    mock_api_client.get_transaction.side_effect = FiftyFiveError("Tx detail failed")

    coordinator = FiftyFiveCoordinator(hass, mock_config_entry, mock_api_client)
    data = await coordinator._async_update_data()

    assert len(data) == 2
    assert coordinator.charge_cards == []
    assert data[MOCK_STATION_ID].active_transaction_details is None

    # Subsequent poll retries get_charge_cards until it succeeds, then caches it
    mock_api_client.get_charge_cards.side_effect = None
    await coordinator._async_update_data()
    assert len(coordinator.charge_cards) == 2
    assert mock_api_client.get_charge_cards.await_count == 2

    await coordinator._async_update_data()
    assert mock_api_client.get_charge_cards.await_count == 2


async def test_coordinator_skips_active_transaction_when_all_stations_idle(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mock_charge_stations: list[ChargeStation],
) -> None:
    """Test lmsActiveTransaction is skipped when all channels are idle."""
    idle_stations = [
        st.model_copy(
            update={
                "channels": [
                    ch.model_copy(
                        update={"global_status": models.ChannelGlobalStatus.AVAILABLE}
                    )
                    for ch in (st.channels or [])
                ]
            }
        )
        for st in mock_charge_stations
    ]
    mock_api_client.get_customer_charge_stations.return_value = idle_stations

    coordinator = FiftyFiveCoordinator(hass, mock_config_entry, mock_api_client)
    data = await coordinator._async_update_data()

    mock_api_client.get_active_transaction.assert_not_awaited()
    assert data[MOCK_STATION_ID].active_transaction is None

    # Pending optimistic start SHOULD query lmsActiveTransaction even while channel is Available
    coordinator.set_optimistic_charging_state(
        MOCK_STATION_ID, "ch_999_1", True, card_id="NL-50F-123456-7"
    )
    await hass.async_block_till_done()
    data2 = await coordinator._async_update_data()
    mock_api_client.get_active_transaction.assert_awaited_once()
    assert data2[MOCK_STATION_ID].active_transaction is not None


async def test_coordinator_throttles_completed_transactions_when_idle(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mock_charge_stations: list[ChargeStation],
) -> None:
    """Test getTransactions is throttled when idle, refreshed post-session, and hourly."""
    from unittest.mock import patch

    station_base = mock_charge_stations[0].model_copy(update={"transactions": None})
    initial_txs = mock_charge_stations[0].transactions.items
    new_tx = initial_txs[0].model_copy(update={"id": "tx_last_2", "total_energy": 15.0})

    mock_api_client.get_customer_charge_stations.return_value = [station_base]
    mock_api_client.get_charge_station_transactions.side_effect = None
    mock_api_client.get_charge_station_transactions.return_value = initial_txs

    coordinator = FiftyFiveCoordinator(hass, mock_config_entry, mock_api_client)
    now = [1000.0]

    with patch.object(coordinator_mod.time, "monotonic", side_effect=lambda: now[0]):
        # 1. Startup poll fetches transactions once
        coordinator.data = await coordinator._async_update_data()
        assert mock_api_client.get_charge_station_transactions.await_count == 1
        assert coordinator.data[MOCK_STATION_ID].station.last_transaction.id == "tx_last_1"

        # 2. Idle poll 60s later skips getTransactions and reuses cached last_transaction
        now[0] = 1060.0
        coordinator.data = await coordinator._async_update_data()
        assert mock_api_client.get_charge_station_transactions.await_count == 1
        assert coordinator.data[MOCK_STATION_ID].station.last_transaction.id == "tx_last_1"

        # 3. Station starts charging -> still no completed-history fetch
        charging_station = station_base.model_copy(
            update={
                "channels": [
                    station_base.channels[0].model_copy(
                        update={"global_status": models.ChannelGlobalStatus.CHARGING}
                    )
                ]
            }
        )
        mock_api_client.get_customer_charge_stations.return_value = [charging_station]
        now[0] = 1120.0
        coordinator.data = await coordinator._async_update_data()
        assert mock_api_client.get_charge_station_transactions.await_count == 1

        # 4. Charging ends (Charging -> Available) -> triggers post-session fetch
        mock_api_client.get_customer_charge_stations.return_value = [station_base]
        mock_api_client.get_charge_station_transactions.return_value = [new_tx]
        now[0] = 1180.0
        coordinator.data = await coordinator._async_update_data()
        assert mock_api_client.get_charge_station_transactions.await_count == 2
        assert coordinator.data[MOCK_STATION_ID].station.last_transaction.id == "tx_last_2"

        # 5. New tx ID was caught -> post-session window clears early, next idle poll skips
        now[0] = 1240.0
        coordinator.data = await coordinator._async_update_data()
        assert mock_api_client.get_charge_station_transactions.await_count == 2

        # 6. Hourly fallback triggers after 3600s
        now[0] = 1180.0 + 3600.0
        coordinator.data = await coordinator._async_update_data()
        assert mock_api_client.get_charge_station_transactions.await_count == 3
