"""Tests for 50five typed data models."""

import importlib
from datetime import datetime, timezone

models = importlib.import_module("custom_components.50five.models")

AccessOptions = models.AccessOptions
AccessType = models.AccessType
ActiveTransaction = models.ActiveTransaction
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
    """Test GlobalStatus enum parsing."""
    assert GlobalStatus.from_str("AVAILABLE") == GlobalStatus.AVAILABLE
    assert GlobalStatus.from_str("charging") == GlobalStatus.CHARGING
    assert GlobalStatus.from_str("SUSPENDED_EV") == GlobalStatus.SUSPENDED_EV
    assert GlobalStatus.from_str("non_existent_status") == GlobalStatus.UNKNOWN
    assert GlobalStatus.from_str(None) == GlobalStatus.UNKNOWN


def test_access_type_enum() -> None:
    """Test AccessType enum parsing."""
    assert AccessType.from_str("PRIVATE") == AccessType.PRIVATE
    assert AccessType.from_str("PublicPaid") == AccessType.PUBLIC_PAID
    assert AccessType.from_str("publicfree") == AccessType.PUBLIC_FREE
    assert AccessType.from_str("invalid") == AccessType.UNKNOWN
    assert AccessType.from_str(None) == AccessType.UNKNOWN


def test_price_element_model() -> None:
    """Test PriceElement parsing."""
    pe = PriceElement.from_dict({"type": "ENERGY", "price": 0.35})
    assert pe is not None
    assert pe.type == "ENERGY"
    assert pe.price == 0.35
    assert PriceElement.from_dict(None) is None


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
    tx = ActiveTransaction.from_dict(data)
    assert tx is not None
    assert tx.energy_delivered == 15.5
    assert tx.duration_charging == 7200.0
    assert tx.duration_hours == 2.0
    assert tx.total_amount == 5.42
    assert tx.vat == 21.0
    assert len(tx.price_elements) == 1
    assert tx.channel_visible_id == 1

    assert ActiveTransaction.from_dict(None) is None


def test_completed_transaction_model() -> None:
    """Test CompletedTransaction parsing and properties."""
    data = {
        "id": "tx_100",
        "status": "COMPLETED",
        "startDate": "2024-08-01T12:00:00Z",
        "lastUpdateDate": "2024-08-01T14:30:00Z",
        "totalDuration": 9000.0,
        "totalEnergy": 22.0,
        "homeCharging": True,
        "cardSnapshot": {
            "externalId": "NL-50F-111",
            "type": "RFID",
        },
        "transactionPrices": [
            {
                "totalCost": 7.70,
                "currency": {"code": "EUR"},
            }
        ],
    }
    tx = CompletedTransaction.from_dict(data)
    assert tx is not None
    assert tx.id == "tx_100"
    assert tx.duration_hours == 2.5
    assert tx.total_energy == 22.0
    assert tx.home_charging is True
    assert tx.card_id == "NL-50F-111"
    assert tx.total_cost == 7.70
    assert tx.currency == "EUR"
    assert tx.start_datetime == datetime(2024, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert tx.end_datetime == datetime(2024, 8, 1, 14, 30, 0, tzinfo=timezone.utc)

    # Fallback to internalId or contractId if externalId missing
    data_internal = {
        "id": "tx_101",
        "cardSnapshot": {"internalId": "INT_99"},
    }
    tx_internal = CompletedTransaction.from_dict(data_internal)
    assert tx_internal.card_id == "INT_99"

    data_contract = {
        "id": "tx_102",
        "cardSnapshot": {"contractId": "CON_88"},
    }
    tx_contract = CompletedTransaction.from_dict(data_contract)
    assert tx_contract.card_id == "CON_88"

    assert CompletedTransaction.from_dict(None) is None


def test_home_charging_compensation_model() -> None:
    """Test HomeChargingCompensation parsing and calculations."""
    hcc = HomeChargingCompensation.from_dict(
        {"hccEnabled": True, "hccTariff": 0.30},
        vat_multiplier=1.21,
    )
    assert hcc.hcc_enabled is True
    assert hcc.raw_hcc_tariff == 0.30
    assert hcc.hcc_tariff == 0.3630
    assert hcc.vat_multiplier == 1.21
    assert hcc.vat_percentage == 21.0

    # Test 4 decimal precision
    hcc_precise = HomeChargingCompensation.from_dict(
        {"hccEnabled": True, "hccTariff": 0.2830188679245283},
        vat_multiplier=1.06,
    )
    assert hcc_precise.raw_hcc_tariff == 0.2830
    assert hcc_precise.hcc_tariff == 0.3000

    # Null tariff handling
    hcc_none = HomeChargingCompensation.from_dict(None, vat_multiplier=1.21)
    assert hcc_none.hcc_enabled is False
    assert hcc_none.hcc_tariff is None


def test_charge_station_channel_model() -> None:
    """Test ChargeStationChannel formatted status and parsing."""
    ch = ChargeStationChannel.from_dict(
        {
            "id": "ch_1",
            "channelNo": 1,
            "globalStatus": "SUSPENDED_EVSE",
            "cableLock": "LOCKED",
            "soc": 65,
        }
    )
    assert ch.id == "ch_1"
    assert ch.channel_no == 1
    assert ch.global_status == GlobalStatus.SUSPENDED_EVSE
    assert ch.formatted_status == "Suspended Evse"
    assert ch.cable_lock == "LOCKED"
    assert ch.soc == 65


def test_charge_station_and_station_data() -> None:
    """Test ChargeStation and StationData container."""
    station_dict = {
        "id": "st_1",
        "name": "My Station",
        "channels": [
            {"id": "ch_1", "channelNo": 1, "globalStatus": "AVAILABLE"},
            {"id": "ch_2", "channelNo": 2, "globalStatus": "CHARGING"},
        ],
        "manufacturerType": {"vendor": "Alfen", "model": "Eve"},
        "location": {
            "address": "Main St 1",
            "countryDetails": {"code": "NL", "currency": {"code": "EUR"}},
        },
        "transactions": {
            "items": [{"id": "tx_prev", "totalEnergy": 10.0}]
        },
    }
    station = ChargeStation.from_dict(station_dict, vat_multiplier=1.21)
    assert station.id == "st_1"
    assert len(station.channels) == 2
    assert station.last_transaction is not None
    assert station.last_transaction.total_energy == 10.0

    st_data = StationData(
        station=station,
        channels={ch.channel_no: ch for ch in station.channels},
    )
    assert st_data.num_channels == 2
    assert st_data.last_transaction.id == "tx_prev"


def test_login_result_model() -> None:
    """Test LoginResult parsing."""
    res = LoginResult.from_dict(
        {"accessToken": "jwt_token", "expiresIn": 3600, "tokenType": "Bearer"}
    )
    assert res.access_token == "jwt_token"
    assert res.expires_in == 3600
    assert res.token_type == "Bearer"

    # Snake_case variant
    res2 = LoginResult.from_dict(
        {"access_token": "jwt_token2", "expires_in": "7200", "token_type": "Bearer"}
    )
    assert res2.access_token == "jwt_token2"
    assert res2.expires_in == 7200


def test_charge_card_model() -> None:
    """Test ChargeCard identifier, display_name, and active properties."""
    card = ChargeCard.from_dict(
        {
            "id": "card_1",
            "externalId": "NL-50F-0001",
            "state": "ACTIVE",
            "cardProvider": {"name": "50five"},
        }
    )
    assert card is not None
    assert card.identifier == "NL-50F-0001"
    assert card.display_name == "NL-50F-0001 (50five)"
    assert card.is_active is True

    # Card with contractId fallback and type in display name
    card_contract = ChargeCard.from_dict(
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

    assert ChargeCard.from_dict(None) is None
