"""Binary sensor platform for 50five GraphQL integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import FiftyFiveConfigEntry, FiftyFiveCoordinator
from .entity import FiftyFiveEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FiftyFiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 50five binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        FiftyFiveHccEnabledBinarySensor(coordinator, spot_id)
        for spot_id in coordinator.data
    )


class FiftyFiveHccEnabledBinarySensor(FiftyFiveEntity, BinarySensorEntity):
    """Binary sensor indicating whether Home Charging Compensation is enabled."""

    _attr_translation_key = "hcc_enabled"
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(self, coordinator: FiftyFiveCoordinator, spot_id: str) -> None:
        """Initialize HCC enabled binary sensor."""
        super().__init__(coordinator, spot_id)
        self._attr_unique_id = f"{spot_id}_hcc_enabled"

    @property
    def is_on(self) -> bool | None:
        """Return whether Home Charging Compensation is enabled."""
        station_data = self.coordinator.data.get(self._spot_id)
        if not station_data:
            return None
        return bool(station_data.station.hcc and station_data.station.hcc.hcc_enabled)
