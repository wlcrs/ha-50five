# 50five Charging Station Integration for Home Assistant

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![Validate](https://github.com/wlcrs/ha-50five/actions/workflows/validate.yaml/badge.svg)](https://github.com/wlcrs/ha-50five/actions/workflows/validate.yaml)

A custom integration for Home Assistant to monitor and control your [50five](https://50five.com/) EV charging stations using the official 50five / LMS GraphQL API backend (the same backend used by the mobile application).

> [!WARNING]
> This integration is not affiliated with or approved by 50five in any way.
>
> Use at your own risk. 

> [!NOTE]
> Your charging card ID is clearly visible when using this integration: as an entity name, sensor state and in the logs.
> This is a deliberate choice so that it is always 100% clear which card you are using to start charging.
>
> When sharing your dashboards and/or logs with 3rd parties, please be aware of this.

---

## Features

### 🔌 Charging Control (Switches)
* **Per-Card Switches**: Select one or more charge cards from your 50five account during setup (or later via **Configure**); each selected card is exposed as its own charging switch per channel/connector, named with the card ID (e.g. `Charge with card NL-50F-...` / `Laden met laadpas NL-50F-...`). Only checked cards are exposed in Home Assistant.
* **Start & Stop Charging**: Turn on a card's switch to start a charging session with that card, or turn it off to stop the active session.
* **Multi-Connector Support**: Automatically handles single and multi-channel charge stations with separate per-card switches per channel.

> [!IMPORTANT]
> **Known limitation — Detecting which card is actively charging:**
>
> In most cases, 50five does not report which charge card is being used while a charging session is still in progress (it only becomes available after the session finishes).
>
> Here is how the card switches behave as a result:
> * **Started from Home Assistant** (using a card switch or the `50five.start_charging` service): the integration remembers which card you used and keeps that card's switch **on** while the session is active.
> * **Started with a physical card or via the 50five app**: unless 50five reports the active card for your account, the integration cannot tell which card is in use. In that case, **none of the card switches will turn on** (an informational message is logged). You can still see that the station is charging via the **Status** sensor, and stop the session using the `50five.stop_charging` service.

### 🔘 Action Buttons
* **Unlock Connector**: Remotely unlock the charging cable connector (available per channel).
* **Soft Reset**: Perform a soft reboot of the charging station.
* **Hard Reset**: Perform a full hardware power cycle / hard reset of the station.
* **Reset Cache**: Clear the charging station's local parameter cache.
* **Refresh Status**: Manually trigger an immediate telemetry and status sync from your charging station by the 50five backend.

### 📊 Real-Time & Active Session Sensors
* **Connector Status**: Operational state enum (`Available`, `Charging`, `Occupied`, `Faulted`, `Unavailable`, `Suspended (EVSE)`, `Suspended (EV)`, `Preparing`, `Finishing`, `Reserved`, `Unknown`).
* **Session Energy**: Total energy delivered during the active charging session (kWh).
* **Session Time**: Active charging session duration (hours).
* **Session Cost**: Total monetary cost accrued during the active session (€).

> [!NOTE]
> We report the values returned by the 50five backend. These might not be accurate, and just stay at 0.
> This is not a bug in this integration, but a limitation of the 50five backend.

### 📈 Last Completed Session Sensors
* **Last Session Energy**: Total energy delivered in the last completed charging session (kWh).
* **Last Session Duration**: Duration of the last completed session (hours).
* **Last Session Start Time**: Timestamp when the last session started.
* **Last Session End Time**: Timestamp when the last session completed.
* **Last Session Cost**: Total cost of the last completed session (€).
* **Last Session Card**: RFID card ID / contract ID used for the last session.

### 📋 Recent Transactions Dashboard Card
The integration automatically registers a custom Lovelace card (`custom:fiftyfive-transactions-card`) — no manual resource configuration is required. You can add **50five Transactions** directly from the dashboard card picker (including a visual configuration editor) or via YAML:

```yaml
type: custom:fiftyfive-transactions-card
entity: sensor.home_charger_status
title: Recent Charging Sessions
limit: 5
show_card: true
compact: false
```

| Option | Type | Default | Description |
|---|---|---|---|
| `entity` | `string` *(required)* | – | Any `50five` entity belonging to the charge station you want to display. |
| `title` | `string` | `Recent Charging Sessions` | Card header title. |
| `limit` | `number` (`1`–`50`) | `5` | Number of transactions shown per page. |
| `show_card` | `boolean` | `true` | Show the RFID card ID column. |
| `compact` | `boolean` | `false` | Use compact row padding. |

The card fetches transactions on demand via the `50five.get_transactions` service (rather than storing a full history in entity attributes), supports **Previous/Next** page navigation and a manual **Refresh** button, and automatically reloads whenever the configured `entity` changes state (for example, when a session finishes or the status sensor updates).

#### What transactions are visible (and which ones are not)
* **Visible:**
  * **Completed/settled sessions on the targeted charge station** updated within the **last calendar month**, sorted newest-first by start time.
  * **All cards and start methods used on that station** — includes sessions started via Home Assistant, the 50five app, or physical RFID cards (not just the cards you exposed as switches in Home Assistant).
* **Not visible:**
  * **Transactions older than 1 calendar month:** The 50five backend restricts each `getTransactions` query to a maximum 1-month date range, and the card uses the service's default last-month window (unlike the 50five mobile app, which queries up to 3 monthly windows sequentially). To inspect older sessions, call the `50five.get_transactions` service directly with `date_from` and `date_to` (spanning up to 1 month).
  * **In-progress / active sessions:** Live telemetry for ongoing sessions comes from a separate endpoint and is shown in the **Real-Time & Active Session Sensors**; transactions appear in the card once they are completed/settled in the 50five backend (there can be a short delay right after a session stops).
  * **Sessions at other or public charging stations:** The card queries history scoped to the targeted charge station only, not your charge card's roaming or public charging sessions elsewhere.

### ⚡ Home Charging Compensation (HCC) Sensors and Control
* **HCC Status**: Binary sensor indicating whether Home Charging Compensation reimbursement is enabled (`On` / `Off`).
* **HCC Tariff (Sensor)**: Active compensation reimbursement rate including VAT (€/kWh), with the raw net tariff, VAT percentage, and VAT multiplier exposed as attributes.
* **HCC Tariff (Number)**: A disabled-by-default number entity for changing the HCC tariff, displayed **including VAT** just like the mobile app. Its minimum and maximum come from the backend `reimbursementTariffRange` (fallback: €0.0001–€0.67/kWh net) with the account's VAT multiplier applied and rounded to 4 decimal places. Entered values are divided by the VAT multiplier (rounded to 4 decimals) before saving to the backend, and updates are verified by reading the tariff back. The entity is omitted for Belgian provider-category accounts, where the app hides the edit control.

> [!NOTE]
> The VAT multipliers used for HCC tariff calculations are **hard-coded** in the integration (mirroring the 50five mobile app's `VatTariff` lookup by customer `providerCategory`, with a `1.21` / 21% fallback). If VAT rates change in your country, the integration must be updated to reflect the new rate.

### 🛠️ Home Assistant Services
The integration registers custom services under the `50five` domain for automations that require specific parameters (such as a custom RFID card):

| Service | Description | Fields |
|---|---|---|
| `50five.start_charging` | Start charging on targeted station/channel with an optional card ID | `card_id` *(optional)* |
| `50five.stop_charging` | Stop charging on targeted station/channel | – |
| `50five.get_transactions` | Fetch recent completed transactions for targeted charge station(s) *(returns service response data)* | `limit` *(optional, 1–50, default `5`)*, `date_from` *(optional)*, `date_to` *(optional, max 1-month span; defaults to the last calendar month)*, `page` *(optional, default `1`)* |


### 🔍 Diagnostics & Troubleshooting
* **Home Assistant Diagnostics**: Download redacted diagnostic data directly from the device/integration settings.
* **Reconfiguration & Options**: Update credentials or check/uncheck which charge cards are exposed on the fly without re-adding the integration.

---

## Installation

### Method 1: HACS (Recommended)
1. Open **HACS** in your Home Assistant instance.
2. Go to **Integrations** > **Custom repositories** (three dots top right).
3. Add the repository URL and category `Integration`.
4. Search for `50five` and click **Download**.
5. Restart Home Assistant.

### Method 2: Manual Installation
1. Download the latest release `.zip` or clone this repository.
2. Copy the `custom_components/50five` directory into your Home Assistant `<config_dir>/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, navigate to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **50five**.
3. Step 1 (Credentials): Enter your 50five account credentials (**Email** and **Password**).
4. Step 2 (Charge Cards): Check one or more charge cards linked to your account that you want to expose as switches in Home Assistant, and check the ownership confirmation box (*"I hereby confirm that the selected charge card(s) are in my possession and that I am the owner"*). You may leave all cards unchecked if you do not wish to expose any charging switches at this time.

> [!NOTE]
> Only the charge cards you check are exposed as switch entities (per channel), and each switch name reflects its card ID (e.g. `Charge with card NL-50F-...` / `Laden met laadpas NL-50F-...`). You can add or remove cards at any time from the integration's **Configure** (options) menu; unchecked cards are automatically removed.
