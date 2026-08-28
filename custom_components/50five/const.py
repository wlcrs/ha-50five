"""Constants for the 50five integration."""

DOMAIN = "50five"

# Configuration keys
CONF_ACCESS_TOKEN = "access_token"
CONF_CONFIRM_OWNERSHIP = "confirm_ownership"
CONF_CARD_ID = "card_id"
CONF_CUSTOMER_ID = "customer_id"
CONF_DEVICE_ID = "device_id"
CONF_TOKEN_EXPIRES_AT = "token_expires_at"

# API Endpoint
DEFAULT_BASE_URL = "https://lms.servicelayer.platform-01.plugz.dev/graphql"
DEFAULT_SCAN_INTERVAL = 60  # seconds
ACTION_SETTLE_DELAY_SEC = (
    5  # Seconds to wait after action before refreshing coordinator data
)

# Attribute names
ATTR_CHARGE_STATION_ID = "charge_station_id"
ATTR_COMM_ID = "comm_id"
ATTR_CHANNEL = "channel"
ATTR_STATUS = "status"
ATTR_POWER = "power"
ATTR_ENERGY = "energy"
ATTR_CUSTOMER_ID = "customer_id"
ATTR_CARD_ID = "card_id"
ATTR_DURATION = "duration"
ATTR_TOTAL_AMOUNT = "total_amount"
ATTR_CURRENCY = "currency"
ATTR_RAW_TARIFF = "raw_tariff"
ATTR_VAT = "vat"
ATTR_VAT_MULTIPLIER = "vat_multiplier"

# Standard Channel / Connector Statuses from GraphQL
STATUS_AVAILABLE = "AVAILABLE"
STATUS_CHARGING = "CHARGING"
STATUS_OCCUPIED = "OCCUPIED"
STATUS_FAULTED = "FAULTED"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_SUSPENDED_EVSE = "SUSPENDED_EVSE"
STATUS_SUSPENDED_EV = "SUSPENDED_EV"
STATUS_PREPARING = "PREPARING"
STATUS_FINISHING = "FINISHING"
STATUS_RESERVED = "RESERVED"

# Provider Category VAT Multipliers (matching mobile app VatTariff)
VAT_MULTIPLIERS: dict[str, float] = {
    "AT": 1.20,
    "BE": 1.06,
    "CHF": 1.081,
    "DE": 1.19,
    "ES": 1.21,
    "FR": 1.20,
    "IT": 1.22,
    "NL": 1.21,
    "UK": 1.20,
    "PL": 1.23,
    "NONE": 1.0,
    "None": 1.0,
    "UBER": 1.0,
}
DEFAULT_VAT_MULTIPLIER = 1.21  # Default fallback (NL)

