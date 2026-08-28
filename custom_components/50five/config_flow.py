"""Config flow for 50five GraphQL integration."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FiftyFiveApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CARD_ID,
    CONF_CONFIRM_OWNERSHIP,
    CONF_CUSTOMER_ID,
    CONF_DEVICE_ID,
    CONF_TOKEN_EXPIRES_AT,
    DOMAIN,
)
from .coordinator import FiftyFiveCoordinator
from .exceptions import FiftyFiveAuthError, FiftyFiveConnectionError, FiftyFiveError
from .models import ChargeCard

_LOGGER = logging.getLogger(__name__)


class FiftyFiveConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 50five GraphQL."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize config flow with a fresh persistent device ID."""
        self._device_id: str = str(uuid.uuid4())
        self._data: dict[str, Any] = {}
        self._cards: list[ChargeCard] = []
        self._reconfig_entry: config_entries.ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlow:
        """Get options flow handler."""
        return FiftyFiveOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial user step (credentials)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]

            session = async_get_clientsession(self.hass)
            client = FiftyFiveApiClient(
                username=username,
                password=password,
                session=session,
                device_id=self._device_id,
            )

            try:
                if await client.authenticate():
                    await self.async_set_unique_id(f"{DOMAIN}_{username.lower()}")
                    self._abort_if_unique_id_configured()

                    self._data = {
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_DEVICE_ID: self._device_id,
                        CONF_ACCESS_TOKEN: client.access_token,
                        CONF_TOKEN_EXPIRES_AT: (
                            client.token_expires_at.isoformat()
                            if client.token_expires_at
                            else None
                        ),
                    }
                    if client.customer_id:
                        self._data[CONF_CUSTOMER_ID] = client.customer_id

                    try:
                        self._cards = await client.get_tokens()
                    except FiftyFiveError as err:
                        _LOGGER.warning(
                            "Could not fetch charge cards for account: %s", err
                        )
                        self._cards = []

                    return await self.async_step_card()

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
            selected_card = (user_input.get(CONF_CARD_ID) or "").strip()
            confirmed = bool(user_input.get(CONF_CONFIRM_OWNERSHIP))

            if selected_card and not confirmed:
                errors[CONF_CONFIRM_OWNERSHIP] = "must_confirm_ownership"
            else:
                if self._reconfig_entry:
                    self.hass.config_entries.async_update_entry(
                        self._reconfig_entry,
                        data={
                            **self._reconfig_entry.data,
                            **self._data,
                            CONF_CARD_ID: selected_card,
                        },
                    )
                    return self.async_abort(reason="reconfigure_successful")

                return self.async_create_entry(
                    title=self._data[CONF_USERNAME],
                    data={
                        **self._data,
                        CONF_CARD_ID: selected_card,
                    },
                )

        card_options: dict[str, str] = {"": "None (skip)"}
        for card in self._cards:
            ident = card.identifier
            if ident:
                card_options[ident] = card.display_name

        schema = vol.Schema(
            {
                vol.Optional(CONF_CARD_ID, default=""): vol.In(card_options),
                vol.Optional(CONF_CONFIRM_OWNERSHIP, default=False): bool,
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
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )

        if not config_entry:
            return self.async_abort(reason="unknown")

        device_id = config_entry.data.get(CONF_DEVICE_ID) or str(uuid.uuid4())

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD] or config_entry.data.get(CONF_PASSWORD)

            session = async_get_clientsession(self.hass)
            client = FiftyFiveApiClient(
                username=username,
                password=password,
                session=session,
                device_id=device_id,
            )

            try:
                if await client.authenticate():
                    self._reconfig_entry = config_entry
                    self._data = {
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_DEVICE_ID: device_id,
                        CONF_ACCESS_TOKEN: client.access_token,
                        CONF_TOKEN_EXPIRES_AT: (
                            client.token_expires_at.isoformat()
                            if client.token_expires_at
                            else None
                        ),
                    }
                    if client.customer_id:
                        self._data[CONF_CUSTOMER_ID] = client.customer_id

                    try:
                        self._cards = await client.get_tokens()
                    except FiftyFiveError as err:
                        _LOGGER.warning(
                            "Could not fetch charge cards for account: %s", err
                        )
                        self._cards = []

                    return await self.async_step_card()

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
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication triggered by ConfigEntryAuthFailed."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication with new password."""
        errors: dict[str, str] = {}
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )

        if not config_entry:
            return self.async_abort(reason="unknown")

        username = config_entry.data.get(CONF_USERNAME, "")
        device_id = config_entry.data.get(CONF_DEVICE_ID) or str(uuid.uuid4())

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            session = async_get_clientsession(self.hass)
            client = FiftyFiveApiClient(
                username=username,
                password=password,
                session=session,
                device_id=device_id,
            )

            try:
                if await client.authenticate():
                    new_data = {
                        **config_entry.data,
                        CONF_PASSWORD: password,
                        CONF_ACCESS_TOKEN: client.access_token,
                        CONF_TOKEN_EXPIRES_AT: (
                            client.token_expires_at.isoformat()
                            if client.token_expires_at
                            else None
                        ),
                    }
                    if client.customer_id:
                        new_data[CONF_CUSTOMER_ID] = client.customer_id

                    self.hass.config_entries.async_update_entry(
                        config_entry, data=new_data
                    )
                    await self.hass.config_entries.async_reload(
                        config_entry.entry_id
                    )
                    return self.async_abort(reason="reauth_successful")

                errors["base"] = "invalid_auth"
            except AbortFlow:
                raise
            except FiftyFiveAuthError:
                errors["base"] = "invalid_auth"
            except FiftyFiveConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during reauth")
                errors["base"] = "unknown"

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


class FiftyFiveOptionsFlowHandler(OptionsFlow):
    """Handle options flow for 50five."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_card = (user_input.get(CONF_CARD_ID) or "").strip()
            confirmed = bool(user_input.get(CONF_CONFIRM_OWNERSHIP))

            if selected_card and not confirmed:
                errors[CONF_CONFIRM_OWNERSHIP] = "must_confirm_ownership"
            else:
                return self.async_create_entry(
                    title="",
                    data={CONF_CARD_ID: selected_card},
                )

        cards: list[ChargeCard] = []
        data_obj = getattr(self.config_entry, "runtime_data", None)
        coordinator: FiftyFiveCoordinator | None = (
            data_obj.coordinator
            if data_obj and hasattr(data_obj, "coordinator")
            else data_obj
        )
        if coordinator and coordinator.client:
            try:
                cards = await coordinator.client.get_tokens()
            except FiftyFiveError as err:
                _LOGGER.warning("Could not fetch charge cards in options flow: %s", err)

        current_card = self.config_entry.options.get(
            CONF_CARD_ID, self.config_entry.data.get(CONF_CARD_ID, "")
        )
        card_options: dict[str, str] = {"": "None (no card configured)"}
        for card in cards:
            ident = card.identifier
            if ident:
                card_options[ident] = card.display_name
        if current_card and current_card not in card_options:
            card_options[current_card] = current_card

        schema = vol.Schema(
            {
                vol.Optional(CONF_CARD_ID, default=current_card): vol.In(card_options),
                vol.Optional(CONF_CONFIRM_OWNERSHIP, default=bool(current_card)): bool,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
