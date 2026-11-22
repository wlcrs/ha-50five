"""Config flow for 50five GraphQL integration."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import FiftyFiveApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CARD_ID,
    CONF_CARD_IDS,
    CONF_CONFIRM_OWNERSHIP,
    CONF_CUSTOMER_ID,
    CONF_DEVICE_ID,
    CONF_TOKEN_EXPIRES_AT,
    DOMAIN,
)
from .coordinator import FiftyFiveCoordinator, get_configured_card_ids
from .exceptions import FiftyFiveAuthError, FiftyFiveConnectionError, FiftyFiveError
from .models import ChargeCard

_LOGGER = logging.getLogger(__name__)


def _build_entry_data(
    client: FiftyFiveApiClient,
    username: str,
    password: str,
    device_id: str,
) -> dict[str, Any]:
    """Build config entry data dictionary from an authenticated client."""
    data: dict[str, Any] = {
        CONF_USERNAME: username,
        CONF_PASSWORD: password,
        CONF_DEVICE_ID: device_id,
        CONF_ACCESS_TOKEN: client.access_token,
        CONF_TOKEN_EXPIRES_AT: (
            client.token_expires_at.isoformat() if client.token_expires_at else None
        ),
    }
    if client.customer_id:
        data[CONF_CUSTOMER_ID] = client.customer_id
    return data


def _build_card_options(
    cards: list[ChargeCard],
    existing_ids: list[str] | None = None,
) -> dict[str, str]:
    """Build multi-select options mapping card identifier to display name."""
    card_options: dict[str, str] = {}
    for card in cards:
        ident = card.identifier
        if ident:
            card_options[ident] = card.display_name
    for ident in existing_ids or []:
        if ident and ident not in card_options:
            card_options[ident] = ident
    return card_options


def _build_card_selector(
    cards: list[ChargeCard],
    existing_ids: list[str] | None = None,
) -> SelectSelector:
    """Build a multi-select list selector for charge cards."""
    options_map = _build_card_options(cards, existing_ids)
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=ident, label=label)
                for ident, label in options_map.items()
            ],
            multiple=True,
            mode=SelectSelectorMode.LIST,
        )
    )


def _validate_card_selection(
    user_input: dict[str, Any],
) -> tuple[list[str], dict[str, str]]:
    """Validate multi-card selection and ownership confirmation."""
    raw_selected = user_input.get(CONF_CARD_IDS) or []
    selected_cards = [
        card.strip()
        for card in raw_selected
        if isinstance(card, str) and card.strip()
    ]
    confirmed = bool(user_input.get(CONF_CONFIRM_OWNERSHIP))
    errors: dict[str, str] = {}
    if selected_cards and not confirmed:
        errors[CONF_CONFIRM_OWNERSHIP] = "must_confirm_ownership"
    return selected_cards, errors


class FiftyFiveConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 50five GraphQL."""

    VERSION = 2
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize config flow with a fresh persistent device ID."""
        self._device_id: str = str(uuid.uuid4())
        self._data: dict[str, Any] = {}
        self._cards: list[ChargeCard] = []
        self._reconfig_entry: config_entries.ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowWithReload:
        """Get options flow handler."""
        return FiftyFiveOptionsFlowHandler()

    async def _async_authenticate(
        self,
        username: str,
        password: str,
        device_id: str,
    ) -> tuple[FiftyFiveApiClient | None, dict[str, str]]:
        """Authenticate credentials and return (client, errors)."""
        errors: dict[str, str] = {}
        session = async_get_clientsession(self.hass)
        client = FiftyFiveApiClient(
            username=username,
            password=password,
            session=session,
            device_id=device_id,
        )
        try:
            if await client.authenticate():
                return client, errors
            errors["base"] = "invalid_auth"
        except AbortFlow:
            raise
        except FiftyFiveAuthError:
            errors["base"] = "invalid_auth"
        except FiftyFiveConnectionError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected exception during config flow")
            errors["base"] = "unknown"
        return None, errors

    async def _async_fetch_cards(self, client: FiftyFiveApiClient) -> list[ChargeCard]:
        """Fetch charge cards for an authenticated account."""
        try:
            return await client.get_tokens()
        except FiftyFiveError as err:
            _LOGGER.warning("Could not fetch charge cards for account: %s", err)
            return []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial user step (credentials)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            client, errors = await self._async_authenticate(
                username, password, self._device_id
            )
            if client is not None:
                await self.async_set_unique_id(f"{DOMAIN}_{username.lower()}")
                self._abort_if_unique_id_configured()
                self._data = _build_entry_data(
                    client, username, password, self._device_id
                )
                self._cards = await self._async_fetch_cards(client)
                return await self.async_step_card()

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_card(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle charge card selection and ownership confirmation step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_cards, errors = _validate_card_selection(user_input)
            if not errors:
                if self._reconfig_entry:
                    new_data = {
                        **self._reconfig_entry.data,
                        **self._data,
                        CONF_CARD_IDS: selected_cards,
                    }
                    new_data.pop(CONF_CARD_ID, None)
                    new_options = {
                        k: v
                        for k, v in self._reconfig_entry.options.items()
                        if k not in (CONF_CARD_ID, CONF_CARD_IDS)
                    }
                    return self.async_update_reload_and_abort(
                        self._reconfig_entry,
                        data=new_data,
                        options=new_options,
                        reason="reconfigure_successful",
                    )

                return self.async_create_entry(
                    title=self._data[CONF_USERNAME],
                    data={
                        **self._data,
                        CONF_CARD_IDS: selected_cards,
                    },
                )

        current_cards = (
            get_configured_card_ids(
                self._reconfig_entry.data, self._reconfig_entry.options
            )
            if self._reconfig_entry
            else []
        )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CARD_IDS, default=current_cards
                ): _build_card_selector(self._cards, current_cards),
                vol.Optional(
                    CONF_CONFIRM_OWNERSHIP, default=bool(current_cards)
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="card",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration step."""
        errors: dict[str, str] = {}
        try:
            config_entry = self._get_reconfigure_entry()
        except config_entries.UnknownEntry:
            return self.async_abort(reason="unknown")

        device_id = config_entry.data.get(CONF_DEVICE_ID) or str(uuid.uuid4())

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD] or config_entry.data.get(
                CONF_PASSWORD, ""
            )
            client, errors = await self._async_authenticate(
                username, password, device_id
            )
            if client is not None:
                await self.async_set_unique_id(f"{DOMAIN}_{username.lower()}")
                self._abort_if_unique_id_mismatch()
                self._reconfig_entry = config_entry
                self._data = _build_entry_data(client, username, password, device_id)
                self._cards = await self._async_fetch_cards(client)
                return await self.async_step_card()

        current_data = config_entry.data
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME, default=current_data.get(CONF_USERNAME)
                ): str,
                vol.Optional(CONF_PASSWORD, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication triggered by ConfigEntryAuthFailed."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication with new password."""
        errors: dict[str, str] = {}
        try:
            config_entry = self._get_reauth_entry()
        except config_entries.UnknownEntry:
            return self.async_abort(reason="unknown")

        username = config_entry.data.get(CONF_USERNAME, "")
        device_id = config_entry.data.get(CONF_DEVICE_ID) or str(uuid.uuid4())

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            client, errors = await self._async_authenticate(
                username, password, device_id
            )
            if client is not None:
                data_updates = {
                    CONF_PASSWORD: password,
                    CONF_ACCESS_TOKEN: client.access_token,
                    CONF_TOKEN_EXPIRES_AT: (
                        client.token_expires_at.isoformat()
                        if client.token_expires_at
                        else None
                    ),
                }
                if client.customer_id:
                    data_updates[CONF_CUSTOMER_ID] = client.customer_id

                return self.async_update_reload_and_abort(
                    config_entry,
                    data_updates=data_updates,
                    reason="reauth_successful",
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            description_placeholders={"username": username},
            errors=errors,
        )


class FiftyFiveOptionsFlowHandler(OptionsFlowWithReload):
    """Handle options flow for 50five."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_cards, errors = _validate_card_selection(user_input)
            if not errors:
                return self.async_create_entry(
                    title="",
                    data={CONF_CARD_IDS: selected_cards},
                )

        cards: list[ChargeCard] = []
        coordinator: FiftyFiveCoordinator | None = getattr(
            self.config_entry, "runtime_data", None
        )
        if coordinator and coordinator.client:
            try:
                cards = await coordinator.client.get_tokens()
            except FiftyFiveError as err:
                _LOGGER.warning("Could not fetch charge cards in options flow: %s", err)

        current_cards = get_configured_card_ids(
            self.config_entry.data, self.config_entry.options
        )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CARD_IDS, default=current_cards
                ): _build_card_selector(cards, current_cards),
                vol.Optional(
                    CONF_CONFIRM_OWNERSHIP, default=bool(current_cards)
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
