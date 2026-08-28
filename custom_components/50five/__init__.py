# ruff: noqa: N999
"""The 50five GraphQL integration."""

from __future__ import annotations

import logging
import re
import uuid

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import service
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import FiftyFiveApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CARD_ID,
    CONF_CUSTOMER_ID,
    CONF_DEVICE_ID,
    CONF_TOKEN_EXPIRES_AT,
    DOMAIN,
)
from .coordinator import FiftyFiveConfigEntry, FiftyFiveCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.BUTTON]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _resolve_fiftyfive_target(
    hass: HomeAssistant,
    entity_id: str,
) -> tuple[FiftyFiveCoordinator, str, str] | None:
    """Resolve entity_id to (coordinator, spot_id, channel_id)."""
    entity_entry = er.async_get(hass).async_get(entity_id)
    if not entity_entry or not entity_entry.config_entry_id or not entity_entry.unique_id:
        return None

    config_entry: FiftyFiveConfigEntry | None = hass.config_entries.async_get_entry(
        entity_entry.config_entry_id
    )
    if not config_entry or not hasattr(config_entry, "runtime_data"):
        return None

    coordinator: FiftyFiveCoordinator = config_entry.runtime_data

    # Spot ID from HA Device Registry (with fallback to unique_id prefix)
    spot_id: str | None = None
    if entity_entry.device_id:
        dev = dr.async_get(hass).async_get(entity_entry.device_id)
        if dev:
            spot_id = next((ident for dom, ident in dev.identifiers if dom == DOMAIN), None)

    if not spot_id:
        spot_id = entity_entry.unique_id.split("_", 1)[0]
    if not spot_id:
        return None

    # Channel ID (matches _ch<N>_ in unique_id if multi-channel, else channel 1)
    m = re.search(r"_ch(\d+)_", entity_entry.unique_id)
    ch_num = int(m.group(1)) if m else 1
    channel_id = coordinator.get_channel_id(spot_id, ch_num)

    return (coordinator, spot_id, channel_id)


async def _async_extract_targets(
    hass: HomeAssistant, call: ServiceCall
) -> list[tuple[FiftyFiveCoordinator, str, str]]:
    """Extract list of unique valid target tuples for a service call."""
    try:
        entity_ids = await service.async_extract_entity_ids(hass, call)
    except TypeError:
        entity_ids = await service.async_extract_entity_ids(call)

    targets: dict[tuple[int, str, str], tuple[FiftyFiveCoordinator, str, str]] = {}
    for entity_id in entity_ids:
        target = _resolve_fiftyfive_target(hass, entity_id)
        if target:
            coord, spot_id, channel_id = target
            targets[(id(coord), spot_id, channel_id)] = target

    return list(targets.values())


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register 50five integration services."""

    async def async_handle_start_charging(call: ServiceCall) -> None:
        """Start charging on targeted channels."""
        card_id = call.data.get("card_id")
        targets = await _async_extract_targets(hass, call)
        coordinators_to_refresh: set[FiftyFiveCoordinator] = set()

        for coordinator, spot_id, channel_id in targets:
            config_entry = getattr(coordinator, "config_entry", None)
            effective_card = (
                card_id
                or (config_entry.options.get(CONF_CARD_ID) if config_entry else None)
                or (config_entry.data.get(CONF_CARD_ID) if config_entry else None)
            )
            await coordinator.client.start_charging(spot_id, channel_id, effective_card)
            coordinators_to_refresh.add(coordinator)

        for coordinator in coordinators_to_refresh:
            await coordinator.async_request_refresh()

    async def async_handle_stop_charging(call: ServiceCall) -> None:
        """Stop charging on targeted channels."""
        targets = await _async_extract_targets(hass, call)
        coordinators_to_refresh: set[FiftyFiveCoordinator] = set()

        for coordinator, spot_id, channel_id in targets:
            await coordinator.client.stop_charging(spot_id, channel_id)
            coordinators_to_refresh.add(coordinator)

        for coordinator in coordinators_to_refresh:
            await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "start_charging", async_handle_start_charging)
    hass.services.async_register(DOMAIN, "stop_charging", async_handle_stop_charging)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: FiftyFiveConfigEntry) -> bool:
    """Set up 50five from a config entry."""
    device_id = entry.data.get(CONF_DEVICE_ID)
    if not device_id:
        device_id = str(uuid.uuid4())
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_DEVICE_ID: device_id},
        )

    session = async_get_clientsession(hass)

    @callback
    def _async_on_token_refreshed(
        new_token: str, expires_at_iso: str, customer_id: str | None
    ) -> None:
        """Update config entry with newly refreshed access token and expiration."""
        new_data = {
            **entry.data,
            CONF_ACCESS_TOKEN: new_token,
            CONF_TOKEN_EXPIRES_AT: expires_at_iso,
        }
        if customer_id:
            new_data[CONF_CUSTOMER_ID] = customer_id
        hass.config_entries.async_update_entry(entry, data=new_data)

    client = FiftyFiveApiClient(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        session=session,
        device_id=device_id,
        customer_id=entry.data.get(CONF_CUSTOMER_ID),
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        token_expires_at=entry.data.get(CONF_TOKEN_EXPIRES_AT),
        on_token_refreshed=_async_on_token_refreshed,
    )

    coordinator = FiftyFiveCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    # Modern HA 2024.4+ runtime data storage
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: FiftyFiveConfigEntry) -> bool:
    """Unload a 50five config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(
    hass: HomeAssistant, entry: FiftyFiveConfigEntry
) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
