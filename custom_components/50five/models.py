"""Typed data models for 50five GraphQL schema."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
)
from pydantic.alias_generators import to_camel


class ToRedact:
    """Annotation marker for values that must be fully redacted."""


class ToMask:
    """Annotation marker for values that should be partially masked."""


RedactedStr = Annotated[str, ToRedact]
MaskedStr = Annotated[str, ToMask]


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="ignore",
        frozen=True,
        populate_by_name=True,
        coerce_numbers_to_str=True,
    )


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

class ChannelGlobalStatus(StrEnum):
    """GraphQL ``ChargeStationChannelGlobalStatus`` enum values."""

    AVAILABLE = "Available"
    RESERVED = "Reserved"
    CHARGING = "Charging"
    UNAVAILABLE = "Unavailable"
    NO_COMMUNICATION = "NoCommunication"
    POWERED_OFF = "PoweredOff"
    FAULTY = "Faulty"
    UNKNOWN = "Unknown"


class AccessType(StrEnum):
    """GraphQL ``AccessOptionsEnum`` enum values."""

    PRIVATE = "Private"
    PUBLIC_PAID = "PublicPaid"
    PUBLIC_FREE = "PublicFree"


class CardType(StrEnum):
    """GraphQL ``CardType`` enum values."""

    RFID = "RFID"
    REMOTE = "Remote"
    PLUG_AND_CHARGE = "PlugAndCharge"
    IEC_15118 = "IEC_15118"
    BARCODE = "Barcode"
    QR_CODE = "QRcode"
    GROUP = "Group"
    ANONYMOUS = "Anonymous"


class TransactionStatus(StrEnum):
    """GraphQL ``TransactionStatus`` enum values."""

    BILLABLE = "Billable"
    BILLING_DELEGATED = "BillingDelegated"
    BILLED = "Billed"


class TransactionGlobalStatus(StrEnum):
    """GraphQL ``TransactionGlobalStatus`` enum values."""

    INVALID = "GlobalStatusInvalid"
    PENDING = "GlobalStatusPending"
    ACTIVE = "GlobalStatusActive"
    COMPLETED = "GlobalStatusCompleted"
    BILLABLE = "GlobalStatusBillable"
    BILLED = "GlobalStatusBilled"
    BILLING_DELEGATED = "GlobalStatusBillingDelegated"


class TransactionType(StrEnum):
    """GraphQL ``TransactionType`` enum values."""

    LOCAL = "Local"
    INTERNAL_ROAMING = "InternalRoaming"
    INTERNAL_ROAMING_DIFF_ROAMING_PROFILES = "InternalRoamingDiffRoamingProfiles"
    EXTERNAL_ROAMING_MSP = "ExternalRoamingMSP"
    EXTERNAL_ROAMING_CPO = "ExternalRoamingCPO"
    DIRECT = "Direct"
    CPO_UNKNOWN = "CPOUnknown"
    MSP_UNKNOWN = "MSPUnknown"


class TransactionPeriodItemType(StrEnum):
    """GraphQL ``TransactionPeriodItemType`` enum values."""

    CPO_ROAMING = "CpoRoaming"
    CPO_CUSTOMER = "CpoCustomer"
    CPO_PROVIDER = "CpoProvider"
    CPO_APP_MANAGER = "CpoAppManager"
    CPO_ADDITIONAL_PROVIDER = "CpoAdditionalProvider"
    MSP_ROAMING = "MspRoaming"
    MSP_CUSTOMER = "MspCustomer"
    MSP_PROVIDER = "MspProvider"
    MSP_APP_MANAGER = "MspAppManager"
    MSP_APP_MANAGER_TO_PROVIDER = "MspAppManagerToProvider"
    MSP_ADDITIONAL_PROVIDER = "MspAdditionalProvider"
    MSP_CPO = "MspCpo"

class PriceElement(_Model):
    """Selected fields from GraphQL ``PriceElement`` for active telemetry."""

    type: str | None = None
    price: float | None = None

class ActiveTransaction(_Model):
    """Selected fields from GraphQL ``Transaction`` via ``lmsActiveTransaction``."""

    update_date: str | None = None
    address: RedactedStr | None = None
    zip_code: RedactedStr | None = None
    city: RedactedStr | None = None
    energy_delivered: float = 0.0
    start_date: str | None = None
    country_code: str | None = None
    currency: str | None = None
    total_amount: float = 0.0
    vat: float | None = None
    duration_charging: float = 0.0  # seconds
    price_elements: list[PriceElement] = Field(default_factory=list)
    tariff_id: MaskedStr | None = None
    channel_visible_id: int | MaskedStr | None = None



class TransactionCardSnapshot(_Model):
    """Selected fields from GraphQL ``TransactionCard``."""

    external_id: MaskedStr | None = None
    internal_id: MaskedStr | None = None
    contract_id: MaskedStr | None = None
    type: CardType | None = None


class TransactionLocationEVSE(_Model):
    """Selected ``id`` field from GraphQL ``TransactionLocationEvse``."""

    id: MaskedStr | None = None


class TransactionLocationSnapshot(_Model):
    """Selected fields from GraphQL ``TransactionLocation``."""

    charge_station_name: MaskedStr | None = None
    evse: TransactionLocationEVSE | None = None


class TransactionCurrency(_Model):
    """Selected ``code`` field from GraphQL ``Currency``."""

    code: str | None = None


class TransactionPrice(_Model):
    """Selected fields from GraphQL ``TransactionPrice``."""

    total_cost: float | None = None
    type: TransactionPeriodItemType | None = None
    vat_percentage: float | None = None
    currency: TransactionCurrency | None = None


class CompletedTransaction(_Model):
    """Selected fields from GraphQL ``LmsTransaction`` in history results."""

    id: MaskedStr
    status: TransactionStatus
    global_status: TransactionGlobalStatus | None = None
    type: TransactionType | None = None
    start_date: AwareDatetime | None = None
    last_update_date: AwareDatetime | None = None
    total_duration: float | None = None  # hours
    total_energy: float | None = None  # kWh
    total_idle_time: float | None = None  # hours
    home_charging: bool | None = None
    card_snapshot: TransactionCardSnapshot | None = None
    location_snapshot: TransactionLocationSnapshot | None = None
    transaction_prices: list[TransactionPrice] | None = None

    @property
    def card_id(self) -> str | None:
        """Return the best available card identifier from the snapshot."""
        if self.card_snapshot is None:
            return None
        return (
            self.card_snapshot.external_id
            or self.card_snapshot.internal_id
            or self.card_snapshot.contract_id
        )

    @property
    def total_cost(self) -> float | None:
        """Return the first total cost present in the transaction prices."""
        for price in self.transaction_prices or []:
            if price.total_cost is not None:
                return price.total_cost
        return None

    @property
    def currency(self) -> str:
        """Return the currency associated with the first total cost."""
        for price in self.transaction_prices or []:
            if price.total_cost is not None:
                return price.currency.code if price.currency and price.currency.code else "EUR"
        return "EUR"

class TransactionCollection(_Model):
    """GraphQL ``TransactionCollection`` returned by ``getTransactions``."""

    items: list[CompletedTransaction] | None = None
    has_next: bool | None = None


class ManufacturerType(_Model):
    """Selected fields from GraphQL ``ManufacturerType``."""

    vendor: str | None = None
    model: str | None = None

class CountryDetails(_Model):
    """Selected fields from GraphQL ``CountryDetails``."""

    code: str | None = None
    currency: TransactionCurrency | None = None


class Location(_Model):
    """Selected fields from GraphQL ``Location``."""

    id: MaskedStr | None = None
    address: RedactedStr | None = None
    postal_code: RedactedStr | None = None
    city: RedactedStr | None = None
    country_details: CountryDetails = Field(default_factory=CountryDetails)

class AccessOptions(_Model):
    """Selected fields from GraphQL ``AccessOptions``."""

    authorization_mode: str | None = None
    access_type: AccessType | None = None
    published_on_map: bool | None = None

class HomeChargingCompensation(_Model):
    """Selected fields from GraphQL ``HomeChargingCompensation``."""

    hcc_enabled: bool = False
    hcc_tariff: float | None = None

    @property
    def raw_hcc_tariff(self) -> float | None:
        """Return the net tariff rounded to four decimal places."""
        return round(self.hcc_tariff, 4) if self.hcc_tariff is not None else None

    def tariff_with_vat(self, vat_multiplier: float) -> float | None:
        """Return the gross tariff for the configured VAT multiplier."""
        if self.hcc_tariff is None:
            return None
        return round(self.hcc_tariff * vat_multiplier, 4)


class SubscriptionProduct(_Model):
    """Selected ``id`` and ``name`` fields from GraphQL ``Product``."""

    id: MaskedStr
    name: str | None = None


class StationSubscription(_Model):
    """Selected fields from GraphQL ``LmsSubscription``."""

    id: MaskedStr
    start_date: str | None = None
    end_date: str | None = None
    product: SubscriptionProduct | None = None


class ChargeGroupTariff(_Model):
    """Tariff fields selected from GraphQL ``TariffResult``."""

    energy: float | None = None
    flat: float | None = None
    time: float | None = None


class ChargeGroup(_Model):
    """Selected tariff fields from GraphQL ``ChargeGroup``."""

    tariff_vat: ChargeGroupTariff | None = None
    anonymous_tariff_vat: ChargeGroupTariff | None = None


class ChargeStationChannel(_Model):
    """Selected fields from GraphQL ``ChargeStationChannel``."""

    id: MaskedStr = ""
    channel_no: int = 1
    evse_id: MaskedStr | None = None
    global_status: ChannelGlobalStatus | None = None
    cable_lock: str | None = None
    soc: int | None = None

    @property
    def formatted_status(self) -> str:
        """Formatted human-readable status."""
        return self.status.value.replace("_", " ").title()

    @property
    def status(self) -> GlobalStatus:
        """Map the schema status to the integration-level status enum."""
        return {
            ChannelGlobalStatus.AVAILABLE: GlobalStatus.AVAILABLE,
            ChannelGlobalStatus.RESERVED: GlobalStatus.RESERVED,
            ChannelGlobalStatus.CHARGING: GlobalStatus.CHARGING,
            ChannelGlobalStatus.UNAVAILABLE: GlobalStatus.UNAVAILABLE,
            ChannelGlobalStatus.NO_COMMUNICATION: GlobalStatus.UNAVAILABLE,
            ChannelGlobalStatus.POWERED_OFF: GlobalStatus.UNAVAILABLE,
            ChannelGlobalStatus.FAULTY: GlobalStatus.FAULTED,
            ChannelGlobalStatus.UNKNOWN: GlobalStatus.UNKNOWN,
            None: GlobalStatus.UNKNOWN,
        }[self.global_status]

class ChargeStation(_Model):
    """Selected fields from GraphQL ``ChargeStation``."""

    id: MaskedStr
    name: str | None = None
    comm_id: MaskedStr | None = None
    channels: list[ChargeStationChannel] | None = None
    manufacturer: ManufacturerType | None = Field(
        default=None, alias="manufacturerType"
    )
    access_options: AccessOptions = Field(default_factory=AccessOptions)
    hcc: HomeChargingCompensation | None = Field(
        default=None,
        alias="homeChargingCompensation",
    )
    location: Location | None = None
    subscriptions: list[StationSubscription] | None = None
    charge_group: ChargeGroup | None = None
    transactions: TransactionCollection | None = None

    @property
    def display_name(self) -> str:
        """Return the API name with a stable fallback for unnamed stations."""
        return self.name or self.comm_id or f"Charge Station {self.id}"

    @property
    def last_transaction(self) -> CompletedTransaction | None:
        """Get the most recent completed transaction."""
        if self.transactions and self.transactions.items:
            return self.transactions.items[0]
        return None

class StationData(_Model):
    """Integration aggregate; not a GraphQL schema type."""

    station: ChargeStation
    channels: dict[int, ChargeStationChannel]
    active_transaction: ActiveTransaction | None = None
    vat_multiplier: float = 1.0

    @property
    def num_channels(self) -> int:
        """Total channel count."""
        return max(1, len(self.channels))

    @property
    def hcc_tariff(self) -> float | None:
        """Return the station's VAT-inclusive HCC tariff."""
        if self.station.hcc is None:
            return None
        return self.station.hcc.tariff_with_vat(self.vat_multiplier)

    @property
    def raw_hcc_tariff(self) -> float | None:
        """Return the station's net HCC tariff."""
        return self.station.hcc.raw_hcc_tariff if self.station.hcc else None

    @property
    def vat_percentage(self) -> float:
        """Return the VAT percentage for this station's tariff."""
        return round((self.vat_multiplier - 1.0) * 100, 2)

    def get_channel_id(self, channel_no: int = 1) -> str | None:
        """Resolve the GraphQL channel ID for a given channel number."""
        ch = self.channels.get(channel_no)
        if ch and ch.id:
            return ch.id
        for ch_item in self.station.channels or []:
            if ch_item.channel_no == channel_no and ch_item.id:
                return ch_item.id
        if self.station.channels and self.station.channels[0].id:
            return self.station.channels[0].id
        return None


class LoginResult(_Model):
    """GraphQL ``JwtToken`` fields aliased in the login operation."""

    access_token: RedactedStr = ""
    expires_in: int | None = None
    token_type: str | None = None



class CardProvider(_Model):
    """Selected ``name`` field from GraphQL ``CardProvider``."""

    name: RedactedStr | None = None


class CustomerReference(_Model):
    """Selected ``id`` field from GraphQL ``Customer``/``TransactionCustomer``."""

    id: MaskedStr | None = None


class ChargeCard(_Model):
    """Selected fields from GraphQL ``Card`` used by charging flows."""

    id: MaskedStr | None = None
    external_id: MaskedStr | None = None
    internal_id: MaskedStr | None = None
    contract_id: MaskedStr | None = None
    state: str | None = None
    type: str | None = None
    roaming: bool = False
    roaming_home_charging_enabled: bool | None = None
    roaming_hub_status: str | None = None
    card_provider: CardProvider | None = None
    customer: CustomerReference | None = None
    transaction_customer: CustomerReference | None = None
    info: str | None = None

    @property
    def identifier(self) -> str:
        """Preferred identifier to use when starting transactions."""
        return self.external_id or self.contract_id or self.internal_id or self.id or ""

    @property
    def display_name(self) -> str:
        """Formatted human-readable display name for the card."""
        ident = self.identifier
        provider_name = self.card_provider.name if self.card_provider else None
        if provider_name and provider_name.lower() != "unknown":
            return f"{ident} ({provider_name})"
        if self.type and self.type.lower() != "unknown":
            return f"{ident} ({self.type})"
        return ident

    @property
    def is_active(self) -> bool:
        """Return whether the card is in an active state."""
        return self.state is None or self.state.lower() == "active"

class CustomerChargeCards(_Model):
    """Selected ``id`` and ``cards`` fields from GraphQL ``Customer``."""

    id: MaskedStr | None = None
    cards: list[ChargeCard] | None = None


class GetCustomerChargeCardsResponse(_Model):
    """Operation response envelope for the ``getCustomerById`` card query."""

    get_customer_by_id: CustomerChargeCards | None = None


class CustomerVatProfile(_Model):
    """Selected ``id`` and ``providerCategory`` fields from GraphQL ``Customer``."""

    id: MaskedStr
    provider_category: str | None = None


class GetCustomerByIdResponse(_Model):
    """Response envelope for the ``getCustomerById`` VAT lookup."""

    get_customer_by_id: CustomerVatProfile | None = None


class GetCustomerChargeStationsResponse(_Model):
    """Response envelope for ``getCustomerChargeStations``."""

    get_customer_charge_stations: list[ChargeStation] | None = None


class GetChargeStationByIdResponse(_Model):
    """Response envelope for ``getChargeStationById``."""

    get_charge_station_by_id: ChargeStation | None = None


class LmsActiveTransactionResponse(_Model):
    """Response envelope for ``lmsActiveTransaction``."""

    lms_active_transaction: ActiveTransaction | None = None


class LoginMutationResponse(_Model):
    """Response envelope for the login mutation."""

    login_fifty_five: LoginResult | None = None


class StartTransactionResponse(_Model):
    """Response envelope for ``startTransaction``."""

    start_transaction: bool | None = None


class StopTransactionResponse(_Model):
    """Response envelope for ``stopTransaction``."""

    stop_transaction: bool | None = None


class UnlockConnectorResponse(_Model):
    """Response envelope for ``unlockConnector``."""

    unlock_connector: bool | None = None


class SoftResetResponse(_Model):
    """Response envelope for ``softReset``."""

    soft_reset: bool | None = None


class HardResetResponse(_Model):
    """Response envelope for ``hardReset``."""

    hard_reset: bool | None = None


class ResetParametersCacheResponse(_Model):
    """Response envelope for ``resetChargeStationParametersCache``."""

    reset_charge_station_parameters_cache: bool | None = None
