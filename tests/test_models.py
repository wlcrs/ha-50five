"""Tests for 50five typed data models."""

import importlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

models = importlib.import_module("custom_components.50five.models")

AccessOptions = models.AccessOptions
AccessType = models.AccessType
ActiveTransaction = models.ActiveTransaction
ChannelGlobalStatus = models.ChannelGlobalStatus
ChargeCard = models.ChargeCard
ChargeStation = models.ChargeStation
ChargeStationChannel = models.ChargeStationChannel
CompletedTransaction = models.CompletedTransaction
CountryDetails = models.CountryDetails
GlobalStatus = models.GlobalStatus
HomeChargingCompensation = models.HomeChargingCompensation
Location = models.Location
LoginResult = models.LoginResult
ManufacturerType = models.ManufacturerType
PriceElement = models.PriceElement
StationData = models.StationData


def test_global_status_enum() -> None:
    """Test schema enum validation and Home Assistant status mapping."""
    assert GlobalStatus("available") == GlobalStatus.AVAILABLE

    channel = ChargeStationChannel.model_validate({"globalStatus": "Charging"})
    assert channel.global_status == ChannelGlobalStatus.CHARGING
    assert channel.status == GlobalStatus.CHARGING

    faulty = ChargeStationChannel.model_validate({"globalStatus": "Faulty"})
    assert faulty.status == GlobalStatus.FAULTED

    no_communication = ChargeStationChannel.model_validate(
        {"globalStatus": "NoCommunication"}
    )
    assert no_communication.status == GlobalStatus.UNAVAILABLE

    with pytest.raises(ValidationError):
        ChargeStationChannel.model_validate({"globalStatus": "UnexpectedStatus"})


def test_access_type_enum() -> None:
    """Test GraphQL access type enum validation."""
    options = AccessOptions.model_validate({"accessType": "PublicPaid"})
    assert options.access_type == AccessType.PUBLIC_PAID


def test_price_element_model() -> None:
    """Test PriceElement parsing."""
    pe = PriceElement.model_validate({"type": "ENERGY", "price": 0.35})
    assert pe is not None
    assert pe.type == "ENERGY"
    assert pe.price == 0.35
    with pytest.raises(ValidationError):
        PriceElement.model_validate(None)


def test_active_transaction_model() -> None:
    """Test ActiveTransaction parsing and properties."""
    data = {
        "energyDelivered": 15.5,
        "durationCharging": 7200.0,
        "totalAmount": 5.42,
        "vat": 21.0,
        "priceElements": [{"type": "ENERGY", "price": 0.35}],
        "channelVisibleId": 1,
    }
    tx = ActiveTransaction.model_validate(data)
    assert tx is not None
    assert tx.energy_delivered == 15.5
    assert tx.duration_charging == 7200.0
    assert tx.total_amount == 5.42
    assert tx.vat == 21.0
    assert len(tx.price_elements) == 1
    assert tx.channel_visible_id == 1

    with pytest.raises(ValidationError):
        ActiveTransaction.model_validate(None)


def test_completed_transaction_model() -> None:
    """Test CompletedTransaction parsing and properties."""
    data = {
        "id": "tx_100",
        "status": "Billable",
        "globalStatus": "GlobalStatusCompleted",
        "type": "Local",
        "startDate": "2024-08-01T12:00:00Z",
        "lastUpdateDate": "2024-08-01T14:30:00Z",
        "totalDuration": 2.5,
        "totalEnergy": 22.0,
        "totalIdleTime": 0.08333333333333333,
        "homeCharging": True,
        "cardSnapshot": {
            "externalId": "NL-50F-111",
            "type": "RFID",
        },
        "locationSnapshot": {
            "chargeStationName": "Home Charger",
            "evse": {"id": "evse_1"},
        },
        "transactionPrices": [
            {
                "totalCost": 7.70,
                "type": "CpoCustomer",
                "vatPercentage": 21.0,
                "currency": {"code": "EUR"},
            }
        ],
    }
    tx = CompletedTransaction.model_validate(data)
    assert tx is not None
    assert tx.id == "tx_100"
    assert tx.status is models.TransactionStatus.BILLABLE
    assert tx.global_status is models.TransactionGlobalStatus.COMPLETED
    assert tx.type is models.TransactionType.LOCAL
    assert tx.total_duration == 2.5
    assert tx.total_duration == 2.5
    assert tx.total_energy == 22.0
    assert tx.total_idle_time == pytest.approx(5 / 60)
    assert tx.home_charging is True
    assert tx.card_id == "NL-50F-111"
    assert tx.total_cost == 7.70
    assert tx.currency == "EUR"
    assert tx.card_snapshot is not None
    assert tx.card_snapshot.external_id == "NL-50F-111"
    assert tx.card_snapshot.type is models.CardType.RFID
    assert tx.location_snapshot is not None
    assert tx.location_snapshot.evse is not None
    assert tx.location_snapshot.evse.id == "evse_1"
    assert tx.start_date == datetime(2024, 8, 1, 12, 0, 0, tzinfo=UTC)
    assert tx.last_update_date == datetime(2024, 8, 1, 14, 30, 0, tzinfo=UTC)

    # Fallback to internalId or contractId if externalId missing
    data_internal = {
        "id": "tx_101",
        "status": "Billed",
        "cardSnapshot": {"internalId": "INT_99"},
    }
    tx_internal = CompletedTransaction.model_validate(data_internal)
    assert tx_internal.card_id == "INT_99"

    data_contract = {
        "id": "tx_102",
        "status": "BillingDelegated",
        "cardSnapshot": {"contractId": "CON_88"},
    }
    tx_contract = CompletedTransaction.model_validate(data_contract)
    assert tx_contract.card_id == "CON_88"

    with pytest.raises(ValidationError):
        CompletedTransaction.model_validate(None)

    with pytest.raises(ValidationError):
        CompletedTransaction.model_validate(
            {"id": "tx_naive", "status": "Billable", "startDate": "2024-08-01T12:00:00"}
        )


def test_home_charging_compensation_model() -> None:
    """Test HomeChargingCompensation parsing and calculations."""
    hcc = HomeChargingCompensation.model_validate(
        {"hccEnabled": True, "hccTariff": 0.30},
        context={"vat_multiplier": 1.21},
    )
    assert hcc.hcc_enabled is True
    assert hcc.hcc_tariff == 0.30
    assert hcc.raw_hcc_tariff == 0.30
    assert hcc.tariff_with_vat(1.21) == 0.3630

    # Test 4 decimal precision
    hcc_precise = HomeChargingCompensation.model_validate(
        {"hccEnabled": True, "hccTariff": 0.2830188679245283},
        context={"vat_multiplier": 1.06},
    )
    assert hcc_precise.raw_hcc_tariff == 0.2830
    assert hcc_precise.tariff_with_vat(1.06) == 0.3000

    # Null tariff handling
    hcc_none = HomeChargingCompensation.model_validate(
        {}
    )
    assert hcc_none.hcc_enabled is False
    assert hcc_none.hcc_tariff is None


def test_charge_station_channel_model() -> None:
    """Test ChargeStationChannel formatted status and parsing."""
    ch = ChargeStationChannel.model_validate(
        {
            "id": "ch_1",
            "channelNo": 1,
            "globalStatus": "NoCommunication",
            "cableLock": "LOCKED",
            "soc": 65,
        }
    )
    assert ch.id == "ch_1"
    assert ch.channel_no == 1
    assert ch.global_status == ChannelGlobalStatus.NO_COMMUNICATION
    assert ch.status == GlobalStatus.UNAVAILABLE
    assert ch.formatted_status == "Unavailable"
    assert ch.cable_lock == "LOCKED"
    assert ch.soc == 65


def test_charge_station_and_station_data() -> None:
    """Test ChargeStation and StationData container."""
    station_dict = {
        "id": "st_1",
        "name": "My Station",
        "channels": [
            {"id": "ch_1", "channelNo": 1, "globalStatus": "Available"},
            {"id": "ch_2", "channelNo": 2, "globalStatus": "Charging"},
        ],
        "manufacturerType": {"vendor": "Alfen", "model": "Eve"},
        "homeChargingCompensation": {"hccEnabled": True, "hccTariff": 0.30},
        "location": {
            "address": "Main St 1",
            "countryDetails": {"code": "NL", "currency": {"code": "EUR"}},
        },
        "transactions": {
            "items": [
                {"id": "tx_prev", "status": "Billable", "totalEnergy": 10.0}
            ]
        },
    }
    station = ChargeStation.model_validate(station_dict)
    assert station.id == "st_1"
    assert len(station.channels) == 2
    assert station.last_transaction is not None
    assert station.last_transaction.total_energy == 10.0
    assert station.location is not None
    assert station.location.country_details.currency is not None
    assert station.location.country_details.currency.code == "EUR"

    st_data = StationData(
        station=station,
        channels={ch.channel_no: ch for ch in station.channels},
        vat_multiplier=1.21,
    )
    assert st_data.num_channels == 2
    assert st_data.station.last_transaction.id == "tx_prev"
    assert st_data.hcc_tariff == 0.363


def test_login_result_model() -> None:
    """Test LoginResult parsing."""
    res = LoginResult.model_validate(
        {"accessToken": "jwt_token", "expiresIn": 3600, "tokenType": "Bearer"}
    )
    assert res.access_token == "jwt_token"
    assert res.expires_in == 3600
    assert res.token_type == "Bearer"

    # Snake_case variant
    res2 = LoginResult.model_validate(
        {"access_token": "jwt_token2", "expires_in": "7200", "token_type": "Bearer"}
    )
    assert res2.access_token == "jwt_token2"
    assert res2.expires_in == 7200


def test_charge_card_model() -> None:
    """Test ChargeCard identifier, display_name, and active properties."""
    card = ChargeCard.model_validate(
        {
            "id": "card_1",
            "externalId": "NL-50F-0001",
            "state": "ACTIVE",
            "cardProvider": {"name": "50five"},
            "customer": {"id": "customer_1"},
            "transactionCustomer": {"id": "transaction_customer_1"},
        }
    )
    assert card is not None
    assert card.identifier == "NL-50F-0001"
    assert card.card_provider is not None
    assert card.card_provider.name == "50five"
    assert card.customer is not None
    assert card.customer.id == "customer_1"
    assert card.transaction_customer is not None
    assert card.transaction_customer.id == "transaction_customer_1"
    assert card.display_name == "NL-50F-0001 (50five)"
    assert card.is_active is True

    # Card with contractId fallback and type in display name
    card_contract = ChargeCard.model_validate(
        {
            "id": "card_2",
            "contractId": "CON-999",
            "type": "RFID",
            "state": "INACTIVE",
        }
    )
    assert card_contract.identifier == "CON-999"
    assert card_contract.display_name == "CON-999 (RFID)"
    assert card_contract.is_active is False

    with pytest.raises(ValidationError):
        ChargeCard.model_validate(None)
