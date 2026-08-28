"""Tests for the 50five config flow and options flow."""

import importlib
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

const = importlib.import_module("custom_components.50five.const")
exceptions = importlib.import_module("custom_components.50five.exceptions")

CONF_ACCESS_TOKEN = const.CONF_ACCESS_TOKEN
CONF_CARD_ID = const.CONF_CARD_ID
CONF_CONFIRM_OWNERSHIP = const.CONF_CONFIRM_OWNERSHIP
CONF_CUSTOMER_ID = const.CONF_CUSTOMER_ID
CONF_DEVICE_ID = const.CONF_DEVICE_ID
CONF_TOKEN_EXPIRES_AT = const.CONF_TOKEN_EXPIRES_AT
DOMAIN = const.DOMAIN

FiftyFiveAuthError = exceptions.FiftyFiveAuthError
FiftyFiveConnectionError = exceptions.FiftyFiveConnectionError
FiftyFiveError = exceptions.FiftyFiveError

from .const import (
    MOCK_CARD_ID,
    MOCK_CONFIG_DATA,
    MOCK_PASSWORD,
    MOCK_USER_STEP_INPUT,
    MOCK_USERNAME,
)


async def test_full_user_flow_success(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test full user step into card step with successful entry creation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=MOCK_USER_STEP_INPUT,
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "card"

    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        user_input={
            CONF_CARD_ID: MOCK_CARD_ID,
            CONF_CONFIRM_OWNERSHIP: True,
        },
    )
    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert result3["title"] == MOCK_USERNAME
    assert result3["data"][CONF_USERNAME] == MOCK_USERNAME
    assert result3["data"][CONF_CARD_ID] == MOCK_CARD_ID


async def test_user_flow_skip_card(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test user step then skipping card selection."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=MOCK_USER_STEP_INPUT,
    )
    assert result2["step_id"] == "card"

    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        user_input={
            CONF_CARD_ID: "",
            CONF_CONFIRM_OWNERSHIP: False,
        },
    )
    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert result3["data"][CONF_CARD_ID] == ""


async def test_card_step_must_confirm_ownership(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test card step shows error when card selected without confirmation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=MOCK_USER_STEP_INPUT,
    )

    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        user_input={
            CONF_CARD_ID: MOCK_CARD_ID,
            CONF_CONFIRM_OWNERSHIP: False,
        },
    )
    assert result3["type"] is FlowResultType.FORM
    assert result3["step_id"] == "card"
    assert result3["errors"] == {CONF_CONFIRM_OWNERSHIP: "must_confirm_ownership"}


async def test_user_flow_invalid_auth(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test user step with invalid authentication."""
    mock_api_client.authenticate.side_effect = FiftyFiveAuthError("Invalid credentials")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=MOCK_USER_STEP_INPUT,
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test user step with connection error."""
    mock_api_client.authenticate.side_effect = FiftyFiveConnectionError("Network error")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=MOCK_USER_STEP_INPUT,
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_user_flow_unexpected_exception(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
) -> None:
    """Test user step with unexpected exception."""
    mock_api_client.authenticate.side_effect = RuntimeError("Crash")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=MOCK_USER_STEP_INPUT,
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "unknown"}


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test duplicate configuration aborts."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=MOCK_USER_STEP_INPUT,
    )
    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_user_flow_get_tokens_error_fallback(
    hass: HomeAssistant,
    mock_api_client: AsyncMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test token retrieval error still allows progressing to card step."""
    mock_api_client.get_tokens.side_effect = FiftyFiveError("Tokens unavailable")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=MOCK_USER_STEP_INPUT,
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "card"


async def test_reconfigure_flow_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test successful reconfiguration flow."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_config_entry.entry_id,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_USERNAME: MOCK_USERNAME,
            CONF_PASSWORD: "new-password",
        },
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "card"

    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        user_input={
            CONF_CARD_ID: "NL-50F-999999-9",
            CONF_CONFIRM_OWNERSHIP: True,
        },
    )
    assert result3["type"] is FlowResultType.ABORT
    assert result3["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_CARD_ID] == "NL-50F-999999-9"


async def test_reauth_flow_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test successful re-authentication flow."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=dict(mock_config_entry.data),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: "updated-password"},
        )
    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "updated-password"


async def test_reauth_flow_invalid_auth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test reauth flow with invalid credentials."""
    mock_api_client.authenticate.side_effect = FiftyFiveAuthError("Invalid credentials")
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=dict(mock_config_entry.data),
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_PASSWORD: "wrong-password"},
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_options_flow(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test options flow to update charge card."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    # 1. Unconfirmed ownership
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_CARD_ID: "NL-50F-999999-9",
            CONF_CONFIRM_OWNERSHIP: False,
        },
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {CONF_CONFIRM_OWNERSHIP: "must_confirm_ownership"}

    # 2. Confirmed ownership
    result3 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_CARD_ID: "NL-50F-999999-9",
            CONF_CONFIRM_OWNERSHIP: True,
        },
    )
    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_CARD_ID] == "NL-50F-999999-9"


async def test_reconfigure_flow_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test reconfigure error branches."""
    mock_config_entry.add_to_hass(hass)

    # 1. Invalid auth
    mock_api_client.authenticate.side_effect = FiftyFiveAuthError("Bad creds")
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_config_entry.entry_id,
        },
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: "bad"},
    )
    assert result2["errors"] == {"base": "invalid_auth"}

    # 2. Connection error
    mock_api_client.authenticate.side_effect = FiftyFiveConnectionError("No conn")
    result3 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: "bad"},
    )
    assert result3["errors"] == {"base": "cannot_connect"}

    # 3. Unexpected error
    mock_api_client.authenticate.side_effect = RuntimeError("Crash")
    result4 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: "bad"},
    )
    assert result4["errors"] == {"base": "unknown"}


async def test_reconfigure_missing_entry(hass: HomeAssistant) -> None:
    """Test reconfigure aborts if entry is missing."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": "non_existent_entry",
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unknown"


async def test_reauth_missing_entry(hass: HomeAssistant) -> None:
    """Test reauth aborts if entry is missing."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": "non_existent_entry",
        },
        data={},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unknown"


async def test_reauth_flow_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: AsyncMock,
) -> None:
    """Test reauth connection error and unexpected error branches."""
    mock_config_entry.add_to_hass(hass)

    # 1. Connection error
    mock_api_client.authenticate.side_effect = FiftyFiveConnectionError("No conn")
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=dict(mock_config_entry.data),
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_PASSWORD: "bad"},
    )
    assert result2["errors"] == {"base": "cannot_connect"}

    # 2. Unexpected error
    mock_api_client.authenticate.side_effect = RuntimeError("Crash")
    result3 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_PASSWORD: "bad"},
    )
    assert result3["errors"] == {"base": "unknown"}
