"""Diagnostics support for the 50five integration."""

from __future__ import annotations

import dataclasses
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_ACCESS_TOKEN, CONF_CARD_ID, CONF_CUSTOMER_ID, CONF_DEVICE_ID
from .coordinator import FiftyFiveCoordinator
from .redact import censor, mask_value

TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_CARD_ID,
    CONF_CUSTOMER_ID,
    CONF_DEVICE_ID,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a 50five config entry."""
    data: dict[str, Any] = {
        "config_entry": async_redact_data(config_entry.as_dict(), TO_REDACT),
    }

    coordinator: FiftyFiveCoordinator | None = getattr(
        config_entry, "runtime_data", None
    )
    if coordinator is None:
        return data

    client = coordinator.client
    data["client"] = {
        "username": mask_value(client.username),
        "device_id": mask_value(client.device_id),
        "customer_id": mask_value(client.customer_id) if client.customer_id else None,
        "base_url": client.base_url,
        "token_expires_at": (
            client.token_expires_at.isoformat() if client.token_expires_at else None
        ),
        "is_token_expired": client.is_token_expired(),
    }

    if coordinator.data:
        data["stations"] = {
            mask_value(station_id): censor(dataclasses.asdict(station_data))
            for station_id, station_data in coordinator.data.items()
        }

    return data
