"""Tests for the 50five per-card charging switch platform."""

import importlib
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

const = importlib.import_module("custom_components.50five.const")
coordinator_mod = importlib.import_module("custom_components.50five.coordinator")
exceptions = importlib.import_module("custom_components.50five.exceptions")
models = importlib.import_module("custom_components.50five.models")

CONF_CARD_IDS = const.CONF_CARD_IDS
DOMAIN = const.DOMAIN
FiftyFiveApiError = exceptions.FiftyFiveApiError
CompletedTransaction = models.CompletedTransaction

from .const import (
    MOCK_CARD_ID,
    MOCK_CARD_ID_2,
    MOCK_CONFIG_DATA,
    MOCK_GET_TRANSACTION_RESPONSE,
    MOCK_MULTI_STATION_ID,
    MOCK_STATION_ID,
    MOCK_USERNAME,
)

SINGLE_CARD1_ENTITY = "switch.home_charger_single_charge_with_card_nl_50f_123456_7"
SINGLE_CARD2_ENTITY = "switch.home_charger_single_charge_with_card_nl_50f_999999_9"
MULTI_CH1_CARD1_ENTITY = (
    "switch.office_charger_dual_ch_1_charge_with_card_nl_50f_123456_7"
)
MULTI_CH1_CARD2_ENTITY = (
    "switch.office_charger_dual_ch_1_charge_with_card_nl_50f_999999_9"
)
MULTI_CH2_CARD1_ENTITY = (
    "switch.office_charger_dual_ch_2_charge_with_card_nl_50f_123456_7"
)
MULTI_CH2_CARD2_ENTITY = (
    "switch.office_charger_dual_ch_2_charge_with_card_nl_50f_999999_9"
)


async def test_switch_creation_skipped_without_checked_cards(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test switch entities are not created when no charge cards are checked."""
    entry_data = dict(MOCK_CONFIG_DATA)
    entry_data[CONF_CARD_IDS] = []

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_USERNAME,
        data=entry_data,
        options={},
        entry_id="test_no_cards",
        version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    switches = hass.states.async_entity_ids(SWITCH_DOMAIN)
    assert len(switches) == 0


async def test_only_checked_cards_are_exposed_as_switches(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test only cards checked in config/options are exposed, hiding unchecked account cards."""
    entry_data = dict(MOCK_CONFIG_DATA)
    entry_data[CONF_CARD_IDS] = [MOCK_CARD_ID]

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_USERNAME,
        data=entry_data,
        options={},
        entry_id="test_one_card",
        version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Only card 1 (3 channels across 2 stations = 3 switches); card 2 is NOT exposed
    assert len(hass.states.async_entity_ids(SWITCH_DOMAIN)) == 3
    assert hass.states.get(SINGLE_CARD1_ENTITY) is not None
    assert hass.states.get(SINGLE_CARD2_ENTITY) is None
    assert hass.states.get(MULTI_CH1_CARD1_ENTITY) is not None
    assert hass.states.get(MULTI_CH1_CARD2_ENTITY) is None


async def test_switches_created_for_every_card_and_api_active_card_turns_on_matching_switch(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mock_active_transaction,
) -> None:
    """Test per-card switches are created and API-reported card activates only the matching switch."""
    mock_api_client.get_active_transaction.return_value = (
        mock_active_transaction.model_copy(update={"channel_id": "ch_999_1"})
    )
    mock_api_client.get_transaction.return_value = CompletedTransaction.model_validate(
        MOCK_GET_TRANSACTION_RESPONSE["getTransaction"]
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # 2 cards x (1 channel on single + 2 channels on multi) = 6 switches
    assert len(hass.states.async_entity_ids(SWITCH_DOMAIN)) == 6

    # Single-channel charger has active transaction with card 1 via getTransaction -> card 1 ON, card 2 OFF
    assert hass.states.get(SINGLE_CARD1_ENTITY).state == STATE_ON
    assert hass.states.get(SINGLE_CARD2_ENTITY).state == STATE_OFF

    # Multi-channel charger ch1 has CHARGING status without card info -> both OFF
    assert hass.states.get(MULTI_CH1_CARD1_ENTITY).state == STATE_OFF
    assert hass.states.get(MULTI_CH1_CARD2_ENTITY).state == STATE_OFF

    # Multi-channel charger ch2 is AVAILABLE -> both OFF
    assert hass.states.get(MULTI_CH2_CARD1_ENTITY).state == STATE_OFF
    assert hass.states.get(MULTI_CH2_CARD2_ENTITY).state == STATE_OFF


async def test_physical_card_swipe_logs_info_once_and_leaves_all_switches_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test charging without API card info and without HA start logs INFO once and keeps switches OFF."""
    mock_api_client.get_active_transaction.return_value = None
    mock_config_entry.add_to_hass(hass)

    with caplog.at_level("INFO"):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Multi-channel ch1 is Charging, no card known -> both card switches remain OFF
    assert hass.states.get(MULTI_CH1_CARD1_ENTITY).state == STATE_OFF
    assert hass.states.get(MULTI_CH1_CARD2_ENTITY).state == STATE_OFF

    info_messages = [
        rec.message
        for rec in caplog.records
        if "did not report which charge card is active" in rec.message
    ]
    assert len(info_messages) == 1

    # Subsequent poll while still charging should not spam the INFO log
    caplog.clear()
    with caplog.at_level("INFO"):
        await mock_config_entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    assert not any(
        "did not report which charge card is active" in rec.message
        for rec in caplog.records
    )


async def test_switch_turn_on_tracks_card_across_backend_confirmation(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mock_charge_stations,
) -> None:
    """Test turning on card 2 switch turns only card 2 ON even when API omits card info."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        SWITCH_DOMAIN,
        "turn_on",
        {"entity_id": MULTI_CH2_CARD2_ENTITY},
        blocking=True,
    )

    mock_api_client.start_charging.assert_called_once_with(
        charge_station_id=MOCK_MULTI_STATION_ID,
        channel_id="ch_888_2",
        card=MOCK_CARD_ID_2,
    )
    assert hass.states.get(MULTI_CH2_CARD2_ENTITY).state == STATE_ON
    assert hass.states.get(MULTI_CH2_CARD1_ENTITY).state == STATE_OFF

    # Backend now confirms ch2 is Charging (without reporting card ID) -> card 2 stays ON, card 1 OFF
    updated_stations = list(mock_charge_stations)
    multi = updated_stations[1]
    updated_channels = [
        multi.channels[0],
        multi.channels[1].model_copy(
            update={"global_status": models.ChannelGlobalStatus.CHARGING}
        ),
    ]
    updated_stations[1] = multi.model_copy(update={"channels": updated_channels})
    mock_api_client.get_customer_charge_stations.return_value = updated_stations

    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(MULTI_CH2_CARD2_ENTITY).state == STATE_ON
    assert hass.states.get(MULTI_CH2_CARD1_ENTITY).state == STATE_OFF

    # Backend later reports Available -> remembered card cleared, both switches OFF
    mock_api_client.get_customer_charge_stations.return_value = mock_charge_stations
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(MULTI_CH2_CARD2_ENTITY).state == STATE_OFF
    assert hass.states.get(MULTI_CH2_CARD1_ENTITY).state == STATE_OFF


async def test_switch_turn_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test turning off charging switch."""
    mock_api_client.get_transaction.return_value = CompletedTransaction.model_validate(
        MOCK_GET_TRANSACTION_RESPONSE["getTransaction"]
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        SWITCH_DOMAIN,
        "turn_off",
        {"entity_id": SINGLE_CARD1_ENTITY},
        blocking=True,
    )

    mock_api_client.stop_charging.assert_called_once_with(
        charge_station_id=MOCK_STATION_ID,
        channel_id="ch_999_1",
    )
    assert hass.states.get(SINGLE_CARD1_ENTITY).state == STATE_OFF


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

    with pytest.raises((FiftyFiveApiError, HomeAssistantError)):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            "turn_on",
            {"entity_id": MULTI_CH2_CARD1_ENTITY},
            blocking=True,
        )

    assert hass.states.get(MULTI_CH2_CARD1_ENTITY).state == STATE_OFF
    assert (
        mock_config_entry.runtime_data.get_last_used_card(
            MOCK_MULTI_STATION_ID, "ch_888_2"
        )
        is None
    )


async def test_switch_turn_off_error_rollback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test turning off switch rolls back optimistic state on error."""
    mock_api_client.get_transaction.return_value = CompletedTransaction.model_validate(
        MOCK_GET_TRANSACTION_RESPONSE["getTransaction"]
    )
    mock_api_client.stop_charging.side_effect = FiftyFiveApiError("LMS failed")
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises((FiftyFiveApiError, HomeAssistantError)):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            "turn_off",
            {"entity_id": SINGLE_CARD1_ENTITY},
            blocking=True,
        )

    # State should remain ON
    assert hass.states.get(SINGLE_CARD1_ENTITY).state == STATE_ON


async def test_switch_optimistic_grace_window_and_expiry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mock_charge_stations,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test switch holds optimistic ON across polls for 4 minutes, then expires."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(MULTI_CH2_CARD1_ENTITY).state == STATE_OFF

    now = [1000.0]
    with patch.object(
        coordinator_mod.time,
        "monotonic",
        side_effect=lambda: now[0],
    ):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            "turn_on",
            {"entity_id": MULTI_CH2_CARD1_ENTITY},
            blocking=True,
        )
        assert hass.states.get(MULTI_CH2_CARD1_ENTITY).state == STATE_ON
        assert hass.states.get(MULTI_CH2_CARD2_ENTITY).state == STATE_OFF

        # Coordinator poll at +60s while backend still reports AVAILABLE -> stays ON
        now[0] = 1060.0
        with caplog.at_level("DEBUG"):
            await mock_config_entry.runtime_data.async_refresh()
            await hass.async_block_till_done()
        assert hass.states.get(MULTI_CH2_CARD1_ENTITY).state == STATE_ON
        assert "Overriding backend charging state" in caplog.text

        # Grace window expires at +240s without backend confirmation -> reverts to OFF
        now[0] = 1240.0
        await mock_config_entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(MULTI_CH2_CARD1_ENTITY).state == STATE_OFF
        assert (
            mock_config_entry.runtime_data.get_last_used_card(
                MOCK_MULTI_STATION_ID, "ch_888_2"
            )
            is None
        )


async def test_switch_survives_ha_restart_mid_session(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
    mock_charge_stations,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test remembered card persists across unload/reload while same session continues."""
    mock_api_client.get_active_transaction.return_value = None
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Start charging on ch2 with card 2
    await hass.services.async_call(
        SWITCH_DOMAIN,
        "turn_on",
        {"entity_id": MULTI_CH2_CARD2_ENTITY},
        blocking=True,
    )
    await hass.async_block_till_done()

    # Backend confirms ch2 is Charging with a status change timestamp
    charging_stations = list(mock_charge_stations)
    multi = charging_stations[1]
    charging_stations[1] = multi.model_copy(
        update={
            "channels": [
                multi.channels[0].model_copy(
                    update={"global_status": models.ChannelGlobalStatus.AVAILABLE}
                ),
                multi.channels[1].model_copy(
                    update={
                        "global_status": models.ChannelGlobalStatus.CHARGING,
                        "last_status_change_date": datetime.fromisoformat(
                            "2026-11-22T07:39:50+01:00"
                        ),
                    }
                ),
            ]
        }
    )
    mock_api_client.get_customer_charge_stations.return_value = charging_stations
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(MULTI_CH2_CARD2_ENTITY).state == STATE_ON
    assert hass.states.get(MULTI_CH2_CARD1_ENTITY).state == STATE_OFF

    # Simulate HA restart (unload & setup fresh coordinator with same entry_id)
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    caplog.clear()
    with caplog.at_level("INFO"):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Same session still active -> card 2 restored ON, card 1 OFF, no unknown-card INFO log
    assert hass.states.get(MULTI_CH2_CARD2_ENTITY).state == STATE_ON
    assert hass.states.get(MULTI_CH2_CARD1_ENTITY).state == STATE_OFF
    assert not any(
        "did not report which charge card is active" in rec.message
        for rec in caplog.records
    )

    # Simulate restart after old session ended and a new physical-card session started
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    new_session_stations = list(charging_stations)
    new_multi = new_session_stations[1]
    new_session_stations[1] = new_multi.model_copy(
        update={
            "channels": [
                new_multi.channels[0],
                new_multi.channels[1].model_copy(
                    update={
                        "global_status": models.ChannelGlobalStatus.CHARGING,
                        "last_status_change_date": datetime.fromisoformat(
                            "2026-11-22T11:15:00+01:00"
                        ),
                    }
                ),
            ]
        }
    )
    mock_api_client.get_customer_charge_stations.return_value = new_session_stations

    caplog.clear()
    with caplog.at_level("INFO"):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # New session timestamp mismatch -> stale card discarded, both switches OFF, INFO logged
    assert hass.states.get(MULTI_CH2_CARD2_ENTITY).state == STATE_OFF
    assert hass.states.get(MULTI_CH2_CARD1_ENTITY).state == STATE_OFF
    assert any(
        "did not report which charge card is active" in rec.message
        for rec in caplog.records
    )
