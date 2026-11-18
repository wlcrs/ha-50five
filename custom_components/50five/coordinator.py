"""DataUpdateCoordinator for 50five GraphQL integration with strongly typed data."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FiftyFiveApiClient
from .const import (
    CHARGING_OPTIMISTIC_GRACE_SECONDS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HCC_TARIFF_HIDDEN_PROVIDER_CATEGORIES,
)
from .exceptions import FiftyFiveAuthError, FiftyFiveError
from .models import (
    ActiveTransaction,
    ChargeStation,
    StationData,
    TariffRange,
    TransactionCollection,
)

_LOGGER = logging.getLogger(__name__)

type FiftyFiveConfigEntry = ConfigEntry[FiftyFiveCoordinator]


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
        self._optimistic_charging: dict[tuple[str, str], tuple[bool, float]] = {}

    @property
    def charge_stations(self) -> list[ChargeStation]:
        """Return the list of charge stations from the latest coordinator data."""
        return [sd.station for sd in self.data.values()] if self.data else []

    def set_optimistic_charging_state(
        self,
        spot_id: str,
        channel_id: str,
        is_on: bool,
        ttl_seconds: float = CHARGING_OPTIMISTIC_GRACE_SECONDS,
    ) -> None:
        """Store a temporary optimistic charging state for a station channel."""
        self._optimistic_charging[(spot_id, channel_id)] = (
            is_on,
            time.monotonic() + ttl_seconds,
        )
        self.async_update_listeners()

    def clear_optimistic_charging_state(self, spot_id: str, channel_id: str) -> None:
        """Clear any pending optimistic charging state for a station channel."""
        if self._optimistic_charging.pop((spot_id, channel_id), None) is not None:
            self.async_update_listeners()

    def get_optimistic_charging_state(
        self,
        spot_id: str,
        channel_id: str,
        *,
        backend_is_on: bool | None = None,
    ) -> bool | None:
        """Return active optimistic state, clearing if confirmed or expired."""
        entry = self._optimistic_charging.get((spot_id, channel_id))
        if entry is None:
            return None
        target_state, expires_at = entry
        if backend_is_on is not None and backend_is_on == target_state:
            self._optimistic_charging.pop((spot_id, channel_id), None)
            return None
        if time.monotonic() >= expires_at:
            self._optimistic_charging.pop((spot_id, channel_id), None)
            return None
        return target_state

    def get_channel_id(self, spot_id: str, channel_no: int = 1) -> str:
        """Resolve the GraphQL channel ID for a station and channel number."""
        station_data = self.data.get(spot_id) if self.data else None
        if station_data:
            ch_id = station_data.get_channel_id(channel_no)
            if ch_id:
                return ch_id
        return str(channel_no)

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

            # Query all customer charge stations (returns list[ChargeStation])
            stations = await self.client.get_customer_charge_stations() or []

            if not stations:
                _LOGGER.warning("No charge stations found for this account")
                return {}

            # Query active transaction telemetry (returns ActiveTransaction | None)
            active_transaction: ActiveTransaction | None = None
            try:
                active_transaction = await self.client.get_active_transaction()
            except FiftyFiveError as tx_err:
                _LOGGER.debug("Could not fetch active transaction: %s", tx_err)

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
                data[station_to_store.id] = StationData(
                    station=station_to_store,
                    channels=channels_by_num,
                    active_transaction=(
                        active_transaction
                        if _station_matches_active_tx(
                            station_to_store, active_transaction
                        )
                        else None
                    ),
                    vat_multiplier=vat_multiplier,
                )

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
