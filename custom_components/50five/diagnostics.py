"""Diagnostics support for the 50five integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_ACCESS_TOKEN, CONF_CARD_ID, CONF_DEVICE_ID
from .coordinator import FiftyFiveCoordinator

TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_CARD_ID,
    CONF_DEVICE_ID,
}


def _anonymize_identifier(value: str) -> str:
    """Return an identifier with only its first and last two characters."""
    if len(value) <= 4:
        return "**REDACTED**"
    return f"{value[:2]}***{value[-2:]}"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a 50five config entry."""
    data: dict[str, Any] = {
        "config_entry": async_redact_data(config_entry.as_dict(), TO_REDACT),
    }

    data_obj = getattr(config_entry, "runtime_data", None)
    coordinator: FiftyFiveCoordinator | None = None
    config_coordinator = None
    if data_obj is not None:
        if hasattr(data_obj, "coordinator"):
            coordinator = data_obj.coordinator
            config_coordinator = getattr(data_obj, "config_coordinator", None)
        elif isinstance(data_obj, FiftyFiveCoordinator):
            coordinator = data_obj

    if coordinator is not None and coordinator.data:
        stations_data = []
        for st_data in coordinator.data.values():
            station = st_data.station
            tx = st_data.last_transaction
            stations_data.append(
                {
                    "id": _anonymize_identifier(station.id),
                    "name": station.name,
                    "num_channels": st_data.num_channels,
                    "manufacturer": {
                        "vendor": station.manufacturer.vendor,
                        "model": station.manufacturer.model,
                    },
                    "access_type": station.access_options.access_type.value,
                    "hcc_enabled": station.hcc.hcc_enabled,
                    "hcc_tariff": station.hcc.hcc_tariff,
                    "raw_hcc_tariff": station.hcc.raw_hcc_tariff,
                    "net_balanced_charging": (
                        config_coordinator.data.get(station.id)
                        if config_coordinator and config_coordinator.data
                        else None
                    ),
                    "has_last_transaction": tx is not None,
                    "last_transaction_energy": tx.total_energy if tx else None,
                }
            )
        data["stations"] = stations_data

    return data
