"""Constants and mock data for 50five tests."""

import importlib

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

const = importlib.import_module("custom_components.50five.const")

CONF_ACCESS_TOKEN = const.CONF_ACCESS_TOKEN
CONF_CARD_ID = const.CONF_CARD_ID
CONF_CONFIRM_OWNERSHIP = const.CONF_CONFIRM_OWNERSHIP
CONF_CUSTOMER_ID = const.CONF_CUSTOMER_ID
CONF_DEVICE_ID = const.CONF_DEVICE_ID
CONF_TOKEN_EXPIRES_AT = const.CONF_TOKEN_EXPIRES_AT
DOMAIN = const.DOMAIN

MOCK_USERNAME = "test@example.com"
MOCK_PASSWORD = "test-password-123"
MOCK_DEVICE_ID = "550e8400-e29b-41d4-a716-446655440000"
MOCK_CUSTOMER_ID = "cust_12345"
MOCK_CARD_ID = "NL-50F-123456-7"
MOCK_STATION_ID = "station_999"
MOCK_MULTI_STATION_ID = "station_multi_888"

# Mock JWT token containing customerId and far future exp timestamp
MOCK_ACCESS_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpZCI6ImN1c3RfMTIzNDUiLCJleHAiOjIwMDAwMDAwMDAsImVtYWlsIjoidGVzdEBleGFtcGxlLmNvbSIsImV4dGVybmFsX2FwaSI6eyJjdXN0b21lcklkIjoiY3VzdF8xMjM0NSJ9fQ."
    "signature"
)

MOCK_TOKEN_EXPIRES_AT = "2033-05-18T03:33:20+00:00"

MOCK_CONFIG_DATA = {
    CONF_USERNAME: MOCK_USERNAME,
    CONF_PASSWORD: MOCK_PASSWORD,
    CONF_DEVICE_ID: MOCK_DEVICE_ID,
    CONF_CUSTOMER_ID: MOCK_CUSTOMER_ID,
    CONF_ACCESS_TOKEN: MOCK_ACCESS_TOKEN,
    CONF_TOKEN_EXPIRES_AT: MOCK_TOKEN_EXPIRES_AT,
    CONF_CARD_ID: MOCK_CARD_ID,
}

MOCK_USER_STEP_INPUT = {
    CONF_USERNAME: MOCK_USERNAME,
    CONF_PASSWORD: MOCK_PASSWORD,
}

MOCK_CARD_STEP_INPUT = {
    CONF_CARD_ID: MOCK_CARD_ID,
    CONF_CONFIRM_OWNERSHIP: True,
}

MOCK_LOGIN_RESPONSE = {
    "login": {
        "accessToken": MOCK_ACCESS_TOKEN,
        "expiresIn": 86400,
        "tokenType": "Bearer",
    }
}

MOCK_CUSTOMER_RESPONSE = {
    "getCustomerById": {
        "id": MOCK_CUSTOMER_ID,
        "providerCategory": "NL",
    }
}

MOCK_CUSTOMER_CHARGE_CARDS_RESPONSE = {
    "getCustomerById": {
        "id": MOCK_CUSTOMER_ID,
        "cards": [
            {
                "id": "card_1",
                "externalId": MOCK_CARD_ID,
                "internalId": "INT_001",
                "contractId": "CON_001",
                "roaming": True,
                "state": "ACTIVE",
                "type": "RFID",
                "roamingHomeChargingEnabled": True,
                "roamingHubStatus": "ACTIVE",
                "cardProvider": {"name": "50five"},
                "customer": {"id": MOCK_CUSTOMER_ID},
                "transactionCustomer": {"id": MOCK_CUSTOMER_ID},
            },
            {
                "id": "card_2",
                "externalId": "NL-50F-999999-9",
                "internalId": "INT_002",
                "contractId": "CON_002",
                "roaming": False,
                "state": "ACTIVE",
                "type": "APP",
                "roamingHomeChargingEnabled": False,
                "roamingHubStatus": None,
                "cardProvider": {"name": "External Provider"},
                "customer": {"id": MOCK_CUSTOMER_ID},
                "transactionCustomer": {"id": MOCK_CUSTOMER_ID},
            },
        ],
    }
}

MOCK_CUSTOMER_CHARGE_STATIONS_RESPONSE = {
    "getCustomerChargeStations": [
        {
            "id": MOCK_STATION_ID,
            "commId": "COMM_999",
            "name": "Home Charger Single",
            "channels": [
                {
                    "id": "ch_999_1",
                    "evseId": "NL*50F*E999*1",
                    "channelNo": 1,
                    "globalStatus": "AVAILABLE",
                }
            ],
            "location": {
                "countryDetails": {
                    "code": "NL",
                    "currency": {"code": "EUR"},
                }
            },
            "manufacturerType": {
                "vendor": "Alfen",
                "model": "Eve Single Pro-line",
            },
            "subscriptions": [
                {
                    "id": "sub_1",
                    "startDate": "2024-01-01",
                    "endDate": "2025-01-01",
                    "product": {"id": "prod_1", "name": "Basic Care"},
                }
            ],
            "chargeGroup": {
                "tariffVat": {"energy": 0.35},
                "anonymousTariffVat": {"energy": 0.40, "flat": 1.0, "time": 0.0},
            },
            "accessOptions": {
                "authorizationMode": "RFID",
                "accessType": "PRIVATE",
                "publishedOnMap": False,
            },
            "homeChargingCompensation": {
                "hccEnabled": True,
                "hccTariff": 0.30,
            },
            "transactions": {
                "items": [
                    {
                        "id": "tx_last_1",
                        "status": "COMPLETED",
                        "globalStatus": "FINISHED",
                        "type": "REGULAR",
                        "startDate": "2024-08-20T10:00:00Z",
                        "lastUpdateDate": "2024-08-20T14:30:00Z",
                        "totalDuration": 16200.0,
                        "totalEnergy": 28.5,
                        "totalIdleTime": 300.0,
                        "homeCharging": True,
                        "cardSnapshot": {
                            "externalId": MOCK_CARD_ID,
                            "internalId": "INT_001",
                            "contractId": "CON_001",
                            "type": "RFID",
                        },
                        "transactionPrices": [
                            {
                                "totalCost": 9.98,
                                "type": "CONSUMPTION",
                                "vatPercentage": 21.0,
                                "currency": {"code": "EUR"},
                            }
                        ],
                    }
                ]
            },
        },
        {
            "id": MOCK_MULTI_STATION_ID,
            "commId": "COMM_888",
            "name": "Office Charger Dual",
            "channels": [
                {
                    "id": "ch_888_1",
                    "evseId": "NL*50F*E888*1",
                    "channelNo": 1,
                    "globalStatus": "CHARGING",
                },
                {
                    "id": "ch_888_2",
                    "evseId": "NL*50F*E888*2",
                    "channelNo": 2,
                    "globalStatus": "AVAILABLE",
                },
            ],
            "location": {
                "countryDetails": {
                    "code": "NL",
                    "currency": {"code": "EUR"},
                }
            },
            "manufacturerType": {
                "vendor": "Alfen",
                "model": "Eve Double Pro-line",
            },
            "accessOptions": {
                "authorizationMode": "RFID",
                "accessType": "PUBLIC_PAID",
                "publishedOnMap": True,
            },
            "homeChargingCompensation": {
                "hccEnabled": False,
                "hccTariff": None,
            },
            "transactions": {"items": []},
        },
    ]
}

MOCK_CHARGE_STATION_DETAILS_RESPONSE = {
    "getChargeStationById": {
        "id": MOCK_STATION_ID,
        "commId": "COMM_999",
        "name": "Home Charger Single",
        "channels": [
            {
                "id": "ch_999_1",
                "evseId": "NL*50F*E999*1",
                "channelNo": 1,
                "globalStatus": "AVAILABLE",
                "cableLock": "UNLOCKED",
                "soc": 80,
                "activeTariff": {"energy": 0.35, "flat": 0.0, "time": 0.0},
            }
        ],
        "location": {
            "id": "loc_1",
            "address": "Street 1",
            "postalCode": "1234AB",
            "city": "Amsterdam",
            "countryDetails": {
                "code": "NL",
                "currency": {"code": "EUR"},
            },
        },
        "manufacturerType": {
            "vendor": "Alfen",
            "model": "Eve Single Pro-line",
        },
        "transactions": {"items": []},
    }
}

MOCK_ACTIVE_TRANSACTION_RESPONSE = {
    "lmsActiveTransaction": {
        "updateDate": "2024-08-28T10:30:00Z",
        "address": "Street 1",
        "zipCode": "1234AB",
        "city": "Amsterdam",
        "energyDelivered": 12.4,
        "startDate": "2024-08-28T09:00:00Z",
        "countryCode": "NL",
        "currency": "EUR",
        "totalAmount": 4.34,
        "vat": 21.0,
        "durationCharging": 5400.0,
        "priceElements": [
            {"type": "ENERGY", "price": 0.35},
        ],
        "tariffId": "tariff_1",
        "channelVisibleId": 1,
    }
}
