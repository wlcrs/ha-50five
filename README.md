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
* **Start & Stop Charging**: Control charging sessions per channel/connector directly from Home Assistant.
* **RFID Card Support**: Start charging using a default configured RFID card or specify a custom card ID per session.
* **Multi-Connector Support**: Automatically handles single and multi-channel charge stations with separate switches per channel.

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


### 🔍 Diagnostics & Troubleshooting
* **Home Assistant Diagnostics**: Download redacted diagnostic data directly from the device/integration settings.
* **Reconfiguration & Options**: Update credentials or change default RFID card ID on the fly without re-adding the integration.

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
4. Step 2 (Charge Card): Select your default charge card from the cards linked to your account and check the confirmation box (*"I hereby confirm that the selected charge card is in my possession and that I am the owner"*). This step can be skipped if you do not wish to link a charge card at this time.

> [!NOTE]
> The charging switch entity is only created if a charge card is selected and configured, and its name reflects the active card (e.g. `Charge with card NL-50F-...` / `Laden met laadpas NL-50F-...`). You can configure or change your card at any time from the integration's **Configure** (options) menu.
