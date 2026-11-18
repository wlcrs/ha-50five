"""Number platform for 50five GraphQL integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import CURRENCY_EURO, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_HCC_TARIFF_MAX,
    DEFAULT_HCC_TARIFF_MIN,
    DOMAIN,
    HCC_TARIFF_HIDDEN_PROVIDER_CATEGORIES,
)
from .coordinator import FiftyFiveConfigEntry, FiftyFiveCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FiftyFiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 50five number entities."""
    coordinator = entry.runtime_data
    provider_category = coordinator.provider_category
    if (
        not isinstance(provider_category, str)
        or provider_category.strip().upper()
        in HCC_TARIFF_HIDDEN_PROVIDER_CATEGORIES
    ):
        return

    tariff_range = await coordinator.client.get_reimbursement_tariff_range()
    tariff_min = (
        tariff_range.min
        if tariff_range and tariff_range.min is not None
        else DEFAULT_HCC_TARIFF_MIN
    )
    tariff_max = (
        tariff_range.max
        if tariff_range and tariff_range.max is not None
        else DEFAULT_HCC_TARIFF_MAX
    )

    async_add_entities(
        FiftyFiveHccTariffNumber(coordinator, spot_id, tariff_min, tariff_max)
        for spot_id in coordinator.data
    )


class FiftyFiveHccTariffNumber(
    CoordinatorEntity[FiftyFiveCoordinator], NumberEntity
):
    """Representation of a 50five HCC tariff."""

    _attr_has_entity_name = True
    _attr_translation_key = "hcc_tariff"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:currency-eur"
    _attr_mode = NumberMode.BOX
    _attr_native_step = 0.0001
    _attr_native_unit_of_measurement = f"{CURRENCY_EURO}/kWh"
    _attr_suggested_display_precision = 4

    def __init__(
        self,
        coordinator: FiftyFiveCoordinator,
        spot_id: str,
        tariff_min: float,
        tariff_max: float,
    ) -> None:
        """Initialize the HCC tariff number."""
        super().__init__(coordinator)
        self._spot_id = spot_id
        self._attr_native_min_value = tariff_min
        self._attr_native_max_value = tariff_max
        self._attr_unique_id = f"{spot_id}_hcc_tariff"

        station_data = coordinator.data.get(spot_id)
        station_name = (
            station_data.station.display_name
            if station_data
            else f"Charge Station {spot_id}"
        )
        manufacturer = station_data.station.manufacturer if station_data else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, spot_id)},
            name=station_name,
            manufacturer=(
                manufacturer.vendor
                if manufacturer and manufacturer.vendor
                else "50five / LMS"
            ),
            model=(
                manufacturer.model
                if manufacturer and manufacturer.model
                else "Charging Station"
            ),
        )

    @property
    def available(self) -> bool:
        """Return whether the station is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._spot_id in self.coordinator.data
        )

    @property
    def native_value(self) -> float | None:
        """Return the net HCC tariff registered by the backend."""
        station_data = self.coordinator.data.get(self._spot_id)
        return station_data.raw_hcc_tariff if station_data else None

    async def async_set_native_value(self, value: float) -> None:
        """Update the HCC tariff and refresh its verified backend value."""
        await self.coordinator.client.update_hcc_tariff(self._spot_id, value)
        await self.coordinator.async_request_refresh()
