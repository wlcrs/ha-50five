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
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_RAW_TARIFF, ATTR_VAT, ATTR_VAT_MULTIPLIER, DOMAIN
from .coordinator import FiftyFiveConfigEntry, FiftyFiveCoordinator
from .models import GlobalStatus, StationData

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
    return ch.global_status.value if ch else GlobalStatus.UNKNOWN.value


def _matching_active_tx(data: StationData, channel_no: int):
    """Return active transaction if matching this channel."""
    tx = data.active_transaction
    if not tx:
        return None
    if tx.channel_visible_id is not None and str(tx.channel_visible_id) != str(
        channel_no
    ):
        return None
    return tx


def _get_current_power(data: StationData, channel_no: int) -> float:
    """Return momentary charging power (kW)."""
    tx = _matching_active_tx(data, channel_no)
    if not tx:
        return 0.0
    return 0.0


def _get_session_duration(data: StationData, channel_no: int) -> float:
    """Return active charging session duration in seconds."""
    tx = _matching_active_tx(data, channel_no)
    return tx.duration_charging if tx else 0.0


def _get_session_energy_kwh(data: StationData, channel_no: int) -> float:
    """Return energy delivered in active charging session (kWh)."""
    tx = _matching_active_tx(data, channel_no)
    return tx.energy_delivered if tx else 0.0


def _get_session_cost(data: StationData, channel_no: int) -> float:
    """Return total cost of active charging session."""
    tx = _matching_active_tx(data, channel_no)
    return tx.total_amount if tx else 0.0


def _get_hcc_tariff(data: StationData, _ch: int) -> float | None:
    """Return Home Charging Compensation tariff (€/kWh)."""
    return data.station.hcc.hcc_tariff


def _get_hcc_tariff_attrs(data: StationData, _ch: int) -> dict[str, Any]:
    """Return extra state attributes for HCC tariff entity."""
    hcc = data.station.hcc
    vat_pct = hcc.vat_percentage
    return {
        ATTR_RAW_TARIFF: hcc.raw_hcc_tariff,
        ATTR_VAT: int(vat_pct) if vat_pct.is_integer() else vat_pct,
        ATTR_VAT_MULTIPLIER: hcc.vat_multiplier,
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
        key="current_power",
        translation_key="current_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        value_fn=_get_current_power,
    ),
    FiftyFiveSensorEntityDescription(
        key="session_energy",
        translation_key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:battery-charging",
        value_fn=_get_session_energy_kwh,
    ),
    FiftyFiveSensorEntityDescription(
        key="session_time",
        translation_key="session_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=2,
        icon="mdi:timer",
        value_fn=_get_session_duration,
    ),
    FiftyFiveSensorEntityDescription(
        key="session_cost",
        translation_key="session_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_EURO,
        icon="mdi:cash",
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
    FiftyFiveSensorEntityDescription(
        key="hcc_enabled",
        translation_key="hcc_enabled",
        icon="mdi:home-lightning-bolt",
        value_fn=lambda data, _ch: (
            "Enabled" if data.station.hcc.hcc_enabled else "Disabled"
        ),
    ),
    # Last completed transaction sensors
    FiftyFiveSensorEntityDescription(
        key="last_transaction_energy",
        translation_key="last_transaction_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:lightning-bolt-circle",
        value_fn=lambda data, _ch: (
            data.last_transaction.total_energy if data.last_transaction else None
        ),
    ),
    FiftyFiveSensorEntityDescription(
        key="last_transaction_duration",
        translation_key="last_transaction_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:timer-sand",
        value_fn=lambda data, _ch: (
            data.last_transaction.total_duration if data.last_transaction else None
        ),
    ),
    FiftyFiveSensorEntityDescription(
        key="last_transaction_start_time",
        translation_key="last_transaction_start_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-start",
        value_fn=lambda data, _ch: (
            data.last_transaction.start_datetime if data.last_transaction else None
        ),
    ),
    FiftyFiveSensorEntityDescription(
        key="last_transaction_end_time",
        translation_key="last_transaction_end_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-end",
        value_fn=lambda data, _ch: (
            data.last_transaction.end_datetime if data.last_transaction else None
        ),
    ),
    FiftyFiveSensorEntityDescription(
        key="last_transaction_cost",
        translation_key="last_transaction_cost",
        device_class=SensorDeviceClass.MONETARY,
        icon="mdi:cash-check",
        value_fn=lambda data, _ch: (
            data.last_transaction.total_cost if data.last_transaction else None
        ),
    ),
    FiftyFiveSensorEntityDescription(
        key="last_transaction_card",
        translation_key="last_transaction_card",
        icon="mdi:card-account-details-outline",
        value_fn=lambda data, _ch: (
            data.last_transaction.card_id if data.last_transaction else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FiftyFiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 50five sensors."""
    coordinator = entry.runtime_data.coordinator

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


class FiftyFiveBaseSensor(CoordinatorEntity[FiftyFiveCoordinator], SensorEntity):
    """Base sensor for 50five."""

    entity_description: FiftyFiveSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FiftyFiveCoordinator,
        spot_id: str,
        description: FiftyFiveSensorEntityDescription,
    ) -> None:
        """Initialize base sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._spot_id = spot_id

        station_data = coordinator.data.get(spot_id)
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
        """Return if entity is available."""
        return self._spot_id in self.coordinator.data

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
