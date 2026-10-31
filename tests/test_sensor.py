"""Tests for the 50five sensor platform."""

import importlib
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

const = importlib.import_module("custom_components.50five.const")

ATTR_RAW_TARIFF = const.ATTR_RAW_TARIFF
ATTR_VAT = const.ATTR_VAT
ATTR_VAT_MULTIPLIER = const.ATTR_VAT_MULTIPLIER


async def test_sensors_single_channel_station(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test sensor platform entities for a single-channel charging station."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Status sensor
    status_state = hass.states.get("sensor.home_charger_single_status")
    assert status_state is not None
    assert status_state.state == "available"

    # Active session energy sensor (active transaction has 12.4 kWh)
    energy_state = hass.states.get("sensor.home_charger_single_session_energy")
    assert energy_state is not None
    assert float(energy_state.state) == 12.4

    # Active session duration sensor (5400s converted to 1.5h by suggested_unit_of_measurement)
    duration_state = hass.states.get("sensor.home_charger_single_session_time")
    assert duration_state is not None
    assert float(duration_state.state) == 1.5

    # Active session cost sensor (active transaction has 4.34)
    cost_state = hass.states.get("sensor.home_charger_single_session_cost")
    assert cost_state is not None
    assert float(cost_state.state) == 4.34

    # Station HCC tariff sensor (0.30 raw * 1.21 VAT = 0.363)
    hcc_state = hass.states.get("sensor.home_charger_single_hcc_tariff")
    assert hcc_state is not None
    assert float(hcc_state.state) == 0.363
    assert hcc_state.attributes[ATTR_RAW_TARIFF] == 0.30
    assert hcc_state.attributes[ATTR_VAT] == 21
    assert hcc_state.attributes[ATTR_VAT_MULTIPLIER] == 1.21

    # HCC enabled sensor
    hcc_enabled_state = hass.states.get("sensor.home_charger_single_hcc_status")
    assert hcc_enabled_state is not None
    assert hcc_enabled_state.state == "Enabled"

    # Last transaction sensors
    last_energy_state = hass.states.get(
        "sensor.home_charger_single_last_session_energy"
    )
    assert last_energy_state is not None
    assert float(last_energy_state.state) == 28.5

    last_duration_state = hass.states.get(
        "sensor.home_charger_single_last_session_duration"
    )
    assert last_duration_state is not None
    assert float(last_duration_state.state) == 4.5
    assert last_duration_state.attributes["unit_of_measurement"] == "h"

    last_idle_time_state = hass.states.get(
        "sensor.home_charger_single_last_session_idle_time"
    )
    assert last_idle_time_state is not None
    assert float(last_idle_time_state.state) == pytest.approx(5 / 60)
    assert last_idle_time_state.attributes["unit_of_measurement"] == "h"

    last_cost_state = hass.states.get("sensor.home_charger_single_last_session_cost")
    assert last_cost_state is not None
    assert float(last_cost_state.state) == 9.98

    last_card_state = hass.states.get("sensor.home_charger_single_last_session_card")
    assert last_card_state is not None
    assert last_card_state.state == "NL-50F-123456-7"


async def test_sensors_multi_channel_station(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test sensor platform entities for a multi-channel charging station."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Channel 1 status (CHARGING)
    ch1_state = hass.states.get("sensor.office_charger_dual_ch_1_status")
    assert ch1_state is not None
    assert ch1_state.state == "charging"

    # Channel 2 status (AVAILABLE)
    ch2_state = hass.states.get("sensor.office_charger_dual_ch_2_status")
    assert ch2_state is not None
    assert ch2_state.state == "available"

    # Channel 2 session energy should be 0.0 (active transaction is on channel 1)
    ch2_energy = hass.states.get("sensor.office_charger_dual_ch_2_session_energy")
    assert ch2_energy is not None
    assert float(ch2_energy.state) == 0.0
