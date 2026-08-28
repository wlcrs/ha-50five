"""Tests for the 50five button platform."""

import importlib
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

exceptions = importlib.import_module("custom_components.50five.exceptions")
FiftyFiveApiError = exceptions.FiftyFiveApiError

from .const import MOCK_MULTI_STATION_ID, MOCK_STATION_ID


async def test_button_entities_created(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test all button entities are created."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Refresh status button
    assert hass.states.get("button.home_charger_single_refresh_status") is not None

    # Soft reset button
    assert hass.states.get("button.home_charger_single_soft_reset") is not None

    # Hard reset button
    assert hass.states.get("button.home_charger_single_hard_reset") is not None

    # Reset cache button
    assert hass.states.get("button.home_charger_single_reset_cache") is not None

    # Single-channel unlock connector
    assert hass.states.get("button.home_charger_single_unlock_connector") is not None

    # Multi-channel unlock connector buttons
    assert (
        hass.states.get("button.office_charger_dual_ch_1_unlock_connector")
        is not None
    )
    assert (
        hass.states.get("button.office_charger_dual_ch_2_unlock_connector")
        is not None
    )


async def test_button_press_actions(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test pressing buttons triggers corresponding API actions."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # 1. Refresh Status
    with patch.object(
        mock_config_entry.runtime_data.coordinator,
        "async_request_refresh",
        new_callable=AsyncMock,
    ) as mock_refresh:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            "press",
            {"entity_id": "button.home_charger_single_refresh_status"},
            blocking=True,
        )
        mock_refresh.assert_called_once()

    # 2. Soft Reset
    await hass.services.async_call(
        BUTTON_DOMAIN,
        "press",
        {"entity_id": "button.home_charger_single_soft_reset"},
        blocking=True,
    )
    mock_api_client.soft_reset.assert_called_once_with(MOCK_STATION_ID)

    # 3. Hard Reset
    await hass.services.async_call(
        BUTTON_DOMAIN,
        "press",
        {"entity_id": "button.home_charger_single_hard_reset"},
        blocking=True,
    )
    mock_api_client.hard_reset.assert_called_once_with(MOCK_STATION_ID)

    # 4. Reset Cache
    await hass.services.async_call(
        BUTTON_DOMAIN,
        "press",
        {"entity_id": "button.home_charger_single_reset_cache"},
        blocking=True,
    )
    mock_api_client.reset_parameters_cache.assert_called_once_with(MOCK_STATION_ID)

    # 5. Unlock Connector on Channel 2 of dual charger
    await hass.services.async_call(
        BUTTON_DOMAIN,
        "press",
        {"entity_id": "button.office_charger_dual_ch_2_unlock_connector"},
        blocking=True,
    )
    mock_api_client.unlock_connector.assert_called_once_with(
        MOCK_MULTI_STATION_ID, "ch_888_2"
    )


async def test_button_press_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test error handling when button action fails."""
    mock_api_client.soft_reset.side_effect = FiftyFiveApiError("Station unreachable")
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(FiftyFiveApiError):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            "press",
            {"entity_id": "button.home_charger_single_soft_reset"},
            blocking=True,
        )
