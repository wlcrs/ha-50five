"""Switch platform for 50five GraphQL integration with optimistic state updates."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ACTION_SETTLE_DELAY_SEC,
    CONF_CARD_ID,
    DOMAIN,
)
from .coordinator import (
    FiftyFiveConfigEntry,
    FiftyFiveCoordinator,
    FiftyFiveConfigurationUpdateCoordinator,
)
from .models import GlobalStatus

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FiftyFiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 50five switches."""
    data = entry.runtime_data
    coordinator = data.coordinator
    config_coordinator = data.config_coordinator
    entities: list[SwitchEntity] = []

    card_id = entry.options.get(CONF_CARD_ID) or entry.data.get(CONF_CARD_ID)

    for spot_id in coordinator.data:
        station_data = coordinator.data[spot_id]

        # Net balanced charging switch (per station, managed via 15-minute coordinator)
        nbc_switch = FiftyFiveNetBalancedChargingSwitch(
            config_coordinator,
            coordinator,
            spot_id,
        )
        entities.append(nbc_switch)
        coordinator.entities[nbc_switch.unique_id] = nbc_switch

        # Charging session switches (require a card configured)
        if card_id:
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
                coordinator.entities[ch_switch.unique_id] = ch_switch
        else:
            _LOGGER.debug(
                "No charge card configured, skipping charging switch creation for %s",
                spot_id,
            )

    async_add_entities(entities)


class FiftyFiveChargingSwitch(CoordinatorEntity[FiftyFiveCoordinator], SwitchEntity):
    """Representation of a 50five charging switch."""

    _attr_has_entity_name = True
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
        super().__init__(coordinator)
        self._spot_id = spot_id
        self._entry = entry
        self._channel_no = channel_no
        self._is_multi = is_multi_channel
        self._optimistic_is_on: bool | None = None

        station_data = coordinator.data.get(spot_id)
        station_name = (
            station_data.station.name if station_data else f"Charge Station {spot_id}"
        )
        mfg = station_data.station.manufacturer if station_data else None

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

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, spot_id)},
            name=station_name,
            manufacturer=mfg.vendor if mfg and mfg.vendor else "50five / LMS",
            model=mfg.model if mfg and mfg.model else "Charging Station",
        )

    @property
    def available(self) -> bool:
        """Return if switch is available."""
        return self._spot_id in self.coordinator.data

    @property
    def is_on(self) -> bool:
        """Return true if charging session is active on this channel."""
        # Use optimistic state if an action is currently pending
        if self._optimistic_is_on is not None:
            return self._optimistic_is_on

        station_data = self.coordinator.data.get(self._spot_id)
        if not station_data:
            return False

        ch = station_data.channels.get(self._channel_no)
        if ch and ch.global_status in (
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

    def _get_channel_id(self) -> str:
        """Resolve the GraphQL channel ID."""
        return self.coordinator.get_channel_id(self._spot_id, self._channel_no)

    async def _async_schedule_refresh(self) -> None:
        """Schedule non-blocking deferred refresh to settle hardware state."""

        async def _delayed_refresh() -> None:
            await asyncio.sleep(ACTION_SETTLE_DELAY_SEC)
            self._optimistic_is_on = None
            await self.coordinator.async_request_refresh()

        self.hass.async_create_task(_delayed_refresh())

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start charging session on this channel with immediate UI feedback."""
        channel_id = self._get_channel_id()
        card_id = kwargs.get("card_id") or self._card_id

        _LOGGER.info(
            "Starting charging session on station %s, channel %s (card: %s)",
            self._spot_id,
            channel_id,
            card_id or "default/none",
        )

        # 1. Immediately update UI state
        self._optimistic_is_on = True
        self.async_write_ha_state()

        # 2. Perform API request
        try:
            await self.coordinator.client.start_charging(
                charge_station_id=self._spot_id,
                channel_id=channel_id,
                card=card_id,
            )
            # 3. Schedule non-blocking background refresh to confirm state from LMS backend
            await self._async_schedule_refresh()
        except Exception:
            _LOGGER.exception("Failed to start charging on %s", self._spot_id)
            self._optimistic_is_on = None
            self.async_write_ha_state()
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop charging session on this channel with immediate UI feedback."""
        channel_id = self._get_channel_id()

        _LOGGER.info(
            "Stopping charging session on station %s, channel %s",
            self._spot_id,
            channel_id,
        )

        # 1. Immediately update UI state
        self._optimistic_is_on = False
        self.async_write_ha_state()

        # 2. Perform API request
        try:
            await self.coordinator.client.stop_charging(
                charge_station_id=self._spot_id,
                channel_id=channel_id,
            )
            # 3. Schedule non-blocking background refresh to confirm state from LMS backend
            await self._async_schedule_refresh()
        except Exception:
            _LOGGER.exception("Failed to stop charging on %s", self._spot_id)
            self._optimistic_is_on = None
            self.async_write_ha_state()
            raise


class FiftyFiveNetBalancedChargingSwitch(
    CoordinatorEntity[FiftyFiveConfigurationUpdateCoordinator], SwitchEntity
):
    """Representation of a 50five Net Balanced Charging switch."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:scale-balance"
    _attr_translation_key = "net_balanced_charging"

    def __init__(
        self,
        coordinator: FiftyFiveConfigurationUpdateCoordinator,
        main_coordinator: FiftyFiveCoordinator,
        spot_id: str,
    ) -> None:
        """Initialize net balanced charging switch."""
        super().__init__(coordinator)
        self._main_coordinator = main_coordinator
        self._spot_id = spot_id
        self._optimistic_is_on: bool | None = None
        self._attr_unique_id = f"{spot_id}_net_balanced_charging"

        station_data = (
            main_coordinator.data.get(spot_id) if main_coordinator.data else None
        )
        station_name = (
            station_data.station.name if station_data else f"Charge Station {spot_id}"
        )
        mfg = station_data.station.manufacturer if station_data else None

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, spot_id)},
            name=station_name,
            manufacturer=mfg.vendor if mfg and mfg.vendor else "50five / LMS",
            model=mfg.model if mfg and mfg.model else "Charging Station",
        )

    @property
    def available(self) -> bool:
        """Return if switch is available."""
        return (
            self._spot_id in (self.coordinator.data or {})
            and self._spot_id in (self._main_coordinator.data or {})
        )

    @property
    def is_on(self) -> bool:
        """Return true if net balanced charging is enabled."""
        if self._optimistic_is_on is not None:
            return self._optimistic_is_on

        if self.coordinator.data is not None:
            return bool(self.coordinator.data.get(self._spot_id, False))

        return False

    async def _async_schedule_refresh(self) -> None:
        """Schedule non-blocking deferred refresh to settle hardware state."""

        async def _delayed_refresh() -> None:
            await asyncio.sleep(ACTION_SETTLE_DELAY_SEC)
            self._optimistic_is_on = None
            await self.coordinator.async_request_refresh()

        self.hass.async_create_task(_delayed_refresh())

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable net balanced charging."""
        self._optimistic_is_on = True
        self.async_write_ha_state()

        try:
            await self.coordinator.client.set_net_balanced_charging(
                self._spot_id, True
            )
            await self._async_schedule_refresh()
        except Exception:
            _LOGGER.exception(
                "Failed to enable net balanced charging on %s", self._spot_id
            )
            self._optimistic_is_on = None
            self.async_write_ha_state()
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable net balanced charging."""
        self._optimistic_is_on = False
        self.async_write_ha_state()

        try:
            await self.coordinator.client.set_net_balanced_charging(
                self._spot_id, False
            )
            await self._async_schedule_refresh()
        except Exception:
            _LOGGER.exception(
                "Failed to disable net balanced charging on %s", self._spot_id
            )
            self._optimistic_is_on = None
            self.async_write_ha_state()
            raise
