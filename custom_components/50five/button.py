"""Button platform for 50five GraphQL integration with non-blocking feedback."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ACTION_SETTLE_DELAY_SEC, DOMAIN
from .coordinator import FiftyFiveConfigEntry, FiftyFiveCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FiftyFiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 50five control buttons."""
    coordinator = entry.runtime_data

    entities: list[ButtonEntity] = []

    for spot_id in coordinator.data:
        station_data = coordinator.data[spot_id]
        num_channels = station_data.num_channels

        # Station-level buttons
        entities.extend(
            [
                FiftyFiveRefreshStatusButton(coordinator, spot_id),
                FiftyFiveSoftResetButton(coordinator, spot_id),
                FiftyFiveHardResetButton(coordinator, spot_id),
                FiftyFiveResetCacheButton(coordinator, spot_id),
            ]
        )

        # Unlock connector buttons (per channel if multi-channel, or single)
        for ch in range(1, num_channels + 1):
            entities.append(
                FiftyFiveUnlockConnectorButton(
                    coordinator,
                    spot_id,
                    channel_no=ch,
                    is_multi_channel=num_channels > 1,
                )
            )

    async_add_entities(entities)


class FiftyFiveButtonBase(CoordinatorEntity[FiftyFiveCoordinator], ButtonEntity):
    """Base class for 50five buttons."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FiftyFiveCoordinator,
        spot_id: str,
        button_type: str,
        translation_key: str,
        icon: str,
        entity_category: EntityCategory | None = None,
    ) -> None:
        """Initialize button."""
        super().__init__(coordinator)
        self._spot_id = spot_id
        self._button_type = button_type
        self._attr_unique_id = f"{spot_id}_{button_type}"
        self._attr_translation_key = translation_key
        self._attr_icon = icon
        if entity_category:
            self._attr_entity_category = entity_category

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
        """Return if button is available."""
        return self._spot_id in self.coordinator.data

    async def _execute_action(self, action_coro) -> None:
        """Execute action and schedule non-blocking background refresh."""
        try:
            _LOGGER.info(
                "Executing button action %s on station %s",
                self._button_type,
                self._spot_id,
            )
            await action_coro

            async def _delayed_refresh() -> None:
                await asyncio.sleep(ACTION_SETTLE_DELAY_SEC)
                await self.coordinator.async_request_refresh()

            self.hass.async_create_task(_delayed_refresh())
        except Exception:
            _LOGGER.exception(
                "Failed to execute %s", self._button_type
            )
            raise


class FiftyFiveRefreshStatusButton(FiftyFiveButtonBase):
    """Button to manually refresh status from GraphQL API."""

    def __init__(self, coordinator: FiftyFiveCoordinator, spot_id: str) -> None:
        """Initialize refresh button."""
        super().__init__(
            coordinator,
            spot_id,
            "refresh_status",
            "refresh_status",
            "mdi:refresh",
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.coordinator.async_request_refresh()


class FiftyFiveSoftResetButton(FiftyFiveButtonBase):
    """Button to perform soft reset on the charging station."""

    def __init__(self, coordinator: FiftyFiveCoordinator, spot_id: str) -> None:
        """Initialize soft reset button."""
        super().__init__(
            coordinator,
            spot_id,
            "soft_reset",
            "soft_reset",
            "mdi:restart",
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self._execute_action(self.coordinator.client.soft_reset(self._spot_id))


class FiftyFiveHardResetButton(FiftyFiveButtonBase):
    """Button to perform hard reset on the charging station."""

    def __init__(self, coordinator: FiftyFiveCoordinator, spot_id: str) -> None:
        """Initialize hard reset button."""
        super().__init__(
            coordinator,
            spot_id,
            "hard_reset",
            "hard_reset",
            "mdi:restart-alert",
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self._execute_action(self.coordinator.client.hard_reset(self._spot_id))


class FiftyFiveResetCacheButton(FiftyFiveButtonBase):
    """Button to reset station parameter cache."""

    def __init__(self, coordinator: FiftyFiveCoordinator, spot_id: str) -> None:
        """Initialize reset cache button."""
        super().__init__(
            coordinator,
            spot_id,
            "reset_cache",
            "reset_cache",
            "mdi:cached",
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self._execute_action(
            self.coordinator.client.reset_parameters_cache(self._spot_id)
        )


class FiftyFiveUnlockConnectorButton(FiftyFiveButtonBase):
    """Button to unlock connector on a charging channel."""

    def __init__(
        self,
        coordinator: FiftyFiveCoordinator,
        spot_id: str,
        channel_no: int = 1,
        is_multi_channel: bool = False,
    ) -> None:
        """Initialize unlock connector button."""
        button_type = (
            f"ch{channel_no}_unlock_connector"
            if is_multi_channel
            else "unlock_connector"
        )
        translation_key = (
            "channel_unlock_connector" if is_multi_channel else "unlock_connector"
        )
        super().__init__(
            coordinator,
            spot_id,
            button_type,
            translation_key,
            "mdi:lock-open-variant",
        )
        self._channel_no = channel_no
        if is_multi_channel:
            self._attr_translation_placeholders = {"channel": str(channel_no)}

    def _get_channel_id(self) -> str:
        """Resolve the GraphQL channel ID."""
        return self.coordinator.get_channel_id(self._spot_id, self._channel_no)

    async def async_press(self) -> None:
        """Handle button press."""
        channel_id = self._get_channel_id()
        await self._execute_action(
            self.coordinator.client.unlock_connector(self._spot_id, channel_id)
        )
