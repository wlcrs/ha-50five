"""Base entity for the 50five GraphQL integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FiftyFiveCoordinator


class FiftyFiveEntity(CoordinatorEntity[FiftyFiveCoordinator]):
    """Base entity for 50five charge station entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FiftyFiveCoordinator, spot_id: str) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._spot_id = spot_id

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
