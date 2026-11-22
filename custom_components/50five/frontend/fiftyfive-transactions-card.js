/**
 * 50five Transactions Card
 *
 * Custom Lovelace card that fetches recent charging transactions on demand
 * via the `50five.get_transactions` WebSocket service response API and renders
 * them using Home Assistant's native house-style design tokens and components.
 */

const CARD_TAG = "fiftyfive-transactions-card";
const DEFAULT_LIMIT = 5;

class FiftyFiveTransactionsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._transactions = [];
    this._page = 1;
    this._hasNext = false;
    this._loading = false;
    this._error = null;
    this._lastEntityState = undefined;
    this._hasFetched = false;
    this._fetchInFlight = null;
  }

  static getStubConfig(hass) {
    let defaultEntity = "";
    if (hass && hass.states) {
      const candidates = Object.keys(hass.states).filter(
        (eid) =>
          eid.startsWith("sensor.") &&
          (eid.includes("last_session") || eid.includes("50five"))
      );
      if (candidates.length > 0) {
        defaultEntity = candidates[0];
      }
    }
    return {
      entity: defaultEntity,
      title: "Recent Charging Sessions",
      limit: DEFAULT_LIMIT,
      show_card: true,
      compact: false,
    };
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: {
            entity: {
              integration: "50five",
            },
          },
        },
        {
          name: "title",
          selector: { text: {} },
        },
        {
          name: "limit",
          selector: {
            number: {
              min: 1,
              max: 50,
              mode: "box",
            },
          },
        },
        {
          name: "show_card",
          selector: { boolean: {} },
        },
        {
          name: "compact",
          selector: { boolean: {} },
        },
      ],
      computeLabel: (schema) => {
        const labels = {
          entity: "Charge station entity",
          title: "Card title",
          limit: "Transactions to show",
          show_card: "Show RFID card column",
          compact: "Compact rows",
        };
        return labels[schema.name] || schema.name;
      },
    };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Please define a 50five 'entity' in card configuration.");
    }
    const prevEntity = this._config?.entity;
    const prevLimit = this._config?.limit;

    this._config = {
      title: "Recent Charging Sessions",
      limit: DEFAULT_LIMIT,
      show_card: true,
      compact: false,
      ...config,
    };

    if (
      prevEntity !== this._config.entity ||
      prevLimit !== this._config.limit
    ) {
      this._page = 1;
      this._hasNext = false;
      this._hasFetched = false;
      this._lastEntityState = undefined;
    }

    this._render();
    if (this._hass && !this._hasFetched) {
      this._fetchTransactions();
    }
  }

  set hass(hass) {
    this._hass = hass;
    const entityId = this._config?.entity;
    if (!entityId || !hass) {
      return;
    }

    const stateObj = hass.states?.[entityId];
    const currentState = stateObj ? `${stateObj.state}|${stateObj.last_updated}` : undefined;

    if (!this._hasFetched) {
      this._lastEntityState = currentState;
      this._fetchTransactions();
    } else if (stateObj && stateObj.state !== undefined) {
      const prevStateVal = this._lastEntityState?.split("|")[0];
      if (prevStateVal !== undefined && prevStateVal !== stateObj.state) {
        this._lastEntityState = currentState;
        this._fetchTransactions();
      }
    }
  }

  getCardSize() {
    const count = Math.min(this._transactions.length || 3, 10);
    return 2 + Math.ceil(count / 2);
  }

  async _fetchTransactions() {
    if (!this._hass || !this._config?.entity) {
      return;
    }
    if (this._fetchInFlight) {
      return this._fetchInFlight;
    }

    this._loading = true;
    this._error = null;
    this._render();

    const promise = (async () => {
      try {
        const result = await this._hass.callWS({
          type: "call_service",
          domain: "50five",
          service: "get_transactions",
          target: {
            entity_id: this._config.entity,
          },
          service_data: {
            limit: Number(this._config.limit) || DEFAULT_LIMIT,
            page: this._page,
          },
          return_response: true,
        });

        const txs = result?.response?.transactions;
        this._transactions = Array.isArray(txs) ? txs : [];
        this._hasNext = Boolean(result?.response?.has_next);
        if (result?.response?.page) {
          this._page = Number(result.response.page) || this._page;
        }
        this._hasFetched = true;
      } catch (err) {
        this._error = err?.message || "Failed to load transactions.";
        this._hasFetched = true;
      } finally {
        this._loading = false;
        this._fetchInFlight = null;
        this._render();
      }
    })();

    this._fetchInFlight = promise;
    return promise;
  }

  _formatDate(isoString) {
    if (!isoString) {
      return "—";
    }
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) {
      return "—";
    }
    const lang = this._hass?.locale?.language || navigator.language || "en";
    return new Intl.DateTimeFormat(lang, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  _formatEnergy(kwh) {
    if (kwh === null || kwh === undefined || Number.isNaN(Number(kwh))) {
      return "—";
    }
    const lang = this._hass?.locale?.language || navigator.language || "en";
    const formatted = new Intl.NumberFormat(lang, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 2,
    }).format(Number(kwh));
    return `${formatted} kWh`;
  }

  _formatDuration(hours) {
    if (hours === null || hours === undefined || Number.isNaN(Number(hours))) {
      return "—";
    }
    const totalMinutes = Math.round(Number(hours) * 60);
    const h = Math.floor(totalMinutes / 60);
    const m = totalMinutes % 60;
    if (h > 0) {
      return `${h}h ${m}m`;
    }
    return `${m}m`;
  }

  _formatCost(amount, currency) {
    if (amount === null || amount === undefined || Number.isNaN(Number(amount))) {
      return "—";
    }
    const lang = this._hass?.locale?.language || navigator.language || "en";
    try {
      return new Intl.NumberFormat(lang, {
        style: "currency",
        currency: currency || "EUR",
      }).format(Number(amount));
    } catch {
      return `${Number(amount).toFixed(2)} ${currency || "EUR"}`;
    }
  }

  _escapeHtml(str) {
    return String(str)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  _render() {
    if (!this.shadowRoot) {
      return;
    }

    const title = this._config?.title ?? "Recent Charging Sessions";
    const showCard = this._config?.show_card !== false;
    const compact = Boolean(this._config?.compact);

    let bodyHtml = "";
    if (this._error) {
      bodyHtml = `
        <ha-alert alert-type="error">
          ${this._escapeHtml(this._error)}
        </ha-alert>
      `;
    } else if (this._loading && this._transactions.length === 0) {
      bodyHtml = `
        <div class="state-box">
          <ha-circular-progress indeterminate size="small"></ha-circular-progress>
          <span>Loading transactions…</span>
        </div>
      `;
    } else if (this._transactions.length === 0) {
      bodyHtml = `
        <div class="state-box empty">
          <ha-icon icon="mdi:ev-station"></ha-icon>
          <span>No recent transactions found</span>
        </div>
      `;
    } else {
      const rowsHtml = this._transactions
        .map((tx) => {
          const cardCell = showCard
            ? `<td class="card-col">${this._escapeHtml(tx.card_id || "—")}</td>`
            : "";
          return `
            <tr>
              <td class="date-col">${this._escapeHtml(this._formatDate(tx.start_date))}</td>
              <td class="num-col">${this._escapeHtml(this._formatEnergy(tx.total_energy))}</td>
              <td class="num-col">${this._escapeHtml(this._formatDuration(tx.total_duration))}</td>
              <td class="num-col cost-col">${this._escapeHtml(
                this._formatCost(tx.total_cost, tx.currency)
              )}</td>
              ${cardCell}
            </tr>
          `;
        })
        .join("");

      bodyHtml = `
        <div class="table-wrap">
          <table class="${compact ? "compact" : ""}">
            <thead>
              <tr>
                <th>Start</th>
                <th class="num-col">Energy</th>
                <th class="num-col">Duration</th>
                <th class="num-col">Cost</th>
                ${showCard ? "<th>Card</th>" : ""}
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        </div>
      `;
    }

    const showPagination = !this._error && (this._page > 1 || this._hasNext);
    const paginationHtml = showPagination
      ? `
        <div class="pagination">
          <ha-icon-button
            id="prev-page-btn"
            title="Previous page"
            aria-label="Previous page"
            ${this._page <= 1 || this._loading ? "disabled" : ""}
          >
            <ha-icon icon="mdi:chevron-left"></ha-icon>
          </ha-icon-button>
          <span class="page-label">Page ${this._page}</span>
          <ha-icon-button
            id="next-page-btn"
            title="Next page"
            aria-label="Next page"
            ${!this._hasNext || this._loading ? "disabled" : ""}
          >
            <ha-icon icon="mdi:chevron-right"></ha-icon>
          </ha-icon-button>
        </div>
      `
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        ha-card {
          height: 100%;
          display: flex;
          flex-direction: column;
        }
        .card-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px 16px 8px;
          color: var(--ha-card-header-color, var(--primary-text-color));
          font-family: var(--ha-card-header-font-family, inherit);
          font-size: var(--ha-card-header-font-size, 24px);
          font-weight: 400;
          line-height: 32px;
        }
        .header-actions {
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .refresh-btn {
          --mdc-icon-button-size: 36px;
          --mdc-icon-size: 20px;
          color: var(--secondary-text-color);
        }
        .refresh-btn.spinning {
          animation: spin 1s linear infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .card-content {
          padding: 0 16px 16px;
        }
        .table-wrap {
          overflow-x: auto;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          font-size: 14px;
          color: var(--primary-text-color);
        }
        thead th {
          text-align: left;
          font-size: 12px;
          font-weight: 500;
          color: var(--secondary-text-color);
          padding: 8px 8px 10px;
          border-bottom: 1px solid var(--divider-color);
          white-space: nowrap;
        }
        tbody td {
          padding: 12px 8px;
          border-bottom: 1px solid var(--divider-color);
          white-space: nowrap;
        }
        table.compact tbody td {
          padding: 8px;
        }
        tbody tr:last-child td {
          border-bottom: none;
        }
        tbody tr:hover {
          background-color: var(--secondary-background-color);
        }
        .num-col {
          text-align: right;
          font-variant-numeric: tabular-nums;
        }
        thead th.num-col {
          text-align: right;
        }
        .cost-col {
          font-weight: 500;
        }
        .card-col {
          color: var(--secondary-text-color);
          font-size: 13px;
        }
        .state-box {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 12px;
          padding: 24px 16px;
          color: var(--secondary-text-color);
          font-size: 14px;
        }
        .state-box.empty ha-icon {
          --mdc-icon-size: 22px;
          opacity: 0.7;
        }
        ha-alert {
          display: block;
          margin-top: 8px;
        }
        .pagination {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 4px;
          padding-top: 8px;
          margin-top: 4px;
          border-top: 1px solid var(--divider-color);
        }
        .pagination ha-icon-button {
          --mdc-icon-button-size: 32px;
          --mdc-icon-size: 20px;
          color: var(--primary-text-color);
        }
        .pagination ha-icon-button[disabled] {
          color: var(--disabled-text-color);
        }
        .page-label {
          font-size: 12px;
          color: var(--secondary-text-color);
          font-variant-numeric: tabular-nums;
          padding: 0 4px;
        }
      </style>
      <ha-card>
        <div class="card-header">
          <span>${this._escapeHtml(title)}</span>
          <div class="header-actions">
            <ha-icon-button
              class="refresh-btn ${this._loading ? "spinning" : ""}"
              title="Refresh transactions"
              aria-label="Refresh transactions"
            >
              <ha-icon icon="mdi:refresh"></ha-icon>
            </ha-icon-button>
          </div>
        </div>
        <div class="card-content">
          ${bodyHtml}
          ${paginationHtml}
        </div>
      </ha-card>
    `;

    const refreshBtn = this.shadowRoot.querySelector(".refresh-btn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        this._fetchTransactions();
      });
    }

    const prevBtn = this.shadowRoot.getElementById("prev-page-btn");
    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        if (this._page > 1 && !this._loading) {
          this._page -= 1;
          this._fetchTransactions();
        }
      });
    }

    const nextBtn = this.shadowRoot.getElementById("next-page-btn");
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        if (this._hasNext && !this._loading) {
          this._page += 1;
          this._fetchTransactions();
        }
      });
    }
  }
}

if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, FiftyFiveTransactionsCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "50five Transactions",
    description: "Displays recent 50five charging sessions fetched via WebSocket.",
    preview: true,
  });
}
