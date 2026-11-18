"""Number platform for 50five GraphQL integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import CURRENCY_EURO, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEFAULT_HCC_TARIFF_MAX,
    DEFAULT_HCC_TARIFF_MIN,
    DEFAULT_VAT_MULTIPLIER,
    HCC_TARIFF_HIDDEN_PROVIDER_CATEGORIES,
)
from .coordinator import FiftyFiveConfigEntry, FiftyFiveCoordinator
from .entity import FiftyFiveEntity


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

    tariff_range = coordinator.reimbursement_tariff_range
    raw_min = (
        tariff_range.min
        if tariff_range and tariff_range.min is not None
        else DEFAULT_HCC_TARIFF_MIN
    )
    raw_max = (
        tariff_range.max
        if tariff_range and tariff_range.max is not None
        else DEFAULT_HCC_TARIFF_MAX
    )

    async_add_entities(
        FiftyFiveHccTariffNumber(
            coordinator,
            spot_id,
            round(raw_min * station_data.vat_multiplier, 4),
            round(raw_max * station_data.vat_multiplier, 4),
        )
        for spot_id, station_data in coordinator.data.items()
    )


class FiftyFiveHccTariffNumber(FiftyFiveEntity, NumberEntity):
    """Representation of a 50five HCC tariff."""

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
        super().__init__(coordinator, spot_id)
        self._attr_native_min_value = tariff_min
        self._attr_native_max_value = tariff_max
        self._attr_unique_id = f"{spot_id}_hcc_tariff"
        station_data = coordinator.data.get(spot_id) if coordinator.data else None
        if station_data:
            self._attr_native_unit_of_measurement = f"{station_data.currency}/kWh"

    @property
    def native_value(self) -> float | None:
        """Return the VAT-inclusive HCC tariff."""
        station_data = self.coordinator.data.get(self._spot_id)
        return station_data.hcc_tariff if station_data else None

    async def async_set_native_value(self, value: float) -> None:
        """Convert the VAT-inclusive tariff to net and update the backend."""
        station_data = (
            self.coordinator.data.get(self._spot_id) if self.coordinator.data else None
        )
        vat_multiplier = (
            station_data.vat_multiplier if station_data else DEFAULT_VAT_MULTIPLIER
        )
        net_tariff = round(value / vat_multiplier, 4)
        await self.coordinator.client.update_hcc_tariff(self._spot_id, net_tariff)
        await self.coordinator.async_request_refresh()
