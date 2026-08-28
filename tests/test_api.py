"""Tests for 50five GraphQL API client."""

import asyncio
import importlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from gql import gql as parse_gql
from gql.transport.aiohttp import TransportClosed, TransportConnectionFailed
from gql.transport.exceptions import TransportError, TransportServerError

api_mod = importlib.import_module("custom_components.50five.api")
const = importlib.import_module("custom_components.50five.const")
exceptions = importlib.import_module("custom_components.50five.exceptions")

FiftyFiveApiClient = api_mod.FiftyFiveApiClient
HomeAssistantAIOHTTPTransport = api_mod.HomeAssistantAIOHTTPTransport
_extract_customer_id_from_jwt = api_mod._extract_customer_id_from_jwt
_extract_jwt_claims = api_mod._extract_jwt_claims
DEFAULT_VAT_MULTIPLIER = const.DEFAULT_VAT_MULTIPLIER
FiftyFiveError = exceptions.FiftyFiveError
FiftyFiveApiError = exceptions.FiftyFiveApiError
FiftyFiveAuthError = exceptions.FiftyFiveAuthError
FiftyFiveConnectionError = exceptions.FiftyFiveConnectionError

from .const import (
    MOCK_ACCESS_TOKEN,
    MOCK_ACTIVE_TRANSACTION_RESPONSE,
    MOCK_CHARGE_STATION_DETAILS_RESPONSE,
    MOCK_CUSTOMER_CHARGE_CARDS_RESPONSE,
    MOCK_CUSTOMER_CHARGE_STATIONS_RESPONSE,
    MOCK_CUSTOMER_ID,
    MOCK_CUSTOMER_RESPONSE,
    MOCK_DEVICE_ID,
    MOCK_LOGIN_RESPONSE,
    MOCK_PASSWORD,
    MOCK_STATION_ID,
    MOCK_USERNAME,
)


def test_extract_jwt_claims() -> None:
    """Test JWT claims decoding."""
    claims = _extract_jwt_claims(MOCK_ACCESS_TOKEN)
    assert claims.get("id") == MOCK_CUSTOMER_ID
    assert claims.get("email") == MOCK_USERNAME
    assert claims.get("external_api", {}).get("customerId") == MOCK_CUSTOMER_ID

    # Malformed token returns empty dict
    assert _extract_jwt_claims("not.a.valid.jwt") == {}
    assert _extract_customer_id_from_jwt(MOCK_ACCESS_TOKEN) == MOCK_CUSTOMER_ID
    assert _extract_customer_id_from_jwt("invalid") is None


def test_api_client_initialization_and_token_expiry() -> None:
    """Test client initialization and token expiration check."""
    client = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
        device_id=MOCK_DEVICE_ID,
        access_token=MOCK_ACCESS_TOKEN,
    )
    assert client.access_token == MOCK_ACCESS_TOKEN
    assert client.customer_id == MOCK_CUSTOMER_ID
    assert client.is_authenticated is True
    assert client.is_token_expired() is False

    # Expired token in the past
    client_expired = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
        access_token="eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjEwMDAwMDAwMDB9.sig",
    )
    assert client_expired.is_token_expired() is True
    assert client_expired.is_authenticated is False

    # ISO string token_expires_at
    client_iso = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
        access_token="some_token",
        token_expires_at="2035-01-01T00:00:00+00:00",
    )
    assert client_iso.is_token_expired() is False

    # Datetime object token_expires_at
    client_dt = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
        access_token="some_token",
        token_expires_at=datetime(2035, 1, 1, tzinfo=timezone.utc),
    )
    assert client_dt.is_token_expired() is False

    # Empty access token
    client_no_token = FiftyFiveApiClient(username=MOCK_USERNAME, password=MOCK_PASSWORD)
    assert client_no_token.is_token_expired() is True


def test_api_client_headers() -> None:
    """Test mobile app headers."""
    client = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
        device_id=MOCK_DEVICE_ID,
        access_token="test_token",
    )
    headers = client._get_headers()
    assert headers["apollographql-client-name"] == "com.plugz.app50five"
    assert headers["plugz-application-id"] == MOCK_DEVICE_ID
    assert headers["authorization"] == "Bearer test_token"


async def test_authenticate_success() -> None:
    """Test successful authentication flow and callback invocation."""
    token_refreshed = AsyncMock()

    client = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
        device_id=MOCK_DEVICE_ID,
        on_token_refreshed=token_refreshed,
    )

    with patch("gql.Client.execute_async", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = MOCK_LOGIN_RESPONSE

        assert await client.authenticate() is True
        assert client.access_token == MOCK_ACCESS_TOKEN
        assert client.customer_id == MOCK_CUSTOMER_ID
        assert client.token_expires_at is not None
        token_refreshed.assert_awaited_once()


async def test_authenticate_expiration_fallbacks() -> None:
    """Test token expiration fallback when claims have no exp."""
    # Token without exp in claims
    token_no_exp = "eyJhbGciOiJIUzI1NiJ9.eyJpZCI6ImN1c3RfbW9jayJ9.sig"
    client = FiftyFiveApiClient(username=MOCK_USERNAME, password=MOCK_PASSWORD)

    # 1. Fallback to expiresIn
    with patch("gql.Client.execute_async", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {
            "login": {"accessToken": token_no_exp, "expiresIn": 3600}
        }
        assert await client.authenticate() is True
        assert client.token_expires_at is not None

    # 2. Fallback to default 24h
    with patch("gql.Client.execute_async", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {
            "login": {"accessToken": token_no_exp, "expiresIn": None}
        }
        assert await client.authenticate() is True
        assert client.token_expires_at is not None


async def test_authenticate_callback_exception_handling() -> None:
    """Test authenticate still succeeds if callback raises."""
    def bad_callback(token, expires, cust_id):
        raise RuntimeError("Callback crash")

    client = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
        on_token_refreshed=bad_callback,
    )

    with patch("gql.Client.execute_async", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = MOCK_LOGIN_RESPONSE
        assert await client.authenticate() is True


async def test_authenticate_failures() -> None:
    """Test authentication failure scenarios."""
    client = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
    )

    # 1. Invalid response payload
    with patch("gql.Client.execute_async", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"login": None}
        with pytest.raises(FiftyFiveAuthError):
            await client.authenticate()

    # 2. Login response missing access token
    with patch("gql.Client.execute_async", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"login": {"accessToken": ""}}
        with pytest.raises(FiftyFiveAuthError):
            await client.authenticate()

    # 3. 401 Unauthorized transport error
    with patch("gql.Client.execute_async", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = TransportServerError("401 Unauthorized")
        with pytest.raises(FiftyFiveAuthError):
            await client.authenticate()

    # 4. Connection failed
    with patch("gql.Client.execute_async", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = TransportConnectionFailed("Host unreachable")
        with pytest.raises(FiftyFiveConnectionError):
            await client.authenticate()

    # 5. Generic exception with auth keyword
    with patch("gql.Client.execute_async", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = Exception("invalid password provided")
        with pytest.raises(FiftyFiveAuthError):
            await client.authenticate()


async def test_get_vat_multiplier() -> None:
    """Test VAT multiplier calculation for different customer providerCategories."""
    client = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
        access_token=MOCK_ACCESS_TOKEN,
        customer_id=MOCK_CUSTOMER_ID,
    )

    # Belgium category: BE -> 1.06
    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {
            "getCustomerById": {"id": MOCK_CUSTOMER_ID, "providerCategory": "BE"}
        }
        vat = await client.get_vat_multiplier()
        assert vat == 1.06

    # Cached value returns immediately
    assert await client.get_vat_multiplier() == 1.06

    # Reset cache and test fallback on query error
    client._vat_multiplier = None
    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.side_effect = FiftyFiveError("Query error")
        vat_fallback = await client.get_vat_multiplier()
        assert vat_fallback == DEFAULT_VAT_MULTIPLIER

    # Unexpected exception fallback
    client._vat_multiplier = None
    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.side_effect = TypeError("Unexpected error")
        assert await client.get_vat_multiplier() == DEFAULT_VAT_MULTIPLIER


async def test_execute_query_reauth_on_401() -> None:
    """Test _execute_query automatically re-authenticates and retries on 401."""
    client = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
        access_token=MOCK_ACCESS_TOKEN,
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    async def _mock_authenticate():
        client._access_token = "refreshed_token"
        client._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        return True

    with patch.object(
        client, "authenticate", side_effect=_mock_authenticate
    ) as mock_auth, patch(
        "gql.Client.execute_async", new_callable=AsyncMock
    ) as mock_exec:
        # First call fails with 401, second succeeds after auth
        mock_exec.side_effect = [
            TransportServerError("401 Unauthorized"),
            {"result": "success"},
        ]

        _DUMMY_DOC = parse_gql("{ __typename }")
        res = await client._execute_query(_DUMMY_DOC)
        assert res == {"result": "success"}
        assert mock_auth.call_count == 1


async def test_execute_query_connection_and_api_errors() -> None:
    """Test _execute_query error wrapping."""
    client = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
        access_token=MOCK_ACCESS_TOKEN,
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    _DUMMY_DOC = parse_gql("{ __typename }")
    with patch(
        "gql.Client.execute_async", side_effect=TransportConnectionFailed("Conn err")
    ):
        with pytest.raises(FiftyFiveConnectionError):
            await client._execute_query(_DUMMY_DOC)

    with patch(
        "gql.Client.execute_async", side_effect=RuntimeError("General API error")
    ):
        with pytest.raises(FiftyFiveApiError):
            await client._execute_query(_DUMMY_DOC)


async def test_api_query_methods() -> None:
    """Test all API query methods."""
    client = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
        access_token=MOCK_ACCESS_TOKEN,
        customer_id=MOCK_CUSTOMER_ID,
    )

    # 1. get_customer_charge_stations
    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = MOCK_CUSTOMER_CHARGE_STATIONS_RESPONSE
        stations = await client.get_customer_charge_stations()
        assert len(stations) == 2
        assert stations[0].id == MOCK_STATION_ID

    # 2. get_charge_station_details
    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = MOCK_CHARGE_STATION_DETAILS_RESPONSE
        station = await client.get_charge_station_details(MOCK_STATION_ID)
        assert station is not None
        assert station.id == MOCK_STATION_ID

    # 3. get_active_transaction
    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = MOCK_ACTIVE_TRANSACTION_RESPONSE
        tx = await client.get_active_transaction()
        assert tx is not None
        assert tx.energy_delivered == 12.4

    # 4. get_charge_cards / get_tokens
    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = MOCK_CUSTOMER_CHARGE_CARDS_RESPONSE
        cards = await client.get_charge_cards()
        assert len(cards) == 2
        assert cards[0].identifier == "NL-50F-123456-7"
        # get_tokens alias
        tokens = await client.get_tokens()
        assert len(tokens) == 2


async def test_get_charge_cards_edge_cases() -> None:
    """Test get_charge_cards when customer ID missing or response empty."""
    client = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
    )
    # No customer ID and no token
    cards = await client.get_charge_cards()
    assert cards == []

    # getCustomerById returns None
    client.customer_id = "cust_123"
    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {"getCustomerById": None}
        assert await client.get_charge_cards() == []


async def test_api_mutation_methods() -> None:
    """Test all API action/mutation methods."""
    client = FiftyFiveApiClient(
        username=MOCK_USERNAME,
        password=MOCK_PASSWORD,
        access_token=MOCK_ACCESS_TOKEN,
    )

    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {"startTransaction": True}
        assert await client.start_charging(MOCK_STATION_ID, "1", "CARD-1") is True

    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {"stopTransaction": True}
        assert await client.stop_charging(MOCK_STATION_ID, "1") is True

    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {"unlockConnector": True}
        assert await client.unlock_connector(MOCK_STATION_ID, "1") is True

    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {"softReset": True}
        assert await client.soft_reset(MOCK_STATION_ID) is True

    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {"hardReset": True}
        assert await client.hard_reset(MOCK_STATION_ID) is True

    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {"resetChargeStationParametersCache": True}
        assert await client.reset_parameters_cache(MOCK_STATION_ID) is True

    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {"getNetBalancedChargingStatus": True}
        assert await client.get_net_balanced_charging_status(MOCK_STATION_ID) is True

    with patch.object(client, "_execute_query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = {"netBalancedCharging": [{"startTime": "00:00", "stopTime": "23:59", "weekday": "MONDAY"}]}
        assert await client.set_net_balanced_charging(MOCK_STATION_ID, True) is True


async def test_homeassistant_aiohttp_transport() -> None:
    """Test HomeAssistantAIOHTTPTransport lifecycle with shared session."""
    shared_session = MagicMock()
    transport = HomeAssistantAIOHTTPTransport(
        url="https://example.com/graphql",
        shared_session=shared_session,
    )

    await transport.connect()
    assert transport.session == shared_session

    await transport.close()
    assert transport.session is None
    # Verify shared session was NOT closed
    shared_session.close.assert_not_called()

    # Executing when not connected raises TransportClosed
    with pytest.raises(TransportClosed):
        await transport.execute("request")
