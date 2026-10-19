# Comparison with `homeassistant-50five`

This document is for maintainers of `ha-50five`. It focuses on the data paths behind active-session and last-session entities, especially where the 50five/LMS backend may return incomplete or stale values.

The other integration is located in the sibling directory [`homeassistant-50five`](homeassistant-50five). Its GraphQL client is in [`custom_components/fifty_five/api.py`](homeassistant-50five/custom_components/fifty_five/api.py), and its query documents are in [`custom_components/fifty_five/const.py`](homeassistant-50five/custom_components/fifty_five/const.py).

## Executive summary

There are two different data paths:

1. **Active session sensors** in both integrations use the same backend operation, `LmsActiveTransaction` / `lmsActiveTransaction`.
2. **Last completed session sensors** use different query shapes:
   - `ha-50five` reads `getCustomerChargeStations { ... transactions { items } }`.
   - `homeassistant-50five` calls `getTransactions(...)` directly with a station filter.

Therefore, the other integration does **not** provide an alternative source for live session energy, duration, or cost. It does provide a potentially useful alternative for completed-session data, including different filters, timestamp formats, pagination, and selected fields.

## Entity/platform inventory

| Capability | `ha-50five` | `homeassistant-50five` |
|---|---|---|
| Sensors | Per station and per channel | One set for the configured station/channel |
| Switches | Per channel charging switch; net-balanced charging switch | One charging switch |
| Buttons | Refresh, unlock, soft reset, hard reset, cache reset | None |
| Select | None | Charge-card selector |
| Custom services | `start_charging`, `stop_charging` | None |

`ha-50five` registers sensor, switch, and button platforms in [`__init__.py`](ha-50five/custom_components/50five/__init__.py). `homeassistant-50five` registers sensor, switch, and select platforms in [`__init__.py`](homeassistant-50five/custom_components/fifty_five/__init__.py).

## Active-session data path

### GraphQL operation

Both integrations execute the same operation:

```graphql
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
```

The important consequence is that live-session values are backend-global values. They are not calculated from charger meter readings by either integration.

### `ha-50five` model

The response is converted into `ActiveTransaction` in [`models.py`](ha-50five/custom_components/50five/models.py). The fields are mapped as follows:

| GraphQL field | Model field | Used by entity |
|---|---|---|
| `energyDelivered` | `energy_delivered` | `session_energy` |
| `durationCharging` | `duration_charging` | `session_time` |
| `totalAmount` | `total_amount` | `session_cost` |
| `channelVisibleId` | `channel_visible_id` | Channel matching/filtering |
| `updateDate` | `update_date` | Not currently exposed |
| `address` | `address` | Not currently exposed |
| `zipCode` | `zip_code` | Not currently exposed |
| `city` | `city` | Not currently exposed |
| `startDate` | `start_date` | Not currently exposed for active session |
| `countryCode` | `country_code` | Not currently exposed |
| `currency` | `currency` | Not currently exposed |
| `vat` | `vat` | Not currently exposed |
| `priceElements[].type` | `price_elements[].type` | Not currently exposed |
| `priceElements[].price` | `price_elements[].price` | Not currently exposed |
| `tariffId` | `tariff_id` | Not currently exposed |

The active transaction is stored once in `StationData` and then associated with channel sensors. If `channelVisibleId` is set, it must match the channel number. If it is absent, the transaction is accepted for the channel.

The active-session sensors are defined in [`sensor.py`](ha-50five/custom_components/50five/sensor.py):

| Entity | Value | Unit/notes |
|---|---|---|
| `session_energy` | `energyDelivered` | kWh; `0.0` when no matching active transaction |
| `session_time` | `durationCharging` | Treated as seconds; HA suggests displaying hours |
| `session_cost` | `totalAmount` | EUR; `0.0` when no matching active transaction |


### `homeassistant-50five` model

The older integration retains the active transaction as a raw dictionary under:

```text
coordinator.data["active_transaction"]
```

Its sensors read:

| Entity | Raw dictionary field | Unit/notes |
|---|---|---|
| `active_transaction_energy` | `energyDelivered` | kWh |
| `active_transaction_duration` | `durationCharging` | Entity says minutes, but the raw value is not converted |
| `active_transaction_amount` | `totalAmount` | Raw amount |
| `active_transaction_address` | `address` | Raw address |

The charging switch also reads this same dictionary:

| Switch attribute/state | Field |
|---|---|
| Charging state | Existence of `active_transaction` |
| `energy_delivered` | `energyDelivered` |
| `duration_minutes` | `durationCharging` |
| `current_cost` | `totalAmount` |
| `channel_status` | Separate `channel.globalStatus` query |

### Active-session conclusion

There is no alternate session calculation in `homeassistant-50five`:

- Both integrations use `lmsActiveTransaction`.
- Both use `energyDelivered`, `durationCharging`, and `totalAmount` directly.
- Neither calculates energy, duration, or cost from lower-level meter samples.
- Neither queries a different active transaction endpoint.

The differences are normalization and entity handling, not the backend source:

- `ha-50five` converts the response to a typed model and filters by `channelVisibleId`.
- `homeassistant-50five` keeps the response raw and treats the one configured channel as the target.
- `ha-50five` uses seconds consistently for duration.
- `homeassistant-50five` labels the raw duration as minutes without conversion.

## Last completed session data path

This is where the integrations differ materially.

### `ha-50five`: nested station transactions

The station discovery query includes:

```graphql
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
```

The variables currently sent by `ha-50five` are built in [`api.py`](ha-50five/custom_components/50five/api.py):

```json
{
  "txFilters": {
    "dateFrom": "YYYY-MM-DD",
    "dateTo": "YYYY-MM-DD",
    "itemsPerPage": 5
  },
  "txSort": {
    "startDate": "desc"
  }
}
```

The response is converted to `CompletedTransaction` in [`models.py`](ha-50five/custom_components/50five/models.py). The first returned item is treated as the last transaction:

```python
@property
def last_transaction(self) -> CompletedTransaction | None:
    return self.transactions[0] if self.transactions else None
```

The last-session sensors read:

| Entity | GraphQL field(s) | Calculation |
|---|---|---|
| `last_transaction_energy` | `transactions.items[0].totalEnergy` | Direct value |
| `last_transaction_duration` | `transactions.items[0].totalDuration` | Direct value; model treats it as seconds |
| `last_transaction_start_time` | `transactions.items[0].startDate` | ISO timestamp parsing |
| `last_transaction_end_time` | `transactions.items[0].lastUpdateDate` | ISO timestamp parsing |
| `last_transaction_cost` | `transactions.items[0].transactionPrices[].totalCost` | First price with a value |
| `last_transaction_card` | `cardSnapshot.externalId`, then `internalId`, then `contractId` | First available identifier |

### `homeassistant-50five`: direct `getTransactions`

The older integration does not use nested station transactions for its history sensors. It calls:

```graphql
query GetChargingHistory(
  $getTransactionsFilters: TransactionFilter,
  $sort: TransactionSort
) {
  getTransactions(
    filters: $getTransactionsFilters,
    sort: $sort
  ) {
    hasNext
    items {
      id
      startDate
      totalDuration
      totalEnergy
      cardSnapshot {
        externalId
      }
      locationSnapshot {
        chargeStationName
        evse {
          id
        }
      }
      transactionPrices {
        totalCost
        type
        vatPercentage
        currency {
          code
        }
        vatCountry {
          code
        }
      }
    }
  }
}
```

It sends this filter shape:

```json
{
  "getTransactionsFilters": {
    "dateFrom": "ISO datetime",
    "dateTo": "ISO datetime",
    "itemsPerPage": 30,
    "page": 1,
    "chargeStation": {
      "id": "configured station ID"
    }
  },
  "sort": {
    "startDate": "desc"
  }
}
```

The older integration therefore differs from `ha-50five` in four potentially important ways:

1. It uses the top-level `getTransactions` operation rather than nested station transactions.
2. It uses ISO timestamps rather than date-only strings.
3. It requests 30 items and explicitly sends `page: 1`, rather than 5 nested items.
4. It filters directly by `chargeStation.id`.

Its history sensors are calculated from the first returned item, which is expected to be newest because the query requests descending `startDate` order:

| Entity | GraphQL field(s) | Calculation |
|---|---|---|
| `history_transaction_count` | `getTransactions.items[]` | Number of returned items |
| `history_total_energy` | `items[].totalEnergy` | Sum of all returned items |
| `history_total_cost` | `transactionPrices[].totalCost` | Sum of positive costs only |
| `history_total_reimbursement` | `transactionPrices[].totalCost` | Sum of negative costs as positive values |
| `last_transaction_date` | `items[0].startDate` | Formatted as `YYYY-MM-DD HH:MM` |
| `last_transaction_energy` | `items[0].totalEnergy` | Direct value |
| `last_transaction_duration` | `items[0].totalDuration` | Divided by 60 and exposed as minutes |
| `last_transaction_cost` | `items[0].transactionPrices[].totalCost` | First positive cost |

### Last-session conclusion

The older integration has a genuinely different approach for completed sessions. It may be worth testing in `ha-50five`, especially if the nested station transaction response is incomplete or incorrectly ordered.

The most relevant differences to investigate are:

- top-level `getTransactions` versus nested `ChargeStation.transactions`;
- ISO datetime filters versus `YYYY-MM-DD` filters;
- 30 results versus 5 results;
- explicit station filter and page number;
- direct raw response handling versus typed conversion;
- whether the backend sorts nested `transactions.items` consistently.

The older integration also exposes `locationSnapshot.chargeStationName`, `locationSnapshot.evse.id`, `cardSnapshot.externalId`, `transactionPrices[].vatPercentage`, `currency.code`, and `vatCountry.code`. `ha-50five` does not currently request these fields in its nested transaction selection.

## Recommended diagnostic comparison

To determine whether the backend or the query shape is responsible, capture the raw results for the same station and time window from both paths.

Compare at least:

```text
transaction ID
startDate
lastUpdateDate, if returned
totalDuration
totalEnergy
transactionPrices[].totalCost
transactionPrices[].currency.code
cardSnapshot fields
```

The comparison should answer these questions:

1. Does `getTransactions` return the same transaction IDs as nested `transactions.items`?
2. Is the newest transaction the first item in both responses?
3. Does using ISO datetime filters return more or different transactions than date-only filters?
4. Does `itemsPerPage: 5` omit the expected last session?
5. Does the nested response contain `lastUpdateDate` and the same price entries?
6. Are `totalDuration` and `durationCharging` expressed in the same units?
7. Is `lmsActiveTransaction.channelVisibleId` a channel number, channel ID, or another identifier?

Do not log or publish raw card identifiers, access tokens, customer IDs, or full addresses in diagnostics.

## Practical candidate change for `ha-50five`

The most targeted experiment is to add a separate `getTransactions` query to `ha-50five`, matching the older integration's filter behavior, while leaving the current nested query in place behind a comparison/debug option. This would isolate the query-shape question without changing the active-session path.

The experiment should preserve the current typed `CompletedTransaction` model but add a parser for the direct `getTransactions.items` response. If both sources return the same transaction ID and values, the backend data is consistent and the issue is likely entity timing, channel association, or units. If they differ, the query shape or filter semantics are the likely cause.

## Other entity differences

### `ha-50five`

- Charging switch per station/channel.
- Net Balanced Charging switch using `getNetBalancedChargingStatus` and `netBalancedCharging`.
- Refresh status button.
- Connector unlock button using `unlockConnector`.
- Soft reset button using `softReset`.
- Hard reset button using `hardReset`.
- Cache reset button using `resetChargeStationParametersCache`.
- `50five.start_charging` service using `startTransaction`.
- `50five.stop_charging` service using `stopTransaction`.

### `homeassistant-50five`

- One charging switch using `startTransaction` and `stopTransaction`.
- Charge-card select based on `getCustomerById.cards`.
- Reservation status sensor based on `activeReservation.status`.
- Access and HCC sensors based on `getChargeStationById`.
- History aggregate sensors based on `getTransactions`.

## Final assessment

For **active sessions**, there is no alternate backend approach in the other integration. Both depend on `lmsActiveTransaction`, so backend problems affecting `energyDelivered`, `durationCharging`, or `totalAmount` will affect both integrations.

For **last completed sessions**, there is a meaningful alternative. `homeassistant-50five` uses direct `getTransactions` history with a station filter, ISO datetime boundaries, 30 results, and explicit pagination. `ha-50five` uses nested station transactions with date-only boundaries and 5 results. This is the first area to test when last-session sensors are unreliable.

The best next maintainer experiment is therefore:

1. Keep the active-session implementation unchanged while diagnosing the backend response.
2. Capture and compare raw active-session responses from both integrations.
3. Add or temporarily implement the direct `getTransactions` path for completed sessions.
4. Compare transaction IDs and values before changing sensor calculations.
