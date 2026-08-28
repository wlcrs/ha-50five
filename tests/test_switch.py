"""Tests for the 50five charging switch platform."""

import importlib
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

const = importlib.import_module("custom_components.50five.const")
exceptions = importlib.import_module("custom_components.50five.exceptions")

CONF_CARD_ID = const.CONF_CARD_ID
DOMAIN = const.DOMAIN
FiftyFiveApiError = exceptions.FiftyFiveApiError

from .const import (
    MOCK_CARD_ID,
    MOCK_CONFIG_DATA,
    MOCK_MULTI_STATION_ID,
    MOCK_STATION_ID,
    MOCK_USERNAME,
)


async def test_switch_creation_skipped_without_card(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test charging session switch entities are not created when no charge card is configured."""
    entry_data = dict(MOCK_CONFIG_DATA)
    entry_data[CONF_CARD_ID] = ""

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_USERNAME,
        data=entry_data,
        options={},
        entry_id="test_no_card",
        version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Charging session switches should not exist
    charging_switches = [
        s for s in hass.states.async_entity_ids(SWITCH_DOMAIN) if "charge_with_card" in s
    ]
    assert len(charging_switches) == 0

    # Net balanced charging switches are created per station
    nbc_switches = [
        s for s in hass.states.async_entity_ids(SWITCH_DOMAIN) if "net_balanced_charging" in s
    ]
    assert len(nbc_switches) == 2


async def test_net_balanced_charging_switch(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test net balanced charging switch states, turn on, turn off, and error handling."""
    mock_api_client.get_net_balanced_charging_status.return_value = True
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = "switch.home_charger_single_net_balanced_charging"
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_ON

    # Turn off
    await hass.services.async_call(
        SWITCH_DOMAIN,
        "turn_off",
        {"entity_id": entity_id},
        blocking=True,
    )
    mock_api_client.set_net_balanced_charging.assert_called_with(MOCK_STATION_ID, False)

    # Turn on
    await hass.services.async_call(
        SWITCH_DOMAIN,
        "turn_on",
        {"entity_id": entity_id},
        blocking=True,
    )
    mock_api_client.set_net_balanced_charging.assert_called_with(MOCK_STATION_ID, True)

    # Error rollback
    mock_api_client.set_net_balanced_charging.side_effect = FiftyFiveApiError("API Error")
    with pytest.raises((FiftyFiveApiError, HomeAssistantError)):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )



async def test_switch_entities_and_states(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test switch entity states for single and multi-channel chargers."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Single-channel charger has active transaction on channel 1 -> ON
    single_switch = hass.states.get(
        "switch.home_charger_single_charge_with_card_nl_50f_123456_7"
    )
    assert single_switch is not None
    assert single_switch.state == STATE_ON

    # Multi-channel charger: channel 1 has CHARGING status -> ON
    multi_ch1_switch = hass.states.get(
        "switch.office_charger_dual_ch_1_charge_with_card_nl_50f_123456_7"
    )
    assert multi_ch1_switch is not None
    assert multi_ch1_switch.state == STATE_ON

    # Multi-channel charger: channel 2 has AVAILABLE status and no active tx -> OFF
    multi_ch2_switch = hass.states.get(
        "switch.office_charger_dual_ch_2_charge_with_card_nl_50f_123456_7"
    )
    assert multi_ch2_switch is not None
    assert multi_ch2_switch.state == STATE_OFF


async def test_switch_turn_on(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test turning on charging switch."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = "switch.office_charger_dual_ch_2_charge_with_card_nl_50f_123456_7"
    await hass.services.async_call(
        SWITCH_DOMAIN,
        "turn_on",
        {"entity_id": entity_id},
        blocking=True,
    )

    mock_api_client.start_charging.assert_called_once_with(
        charge_station_id=MOCK_MULTI_STATION_ID,
        channel_id="ch_888_2",
        card=MOCK_CARD_ID,
    )


async def test_switch_turn_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test turning off charging switch."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = "switch.home_charger_single_charge_with_card_nl_50f_123456_7"
    await hass.services.async_call(
        SWITCH_DOMAIN,
        "turn_off",
        {"entity_id": entity_id},
        blocking=True,
    )

    mock_api_client.stop_charging.assert_called_once_with(
        charge_station_id=MOCK_STATION_ID,
        channel_id="ch_999_1",
    )


async def test_switch_turn_on_error_rollback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test turning on switch rolls back optimistic state on error."""
    mock_api_client.start_charging.side_effect = FiftyFiveApiError("LMS failed")
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = "switch.office_charger_dual_ch_2_charge_with_card_nl_50f_123456_7"
    with pytest.raises((FiftyFiveApiError, HomeAssistantError)):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            "turn_on",
            {"entity_id": entity_id},
            blocking=True,
        )

    # State should revert to OFF
    state = hass.states.get(entity_id)
    assert state.state == STATE_OFF


async def test_switch_turn_off_error_rollback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test turning off switch rolls back optimistic state on error."""
    mock_api_client.stop_charging.side_effect = FiftyFiveApiError("LMS failed")
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = "switch.home_charger_single_charge_with_card_nl_50f_123456_7"
    with pytest.raises((FiftyFiveApiError, HomeAssistantError)):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )

    # State should remain ON
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
