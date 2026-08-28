"""Typed data models for 50five GraphQL schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class GlobalStatus(StrEnum):
    """Global operational status of a charging channel."""

    AVAILABLE = "available"
    CHARGING = "charging"
    OCCUPIED = "occupied"
    FAULTED = "faulted"
    UNAVAILABLE = "unavailable"
    SUSPENDED_EVSE = "suspended_evse"
    SUSPENDED_EV = "suspended_ev"
    PREPARING = "preparing"
    FINISHING = "finishing"
    RESERVED = "reserved"
    UNKNOWN = "unknown"

    @classmethod
    def from_str(cls, value: str | None) -> GlobalStatus:
        """Parse status string safely."""
        if not value:
            return cls.UNKNOWN
        try:
            return cls(value.lower())
        except ValueError:
            return cls.UNKNOWN


class AccessType(StrEnum):
    """Access type of the charge station."""

    PRIVATE = "private"
    PUBLIC_PAID = "public_paid"
    PUBLIC_FREE = "public_free"
    UNKNOWN = "unknown"

    @classmethod
    def from_str(cls, value: str | None) -> AccessType:
        """Parse access type string safely."""
        if not value:
            return cls.UNKNOWN
        val = (
            value.lower()
            .replace("publicpaid", "public_paid")
            .replace("publicfree", "public_free")
        )
        try:
            return cls(val)
        except ValueError:
            return cls.UNKNOWN


@dataclass(slots=True, frozen=True)
class PriceElement:
    """Price element within an active transaction."""

    type: str | None = None
    price: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PriceElement | None:
        """Parse dictionary to PriceElement."""
        if not data:
            return None
        price_val = data.get("price")
        return cls(
            type=data.get("type"),
            price=float(price_val) if price_val is not None else None,
        )


@dataclass(slots=True, frozen=True)
class ActiveTransaction:
    """Active charging session telemetry from LMS."""

    update_date: str | None = None
    address: str | None = None
    zip_code: str | None = None
    city: str | None = None
    energy_delivered: float = 0.0
    start_date: str | None = None
    country_code: str | None = None
    currency: str | None = None
    total_amount: float = 0.0
    vat: float | None = None
    duration_charging: float = 0.0  # seconds
    price_elements: list[PriceElement] = field(default_factory=list)
    tariff_id: str | None = None
    channel_visible_id: int | str | None = None

    @property
    def duration_hours(self) -> float:
        """Duration in decimal hours."""
        return round(self.duration_charging / 3600.0, 2)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ActiveTransaction | None:
        """Parse dictionary to ActiveTransaction."""
        if not data:
            return None
        raw_prices = data.get("priceElements") or []
        price_elements = [
            pe
            for pe in (
                PriceElement.from_dict(p) for p in raw_prices if isinstance(p, dict)
            )
            if pe is not None
        ]
        return cls(
            update_date=data.get("updateDate"),
            address=data.get("address"),
            zip_code=data.get("zipCode"),
            city=data.get("city"),
            energy_delivered=float(data.get("energyDelivered") or 0.0),
            start_date=data.get("startDate"),
            country_code=data.get("countryCode"),
            currency=data.get("currency"),
            total_amount=float(data.get("totalAmount") or 0.0),
            vat=float(data["vat"]) if data.get("vat") is not None else None,
            duration_charging=float(data.get("durationCharging") or 0.0),
            price_elements=price_elements,
            tariff_id=data.get("tariffId"),
            channel_visible_id=data.get("channelVisibleId"),
        )


@dataclass(slots=True, frozen=True)
class CompletedTransaction:
    """Historical completed transaction for a charge station."""

    id: str
    status: str | None = None
    global_status: str | None = None
    type: str | None = None
    start_date: str | None = None
    last_update_date: str | None = None
    total_duration: float = 0.0  # seconds
    total_energy: float = 0.0  # kWh
    total_idle_time: float = 0.0
    home_charging: bool = False
    card_id: str | None = None
    total_cost: float | None = None
    currency: str = "EUR"

    @property
    def duration_hours(self) -> float:
        """Duration in decimal hours."""
        return round(self.total_duration / 3600.0, 2)

    @property
    def start_datetime(self) -> datetime | None:
        """Parse ISO start timestamp."""
        if not self.start_date:
            return None
        try:
            return datetime.fromisoformat(self.start_date)
        except ValueError:
            return None

    @property
    def end_datetime(self) -> datetime | None:
        """Parse ISO end timestamp."""
        if not self.last_update_date:
            return None
        try:
            return datetime.fromisoformat(self.last_update_date)
        except ValueError:
            return None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CompletedTransaction | None:
        """Parse dictionary to CompletedTransaction."""
        if not data or not isinstance(data, dict):
            return None

        card_snap = data.get("cardSnapshot") or {}
        card_id = (
            card_snap.get("externalId")
            or card_snap.get("internalId")
            or card_snap.get("contractId")
        )

        prices = data.get("transactionPrices") or []
        total_cost = None
        currency = "EUR"
        for p in prices:
            if isinstance(p, dict) and p.get("totalCost") is not None:
                try:
                    total_cost = float(p["totalCost"])
                except ValueError:
                    continue
                curr_obj = p.get("currency")
                if isinstance(curr_obj, dict) and curr_obj.get("code"):
                    currency = curr_obj["code"]
                break

        return cls(
            id=str(data.get("id", "")),
            status=data.get("status"),
            global_status=data.get("globalStatus"),
            type=data.get("type"),
            start_date=data.get("startDate"),
            last_update_date=data.get("lastUpdateDate"),
            total_duration=float(data.get("totalDuration") or 0.0),
            total_energy=float(data.get("totalEnergy") or 0.0),
            total_idle_time=float(data.get("totalIdleTime") or 0.0),
            home_charging=bool(data.get("homeCharging", False)),
            card_id=card_id,
            total_cost=total_cost,
            currency=currency,
        )


@dataclass(slots=True, frozen=True)
class ManufacturerType:
    """Hardware manufacturer information."""

    vendor: str | None = None
    model: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ManufacturerType:
        """Parse dictionary to ManufacturerType."""
        if not data:
            return cls()
        return cls(
            vendor=data.get("vendor"),
            model=data.get("model"),
        )


@dataclass(slots=True, frozen=True)
class CountryDetails:
    """Country and currency info."""

    code: str | None = None
    currency_code: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CountryDetails:
        """Parse dictionary to CountryDetails."""
        if not data:
            return cls()
        currency = data.get("currency") or {}
        return cls(
            code=data.get("code"),
            currency_code=currency.get("code") if isinstance(currency, dict) else None,
        )


@dataclass(slots=True, frozen=True)
class Location:
    """Physical location details."""

    id: str | None = None
    address: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country_details: CountryDetails = field(default_factory=CountryDetails)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Location:
        """Parse dictionary to Location."""
        if not data:
            return cls()
        return cls(
            id=str(data["id"]) if data.get("id") is not None else None,
            address=data.get("address"),
            postal_code=data.get("postalCode"),
            city=data.get("city"),
            country_details=CountryDetails.from_dict(data.get("countryDetails")),
        )


@dataclass(slots=True, frozen=True)
class AccessOptions:
    """Access control options for the charge station."""

    authorization_mode: str | None = None
    access_type: AccessType = AccessType.UNKNOWN
    published_on_map: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AccessOptions:
        """Parse dictionary to AccessOptions."""
        if not data:
            return cls()
        return cls(
            authorization_mode=data.get("authorizationMode"),
            access_type=AccessType.from_str(data.get("accessType")),
            published_on_map=data.get("publishedOnMap"),
        )


@dataclass(slots=True, frozen=True)
class HomeChargingCompensation:
    """Home Charging Compensation (HCC) configuration."""

    hcc_enabled: bool = False
    hcc_tariff: float | None = None
    raw_hcc_tariff: float | None = None
    vat_multiplier: float = 1.0

    @property
    def vat_percentage(self) -> float:
        """Return VAT percentage (e.g. 21.0 for 21% VAT)."""
        return round((self.vat_multiplier - 1.0) * 100, 2)

    @classmethod
    def from_dict(
        cls, data: dict[str, Any] | None, vat_multiplier: float = 1.0
    ) -> HomeChargingCompensation:
        """Parse dictionary to HomeChargingCompensation and calculate gross tariff."""
        if not data:
            return cls(vat_multiplier=vat_multiplier)
        tariff = data.get("hccTariff")
        tariff_float = float(tariff) if tariff is not None else None
        raw_hcc_tariff = (
            round(tariff_float, 4) if tariff_float is not None else None
        )
        hcc_tariff = (
            round(tariff_float * vat_multiplier, 4)
            if tariff_float is not None
            else None
        )
        return cls(
            hcc_enabled=bool(data.get("hccEnabled")),
            hcc_tariff=hcc_tariff,
            raw_hcc_tariff=raw_hcc_tariff,
            vat_multiplier=vat_multiplier,
        )


@dataclass(slots=True, frozen=True)
class ChargeStationChannel:
    """A single connector/channel on a charge station."""

    id: str
    channel_no: int
    evse_id: str | None = None
    global_status: GlobalStatus = GlobalStatus.UNKNOWN
    cable_lock: str | None = None
    soc: int | None = None

    @property
    def formatted_status(self) -> str:
        """Formatted human-readable status."""
        return self.global_status.value.replace("_", " ").title()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargeStationChannel:
        """Parse dictionary to ChargeStationChannel."""
        soc_val = data.get("soc")
        return cls(
            id=str(data.get("id", "")),
            channel_no=int(data.get("channelNo", 1)),
            evse_id=data.get("evseId"),
            global_status=GlobalStatus.from_str(data.get("globalStatus")),
            cable_lock=data.get("cableLock"),
            soc=int(soc_val) if soc_val is not None else None,
        )


@dataclass(slots=True, frozen=True)
class ChargeStation:
    """Full charge station object from GraphQL."""

    id: str
    name: str
    comm_id: str | None = None
    channels: list[ChargeStationChannel] = field(default_factory=list)
    manufacturer: ManufacturerType = field(default_factory=ManufacturerType)
    access_options: AccessOptions = field(default_factory=AccessOptions)
    hcc: HomeChargingCompensation = field(default_factory=HomeChargingCompensation)
    location: Location = field(default_factory=Location)
    transactions: list[CompletedTransaction] = field(default_factory=list)

    @property
    def last_transaction(self) -> CompletedTransaction | None:
        """Get the most recent completed transaction."""
        return self.transactions[0] if self.transactions else None

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], vat_multiplier: float = 1.0
    ) -> ChargeStation:
        """Parse dictionary to ChargeStation."""
        station_id = str(data.get("id", ""))
        name = data.get("name") or data.get("commId") or f"Charge Station {station_id}"
        raw_channels = data.get("channels") or []
        channels = [
            ChargeStationChannel.from_dict(ch)
            for ch in raw_channels
            if isinstance(ch, dict)
        ]

        tx_container = data.get("transactions") or {}
        raw_txs = tx_container.get("items") or []
        transactions = [
            tx
            for tx in (
                CompletedTransaction.from_dict(t)
                for t in raw_txs
                if isinstance(t, dict)
            )
            if tx is not None
        ]

        return cls(
            id=station_id,
            name=name,
            comm_id=data.get("commId"),
            channels=channels,
            manufacturer=ManufacturerType.from_dict(data.get("manufacturerType")),
            access_options=AccessOptions.from_dict(data.get("accessOptions")),
            hcc=HomeChargingCompensation.from_dict(
                data.get("homeChargingCompensation"),
                vat_multiplier=vat_multiplier,
            ),
            location=Location.from_dict(data.get("location")),
            transactions=transactions,
        )


@dataclass(slots=True, frozen=True)
class StationData:
    """Combined state container for a single charge station in the coordinator."""

    station: ChargeStation
    channels: dict[int, ChargeStationChannel]
    active_transaction: ActiveTransaction | None = None

    @property
    def num_channels(self) -> int:
        """Total channel count."""
        return max(1, len(self.channels))

    @property
    def last_transaction(self) -> CompletedTransaction | None:
        """Return the station's last completed transaction."""
        return self.station.last_transaction


@dataclass(slots=True, frozen=True)
class LoginResult:
    """Result of Login mutation."""

    access_token: str
    expires_in: int | None = None
    token_type: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoginResult:
        """Parse dictionary to LoginResult."""
        exp = data.get("expiresIn") or data.get("expires_in")
        return cls(
            access_token=data.get("accessToken") or data.get("access_token", ""),
            expires_in=int(exp) if exp is not None else None,
            token_type=data.get("tokenType") or data.get("token_type"),
        )


@dataclass(slots=True, frozen=True)
class ChargeCard:
    """A charge card or RFID token for starting charging sessions."""

    id: str | None = None
    external_id: str | None = None
    internal_id: str | None = None
    contract_id: str | None = None
    state: str | None = None
    type: str | None = None
    roaming: bool = False
    roaming_home_charging_enabled: bool | None = None
    roaming_hub_status: str | None = None
    provider_name: str | None = None
    customer_id: str | None = None
    transaction_customer_id: str | None = None
    info: str | None = None

    @property
    def identifier(self) -> str:
        """Preferred identifier to use when starting transactions."""
        return (
            self.external_id
            or self.contract_id
            or self.internal_id
            or self.id
            or ""
        )

    @property
    def display_name(self) -> str:
        """Formatted human-readable display name for the card."""
        ident = self.identifier
        if self.provider_name and self.provider_name.lower() != "unknown":
            return f"{ident} ({self.provider_name})"
        if self.type and self.type.lower() != "unknown":
            return f"{ident} ({self.type})"
        return ident

    @property
    def is_active(self) -> bool:
        """Return whether the card is in an active state."""
        return self.state is None or self.state.lower() == "active"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ChargeCard | None:
        """Parse dictionary from GraphQL to ChargeCard."""
        if not data or not isinstance(data, dict):
            return None

        card_provider = data.get("cardProvider") or {}
        provider_name = (
            card_provider.get("name") if isinstance(card_provider, dict) else None
        )

        customer = data.get("customer") or {}
        cust_id = customer.get("id") if isinstance(customer, dict) else None

        tx_customer = data.get("transactionCustomer") or {}
        tx_cust_id = tx_customer.get("id") if isinstance(tx_customer, dict) else None

        return cls(
            id=str(data["id"]) if data.get("id") is not None else None,
            external_id=data.get("externalId"),
            internal_id=data.get("internalId"),
            contract_id=data.get("contractId"),
            state=data.get("state"),
            type=data.get("type"),
            roaming=bool(data.get("roaming", False)),
            roaming_home_charging_enabled=data.get("roamingHomeChargingEnabled"),
            roaming_hub_status=data.get("roamingHubStatus"),
            provider_name=provider_name,
            customer_id=str(cust_id) if cust_id is not None else None,
            transaction_customer_id=str(tx_cust_id) if tx_cust_id is not None else None,
            info=data.get("info"),
        )

