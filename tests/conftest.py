"""Common test fixtures for the 50five integration."""

import importlib
import threading
from collections.abc import Generator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

_original_threading_enumerate = threading.enumerate


def _patched_threading_enumerate():
    """Filter out internal HA safe shutdown threads from test cleanup checks."""
    return [
        t
        for t in _original_threading_enumerate()
        if "_run_safe_shutdown_loop" not in getattr(t, "name", "")
    ]


threading.enumerate = _patched_threading_enumerate

const = importlib.import_module("custom_components.50five.const")
models = importlib.import_module("custom_components.50five.models")
init_mod = importlib.import_module("custom_components.50five")
config_flow_mod = importlib.import_module("custom_components.50five.config_flow")

DOMAIN = const.DOMAIN
ActiveTransaction = models.ActiveTransaction
ChargeCard = models.ChargeCard
ChargeStation = models.ChargeStation

from .const import (
    MOCK_ACTIVE_TRANSACTION_RESPONSE,
    MOCK_CARD_ID,
    MOCK_CONFIG_DATA,
    MOCK_CUSTOMER_CHARGE_CARDS_RESPONSE,
    MOCK_CUSTOMER_CHARGE_STATIONS_RESPONSE,
    MOCK_USERNAME,
)

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in Home Assistant."""
    return


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a mock 50five config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_USERNAME,
        data=dict(MOCK_CONFIG_DATA),
        options={},
        entry_id="50five_test_entry_id",
        unique_id=f"{DOMAIN}_{MOCK_USERNAME}",
        version=2,
    )


@pytest.fixture
def mock_charge_stations() -> list[ChargeStation]:
    """Return mock ChargeStation models."""
    return [
        ChargeStation.from_dict(st, vat_multiplier=1.21)
        for st in MOCK_CUSTOMER_CHARGE_STATIONS_RESPONSE["getCustomerChargeStations"]
    ]


@pytest.fixture
def mock_charge_cards() -> list[ChargeCard]:
    """Return mock ChargeCard models."""
    return [
        c
        for c in (
            ChargeCard.from_dict(raw)
            for raw in MOCK_CUSTOMER_CHARGE_CARDS_RESPONSE["getCustomerById"]["cards"]
        )
        if c is not None
    ]


@pytest.fixture
def mock_active_transaction() -> ActiveTransaction | None:
    """Return mock ActiveTransaction model."""
    return ActiveTransaction.from_dict(
        MOCK_ACTIVE_TRANSACTION_RESPONSE["lmsActiveTransaction"]
    )


@pytest.fixture
def mock_api_client(
    mock_charge_stations: list[ChargeStation],
    mock_charge_cards: list[ChargeCard],
    mock_active_transaction: ActiveTransaction,
) -> Generator[AsyncMock]:
    """Return a mocked FiftyFiveApiClient."""
    with patch.object(
        init_mod,
        "FiftyFiveApiClient",
        autospec=True,
    ) as mock_client_cls, patch.object(
        config_flow_mod,
        "FiftyFiveApiClient",
        new=mock_client_cls,
    ):
        client = mock_client_cls.return_value
        client.username = MOCK_USERNAME
        client.password = "secret"
        client.device_id = "550e8400-e29b-41d4-a716-446655440000"
        client.customer_id = "cust_12345"
        client.access_token = "mock_token"
        client.token_expires_at = datetime(2030, 1, 1, tzinfo=timezone.utc)
        client.is_authenticated = True
        client.is_token_expired.return_value = False

        client.authenticate = AsyncMock(return_value=True)
        client.get_vat_multiplier = AsyncMock(return_value=1.21)
        client.get_customer_charge_stations = AsyncMock(
            return_value=mock_charge_stations
        )
        client.get_charge_station_details = AsyncMock(
            return_value=mock_charge_stations[0]
        )
        client.get_active_transaction = AsyncMock(return_value=mock_active_transaction)
        client.get_charge_cards = AsyncMock(return_value=mock_charge_cards)
        client.get_tokens = AsyncMock(return_value=mock_charge_cards)
        client.start_charging = AsyncMock(return_value=True)
        client.stop_charging = AsyncMock(return_value=True)
        client.unlock_connector = AsyncMock(return_value=True)
        client.soft_reset = AsyncMock(return_value=True)
        client.hard_reset = AsyncMock(return_value=True)
        client.reset_parameters_cache = AsyncMock(return_value=True)
        client.get_net_balanced_charging_status = AsyncMock(return_value=False)
        client.set_net_balanced_charging = AsyncMock(return_value=True)

        yield client


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Mock async_setup_entry."""
    with patch.object(
        init_mod, "async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup
