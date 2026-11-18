"""Switch platform for 50five GraphQL integration with optimistic state updates."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CARD_ID
from .coordinator import FiftyFiveConfigEntry, FiftyFiveCoordinator
from .entity import FiftyFiveEntity
from .models import GlobalStatus

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FiftyFiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 50five charging switches."""
    card_id = entry.options.get(CONF_CARD_ID) or entry.data.get(CONF_CARD_ID)
    if not card_id:
        _LOGGER.debug("No charge card configured, skipping charging switch creation")
        return

    coordinator = entry.runtime_data

    entities: list[SwitchEntity] = []
    for spot_id in coordinator.data:
        station_data = coordinator.data[spot_id]
        num_channels = station_data.num_channels

        for ch in range(1, num_channels + 1):
            ch_switch = FiftyFiveChargingSwitch(
                coordinator,
                spot_id,
                entry,
                channel_no=ch,
                is_multi_channel=num_channels > 1,
            )
            entities.append(ch_switch)

    async_add_entities(entities)


class FiftyFiveChargingSwitch(FiftyFiveEntity, SwitchEntity):
    """Representation of a 50five charging switch."""

    _attr_icon = "mdi:ev-station"

    def __init__(
        self,
        coordinator: FiftyFiveCoordinator,
        spot_id: str,
        entry: FiftyFiveConfigEntry,
        channel_no: int = 1,
        is_multi_channel: bool = False,
    ) -> None:
        """Initialize charging switch."""
        super().__init__(coordinator, spot_id)
        self._entry = entry
        self._channel_no = channel_no
        self._is_multi = is_multi_channel

        self._card_id = (
            entry.options.get(CONF_CARD_ID) or entry.data.get(CONF_CARD_ID) or ""
        )

        if is_multi_channel:
            self._attr_unique_id = f"{spot_id}_ch{channel_no}_charging"
            self._attr_translation_key = "channel_charging"
            self._attr_translation_placeholders = {
                "channel": str(channel_no),
                "card_id": self._card_id,
            }
        else:
            self._attr_unique_id = f"{spot_id}_charging"
            self._attr_translation_key = "charging"
            self._attr_translation_placeholders = {"card_id": self._card_id}

    def _backend_is_on(self) -> bool:
        """Return whether the backend currently reports an active charging session."""
        station_data = self.coordinator.data.get(self._spot_id)
        if not station_data:
            return False

        ch = station_data.channels.get(self._channel_no)
        if ch and ch.status in (
            GlobalStatus.CHARGING,
            GlobalStatus.OCCUPIED,
            GlobalStatus.PREPARING,
        ):
            return True

        active_tx = station_data.active_transaction
        if active_tx:
            ch_visible = active_tx.channel_visible_id
            if ch_visible is None or str(ch_visible) == str(self._channel_no):
                return True

        return False

    @property
    def is_on(self) -> bool:
        """Return true if charging session is active on this channel."""
        backend_on = self._backend_is_on()
        optimistic = self.coordinator.get_optimistic_charging_state(
            self._spot_id,
            self._get_channel_id(),
            backend_is_on=backend_on,
        )
        return optimistic if optimistic is not None else backend_on

    @callback
    def _handle_coordinator_update(self) -> None:
        """Log when a retrieved backend state is overridden by optimistic state."""
        channel_id = self._get_channel_id()
        backend_on = self._backend_is_on()
        optimistic = self.coordinator.get_optimistic_charging_state(
            self._spot_id,
            channel_id,
            backend_is_on=backend_on,
        )
        if optimistic is not None and optimistic != backend_on:
            _LOGGER.info(
                "Overriding backend charging state (%s) with optimistic state (%s) for station %s, channel %s",
                backend_on,
                optimistic,
                self._spot_id,
                channel_id,
            )
        super()._handle_coordinator_update()

    def _get_channel_id(self) -> str:
        """Resolve the GraphQL channel ID."""
        return self.coordinator.get_channel_id(self._spot_id, self._channel_no)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start charging session on this channel with immediate UI feedback."""
        channel_id = self._get_channel_id()

        _LOGGER.info(
            "Starting charging session on station %s, channel %s (card: %s)",
            self._spot_id,
            channel_id,
            self._card_id or "default/none",
        )

        # 1. Immediately update UI state with 4-minute grace window
        self.coordinator.set_optimistic_charging_state(
            self._spot_id, channel_id, True
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
            self.coordinator.clear_optimistic_charging_state(self._spot_id, channel_id)
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop charging session on this channel with immediate UI feedback."""
        channel_id = self._get_channel_id()

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
            self.coordinator.clear_optimistic_charging_state(self._spot_id, channel_id)
            raise
