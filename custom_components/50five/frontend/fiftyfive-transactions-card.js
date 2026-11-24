/**
 * 50five Transactions Card
 *
 * Custom Lovelace card that fetches recent charging transactions on demand
 * via the `50five.get_transactions` WebSocket service response API and renders
 * them using Home Assistant's native house-style design tokens and components.
 */

const CARD_TAG = "fiftyfive-transactions-card";
const DEFAULT_LIMIT = 5;

const TRANSLATIONS = {
  en: {
    default_title: "Recent Charging Sessions",
    loading: "Loading transactions…",
    empty: "No recent transactions found",
    error_default: "Failed to load transactions.",
    col_start: "Start",
    col_energy: "Energy",
    col_duration: "Duration",
    col_cost: "Cost",
    col_card: "Card",
    refresh: "Refresh transactions",
    prev_page: "Previous page",
    next_page: "Next page",
    page: "Page",
    cfg_device: "Charge station",
    cfg_title: "Card title",
    cfg_limit: "Transactions to show",
    cfg_show_card: "Show RFID card column",
    cfg_compact: "Compact rows",
  },
  nl: {
    default_title: "Recente laadsessies",
    loading: "Transacties laden…",
    empty: "Geen recente transacties gevonden",
    error_default: "Laden van transacties mislukt.",
    col_start: "Start",
    col_energy: "Energie",
    col_duration: "Duur",
    col_cost: "Kosten",
    col_card: "Pas",
    refresh: "Transacties vernieuwen",
    prev_page: "Vorige pagina",
    next_page: "Volgende pagina",
    page: "Pagina",
    cfg_device: "Laadpaal",
    cfg_title: "Kaarttitel",
    cfg_limit: "Aantal transacties",
    cfg_show_card: "Laadpas-kolom tonen",
    cfg_compact: "Compacte rijen",
  },
  fr: {
    default_title: "Sessions de charge récentes",
    loading: "Chargement des transactions…",
    empty: "Aucune transaction récente",
    error_default: "Échec du chargement des transactions.",
    col_start: "Début",
    col_energy: "Énergie",
    col_duration: "Durée",
    col_cost: "Coût",
    col_card: "Badge",
    refresh: "Actualiser les transactions",
    prev_page: "Page précédente",
    next_page: "Page suivante",
    page: "Page",
    cfg_device: "Borne de recharge",
    cfg_title: "Titre de la carte",
    cfg_limit: "Transactions à afficher",
    cfg_show_card: "Afficher la colonne badge",
    cfg_compact: "Lignes compactes",
  },
  de: {
    default_title: "Letzte Ladevorgänge",
    loading: "Transaktionen werden geladen…",
    empty: "Keine aktuellen Transaktionen gefunden",
    error_default: "Transaktionen konnten nicht geladen werden.",
    col_start: "Start",
    col_energy: "Energie",
    col_duration: "Dauer",
    col_cost: "Kosten",
    col_card: "Karte",
    refresh: "Transaktionen aktualisieren",
    prev_page: "Vorherige Seite",
    next_page: "Nächste Seite",
    page: "Seite",
    cfg_device: "Ladestation",
    cfg_title: "Kartentitel",
    cfg_limit: "Angezeigte Transaktionen",
    cfg_show_card: "RFID-Kartenspalte anzeigen",
    cfg_compact: "Kompakte Zeilen",
  },
  es: {
    default_title: "Sesiones de carga recientes",
    loading: "Cargando transacciones…",
    empty: "No se encontraron transacciones recientes",
    error_default: "Error al cargar las transacciones.",
    col_start: "Inicio",
    col_energy: "Energía",
    col_duration: "Duración",
    col_cost: "Coste",
    col_card: "Tarjeta",
    refresh: "Actualizar transacciones",
    prev_page: "Página anterior",
    next_page: "Página siguiente",
    page: "Página",
    cfg_device: "Estación de carga",
    cfg_title: "Título de la tarjeta",
    cfg_limit: "Transacciones a mostrar",
    cfg_show_card: "Mostrar columna de tarjeta",
    cfg_compact: "Filas compactas",
  },
  it: {
    default_title: "Sessioni di ricarica recenti",
    loading: "Caricamento transazioni…",
    empty: "Nessuna transazione recente trovata",
    error_default: "Impossibile caricare le transazioni.",
    col_start: "Inizio",
    col_energy: "Energia",
    col_duration: "Durata",
    col_cost: "Costo",
    col_card: "Tessera",
    refresh: "Aggiorna transazioni",
    prev_page: "Pagina precedente",
    next_page: "Pagina successiva",
    page: "Pagina",
    cfg_device: "Stazione di ricarica",
    cfg_title: "Titolo scheda",
    cfg_limit: "Transazioni da mostrare",
    cfg_show_card: "Mostra colonna tessera",
    cfg_compact: "Righe compatte",
  },
  pl: {
    default_title: "Ostatnie sesje ładowania",
    loading: "Ładowanie transakcji…",
    empty: "Brak ostatnich transakcji",
    error_default: "Nie udało się załadować transakcji.",
    col_start: "Start",
    col_energy: "Energia",
    col_duration: "Czas",
    col_cost: "Koszt",
    col_card: "Karta",
    refresh: "Odśwież transakcje",
    prev_page: "Poprzednia strona",
    next_page: "Następna strona",
    page: "Strona",
    cfg_device: "Stacja ładowania",
    cfg_title: "Tytuł karty",
    cfg_limit: "Liczba transakcji",
    cfg_show_card: "Pokaż kolumnę karty",
    cfg_compact: "Kompaktowe wiersze",
  },
};

function getLanguage(hass) {
  const raw =
    hass?.locale?.language ||
    document.querySelector("home-assistant")?.hass?.locale?.language ||
    navigator.language ||
    "en";
  const norm = raw.toLowerCase();
  if (TRANSLATIONS[norm]) {
    return norm;
  }
  const base = norm.split("-")[0];
  return TRANSLATIONS[base] ? base : "en";
}

function localize(hass, key) {
  const lang = getLanguage(hass);
  return TRANSLATIONS[lang]?.[key] || TRANSLATIONS.en[key] || key;
}

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
    let defaultDeviceId = "";
    if (hass && hass.entities) {
      const entry = Object.values(hass.entities).find(
        (ent) => ent.platform === "50five" && ent.device_id
      );
      if (entry) {
        defaultDeviceId = entry.device_id;
      }
    }
    return {
      device_id: defaultDeviceId,
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
          name: "device_id",
          required: true,
          selector: {
            device: {
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
        const labelKeys = {
          device_id: "cfg_device",
          title: "cfg_title",
          limit: "cfg_limit",
          show_card: "cfg_show_card",
          compact: "cfg_compact",
        };
        const key = labelKeys[schema.name];
        return key ? localize(null, key) : schema.name;
      },
    };
  }

  setConfig(config) {
    if (!config || !config.device_id) {
      throw new Error("Please select a 50five charge station in card configuration.");
    }
    const prevDeviceId = this._config?.device_id;
    const prevLimit = this._config?.limit;

    this._config = {
      title: "Recent Charging Sessions",
      limit: DEFAULT_LIMIT,
      show_card: true,
      compact: false,
      ...config,
    };

    if (prevDeviceId !== this._config.device_id || prevLimit !== this._config.limit) {
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

  _getWatchEntityId(hass) {
    const deviceId = this._config?.device_id;
    if (!deviceId || !hass?.entities) {
      return null;
    }
    const deviceEntities = Object.values(hass.entities).filter(
      (ent) => ent.platform === "50five" && ent.device_id === deviceId
    );
    const preferred =
      deviceEntities.find(
        (ent) => hass.states?.[ent.entity_id]?.attributes?.device_class === "timestamp"
      ) ||
      deviceEntities.find((ent) => ent.entity_id.startsWith("sensor.")) ||
      deviceEntities[0];
    return preferred ? preferred.entity_id : null;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config?.device_id || !hass) {
      return;
    }

    const watchEntityId = this._getWatchEntityId(hass);
    const stateObj = watchEntityId ? hass.states?.[watchEntityId] : undefined;
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
    if (!this._hass || !this._config?.device_id) {
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
          service_data: {
            device_id: this._config.device_id,
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

    const title = this._config?.title || localize(this._hass, "default_title");
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
          <span>${this._escapeHtml(localize(this._hass, "loading"))}</span>
        </div>
      `;
    } else if (this._transactions.length === 0) {
      bodyHtml = `
        <div class="state-box empty">
          <ha-icon icon="mdi:ev-station"></ha-icon>
          <span>${this._escapeHtml(localize(this._hass, "empty"))}</span>
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
                <th>${this._escapeHtml(localize(this._hass, "col_start"))}</th>
                <th class="num-col">${this._escapeHtml(localize(this._hass, "col_energy"))}</th>
                <th class="num-col">${this._escapeHtml(localize(this._hass, "col_duration"))}</th>
                <th class="num-col">${this._escapeHtml(localize(this._hass, "col_cost"))}</th>
                ${showCard ? `<th>${this._escapeHtml(localize(this._hass, "col_card"))}</th>` : ""}
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
    const prevLabel = this._escapeHtml(localize(this._hass, "prev_page"));
    const nextLabel = this._escapeHtml(localize(this._hass, "next_page"));
    const pageWord = this._escapeHtml(localize(this._hass, "page"));
    const paginationHtml = showPagination
      ? `
        <div class="pagination">
          <ha-icon-button
            id="prev-page-btn"
            title="${prevLabel}"
            aria-label="${prevLabel}"
            ${this._page <= 1 || this._loading ? "disabled" : ""}
          >
            <ha-icon icon="mdi:chevron-left"></ha-icon>
          </ha-icon-button>
          <span class="page-label">${pageWord} ${this._page}</span>
          <ha-icon-button
            id="next-page-btn"
            title="${nextLabel}"
            aria-label="${nextLabel}"
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
              title="${this._escapeHtml(localize(this._hass, "refresh"))}"
              aria-label="${this._escapeHtml(localize(this._hass, "refresh"))}"
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
