"""Tests for the 50five diagnostics platform."""

import importlib
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

const = importlib.import_module("custom_components.50five.const")
diagnostics_mod = importlib.import_module("custom_components.50five.diagnostics")
redact_mod = importlib.import_module("custom_components.50five.redact")
models_mod = importlib.import_module("custom_components.50five.models")

CONF_ACCESS_TOKEN = const.CONF_ACCESS_TOKEN
CONF_CARD_ID = const.CONF_CARD_ID
CONF_CUSTOMER_ID = const.CONF_CUSTOMER_ID
CONF_DEVICE_ID = const.CONF_DEVICE_ID
mask_value = redact_mod.mask_value
censor = redact_mod.censor
ChargeCard = models_mod.ChargeCard
CardProvider = models_mod.CardProvider
ChargeStationChannel = models_mod.ChargeStationChannel
GetCustomerChargeCardsResponse = models_mod.GetCustomerChargeCardsResponse
ActiveTransaction = models_mod.ActiveTransaction
Location = models_mod.Location
LoginResult = models_mod.LoginResult
async_get_config_entry_diagnostics = diagnostics_mod.async_get_config_entry_diagnostics


def test_mask_value() -> None:
    """Test identifier masking helper."""
    assert mask_value("abcd") == "****"
    assert mask_value("ab") == "**"
    assert mask_value("12345678") == "12****78"
    assert mask_value("station_999") == "st*******99"
    assert mask_value(12345) == "12*45"
    assert censor(
        {"getCustomerByIdId": 12345, "chargeStationId": 67890, "card": 24680}
    ) == {
        "getCustomerByIdId": "12*45",
        "chargeStationId": "67*90",
        "card": "24*80",
    }
    assert censor(ChargeStationChannel(id="channel_12345"))["id"] == (
        "ch*********45"
    )
    assert censor(
        {
            "getCustomerById": {
                "id": "customer_1",
                "cards": [
                    {"id": "card_1", "cardProvider": {"name": "External Provider"}}
                ],
            }
        },
        response_model=GetCustomerChargeCardsResponse,
    ) == {
        "getCustomerById": {
            "id": "cu******_1",
            "cards": [
                {"id": "ca**_1", "cardProvider": {"name": "<redacted>"}}
            ],
        }
    }
    assert censor({"station": {"name": "Home Charger"}}) == {
        "station": {"name": "Home Charger"}
    }
    card = ChargeCard(card_provider=CardProvider(name="External Provider"))
    assert censor(card)["card_provider"]["name"] == "<redacted>"

    active_tx = censor(
        ActiveTransaction(address="Private address", zip_code="12345", city="Town")
    )
    assert active_tx["address"] == "<redacted>"
    assert active_tx["zip_code"] == "<redacted>"
    assert active_tx["city"] == "<redacted>"

    location = censor(
        Location(address="Private address", postal_code="12345", city="Town")
    )
    assert location["address"] == "<redacted>"
    assert location["postal_code"] == "<redacted>"
    assert location["city"] == "<redacted>"

    assert censor(LoginResult(access_token="secret-token"))["access_token"] == (
        "<redacted>"
    )


async def test_diagnostics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test diagnostics output redacts sensitive data and formats station details."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    # Verify config_entry redactions
    entry_diag = diag["config_entry"]
    assert entry_diag["title"] == "**REDACTED**"
    assert entry_diag["unique_id"] == "**REDACTED**"
    assert entry_diag["data"][CONF_ACCESS_TOKEN] == "**REDACTED**"
    assert entry_diag["data"][CONF_DEVICE_ID] == "**REDACTED**"
    assert entry_diag["data"][CONF_CARD_ID] == "**REDACTED**"
    assert entry_diag["data"][CONF_CUSTOMER_ID] == "**REDACTED**"

    # Verify masked client identity info
    client_diag = diag["client"]
    assert client_diag["username"] == mask_value(mock_api_client.username)
    assert client_diag["device_id"] == mask_value(mock_api_client.device_id)
    assert client_diag["customer_id"] == mask_value(mock_api_client.customer_id)

    # Verify station diagnostics, keyed by masked station id
    assert "stations" in diag
    assert len(diag["stations"]) == 2

    st1 = diag["stations"][mask_value("station_999")]
    station = st1["station"]
    assert station["id"] == mask_value("station_999")
    assert station["name"] == "Home Charger Single"
    assert station["manufacturer"] == {
        "vendor": "Alfen",
        "model": "Eve Single Pro-line",
    }
    assert station["access_options"]["access_type"] == "Private"
    assert station["hcc"]["hcc_enabled"] is True
    assert station["hcc"]["hcc_tariff"] == 0.30
    assert st1["vat_multiplier"] == 1.21

    # Sensitive location fields are fully redacted
    assert station["location"]["address"] == "<redacted>"

    # Nested channel and transaction identifiers are masked, not raw
    channel = station["channels"][0]
    assert channel["id"] == mask_value("ch_999_1")
    assert channel["evse_id"] == mask_value("NL*50F*E999*1")

    tx = station["transactions"]["items"][0]
    assert tx["id"] == mask_value("tx_last_1")
    assert tx["total_energy"] == 28.5


async def test_diagnostics_without_runtime_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test diagnostics when runtime_data is not set."""
    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert "config_entry" in diag
    assert "stations" not in diag
