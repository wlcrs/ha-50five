# ruff: noqa: N999
"""The 50five GraphQL integration."""

from __future__ import annotations

import logging
from pathlib import Path
import uuid

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import (
    HomeAssistant,
    callback,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
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
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.NUMBER,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

FRONTEND_CARD_URL = "/50five/fiftyfive-transactions-card.js"
FRONTEND_CARD_PATH = Path(__file__).parent / "frontend" / "fiftyfive-transactions-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register 50five integration services and frontend card."""
    if getattr(hass, "http", None) is not None and FRONTEND_CARD_PATH.is_file():
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    FRONTEND_CARD_URL,
                    str(FRONTEND_CARD_PATH),
                    cache_headers=False,
                )
            ]
        )
        add_extra_js_url(hass, FRONTEND_CARD_URL)

    async_setup_services(hass)

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
