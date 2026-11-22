"""DataUpdateCoordinator for 50five GraphQL integration with strongly typed data."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FiftyFiveApiClient
from .const import (
    CHARGING_OPTIMISTIC_GRACE_SECONDS,
    CONF_CARD_ID,
    CONF_CARD_IDS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HCC_TARIFF_HIDDEN_PROVIDER_CATEGORIES,
)
from .exceptions import FiftyFiveAuthError, FiftyFiveError
from .models import (
    ActiveTransaction,
    ChargeCard,
    ChargeStation,
    CompletedTransaction,
    GlobalStatus,
    StationData,
    TariffRange,
    TransactionCollection,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

type FiftyFiveConfigEntry = ConfigEntry[FiftyFiveCoordinator]


def active_cards_store_key(entry_id: str) -> str:
    """Return the Home Assistant storage key for a config entry's active cards."""
    return f"{DOMAIN}.{entry_id}.active_cards"


def get_configured_card_ids(
    data: Mapping[str, Any],
    options: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return deduplicated configured card IDs from options or data (with legacy card_id fallback)."""
    raw: Any = None
    if options is not None:
        if CONF_CARD_IDS in options:
            raw = options[CONF_CARD_IDS]
        elif CONF_CARD_ID in options:
            raw = [options[CONF_CARD_ID]] if options[CONF_CARD_ID] else []

    if raw is None:
        if CONF_CARD_IDS in data:
            raw = data[CONF_CARD_IDS]
        elif CONF_CARD_ID in data:
            raw = [data[CONF_CARD_ID]] if data[CONF_CARD_ID] else []

    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple, set)):
        return []

    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
    return result


def _station_matches_active_tx(
    station: ChargeStation, tx: ActiveTransaction | None
) -> bool:
    """Return whether an active transaction belongs to the given station."""
    if tx is None:
        return False
    channels = station.channels or []
    if tx.channel_id:
        return any(ch.id == tx.channel_id for ch in channels)
    if tx.evse_id:
        return any(ch.evse_id == tx.evse_id for ch in channels)
    return True


class FiftyFiveCoordinator(DataUpdateCoordinator[dict[str, StationData]]):
    """Class to manage fetching 50five GraphQL data with strong typing."""

    config_entry: FiftyFiveConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FiftyFiveConfigEntry,
        client: FiftyFiveApiClient,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.provider_category: str | None = None
        self.reimbursement_tariff_range: TariffRange | None = None
        self._tariff_range_fetched = False
        self._charge_cards_fetched = False
        self._cached_active_tx_id: str | None = None
        self._cached_active_tx_details: CompletedTransaction | None = None
        self.charge_cards: list[ChargeCard] = []
        self._optimistic_charging: dict[tuple[str, str], tuple[bool, str | None, float]] = {}
        self._last_used_card: dict[tuple[str, str], str] = {}
        self._last_used_card_status_date: dict[tuple[str, str], str] = {}
        self._unknown_active_card_logged: set[tuple[str, str]] = set()
        self._store: Store[dict[str, dict[str, str | None]]] = Store(
            hass,
            STORAGE_VERSION,
            active_cards_store_key(entry.entry_id),
        )
        self._save_pending = False
        self._save_task: asyncio.Task[None] | None = None

    async def async_load_stored_cards(self) -> None:
        """Load persisted last-used card state from Home Assistant storage."""
        try:
            stored = await self._store.async_load()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not load persisted active card state: %s", err)
            return

        if not isinstance(stored, dict):
            return

        for raw_key, payload in stored.items():
            if not isinstance(raw_key, str) or "|" not in raw_key:
                continue
            if not isinstance(payload, dict):
                continue
            spot_id, channel_id = raw_key.split("|", 1)
            card_id = payload.get("card_id")
            if not isinstance(card_id, str) or not card_id:
                continue
            key = (spot_id, channel_id)
            self._last_used_card[key] = card_id
            status_date = payload.get("status_change_date")
            if isinstance(status_date, str) and status_date:
                self._last_used_card_status_date[key] = status_date

    def _serialize_last_used_cards(self) -> dict[str, dict[str, str | None]]:
        """Serialize last-used card state for JSON storage."""
        return {
            f"{spot_id}|{channel_id}": {
                "card_id": card_id,
                "status_change_date": self._last_used_card_status_date.get(
                    (spot_id, channel_id)
                ),
            }
            for (spot_id, channel_id), card_id in self._last_used_card.items()
        }

    def _schedule_save_last_used_cards(self) -> None:
        """Coalesce and serialize persistence of last-used card state."""
        self._save_pending = True
        if self._save_task is not None and not self._save_task.done():
            return
        self._save_task = self.hass.async_create_task(
            self._async_flush_last_used_cards(),
            name=f"{DOMAIN}_{self.config_entry.entry_id}_save_active_cards",
        )

    async def _async_flush_last_used_cards(self) -> None:
        """Write latest last-used card state to storage sequentially."""
        while self._save_pending:
            self._save_pending = False
            payload = self._serialize_last_used_cards()
            try:
                await self._store.async_save(payload)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Could not save active card state: %s", err)

    async def async_flush_stored_cards(self) -> None:
        """Wait for any pending storage write to finish before unload."""
        if self._save_task is not None and not self._save_task.done():
            await self._save_task

    @property
    def charge_stations(self) -> list[ChargeStation]:
        """Return the list of charge stations from the latest coordinator data."""
        return [sd.station for sd in self.data.values()] if self.data else []

    def set_optimistic_charging_state(
        self,
        spot_id: str,
        channel_id: str,
        is_on: bool,
        *,
        card_id: str | None = None,
        ttl_seconds: float = CHARGING_OPTIMISTIC_GRACE_SECONDS,
    ) -> None:
        """Store a temporary optimistic charging state for a station channel."""
        key = (spot_id, channel_id)
        self._optimistic_charging[key] = (
            is_on,
            card_id if is_on else None,
            time.monotonic() + ttl_seconds,
        )
        if is_on:
            if card_id:
                self._last_used_card[key] = card_id
            else:
                self._last_used_card.pop(key, None)
            self._last_used_card_status_date.pop(key, None)
            self._unknown_active_card_logged.discard(key)
        else:
            self._last_used_card.pop(key, None)
            self._last_used_card_status_date.pop(key, None)
            self._unknown_active_card_logged.discard(key)
        self._schedule_save_last_used_cards()
        self.async_update_listeners()

    def get_last_used_card(self, spot_id: str, channel_id: str) -> str | None:
        """Return the card ID last used via Home Assistant on this channel."""
        return self._last_used_card.get((spot_id, channel_id))

    def clear_optimistic_charging_state(
        self,
        spot_id: str,
        channel_id: str,
        *,
        restore_card: bool = False,
        restore_card_id: str | None = None,
    ) -> None:
        """Clear any pending optimistic charging state for a station channel."""
        key = (spot_id, channel_id)
        changed = self._optimistic_charging.pop(key, None) is not None
        if restore_card:
            if restore_card_id:
                self._last_used_card[key] = restore_card_id
            else:
                self._last_used_card.pop(key, None)
                self._last_used_card_status_date.pop(key, None)
            self._schedule_save_last_used_cards()
            changed = True
        if changed:
            self.async_update_listeners()

    def get_optimistic_charging_state(
        self,
        spot_id: str,
        channel_id: str,
        *,
        backend_is_on: bool | None = None,
    ) -> tuple[bool, str | None] | None:
        """Return active optimistic (state, card_id) without mutating state."""
        entry = self._optimistic_charging.get((spot_id, channel_id))
        if entry is None:
            return None
        target_state, card_id, expires_at = entry
        if backend_is_on is not None and backend_is_on == target_state:
            return None
        if time.monotonic() >= expires_at:
            return None
        return (target_state, card_id)

    def _reconcile_optimistic_charging_state(
        self,
        spot_id: str,
        channel_id: str,
        *,
        backend_is_on: bool,
    ) -> tuple[tuple[bool, str | None] | None, bool]:
        """Reconcile optimistic state on poll; returns (active_state, storage_dirty)."""
        key = (spot_id, channel_id)
        entry = self._optimistic_charging.get(key)
        if entry is None:
            return None, False
        target_state, card_id, expires_at = entry
        if backend_is_on == target_state:
            self._optimistic_charging.pop(key, None)
            dirty = False
            if not target_state and self._last_used_card.pop(key, None) is not None:
                self._last_used_card_status_date.pop(key, None)
                dirty = True
            return None, dirty
        if time.monotonic() >= expires_at:
            self._optimistic_charging.pop(key, None)
            dirty = False
            if (
                target_state
                and not backend_is_on
                and self._last_used_card.pop(key, None) is not None
            ):
                self._last_used_card_status_date.pop(key, None)
                dirty = True
            return None, dirty
        return (target_state, card_id), False

    def get_channel_id(self, spot_id: str, channel_no: int = 1) -> str:
        """Resolve the GraphQL channel ID for a station and channel number."""
        station_data = self.data.get(spot_id) if self.data else None
        if station_data:
            ch_id = station_data.get_channel_id(channel_no)
            if ch_id:
                return ch_id
        return str(channel_no)

    def _reconcile_active_card_tracking(
        self, spot_id: str, station_data: StationData
    ) -> None:
        """Reconcile remembered card state and log when charging card is unknown."""
        storage_dirty = False
        for channel_no in range(1, station_data.num_channels + 1):
            channel_id = station_data.get_channel_id(channel_no) or str(channel_no)
            key = (spot_id, channel_id)
            ch = station_data.channels.get(channel_no)
            current_status_date = (
                ch.last_status_change_date.isoformat()
                if ch and ch.last_status_change_date
                else None
            )
            backend_charging = station_data.is_channel_charging(channel_no)
            optimistic, opt_dirty = self._reconcile_optimistic_charging_state(
                spot_id, channel_id, backend_is_on=backend_charging
            )
            if opt_dirty:
                storage_dirty = True

            if not backend_charging:
                if optimistic is None:
                    if self._last_used_card.pop(key, None) is not None:
                        storage_dirty = True
                    if self._last_used_card_status_date.pop(key, None) is not None:
                        storage_dirty = True
                self._unknown_active_card_logged.discard(key)
                continue

            if optimistic is not None and not optimistic[0]:
                continue

            backend_card_ids = station_data.get_backend_active_card_ids(channel_no)
            if backend_card_ids:
                self._unknown_active_card_logged.discard(key)
                continue

            if key in self._last_used_card:
                recorded_status_date = self._last_used_card_status_date.get(key)
                if (
                    recorded_status_date is not None
                    and current_status_date is not None
                    and current_status_date != recorded_status_date
                ):
                    # A different session started while HA was offline; discard stale card.
                    self._last_used_card.pop(key, None)
                    self._last_used_card_status_date.pop(key, None)
                    storage_dirty = True
                else:
                    if recorded_status_date is None and current_status_date is not None:
                        self._last_used_card_status_date[key] = current_status_date
                        storage_dirty = True
                    self._unknown_active_card_logged.discard(key)
                    continue

            if key not in self._unknown_active_card_logged:
                self._unknown_active_card_logged.add(key)
                _LOGGER.info(
                    "Station %s, channel %s is charging, but the 50five API did not "
                    "report which charge card is active and no card was recorded from "
                    "Home Assistant (for example, when started with a physical card); "
                    "leaving all card switches off",
                    spot_id,
                    channel_id,
                )

        if storage_dirty:
            self._schedule_save_last_used_cards()

    def _should_fetch_active_transaction(self, stations: list[ChargeStation]) -> bool:
        """Return whether any station channel is active or optimistically starting."""
        for station in stations:
            for ch in station.channels or []:
                if ch.status in (
                    GlobalStatus.CHARGING,
                    GlobalStatus.OCCUPIED,
                    GlobalStatus.PREPARING,
                ):
                    return True
        now = time.monotonic()
        return any(
            is_on and now < expires_at
            for is_on, _, expires_at in self._optimistic_charging.values()
        )

    async def _async_fetch_station_transactions(
        self, station: ChargeStation
    ) -> ChargeStation:
        """Fetch recent completed transactions for a station if not already attached."""
        if not station.id or (station.transactions and station.transactions.items):
            return station
        try:
            txs = await self.client.get_charge_station_transactions(station.id)
            if txs:
                return station.model_copy(
                    update={"transactions": TransactionCollection(items=txs)}
                )
        except FiftyFiveError as tx_err:
            _LOGGER.warning(
                "Could not fetch recent transactions for station %s: %s",
                station.id,
                tx_err,
            )
        except Exception as tx_err:  # noqa: BLE001
            _LOGGER.debug(
                "Unexpected error fetching transactions for station %s: %s",
                station.id,
                tx_err,
            )
        return station

    async def _async_update_data(self) -> dict[str, StationData]:
        """Fetch charge stations and active transaction data from GraphQL API."""
        try:
            vat_multiplier = await self.client.get_vat_multiplier()
            self.provider_category = self.client.provider_category

            if (
                not self._tariff_range_fetched
                and isinstance(self.provider_category, str)
                and self.provider_category.strip().upper()
                not in HCC_TARIFF_HIDDEN_PROVIDER_CATEGORIES
            ):
                self._tariff_range_fetched = True
                try:
                    self.reimbursement_tariff_range = (
                        await self.client.get_reimbursement_tariff_range()
                    )
                except FiftyFiveError as err:
                    _LOGGER.warning(
                        "Could not fetch reimbursement tariff range, using defaults: %s",
                        err,
                    )
                    self.reimbursement_tariff_range = None

            # Query customer charge cards once (retrying on next poll if initial fetch failed)
            if not self._charge_cards_fetched:
                try:
                    self.charge_cards = await self.client.get_charge_cards() or []
                    self._charge_cards_fetched = True
                except FiftyFiveError as card_err:
                    _LOGGER.warning("Could not fetch charge cards: %s", card_err)

            # Query all customer charge stations (returns list[ChargeStation])
            stations = await self.client.get_customer_charge_stations() or []

            if not stations:
                _LOGGER.warning("No charge stations found for this account")
                return {}

            # Query active transaction telemetry only when a station is active or starting
            active_transaction: ActiveTransaction | None = None
            if self._should_fetch_active_transaction(stations):
                try:
                    active_transaction = await self.client.get_active_transaction()
                except FiftyFiveError as tx_err:
                    _LOGGER.debug("Could not fetch active transaction: %s", tx_err)

            # Query full LMS transaction details (including cardSnapshot) once per
            # active transactionId, degrading gracefully on failure.
            active_transaction_details: CompletedTransaction | None = None
            active_tx_id = (
                active_transaction.transaction_id if active_transaction else None
            )
            if not active_tx_id:
                self._cached_active_tx_id = None
                self._cached_active_tx_details = None
            elif active_tx_id == self._cached_active_tx_id:
                active_transaction_details = self._cached_active_tx_details
            else:
                try:
                    active_transaction_details = await self.client.get_transaction(
                        active_tx_id
                    )
                    self._cached_active_tx_id = active_tx_id
                    self._cached_active_tx_details = active_transaction_details
                except FiftyFiveError as tx_detail_err:
                    _LOGGER.debug(
                        "Could not fetch details for active transaction %s: %s",
                        active_tx_id,
                        tx_detail_err,
                    )

            valid_stations = [station for station in stations if station.id]
            enriched_stations = await asyncio.gather(
                *(
                    self._async_fetch_station_transactions(station)
                    for station in valid_stations
                )
            )

            data: dict[str, StationData] = {}
            for station_to_store in enriched_stations:
                channels_by_num = {
                    ch.channel_no: ch for ch in station_to_store.channels or []
                }
                matches_active = _station_matches_active_tx(
                    station_to_store, active_transaction
                )
                station_data = StationData(
                    station=station_to_store,
                    channels=channels_by_num,
                    active_transaction=active_transaction if matches_active else None,
                    active_transaction_details=(
                        active_transaction_details if matches_active else None
                    ),
                    vat_multiplier=vat_multiplier,
                )
                data[station_to_store.id] = station_data
                self._reconcile_active_card_tracking(station_to_store.id, station_data)

            return data

        except FiftyFiveAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed for 50five user {self.client.username}: {err}"
            ) from err
        except FiftyFiveError as err:
            raise UpdateFailed(f"50five API error: {err}") from err
        except Exception as err:
            raise UpdateFailed(
                f"Unexpected error communicating with 50five: {err}"
            ) from err
