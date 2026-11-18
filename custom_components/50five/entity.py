"""Base entity for the 50five GraphQL integration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from homeassistant.core import CALLBACK_TYPE
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ACTION_SETTLE_DELAY_SEC, DOMAIN
from .coordinator import FiftyFiveCoordinator


class FiftyFiveEntity(CoordinatorEntity[FiftyFiveCoordinator]):
    """Base entity for 50five charge station entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FiftyFiveCoordinator, spot_id: str) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._spot_id = spot_id
        self._refresh_unsub: CALLBACK_TYPE | None = None

        station_data = coordinator.data.get(spot_id) if coordinator.data else None
        station_name = (
            station_data.station.display_name
            if station_data
            else f"Charge Station {spot_id}"
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
        """Return if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._spot_id in self.coordinator.data
        )

    def _cancel_delayed_refresh(self) -> None:
        """Cancel any pending delayed refresh timer."""
        if self._refresh_unsub is not None:
            self._refresh_unsub()
            self._refresh_unsub = None

    def _schedule_delayed_refresh(
        self, on_before_refresh: Callable[[], None] | None = None
    ) -> None:
        """Schedule a debounced refresh after ACTION_SETTLE_DELAY_SEC."""
        self._cancel_delayed_refresh()

        async def _delayed_refresh(_now: datetime) -> None:
            self._refresh_unsub = None
            if on_before_refresh is not None:
                on_before_refresh()
            await self.coordinator.async_request_refresh()

        self._refresh_unsub = async_call_later(
            self.hass, ACTION_SETTLE_DELAY_SEC, _delayed_refresh
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any pending delayed refresh when removed from Home Assistant."""
        self._cancel_delayed_refresh()
        await super().async_will_remove_from_hass()
