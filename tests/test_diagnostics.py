"""Tests for the 50five diagnostics platform."""

import importlib
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

const = importlib.import_module("custom_components.50five.const")
diagnostics_mod = importlib.import_module("custom_components.50five.diagnostics")

CONF_ACCESS_TOKEN = const.CONF_ACCESS_TOKEN
CONF_CARD_ID = const.CONF_CARD_ID
CONF_DEVICE_ID = const.CONF_DEVICE_ID
_anonymize_identifier = diagnostics_mod._anonymize_identifier
async_get_config_entry_diagnostics = diagnostics_mod.async_get_config_entry_diagnostics


def test_anonymize_identifier() -> None:
    """Test identifier anonymization helper."""
    assert _anonymize_identifier("abcd") == "**REDACTED**"
    assert _anonymize_identifier("ab") == "**REDACTED**"
    assert _anonymize_identifier("12345678") == "12***78"
    assert _anonymize_identifier("station_999") == "st***99"


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
    assert entry_diag["data"][CONF_ACCESS_TOKEN] == "**REDACTED**"
    assert entry_diag["data"][CONF_DEVICE_ID] == "**REDACTED**"
    assert entry_diag["data"][CONF_CARD_ID] == "**REDACTED**"

    # Verify station diagnostics
    assert "stations" in diag
    assert len(diag["stations"]) == 2

    st1 = diag["stations"][0]
    assert st1["id"] == "st***99"
    assert st1["name"] == "Home Charger Single"
    assert st1["num_channels"] == 1
    assert st1["manufacturer"] == {"vendor": "Alfen", "model": "Eve Single Pro-line"}
    assert st1["access_type"] == "private"
    assert st1["hcc_enabled"] is True
    assert st1["hcc_tariff"] == 0.363
    assert st1["raw_hcc_tariff"] == 0.30
    assert st1["net_balanced_charging"] is False
    assert st1["has_last_transaction"] is True
    assert st1["last_transaction_energy"] == 28.5


async def test_diagnostics_without_runtime_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test diagnostics when runtime_data is not set."""
    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert "config_entry" in diag
    assert "stations" not in diag
