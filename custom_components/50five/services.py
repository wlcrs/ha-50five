"""Service handlers and registration for the 50five integration."""

from __future__ import annotations

from datetime import datetime
import re

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import service
from homeassistant.util import dt as dt_util

from .api import add_one_month
from .const import DOMAIN
from .coordinator import (
    FiftyFiveConfigEntry,
    FiftyFiveCoordinator,
    get_configured_card_ids,
)

SERVICE_START_CHARGING = "start_charging"
SERVICE_STOP_CHARGING = "stop_charging"
SERVICE_GET_TRANSACTIONS = "get_transactions"

SERVICE_START_CHARGING_SCHEMA = cv.make_entity_service_schema(
    {vol.Optional("card_id"): cv.string}
)
SERVICE_STOP_CHARGING_SCHEMA = cv.make_entity_service_schema({})
SERVICE_GET_TRANSACTIONS_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Optional("limit", default=5): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=50)
        ),
        vol.Optional("date_from"): cv.datetime,
        vol.Optional("date_to"): cv.datetime,
        vol.Optional("page", default=1): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)


def _normalize_service_datetime(value: datetime | None) -> datetime | None:
    """Normalize an optional service datetime to UTC using HA's default timezone."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_util.get_default_time_zone())
    return dt_util.as_utc(value)


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
            next(iter(found_cards)) if len(found_cards) == 1 else None
        )
        result.append((coord, spot_id, channel_id, inferred_card))

    return result


@callback
def async_setup_services(hass: HomeAssistant) -> None:
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

    async def async_handle_get_transactions(call: ServiceCall) -> ServiceResponse:
        """Fetch recent completed transactions for targeted charge stations."""
        targets = await _async_extract_targets(hass, call)
        if not targets:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_valid_targets",
            )

        limit = int(call.data.get("limit", 5))
        date_from = _normalize_service_datetime(call.data.get("date_from"))
        date_to = _normalize_service_datetime(call.data.get("date_to"))
        page = int(call.data.get("page", 1))

        if date_from is not None and date_to is not None:
            if date_from > date_to:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_date_range",
                )
            if date_to > add_one_month(date_from):
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="date_range_too_long",
                )

        seen_stations: set[tuple[int, str]] = set()
        transactions_payload: list[dict[str, object]] = []
        has_next = False

        for coordinator, spot_id, _, _ in targets:
            station_key = (id(coordinator), spot_id)
            if station_key in seen_stations:
                continue
            seen_stations.add(station_key)

            station_data = (
                coordinator.data.get(spot_id) if coordinator.data else None
            )
            station_name = (
                station_data.station.display_name if station_data else spot_id
            )
            collection = await coordinator.client.get_charge_station_transactions_page(
                spot_id,
                date_from=date_from,
                date_to=date_to,
                items_per_page=limit,
                page=page,
            )
            if collection.has_next:
                has_next = True
            for tx in collection.items or []:
                transactions_payload.append(
                    {
                        "id": tx.id,
                        "station_id": spot_id,
                        "station_name": station_name,
                        "status": tx.status.value,
                        "global_status": (
                            tx.global_status.value if tx.global_status else None
                        ),
                        "start_date": (
                            tx.start_date.isoformat() if tx.start_date else None
                        ),
                        "last_update_date": (
                            tx.last_update_date.isoformat()
                            if tx.last_update_date
                            else None
                        ),
                        "total_duration": tx.total_duration,
                        "total_energy": tx.total_energy,
                        "total_idle_time": tx.total_idle_time,
                        "total_cost": tx.total_cost,
                        "currency": tx.currency,
                        "card_id": tx.card_id,
                        "home_charging": tx.home_charging,
                    }
                )

        return {
            "transactions": transactions_payload,
            "page": page,
            "has_next": has_next,
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_CHARGING,
        async_handle_start_charging,
        schema=SERVICE_START_CHARGING_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_CHARGING,
        async_handle_stop_charging,
        schema=SERVICE_STOP_CHARGING_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_TRANSACTIONS,
        async_handle_get_transactions,
        schema=SERVICE_GET_TRANSACTIONS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
