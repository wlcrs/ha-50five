"""Switch platform for 50five GraphQL integration with optimistic state updates."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import (
    FiftyFiveConfigEntry,
    FiftyFiveCoordinator,
    get_configured_card_ids,
)
from .entity import FiftyFiveEntity
from .models import ChargeCard

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FiftyFiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 50five charging switches for each configured charge card."""
    selected_card_ids = get_configured_card_ids(entry.data, entry.options)
    if not selected_card_ids:
        _LOGGER.debug("No charge cards configured, skipping charging switch creation")
        return

    coordinator = entry.runtime_data

    cards_by_identifier = {
        card.identifier: card
        for card in coordinator.charge_cards
        if card.identifier
    }
    cards = [
        cards_by_identifier.get(card_id, ChargeCard(external_id=card_id))
        for card_id in selected_card_ids
    ]

    entities: list[SwitchEntity] = []
    for spot_id in coordinator.data:
        station_data = coordinator.data[spot_id]
        num_channels = station_data.num_channels

        for ch in range(1, num_channels + 1):
            for card in cards:
                ch_switch = FiftyFiveChargingSwitch(
                    coordinator,
                    spot_id,
                    entry,
                    card=card,
                    channel_no=ch,
                    is_multi_channel=num_channels > 1,
                )
                entities.append(ch_switch)

    async_add_entities(entities)


class FiftyFiveChargingSwitch(FiftyFiveEntity, SwitchEntity):
    """Representation of a per-card 50five charging switch."""

    _attr_icon = "mdi:ev-station"

    def __init__(
        self,
        coordinator: FiftyFiveCoordinator,
        spot_id: str,
        entry: FiftyFiveConfigEntry,
        card: ChargeCard,
        channel_no: int = 1,
        is_multi_channel: bool = False,
    ) -> None:
        """Initialize charging switch."""
        super().__init__(coordinator, spot_id)
        self._entry = entry
        self._card = card
        self._card_id = card.identifier
        self._channel_no = channel_no
        self._is_multi = is_multi_channel

        if is_multi_channel:
            self._attr_unique_id = f"{spot_id}_ch{channel_no}_charging_{self._card_id}"
            self._attr_translation_key = "channel_charging"
            self._attr_translation_placeholders = {
                "channel": str(channel_no),
                "card_id": self._card_id,
            }
        else:
            self._attr_unique_id = f"{spot_id}_charging_{self._card_id}"
            self._attr_translation_key = "charging"
            self._attr_translation_placeholders = {"card_id": self._card_id}

    @property
    def _current_card(self) -> ChargeCard:
        """Return the latest ChargeCard metadata from the coordinator, with fallback."""
        for card in self.coordinator.charge_cards:
            if card.identifier == self._card_id:
                return card
        return self._card

    def _backend_channel_is_on(self) -> bool:
        """Return whether the backend currently reports any active session on this channel."""
        station_data = self.coordinator.data.get(self._spot_id)
        if not station_data:
            return False
        return station_data.is_channel_charging(self._channel_no)

    def _backend_is_on(self) -> bool:
        """Return whether the backend (or HA fallback) reports this card as active."""
        station_data = self.coordinator.data.get(self._spot_id)
        if not station_data or not station_data.is_channel_charging(self._channel_no):
            return False

        card = self._current_card

        # 1. Prefer schema-backed active transaction card from the backend
        backend_card_ids = station_data.get_backend_active_card_ids(self._channel_no)
        if backend_card_ids:
            return any(card.matches_identifier(cid) for cid in backend_card_ids)

        # 2. Graceful degradation: fall back to the card last used from HA
        remembered_card = self.coordinator.get_last_used_card(
            self._spot_id, self._get_channel_id()
        )
        if remembered_card:
            return card.matches_identifier(remembered_card)

        # 3. Unknown card (e.g. physical card swipe) -> leave all switches off
        return False

    @property
    def is_on(self) -> bool:
        """Return true if this card's charging session is active on this channel."""
        channel_id = self._get_channel_id()
        backend_channel_on = self._backend_channel_is_on()
        optimistic = self.coordinator.get_optimistic_charging_state(
            self._spot_id,
            channel_id,
            backend_is_on=backend_channel_on,
        )
        if optimistic is not None:
            target_is_on, optimistic_card_id = optimistic
            if not target_is_on:
                return False
            return self._current_card.matches_identifier(optimistic_card_id)

        return self._backend_is_on()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Log when a retrieved backend state is overridden by optimistic state."""
        channel_id = self._get_channel_id()
        backend_channel_on = self._backend_channel_is_on()
        backend_on = self._backend_is_on()
        optimistic = self.coordinator.get_optimistic_charging_state(
            self._spot_id,
            channel_id,
            backend_is_on=backend_channel_on,
        )
        if optimistic is not None:
            target_is_on, optimistic_card_id = optimistic
            effective_optimistic = (
                target_is_on
                and self._current_card.matches_identifier(optimistic_card_id)
            )
            if effective_optimistic != backend_on:
                _LOGGER.debug(
                    "Overriding backend charging state (%s) with optimistic state (%s) for station %s, channel %s (card: %s)",
                    backend_on,
                    effective_optimistic,
                    self._spot_id,
                    channel_id,
                    self._card_id,
                )
        super()._handle_coordinator_update()

    def _get_channel_id(self) -> str:
        """Resolve the GraphQL channel ID."""
        return self.coordinator.get_channel_id(self._spot_id, self._channel_no)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start charging session on this channel with immediate UI feedback."""
        channel_id = self._get_channel_id()
        prev_card = self.coordinator.get_last_used_card(self._spot_id, channel_id)

        _LOGGER.info(
            "Starting charging session on station %s, channel %s (card: %s)",
            self._spot_id,
            channel_id,
            self._card_id or "default/none",
        )

        # 1. Immediately update UI state with 4-minute grace window
        self.coordinator.set_optimistic_charging_state(
            self._spot_id,
            channel_id,
            True,
            card_id=self._card_id,
        )

        # 2. Perform API request
        try:
            await self.coordinator.client.start_charging(
                charge_station_id=self._spot_id,
                channel_id=channel_id,
                card=self._card_id,
            )
            # 3. Schedule non-blocking background refresh to confirm state from LMS backend
            self._schedule_delayed_refresh()
        except Exception:
            _LOGGER.exception("Failed to start charging on %s", self._spot_id)
            self.coordinator.clear_optimistic_charging_state(
                self._spot_id,
                channel_id,
                restore_card=True,
                restore_card_id=prev_card,
            )
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop charging session on this channel with immediate UI feedback."""
        channel_id = self._get_channel_id()
        prev_card = self.coordinator.get_last_used_card(self._spot_id, channel_id)

        _LOGGER.info(
            "Stopping charging session on station %s, channel %s",
            self._spot_id,
            channel_id,
        )

        # 1. Immediately update UI state with 4-minute grace window
        self.coordinator.set_optimistic_charging_state(
            self._spot_id, channel_id, False
        )

        # 2. Perform API request
        try:
            await self.coordinator.client.stop_charging(
                charge_station_id=self._spot_id,
                channel_id=channel_id,
            )
            # 3. Schedule non-blocking background refresh to confirm state from LMS backend
            self._schedule_delayed_refresh()
        except Exception:
            _LOGGER.exception("Failed to stop charging on %s", self._spot_id)
            self.coordinator.clear_optimistic_charging_state(
                self._spot_id,
                channel_id,
                restore_card=True,
                restore_card_id=prev_card,
            )
            raise
