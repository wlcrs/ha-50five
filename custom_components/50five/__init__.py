# ruff: noqa: N999
"""The 50five GraphQL integration."""

from __future__ import annotations

import logging
import re
import uuid

import voluptuous as vol
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import service
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .api import FiftyFiveApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CARD_ID,
    CONF_CARD_IDS,
    CONF_CUSTOMER_ID,
    CONF_DEVICE_ID,
    CONF_TOKEN_EXPIRES_AT,
    DOMAIN,
)
from .coordinator import (
    STORAGE_VERSION,
    FiftyFiveConfigEntry,
    FiftyFiveCoordinator,
    active_cards_store_key,
    get_configured_card_ids,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.NUMBER,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _resolve_fiftyfive_target(
    hass: HomeAssistant,
    entity_id: str,
) -> tuple[FiftyFiveCoordinator, str, str] | None:
    """Resolve entity_id to (coordinator, spot_id, channel_id)."""
    entity_entry = er.async_get(hass).async_get(entity_id)
    if (
        not entity_entry
        or not entity_entry.config_entry_id
        or not entity_entry.unique_id
    ):
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
            spot_id = next(
                (ident for dom, ident in dev.identifiers if dom == DOMAIN), None
            )

    if not spot_id:
        if coordinator.data:
            spot_id = max(
                (
                    sid
                    for sid in coordinator.data
                    if entity_entry.unique_id.startswith(f"{sid}_")
                ),
                key=len,
                default=None,
            )
        if not spot_id:
            spot_id = entity_entry.unique_id.split("_", 1)[0]
    if not spot_id:
        return None

    # Channel ID (matches ch<N>_ suffix after spot_id_ if multi-channel, else channel 1)
    suffix = entity_entry.unique_id.removeprefix(f"{spot_id}_")
    m = re.match(r"ch(\d+)_", suffix)
    ch_num = int(m.group(1)) if m else 1
    channel_id = coordinator.get_channel_id(spot_id, ch_num)

    return (coordinator, spot_id, channel_id)


def _resolve_switch_card_id(
    hass: HomeAssistant,
    entity_id: str,
    spot_id: str,
) -> str | None:
    """Extract the card ID encoded in a per-card charging switch unique_id."""
    entity_entry = er.async_get(hass).async_get(entity_id)
    if (
        not entity_entry
        or entity_entry.domain != Platform.SWITCH
        or not entity_entry.unique_id
    ):
        return None
    suffix = entity_entry.unique_id.removeprefix(f"{spot_id}_")
    suffix = re.sub(r"^ch\d+_", "", suffix)
    if suffix.startswith("charging_") and len(suffix) > len("charging_"):
        return suffix.removeprefix("charging_")
    return None


async def _async_extract_targets(
    hass: HomeAssistant, call: ServiceCall
) -> list[tuple[FiftyFiveCoordinator, str, str, str | None]]:
    """Extract list of unique valid target tuples for a service call."""
    entity_ids = await service.async_extract_entity_ids(call)

    targets: dict[
        tuple[int, str, str], tuple[FiftyFiveCoordinator, str, str, str | None]
    ] = {}
    card_ids_by_key: dict[tuple[int, str, str], set[str | None]] = {}
    for entity_id in entity_ids:
        target = _resolve_fiftyfive_target(hass, entity_id)
        if target:
            coord, spot_id, channel_id = target
            key = (id(coord), spot_id, channel_id)
            card_id = _resolve_switch_card_id(hass, entity_id, spot_id)
            card_ids_by_key.setdefault(key, set()).add(card_id)
            targets[key] = (coord, spot_id, channel_id, card_id)

    result: list[tuple[FiftyFiveCoordinator, str, str, str | None]] = []
    for key, (coord, spot_id, channel_id, _) in targets.items():
        found_cards = card_ids_by_key[key]
        # Only infer a switch's card when all targeted entities on this channel
        # point to that single card switch (not when targeting a whole device).
        inferred_card = (
            next(iter(found_cards))
            if len(found_cards) == 1
            else None
        )
        result.append((coord, spot_id, channel_id, inferred_card))

    return result


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register 50five integration services."""

    async def async_handle_start_charging(call: ServiceCall) -> None:
        """Start charging on targeted channels."""
        card_id = call.data.get("card_id")
        targets = await _async_extract_targets(hass, call)
        if not targets:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_valid_targets",
            )
        coordinators_to_refresh: set[FiftyFiveCoordinator] = set()

        for coordinator, spot_id, channel_id, target_card_id in targets:
            configured_cards = get_configured_card_ids(
                coordinator.config_entry.data, coordinator.config_entry.options
            )
            fallback_card = configured_cards[0] if configured_cards else None
            effective_card = card_id or target_card_id or fallback_card or None
            await coordinator.client.start_charging(spot_id, channel_id, effective_card)
            coordinator.set_optimistic_charging_state(
                spot_id,
                channel_id,
                True,
                card_id=effective_card,
            )
            coordinators_to_refresh.add(coordinator)

        for coordinator in coordinators_to_refresh:
            await coordinator.async_request_refresh()

    async def async_handle_stop_charging(call: ServiceCall) -> None:
        """Stop charging on targeted channels."""
        targets = await _async_extract_targets(hass, call)
        if not targets:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_valid_targets",
            )
        coordinators_to_refresh: set[FiftyFiveCoordinator] = set()

        for coordinator, spot_id, channel_id, _ in targets:
            await coordinator.client.stop_charging(spot_id, channel_id)
            coordinator.set_optimistic_charging_state(spot_id, channel_id, False)
            coordinators_to_refresh.add(coordinator)

        for coordinator in coordinators_to_refresh:
            await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "start_charging",
        async_handle_start_charging,
        schema=cv.make_entity_service_schema({vol.Optional("card_id"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        "stop_charging",
        async_handle_stop_charging,
        schema=cv.make_entity_service_schema({}),
    )

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

    coordinator = FiftyFiveCoordinator(hass, entry, client)
    await coordinator.async_load_stored_cards()
    await coordinator.async_config_entry_first_refresh()

    # Modern HA 2024.4+ runtime data storage
    entry.runtime_data = coordinator

    # Remove legacy entities and switches for cards that were unchecked
    selected_card_ids = get_configured_card_ids(entry.data, entry.options)
    expected_switch_unique_ids = (
        {
            (
                f"{spot_id}_ch{ch}_charging_{card_id}"
                if sd.num_channels > 1
                else f"{spot_id}_charging_{card_id}"
            )
            for spot_id, sd in coordinator.data.items()
            for ch in range(1, sd.num_channels + 1)
            for card_id in selected_card_ids
        }
        if coordinator.data
        else None
    )
    ent_reg = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if entity_entry.domain == Platform.SENSOR and entity_entry.unique_id.endswith(
            "_hcc_enabled"
        ):
            _LOGGER.info(
                "Removing legacy sensor entity %s migrated to binary_sensor",
                entity_entry.entity_id,
            )
            ent_reg.async_remove(entity_entry.entity_id)
        elif (
            entity_entry.domain == Platform.SWITCH
            and expected_switch_unique_ids is not None
            and entity_entry.unique_id not in expected_switch_unique_ids
        ):
            _LOGGER.info(
                "Removing stale switch entity %s",
                entity_entry.entity_id,
            )
            ent_reg.async_remove(entity_entry.entity_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: FiftyFiveConfigEntry
) -> bool:
    """Migrate old config entries to the current minor version."""
    if config_entry.version == 2 and config_entry.minor_version < 2:
        new_data = dict(config_entry.data)
        new_options = dict(config_entry.options)

        if CONF_CARD_IDS not in new_data and CONF_CARD_ID in new_data:
            legacy_card = new_data.pop(CONF_CARD_ID)
            new_data[CONF_CARD_IDS] = (
                [legacy_card.strip()]
                if isinstance(legacy_card, str) and legacy_card.strip()
                else []
            )
        else:
            new_data.pop(CONF_CARD_ID, None)

        if CONF_CARD_IDS not in new_options and CONF_CARD_ID in new_options:
            legacy_opt = new_options.pop(CONF_CARD_ID)
            new_options[CONF_CARD_IDS] = (
                [legacy_opt.strip()]
                if isinstance(legacy_opt, str) and legacy_opt.strip()
                else []
            )
        else:
            new_options.pop(CONF_CARD_ID, None)

        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            options=new_options,
            minor_version=2,
        )
        _LOGGER.debug(
            "Migrated 50five config entry %s to version 2.2", config_entry.entry_id
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: FiftyFiveConfigEntry) -> bool:
    """Unload a 50five config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    coordinator: FiftyFiveCoordinator | None = getattr(entry, "runtime_data", None)
    if coordinator is not None:
        await coordinator.async_flush_stored_cards()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: FiftyFiveConfigEntry) -> None:
    """Remove persisted storage when a 50five config entry is deleted."""
    await Store(
        hass, STORAGE_VERSION, active_cards_store_key(entry.entry_id)
    ).async_remove()
