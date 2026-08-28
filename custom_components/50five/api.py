"""GraphQL API client for 50five charging stations using gql with strong typing."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from gql import Client, gql
from gql.graphql_request import GraphQLRequest
from gql.transport.aiohttp import (
    AIOHTTPTransport,
    TransportClosed,
    TransportConnectionFailed,
    close_files,
)
from gql.transport.exceptions import TransportError, TransportServerError

from .const import DEFAULT_BASE_URL, DEFAULT_VAT_MULTIPLIER, VAT_MULTIPLIERS
from .exceptions import (
    FiftyFiveApiError,
    FiftyFiveAuthError,
    FiftyFiveConnectionError,
    FiftyFiveError,
)
from .models import (
    ActiveTransaction,
    ChargeCard,
    ChargeStation,
    LoginResult,
)

_LOGGER = logging.getLogger(__name__)


def _extract_jwt_claims(token: str) -> dict[str, Any]:
    """Extract claims payload dictionary from JWT token."""
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1]
            padded = payload_b64 + "=" * (-len(payload_b64) % 4)
            return json.loads(base64.urlsafe_b64decode(padded.encode()))
    except Exception:
        pass
    return {}


def _extract_customer_id_from_jwt(token: str) -> str | None:
    """Extract customerId from JWT token payload."""
    claims = _extract_jwt_claims(token)
    return claims.get("external_api", {}).get("customerId") or claims.get("id")


# GraphQL Documents parsed as AST via gql DSL
LOGIN_MUTATION = gql("""
mutation Login($email: String!, $password: String!) {
  login(email: $email, password: $password) {
    accessToken: access_token
    expiresIn: expires_in
    tokenType: token_type
  }
}
""")

GET_CUSTOMER_BY_ID_QUERY = gql("""
query GetCustomerById($getCustomerByIdId: ID!) {
  getCustomerById(id: $getCustomerByIdId) {
    id
    providerCategory
  }
}
""")

GET_CUSTOMER_CHARGE_CARDS_QUERY = gql("""
query GetCustomerChargecards($getCustomerByIdId: ID!) {
  getCustomerById(id: $getCustomerByIdId) {
    id
    cards {
      id
      externalId
      internalId
      contractId
      roaming
      state
      type
      roamingHomeChargingEnabled
      roamingHubStatus
      cardProvider {
        name
      }
      customer {
        id
      }
      transactionCustomer {
        id
      }
    }
  }
}
""")

GET_CUSTOMER_CHARGE_STATIONS_QUERY = gql("""
query GetCustomerChargeStations($txFilters: TransactionFilter, $txSort: TransactionSort) {
  getCustomerChargeStations {
    id
    commId
    name
    channels {
      id
      evseId
      channelNo
      globalStatus
    }
    location {
      countryDetails {
        code
        currency {
          code
        }
      }
    }
    manufacturerType {
      model
      vendor
    }
    subscriptions {
      id
      startDate
      endDate
      product {
        id
        name
      }
    }
    chargeGroup {
      tariffVat {
        energy
      }
      anonymousTariffVat {
        energy
        flat
        time
      }
    }
    accessOptions {
      authorizationMode
      accessType
      publishedOnMap
    }
    homeChargingCompensation {
      hccEnabled
      hccTariff
    }
    transactions(filters: $txFilters, sort: $txSort) {
      items {
        id
        status
        globalStatus
        type
        startDate
        lastUpdateDate
        totalDuration
        totalEnergy
        totalIdleTime
        homeCharging
        cardSnapshot {
          externalId
          internalId
          contractId
          type
        }
        transactionPrices {
          totalCost
          type
          vatPercentage
          currency {
            code
          }
        }
      }
    }
  }
}
""")

GET_CHARGE_STATION_DETAILS_QUERY = gql("""
query GetChargeStationDetails($getChargeStationByIdId: ID!, $txFilters: TransactionFilter, $txSort: TransactionSort) {
  getChargeStationById(id: $getChargeStationByIdId) {
    id
    commId
    name
    channels {
      id
      evseId
      channelNo
      globalStatus
      cableLock
      soc
      activeTariff {
        energy
        flat
        time
      }
    }
    location {
      id
      address
      postalCode
      city
      countryDetails {
        code
        currency {
          code
        }
      }
    }
    manufacturerType {
      vendor
      model
    }
    transactions(filters: $txFilters, sort: $txSort) {
      items {
        id
        status
        globalStatus
        type
        startDate
        lastUpdateDate
        totalDuration
        totalEnergy
        totalIdleTime
        homeCharging
        cardSnapshot {
          externalId
          internalId
          contractId
          type
        }
        transactionPrices {
          totalCost
          type
          vatPercentage
          currency {
            code
          }
        }
      }
    }
  }
}
""")

LMS_ACTIVE_TRANSACTION_QUERY = gql("""
query LmsActiveTransaction {
  lmsActiveTransaction {
    updateDate
    address
    zipCode
    city
    energyDelivered
    startDate
    countryCode
    currency
    totalAmount
    vat
    durationCharging
    priceElements {
      type
      price
    }
    tariffId
    channelVisibleId
  }
}
""")

START_TRANSACTION_MUTATION = gql("""
mutation StartTransaction($chargeStationId: ID!, $channelId: ID!, $card: String) {
  startTransaction(
    chargeStationId: $chargeStationId
    channelId: $channelId
    card: $card
  )
}
""")

STOP_TRANSACTION_MUTATION = gql("""
mutation StopTransaction($chargeStationId: ID!, $channelId: ID!) {
  stopTransaction(chargeStationId: $chargeStationId, channelId: $channelId)
}
""")

UNLOCK_CONNECTOR_MUTATION = gql("""
mutation UnlockConnector($chargeStationId: ID!, $channelId: ID!) {
  unlockConnector(chargeStationId: $chargeStationId, channelId: $channelId)
}
""")

SOFT_RESET_MUTATION = gql("""
mutation SoftReset($chargeStationId: ID!) {
  softReset(chargeStationId: $chargeStationId)
}
""")

HARD_RESET_MUTATION = gql("""
mutation HardReset($chargeStationId: ID!) {
  hardReset(chargeStationId: $chargeStationId)
}
""")

RESET_CACHE_MUTATION = gql("""
mutation resetChargeStationParametersCache($chargeStationId: ID!) {
  resetChargeStationParametersCache(chargeStationId: $chargeStationId)
}
""")


class HomeAssistantAIOHTTPTransport(AIOHTTPTransport):
    """AIOHTTPTransport that uses Home Assistant's shared ClientSession safely without closing it."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        shared_session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize transport."""
        super().__init__(url=url, headers=headers, timeout=timeout)
        self._shared_session = shared_session

    async def connect(self) -> None:
        """Connect by attaching the shared session without reopening."""
        if self._shared_session is not None:
            self.session = self._shared_session
        else:
            await super().connect()

    async def close(self) -> None:
        """Close by detaching without closing the shared Home Assistant session."""
        if self._shared_session is not None:
            self.session = None
        else:
            await super().close()

    async def execute(
        self,
        request: Any,
        *,
        extra_args: dict[str, Any] | None = None,
        upload_files: bool = False,
    ) -> Any:
        """Execute a request with transport headers on the shared session."""
        if self._shared_session is None:
            return await super().execute(
                request,
                extra_args=extra_args,
                upload_files=upload_files,
            )

        if self.session is None:
            raise TransportClosed("Transport is not connected")

        request_args = self._prepare_request(request, extra_args, upload_files)
        request_args["headers"] = self.headers

        try:
            async with self.session.post(
                self.url, ssl=self.ssl, **request_args
            ) as response:
                return await self._prepare_result(response)
        except TransportError:
            raise
        except Exception as err:
            raise TransportConnectionFailed(str(err)) from err
        finally:
            if upload_files:
                close_files(list(self.files.values()))


class FiftyFiveApiClient:
    """Strongly typed GraphQL API client for 50five using gql."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
        device_id: str | None = None,
        customer_id: str | None = None,
        access_token: str | None = None,
        token_expires_at: datetime | str | None = None,
        on_token_refreshed: (
            Callable[[str, str, str | None], Coroutine[Any, Any, None] | None] | None
        ) = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        """Initialize the API client."""
        self.base_url = base_url.rstrip("/") if base_url else DEFAULT_BASE_URL
        self.username = username
        self.password = password
        self.session = session
        self.device_id = device_id or str(uuid.uuid4())
        self.customer_id = customer_id
        self._access_token: str | None = access_token
        self._token_expires_at: datetime | None = None
        self._on_token_refreshed = on_token_refreshed

        if isinstance(token_expires_at, str):
            try:
                self._token_expires_at = datetime.fromisoformat(token_expires_at)
            except ValueError:
                pass
        elif isinstance(token_expires_at, datetime):
            self._token_expires_at = token_expires_at

        # If token was supplied but no explicit expires_at, parse claims
        if self._access_token and self._token_expires_at is None:
            claims = _extract_jwt_claims(self._access_token)
            exp = claims.get("exp")
            if exp:
                self._token_expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
            if not self.customer_id:
                self.customer_id = (
                    claims.get("external_api", {}).get("customerId")
                    or claims.get("id")
                )

        self._vat_multiplier: float | None = None
        self._auth_lock = asyncio.Lock()
        self._client: Client | None = None
        self._rebuild_client()

    @property
    def access_token(self) -> str | None:
        """Return current access token."""
        return self._access_token

    @property
    def token_expires_at(self) -> datetime | None:
        """Return token expiration timestamp."""
        return self._token_expires_at

    @property
    def is_authenticated(self) -> bool:
        """Return if client currently has an active, non-expired access token."""
        return bool(self._access_token and not self.is_token_expired())

    def is_token_expired(self, buffer_seconds: int = 60) -> bool:
        """Check if access token is expired or close to expiring."""
        if not self._access_token:
            return True
        if self._token_expires_at is not None:
            now = datetime.now(timezone.utc)
            return now + timedelta(seconds=buffer_seconds) >= self._token_expires_at

        claims = _extract_jwt_claims(self._access_token)
        exp = claims.get("exp")
        if exp:
            self._token_expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            return now + timedelta(seconds=buffer_seconds) >= self._token_expires_at

        return False

    def _get_headers(self) -> dict[str, str]:
        """Construct mobile app emulation headers."""
        headers = {
            "User-Agent": "50five/1.0.0 (Android; GraphQL)",
            "apollographql-client-name": "com.plugz.app50five",
            "apollographql-client-version": "1.0.0",
            "plugz-application-id": self.device_id,
        }
        if self._access_token:
            headers["authorization"] = f"Bearer {self._access_token}"
        return headers

    def _rebuild_client(self) -> None:
        """Reconstruct the gql client with updated headers."""
        transport = HomeAssistantAIOHTTPTransport(
            url=self.base_url,
            headers=self._get_headers(),
            timeout=30,
            shared_session=self.session,
        )
        self._client = Client(transport=transport, fetch_schema_from_transport=False)

    async def authenticate(self) -> bool:
        """Authenticate with the GraphQL API and acquire JWT access token."""
        async with self._auth_lock:
            # Check if another concurrent task refreshed the token while we waited
            if self._access_token and not self.is_token_expired():
                return True

            _LOGGER.debug(
                "Authenticating user %s against %s (device_id: %s)",
                self.username,
                self.base_url,
                self.device_id,
            )

            login_headers = {
                "User-Agent": "50five/1.0.0 (Android; GraphQL)",
                "apollographql-client-name": "com.plugz.app50five",
                "apollographql-client-version": "1.0.0",
                "plugz-application-id": self.device_id,
            }

            login_transport = HomeAssistantAIOHTTPTransport(
                url=self.base_url,
                headers=login_headers,
                timeout=20,
                shared_session=self.session,
            )
            login_client = Client(
                transport=login_transport, fetch_schema_from_transport=False
            )

            try:
                result = await login_client.execute_async(
                    GraphQLRequest(
                        LOGIN_MUTATION,
                        variable_values={
                            "email": self.username,
                            "password": self.password,
                        },
                    )
                )
                login_dict = result.get("login")
                if not login_dict or not isinstance(login_dict, dict):
                    raise FiftyFiveAuthError("Invalid username or password")

                login_result = LoginResult.from_dict(login_dict)
                if not login_result.access_token:
                    raise FiftyFiveAuthError("Login response missing access token")

                self._access_token = login_result.access_token
                claims = _extract_jwt_claims(self._access_token)
                exp = claims.get("exp")
                if exp:
                    self._token_expires_at = datetime.fromtimestamp(
                        exp, tz=timezone.utc
                    )
                elif login_result.expires_in:
                    self._token_expires_at = datetime.now(timezone.utc) + timedelta(
                        seconds=login_result.expires_in
                    )
                else:
                    self._token_expires_at = datetime.now(timezone.utc) + timedelta(
                        hours=24
                    )

                if not self.customer_id:
                    self.customer_id = (
                        claims.get("external_api", {}).get("customerId")
                        or claims.get("id")
                    )

                self._vat_multiplier = None
                self._rebuild_client()
                _LOGGER.info("Successfully authenticated with 50five GraphQL API")

                if self._on_token_refreshed:
                    try:
                        res = self._on_token_refreshed(
                            self._access_token,
                            self._token_expires_at.isoformat(),
                            self.customer_id,
                        )
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception as cb_err:
                        _LOGGER.debug(
                            "Error invoking token refresh callback: %s", cb_err
                        )

                return True

            except (FiftyFiveAuthError, FiftyFiveConnectionError):
                raise
            except (TransportServerError, TransportError) as err:
                err_str = str(err).lower()
                if any(
                    k in err_str
                    for k in (
                        "unauthenticated",
                        "unauthorized",
                        "invalid credentials",
                        "invalid username",
                        "invalid password",
                        "401",
                        "400",
                    )
                ):
                    raise FiftyFiveAuthError(f"Authentication failed: {err}") from err

                _LOGGER.error("Authentication transport error: %s", err)
                raise FiftyFiveConnectionError(
                    f"Cannot connect to 50five endpoint: {err}"
                ) from err
            except Exception as err:
                err_str = str(err).lower()
                if any(
                    k in err_str
                    for k in (
                        "unauthenticated",
                        "unauthorized",
                        "invalid credentials",
                        "invalid username",
                        "invalid password",
                        "401",
                    )
                ):
                    raise FiftyFiveAuthError(f"Authentication failed: {err}") from err
                _LOGGER.exception("Authentication request error")
                raise FiftyFiveAuthError(f"Authentication failed: {err}") from err

    async def get_vat_multiplier(self) -> float:
        """Retrieve VAT multiplier based on customer providerCategory (matching mobile app)."""
        if self._vat_multiplier is not None:
            return self._vat_multiplier

        if not self.customer_id and self._access_token:
            self.customer_id = _extract_customer_id_from_jwt(self._access_token)

        if self.customer_id:
            try:
                data = await self._execute_query(
                    GET_CUSTOMER_BY_ID_QUERY,
                    {"getCustomerByIdId": str(self.customer_id)},
                )
                cust = data.get("getCustomerById")
                if cust and isinstance(cust, dict):
                    cat = cust.get("providerCategory")
                    if cat:
                        self._vat_multiplier = VAT_MULTIPLIERS.get(
                            str(cat).strip(), DEFAULT_VAT_MULTIPLIER
                        )
                        _LOGGER.debug(
                            "Resolved customer providerCategory %s to VAT multiplier %s",
                            cat,
                            self._vat_multiplier,
                        )
                        return self._vat_multiplier
            except FiftyFiveError as err:
                _LOGGER.warning(
                    "Could not fetch customer providerCategory for VAT calculation: %s",
                    err,
                )
            except Exception as err:
                _LOGGER.debug(
                    "Unexpected error fetching customer providerCategory: %s", err
                )

        self._vat_multiplier = DEFAULT_VAT_MULTIPLIER
        return self._vat_multiplier

    async def _execute_query(
        self,
        document: Any,
        variables: dict[str, Any] | None = None,
        _retry_count: int = 0,
    ) -> dict[str, Any]:
        """Execute a GraphQL query/mutation with automatic proactive token refresh."""
        if not self._access_token or self.is_token_expired():
            _LOGGER.debug("Access token missing or expired, acquiring fresh token...")
            if not await self.authenticate():
                raise FiftyFiveAuthError("Authentication failed")

        try:
            return await self._client.execute_async(
                GraphQLRequest(
                    document,
                    variable_values=variables or {},
                )
            )
        except (TransportServerError, TransportError, Exception) as err:
            err_str = str(err).lower()
            if (
                "401" in err_str
                or "unauthenticated" in err_str
                or "unauthorized" in err_str
            ) and _retry_count < 1:
                _LOGGER.warning(
                    "Access token rejected by backend, re-authenticating and retrying..."
                )
                self._access_token = None
                self._token_expires_at = None
                if await self.authenticate():
                    return await self._execute_query(
                        document, variables, _retry_count + 1
                    )
                raise FiftyFiveAuthError(
                    "Re-authentication failed after token expiry"
                ) from err

            if isinstance(err, (aiohttp.ClientConnectorError, TransportError)):
                raise FiftyFiveConnectionError(
                    f"Cannot connect to 50five API: {err}"
                ) from err

            raise FiftyFiveApiError(f"GraphQL execution error: {err}") from err

    async def get_customer_charge_stations(
        self, days_back: int = 30
    ) -> list[ChargeStation]:
        """Retrieve customer charge stations with nested last transactions."""
        vat_multiplier = await self.get_vat_multiplier()
        now = datetime.now(timezone.utc)
        date_from = (now - timedelta(days=min(days_back, 31))).strftime("%Y-%m-%d")
        date_to = now.strftime("%Y-%m-%d")

        variables = {
            "txFilters": {
                "dateFrom": date_from,
                "dateTo": date_to,
                "itemsPerPage": 5,
            },
            "txSort": {"startDate": "desc"},
        }
        data = await self._execute_query(GET_CUSTOMER_CHARGE_STATIONS_QUERY, variables)
        raw_stations = data.get("getCustomerChargeStations") or []
        return [
            ChargeStation.from_dict(st, vat_multiplier=vat_multiplier)
            for st in raw_stations
            if isinstance(st, dict)
        ]

    async def get_charge_station_details(
        self, charge_station_id: str, days_back: int = 30
    ) -> ChargeStation | None:
        """Retrieve detailed charge station information with nested last transactions."""
        vat_multiplier = await self.get_vat_multiplier()
        now = datetime.now(timezone.utc)
        date_from = (now - timedelta(days=min(days_back, 31))).strftime("%Y-%m-%d")
        date_to = now.strftime("%Y-%m-%d")

        variables = {
            "getChargeStationByIdId": str(charge_station_id),
            "txFilters": {
                "dateFrom": date_from,
                "dateTo": date_to,
                "itemsPerPage": 5,
            },
            "txSort": {"startDate": "desc"},
        }
        data = await self._execute_query(GET_CHARGE_STATION_DETAILS_QUERY, variables)
        station_data = data.get("getChargeStationById")
        if station_data and isinstance(station_data, dict):
            return ChargeStation.from_dict(station_data, vat_multiplier=vat_multiplier)
        return None

    async def get_active_transaction(self) -> ActiveTransaction | None:
        """Retrieve active charging session telemetry as strongly typed model."""
        data = await self._execute_query(LMS_ACTIVE_TRANSACTION_QUERY)
        tx_data = data.get("lmsActiveTransaction")
        if tx_data and isinstance(tx_data, dict):
            return ActiveTransaction.from_dict(tx_data)
        return None

    async def get_charge_cards(self) -> list[ChargeCard]:
        """Retrieve customer charge cards."""
        if not self.customer_id and self._access_token:
            self.customer_id = _extract_customer_id_from_jwt(self._access_token)

        if not self.customer_id:
            _LOGGER.warning("No customer ID available to fetch charge cards")
            return []

        data = await self._execute_query(
            GET_CUSTOMER_CHARGE_CARDS_QUERY,
            {"getCustomerByIdId": str(self.customer_id)},
        )
        cust = data.get("getCustomerById")
        if not cust or not isinstance(cust, dict):
            return []

        raw_cards = cust.get("cards") or []
        cards = [
            ChargeCard.from_dict(c)
            for c in raw_cards
            if isinstance(c, dict)
        ]
        return [c for c in cards if c is not None]

    async def get_tokens(self) -> list[ChargeCard]:
        """Retrieve customer charge cards / tokens (alias for get_charge_cards)."""
        return await self.get_charge_cards()

    async def start_charging(
        self,
        charge_station_id: str,
        channel_id: str,
        card: str | None = None,
    ) -> bool:
        """Start a charging transaction on a specific channel."""
        variables = {
            "chargeStationId": str(charge_station_id),
            "channelId": str(channel_id),
        }
        if card:
            variables["card"] = str(card)

        res = await self._execute_query(START_TRANSACTION_MUTATION, variables)
        return bool(res.get("startTransaction", True))

    async def stop_charging(self, charge_station_id: str, channel_id: str) -> bool:
        """Stop a charging transaction on a specific channel."""
        variables = {
            "chargeStationId": str(charge_station_id),
            "channelId": str(channel_id),
        }
        res = await self._execute_query(STOP_TRANSACTION_MUTATION, variables)
        return bool(res.get("stopTransaction", True))

    async def unlock_connector(self, charge_station_id: str, channel_id: str) -> bool:
        """Unlock the connector on a charging station channel."""
        variables = {
            "chargeStationId": str(charge_station_id),
            "channelId": str(channel_id),
        }
        res = await self._execute_query(UNLOCK_CONNECTOR_MUTATION, variables)
        return bool(res.get("unlockConnector", True))

    async def soft_reset(self, charge_station_id: str) -> bool:
        """Perform a soft reset on the charging station."""
        res = await self._execute_query(
            SOFT_RESET_MUTATION,
            {"chargeStationId": str(charge_station_id)},
        )
        return bool(res.get("softReset", True))

    async def hard_reset(self, charge_station_id: str) -> bool:
        """Perform a hard reset on the charging station."""
        res = await self._execute_query(
            HARD_RESET_MUTATION,
            {"chargeStationId": str(charge_station_id)},
        )
        return bool(res.get("hardReset", True))

    async def reset_parameters_cache(self, charge_station_id: str) -> bool:
        """Reset the cached parameters for the charging station."""
        res = await self._execute_query(
            RESET_CACHE_MUTATION,
            {"chargeStationId": str(charge_station_id)},
        )
        return bool(res.get("resetChargeStationParametersCache", True))
