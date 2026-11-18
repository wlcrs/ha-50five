"""Sensor platform for 50five GraphQL integration with strong typing and enum options."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_RAW_TARIFF, ATTR_VAT, ATTR_VAT_MULTIPLIER
from .coordinator import FiftyFiveConfigEntry, FiftyFiveCoordinator
from .entity import FiftyFiveEntity
from .models import ActiveTransaction, GlobalStatus, StationData

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FiftyFiveSensorEntityDescription(SensorEntityDescription):
    """Describes 50five sensor entity."""

    value_fn: Callable[[StationData, int], Any]
    extra_state_attributes_fn: (
        Callable[[StationData, int], dict[str, Any] | None] | None
    ) = None


def _get_channel_status(data: StationData, channel_no: int) -> str:
    """Extract global status enum string for a channel."""
    ch = data.channels.get(channel_no)
    return ch.status.value if ch else GlobalStatus.UNKNOWN.value


def _matching_active_tx(
    data: StationData, channel_no: int
) -> ActiveTransaction | None:
    """Return active transaction if matching this channel."""
    tx = data.active_transaction
    if not tx:
        return None
    if tx.channel_visible_id is not None and str(tx.channel_visible_id) != str(
        channel_no
    ):
        return None
    return tx


def _get_session_duration(data: StationData, channel_no: int) -> float:
    """Return active charging session duration in seconds."""
    tx = _matching_active_tx(data, channel_no)
    return tx.duration_charging if tx else 0.0


def _get_session_energy_kwh(data: StationData, channel_no: int) -> float | None:
    """Return energy delivered in active charging session (kWh)."""
    tx = _matching_active_tx(data, channel_no)
    if tx is not None:
        return tx.energy_delivered
    ch = data.channels.get(channel_no)
    if ch and ch.status == GlobalStatus.CHARGING:
        return None
    return 0.0


def _get_session_cost(data: StationData, channel_no: int) -> float:
    """Return total cost of active charging session."""
    tx = _matching_active_tx(data, channel_no)
    return tx.total_amount if tx else 0.0


def _get_hcc_tariff(data: StationData, _ch: int) -> float | None:
    """Return Home Charging Compensation tariff (€/kWh)."""
    return data.hcc_tariff


def _get_hcc_tariff_attrs(data: StationData, _ch: int) -> dict[str, Any]:
    """Return extra state attributes for HCC tariff entity."""
    vat_pct = data.vat_percentage
    return {
        ATTR_RAW_TARIFF: data.raw_hcc_tariff,
        ATTR_VAT: int(vat_pct) if vat_pct.is_integer() else vat_pct,
        ATTR_VAT_MULTIPLIER: data.vat_multiplier,
    }


CHANNEL_SENSORS: tuple[FiftyFiveSensorEntityDescription, ...] = (
    FiftyFiveSensorEntityDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in GlobalStatus],
        icon="mdi:ev-station",
        value_fn=_get_channel_status,
    ),
    FiftyFiveSensorEntityDescription(
        key="session_energy",
        translation_key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_get_session_energy_kwh,
    ),
    FiftyFiveSensorEntityDescription(
        key="session_time",
        translation_key="session_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=2,
        value_fn=_get_session_duration,
    ),
    FiftyFiveSensorEntityDescription(
        key="session_cost",
        translation_key="session_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_EURO,
        value_fn=_get_session_cost,
    ),
)

STATION_SENSORS: tuple[FiftyFiveSensorEntityDescription, ...] = (
    FiftyFiveSensorEntityDescription(
        key="hcc_tariff",
        translation_key="hcc_tariff",
        native_unit_of_measurement=f"{CURRENCY_EURO}/kWh",
        suggested_display_precision=4,
        icon="mdi:currency-eur",
        value_fn=_get_hcc_tariff,
        extra_state_attributes_fn=_get_hcc_tariff_attrs,
    ),
    # Last completed transaction sensors
    FiftyFiveSensorEntityDescription(
        key="last_transaction_energy",
        translation_key="last_transaction_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data, _ch: (
            data.station.last_transaction.total_energy if data.station.last_transaction else None
        ),
    ),
    FiftyFiveSensorEntityDescription(
        key="last_transaction_duration",
        translation_key="last_transaction_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda data, _ch: (
            data.station.last_transaction.total_duration if data.station.last_transaction else None
        ),
    ),
    FiftyFiveSensorEntityDescription(
        key="last_transaction_idle_time",
        translation_key="last_transaction_idle_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda data, _ch: (
            data.station.last_transaction.total_idle_time if data.station.last_transaction else None
        ),
    ),
    FiftyFiveSensorEntityDescription(
        key="last_transaction_start_time",
        translation_key="last_transaction_start_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data, _ch: (
            data.station.last_transaction.start_date if data.station.last_transaction else None
        ),
    ),
    FiftyFiveSensorEntityDescription(
        key="last_transaction_end_time",
        translation_key="last_transaction_end_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data, _ch: (
            data.station.last_transaction.last_update_date if data.station.last_transaction else None
        ),
    ),
    FiftyFiveSensorEntityDescription(
        key="last_transaction_cost",
        translation_key="last_transaction_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_EURO,
        value_fn=lambda data, _ch: (
            data.station.last_transaction.total_cost if data.station.last_transaction else None
        ),
    ),
    FiftyFiveSensorEntityDescription(
        key="last_transaction_card",
        translation_key="last_transaction_card",
        icon="mdi:card-account-details-outline",
        value_fn=lambda data, _ch: (
            data.station.last_transaction.card_id if data.station.last_transaction else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FiftyFiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 50five sensors."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = []

    for spot_id in coordinator.data:
        station_data = coordinator.data[spot_id]
        num_channels = station_data.num_channels

        # 1. Per-channel sensors
        for ch in range(1, num_channels + 1):
            for desc in CHANNEL_SENSORS:
                entities.append(
                    FiftyFiveChannelSensor(
                        coordinator,
                        spot_id,
                        desc,
                        channel_no=ch,
                        is_multi_channel=num_channels > 1,
                    )
                )

        # 2. Station-level sensors
        for desc in STATION_SENSORS:
            entities.append(
                FiftyFiveStationSensor(
                    coordinator,
                    spot_id,
                    desc,
                )
            )

    async_add_entities(entities)


class FiftyFiveBaseSensor(FiftyFiveEntity, SensorEntity):
    """Base sensor for 50five."""

    entity_description: FiftyFiveSensorEntityDescription

    def __init__(
        self,
        coordinator: FiftyFiveCoordinator,
        spot_id: str,
        description: FiftyFiveSensorEntityDescription,
    ) -> None:
        """Initialize base sensor."""
        super().__init__(coordinator, spot_id)
        self.entity_description = description
        station_data = coordinator.data.get(spot_id) if coordinator.data else None
        if station_data:
            currency = station_data.currency
            if description.key == "hcc_tariff":
                self._attr_native_unit_of_measurement = f"{currency}/kWh"
            elif description.key in ("session_cost", "last_transaction_cost"):
                self._attr_native_unit_of_measurement = currency

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        if self.entity_description.extra_state_attributes_fn is None:
            return None
        station_data = self.coordinator.data.get(self._spot_id)
        if not station_data:
            return None
        return self.entity_description.extra_state_attributes_fn(
            station_data, getattr(self, "_channel_no", 1)
        )


class FiftyFiveChannelSensor(FiftyFiveBaseSensor):
    """Sensor tied to a specific charging channel/connector."""

    def __init__(
        self,
        coordinator: FiftyFiveCoordinator,
        spot_id: str,
        description: FiftyFiveSensorEntityDescription,
        channel_no: int = 1,
        is_multi_channel: bool = False,
    ) -> None:
        """Initialize channel sensor."""
        super().__init__(coordinator, spot_id, description)
        self._channel_no = channel_no
        self._is_multi = is_multi_channel

        if is_multi_channel:
            self._attr_unique_id = f"{spot_id}_ch{channel_no}_{description.key}"
            self._attr_translation_key = f"channel_{description.translation_key}"
            self._attr_translation_placeholders = {"channel": str(channel_no)}
        else:
            self._attr_unique_id = f"{spot_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return current native value."""
        station_data = self.coordinator.data.get(self._spot_id)
        if not station_data:
            return None
        return self.entity_description.value_fn(station_data, self._channel_no)


class FiftyFiveStationSensor(FiftyFiveBaseSensor):
    """Sensor tied to the charging station as a whole."""

    def __init__(
        self,
        coordinator: FiftyFiveCoordinator,
        spot_id: str,
        description: FiftyFiveSensorEntityDescription,
    ) -> None:
        """Initialize station sensor."""
        super().__init__(coordinator, spot_id, description)
        self._attr_unique_id = f"{spot_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return current native value."""
        station_data = self.coordinator.data.get(self._spot_id)
        if not station_data:
            return None
        return self.entity_description.value_fn(station_data, 1)
