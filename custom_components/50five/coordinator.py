"""DataUpdateCoordinator for 50five GraphQL integration with strongly typed data."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FiftyFiveApiClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .exceptions import FiftyFiveAuthError, FiftyFiveError
from .models import ActiveTransaction, ChargeStation, StationData

_LOGGER = logging.getLogger(__name__)

type FiftyFiveConfigEntry = ConfigEntry[FiftyFiveCoordinator]


class FiftyFiveCoordinator(DataUpdateCoordinator[dict[str, StationData]]):
    """Class to manage fetching 50five GraphQL data with strong typing."""

    config_entry: FiftyFiveConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: FiftyFiveApiClient,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.charge_stations: list[ChargeStation] = []
        self.spot_channels: dict[str, int] = {}
        self.entities: dict[str, Any] = {}

    async def _async_update_data(self) -> dict[str, StationData]:
        """Fetch charge stations and active transaction data from GraphQL API."""
        try:
            # Query all customer charge stations (returns list[ChargeStation])
            stations = await self.client.get_customer_charge_stations()
            self.charge_stations = stations or []

            if not self.charge_stations:
                _LOGGER.warning("No charge stations found for this account")
                return {}

            # Query active transaction telemetry (returns ActiveTransaction | None)
            active_transaction: ActiveTransaction | None = None
            try:
                active_transaction = await self.client.get_active_transaction()
            except FiftyFiveError as tx_err:
                _LOGGER.debug("Could not fetch active transaction: %s", tx_err)

            data: dict[str, StationData] = {}

            for station in self.charge_stations:
                station_id = station.id
                if not station_id:
                    continue

                channels_by_num = {ch.channel_no: ch for ch in station.channels}
                self.spot_channels[station_id] = max(1, len(channels_by_num))

                data[station_id] = StationData(
                    station=station,
                    channels=channels_by_num,
                    active_transaction=active_transaction,
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
