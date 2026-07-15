let chart, candleSeries, smaSeries;
let equityChart, equitySeries, holdEquitySeries;
let lastCandles = [];
let marketsData = {};
let activeSymbol = "BTCUSDT";
let tradesTableFilter = "all";
let lastTradeMarkerStats = { shown: 0, skipped: 0, total: 0 };
let marketMeta = [
  { symbol: "BTCUSDT", label: "BTC" },
  { symbol: "ETHUSDT", label: "ETH" },
  { symbol: "SOLUSDT", label: "SOL" },
  { symbol: "BNBUSDT", label: "BNB" },
  { symbol: "XRPUSDT", label: "XRP", growth: true },
  { symbol: "ADAUSDT", label: "ADA", growth: true },
  { symbol: "AVAXUSDT", label: "AVAX", growth: true },
  { symbol: "LINKUSDT", label: "LINK", growth: true },
  { symbol: "ARBUSDT", label: "ARB", growth: true },
  { symbol: "SUIUSDT", label: "SUI", growth: true },
  { symbol: "NEARUSDT", label: "NEAR", growth: true },
  { symbol: "DOTUSDT", label: "DOT", growth: true },
  { symbol: "INJUSDT", label: "INJ", growth: true },
  { symbol: "TONUSDT", label: "TON", growth: true },
  { symbol: "DOGEUSDT", label: "DOGE", volatile: true },
  { symbol: "PEPEUSDT", label: "PEPE", volatile: true },
  { symbol: "WIFUSDT", label: "WIF", volatile: true, viral: true },
];
let startBalance = 10000;
let tradeSocket = null;

function formatUnixTs(sec, opts) {
  const ts = Number(sec || 0);
  if (!ts || ts < 1e9) return "—";
  return new Date(ts * 1000).toLocaleString("ru-RU", opts);
}

function apiHeaders(json = true) {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  const t = localStorage.getItem("tradesim_token");
  if (t) h["X-API-Token"] = t;
  return h;
}

async function apiFetch(url, options = {}) {
  const opts = { ...options, headers: { ...apiHeaders(options.body != null), ...(options.headers || {}) } };
  const res = await fetch(url, opts);
  if (res.status === 401) showToast("🔐 Нужен API-токен — введи в настройках внизу");
  if (res.status === 429) showToast("⏳ Слишком много запросов — подожди");
  return res;
}
let chatHistory = [];
let lastBrain = null;
let lastTradeMarkers = [];
let activityLog = [];
let lastAnalytics = null;
let lastShadowLab = null;

function showError(msg) {
  const el = document.getElementById("js-error");
  if (el) { el.style.display = "block"; el.textContent = "⚠ " + msg; }
}

function fmtMoney(n, decimals = 2) {
  if (n == null || isNaN(n)) return "—";
  return "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtPct(n) {
  if (n == null || isNaN(n)) return "—";
  return (n >= 0 ? "+" : "") + Number(n).toFixed(2) + "%";
}

function labelFor(sym) {
  const m = marketMeta.find(x => x.symbol === sym);
  return m ? m.label : sym.replace("USDT", "");
}

function priceDecimals(label) {
  const m = marketMeta.find(x => x.label === label);
  if (m?.price_decimals != null) return m.price_decimals;
  if (label === "BTC") return 0;
  if (label === "PEPE") return 8;
  if (label === "DOGE") return 4;
  return 2;
}

function smaPeriod(symbol) {
  const d = marketsData[symbol];
  return d?.strategy?.params?.sma_period || 20;
}

function showToast(text, ms = 5000) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = text;
  el.classList.remove("hidden");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.add("hidden"), ms);
}

function applyMarketMeta(meta) {
  if (!meta?.length) return;
  marketMeta = meta;
  const bt = document.getElementById("backtest-symbol");
  if (bt) {
    bt.innerHTML = meta.map(m => `<option value="${m.symbol}">${m.label}</option>`).join("");
    bt.value = activeSymbol;
  }
}

function renderMarketsTable(rows) {
  const el = document.getElementById("table-markets");
  if (!el) return;
  if (!rows?.length) {
    el.innerHTML = "<p class='muted'>Загрузка рынков...</p>";
    return;
  }
  const tiers = [
    { key: "major", title: "🏦 Majors (4)" },
    { key: "growth", title: "📈 Growth (10)" },
    { key: "volatile", title: "⚡ Meme (2)" },
    { key: "viral", title: "🔥 Viral (1)" },
  ];
  const rowHtml = (r) => {
    const cls = (r.pnl_pct ?? 0) >= 0 ? "up" : "down";
    const tier = r.viral ? "🔥 viral" : r.growth ? "📈 growth" : r.tier === "volatile" ? "⚡ meme" : "🏦 major";
    if (!r.active) return `<tr class="inactive"><td>${r.label}</td><td>${tier}</td><td colspan="7">не подключён</td></tr>`;
    const stype = r.strategy_type || "dca";
    return `<tr><td><b>${r.label}</b></td><td>${tier}</td><td><span class="strategy-tag">${stype}</span></td><td>${fmtMoney(r.price, priceDecimals(r.label))}</td>
      <td>${fmtMoney(r.portfolio_value)}</td><td class="${cls}">${fmtPct(r.pnl_pct)}</td>
      <td>${fmtPct(r.vs_hold_pct)}</td><td>${r.trades}</td><td>${r.bot_enabled ? "✅" : "⏸"}</td>
      <td class="row-actions">
        <button class="shadow-apply-btn" data-action="toggle" data-sym="${r.symbol}">⏯</button>
        <button class="shadow-apply-btn" data-action="sync-strat" data-sym="${r.symbol}" data-st="${stype}">🔄</button>
      </td></tr>`;
  };
  const head = `<table class="data-table"><thead><tr>
    <th>Монета</th><th>Тип</th><th>Стратегия</th><th>Цена</th><th>Портфель</th><th>P&L</th><th>vs hold</th><th>Сделок</th><th>Бот</th><th></th>
  </tr></thead><tbody>`;
  let html = "";
  for (const t of tiers) {
    const group = rows.filter(r =>
      t.key === "viral" ? r.viral :
      t.key === "volatile" ? (r.tier === "volatile" && !r.viral) :
      t.key === "growth" ? r.growth :
      (!r.growth && !r.volatile && !r.viral && r.tier === "major")
    );
    if (!group.length) continue;
    html += `<tr class="tier-header"><td colspan="10">${t.title}</td></tr>${group.map(rowHtml).join("")}`;
  }
  const other = rows.filter(r => !tiers.some(t => {
    if (t.key === "viral") return r.viral;
    if (t.key === "volatile") return r.tier === "volatile" && !r.viral;
    if (t.key === "growth") return r.growth;
    return !r.growth && !r.volatile && !r.viral;
  }));
  if (other.length) html += other.map(rowHtml).join("");
  el.innerHTML = head + html + "</tbody></table>";
  el.querySelectorAll("[data-action=toggle]").forEach(btn => {
    btn.onclick = async () => {
      await apiFetch(`/api/bot/toggle?symbol=${btn.dataset.sym}`, { method: "POST" });
      await refreshStatus();
      renderMarketsTable((await (await fetch("/api/bootstrap")).json()).markets_table);
    };
  });
  el.querySelectorAll("[data-action=sync-strat]").forEach(btn => {
    btn.onclick = async () => {
      const sym = btn.dataset.sym;
      try {
        const res = await apiFetch(`/api/market/sync-strategy?symbol=${sym}`, { method: "POST" });
        const data = await res.json();
        if (data.error) showToast("⚠ " + data.error);
        else {
          showToast(`🔄 ${data.label || sym}: ${data.strategy_type} · ${data.source || "live"}`);
          await refreshStatus();
          renderMarketsTable((await (await fetch("/api/bootstrap")).json()).markets_table);
        }
      } catch (_) {
        showToast("Ошибка синхронизации стратегии");
      }
    };
  });
}

async function loadTradesTable(symbolOrAll) {
  const el = document.getElementById("table-trades");
  if (!el) return;
  if (symbolOrAll !== undefined) tradesTableFilter = symbolOrAll;
  const filter = tradesTableFilter;
  el.innerHTML = "<p class='muted'>Загрузка сделок из SQLite...</p>";
  try {
    const sym = filter === "all" ? "" : (filter || activeSymbol);
    const url = sym ? `/api/trades?limit=500&symbol=${sym}` : "/api/trades?limit=500";
    const data = await (await fetch(url)).json();
    const trades = data.trades || [];
    const markets = Object.keys(marketsData).sort();
    const filterBar = `<div class="trades-filter-bar" style="display:flex;gap:0.5rem;align-items:center;margin-bottom:0.5rem;flex-wrap:wrap">
      <label class="muted">Монета:</label>
      <select id="trades-symbol-filter" class="backtest-select">
        <option value="all"${filter === "all" ? " selected" : ""}>Все монеты (${data.count || trades.length})</option>
        ${markets.map(s => `<option value="${s}"${filter === s ? " selected" : ""}>${labelFor(s)}</option>`).join("")}
      </select>
      <span class="muted tiny">Показано: ${trades.length} · клик по монете вверху = фильтр только её</span>
    </div>`;
    if (!trades.length) {
      el.innerHTML = filterBar + "<p class='muted'>Сделок пока нет — бот купит при DCA или просадке.</p>";
      document.getElementById("trades-symbol-filter")?.addEventListener("change", (e) => loadTradesTable(e.target.value));
      return;
    }
    el.innerHTML = `${filterBar}
    <table class="data-table"><thead><tr>
      <th>Время</th><th>Монета</th><th>Сторона</th><th>Цена</th><th>$</th><th>Fee</th><th>Причина</th>
    </tr></thead><tbody>${trades.map(t => {
      const d = new Date((t.ts || 0) * 1000).toLocaleString("ru-RU", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
      const lbl = t.label || labelFor(t.symbol);
      const cls = t.side === "buy" ? "up" : "down";
      return `<tr><td>${d}</td><td><b>${lbl}</b></td><td class="${cls}">${t.side?.toUpperCase()}</td>
        <td>${fmtMoney(t.price, priceDecimals(lbl))}</td><td>${fmtMoney(t.amount_quote)}</td>
        <td>${t.fee != null ? "$" + Number(t.fee).toFixed(3) : "—"}</td><td>${escapeHtml((t.reason || "").slice(0, 50))}</td></tr>`;
    }).join("")}</tbody></table>`;
    document.getElementById("trades-symbol-filter")?.addEventListener("change", (e) => loadTradesTable(e.target.value));
  } catch (_) {
    el.innerHTML = "<p class='muted'>Не удалось загрузить сделки</p>";
  }
}

function renderAnalyticsTable(analytics) {
  const el = document.getElementById("table-analytics");
  if (!el || !analytics?.markets) return;
  el.innerHTML = `<table class="data-table"><thead><tr>
    <th>Монета</th><th>P&L</th><th>vs hold</th><th>Сделок</th><th>DCA</th><th>DIP</th><th>TP</th><th>STOP</th>
  </tr></thead><tbody>${analytics.markets.map(m => {
    const rs = m.trade_stats?.reasons || {};
    const cls = m.pnl_pct >= 0 ? "up" : "down";
    return `<tr><td><b>${m.label}</b></td><td class="${cls}">${fmtPct(m.pnl_pct)}</td>
      <td>${fmtPct(m.vs_hold_pct)}</td><td>${m.trade_stats?.total || 0}</td>
      <td>${rs.dca || 0}</td><td>${rs.dip || 0}</td><td>${rs.tp || 0}</td><td>${rs.stop || 0}</td></tr>`;
  }).join("")}</tbody></table>
  <p class="muted" style="margin-top:0.5rem">Win rate (FIFO): ${analytics.portfolio_win_rate_pct ?? "—"}% · Max DD: ${analytics.max_drawdown_pct}% · Sharpe: ${analytics.sharpe_proxy ?? "—"}</p>`;
}

function renderLearningTable(learning, history, honesty) {
  const el = document.getElementById("table-learning");
  if (!el) return;
  const ev = honesty?.evidence || {};
  let hist = "";
  const tuneRows = (history?.length ? history : learning?.strategy_versions) || [];
  if (tuneRows.length) {
    hist = `<h4 style="margin:0.75rem 0 0.35rem;font-size:0.8rem">Последние автонастройки</h4>
    <table class="data-table"><thead><tr><th>Время</th><th>Рынок</th><th>Причина</th></tr></thead><tbody>
    ${tuneRows.slice(0, 10).map(t => {
      const ts = t.ts && t.ts > 1e9 ? t.ts : null;
      const d = ts ? new Date(ts * 1000).toLocaleString("ru-RU") : "—";
      return `<tr><td>${d}</td><td>${(t.symbol || "").replace("USDT", "")}</td><td>${(t.reason || "").slice(0, 60)}</td></tr>`;
    }).join("")}</tbody></table>`;
  }
  el.innerHTML = `<table class="data-table"><tbody>
    <tr><td>Сделок в БД</td><td><b>${ev.trades_logged || learning?.trade_count || 0}</b></td></tr>
    <tr><td>Автонастроек</td><td><b>${ev.strategy_tunes || 0}</b></td></tr>
    <tr><td>Shadow переносов</td><td><b>${ev.shadow_promotions || 0}</b></td></tr>
    <tr><td>Циклов мозга</td><td><b>${ev.brain_cycles || 0}</b></td></tr>
  </tbody></table>${hist}`;
}

function renderDepositsTable(deposits) {
  const el = document.getElementById("table-deposits");
  if (!el) return;
  if (!deposits?.length) {
    el.innerHTML = "<p class='muted'>Пополнений пока нет. Нажми «+ Пополнить» в шапке.</p>";
    return;
  }
  el.innerHTML = `<table class="data-table"><thead><tr><th>Время</th><th>Сумма</th><th>Куда</th><th>Итого портфель</th></tr></thead><tbody>
    ${deposits.map(d => `<tr><td>${formatUnixTs(d.ts)}</td>
      <td><b>$${Number(d.amount).toLocaleString()}</b></td><td>${d.note || d.target}</td>
      <td>${fmtMoney(d.total_after)}</td></tr>`).join("")}
  </tbody></table>`;
}

function renderMovementsTable(movements) {
  const el = document.getElementById("table-movements");
  if (!el) return;
  if (!movements?.length) {
    el.innerHTML = "<p class='muted'>Движений пока нет. Пополнение и вывод — кнопки в шапке.</p>";
    return;
  }
  el.innerHTML = `<table class="data-table"><thead><tr><th>Время</th><th>Тип</th><th>Сумма</th><th>Кошелёк</th><th>Примечание</th></tr></thead><tbody>
    ${movements.map(m => `<tr>
      <td>${formatUnixTs(m.ts)}</td>
      <td>${m.kind === "deposit" ? "➕" : "➖"} ${m.kind}</td>
      <td><b>$${Number(m.amount).toLocaleString()}</b></td>
      <td>${m.wallet || "paper"}</td>
      <td>${m.note || m.target || m.symbol || "—"}</td>
    </tr>`).join("")}
  </tbody></table>`;
}

function renderHonestyTable(h) {
  const el = document.getElementById("table-honesty");
  if (!el || !h) return;
  el.innerHTML = `<div class="honesty-box">
    <p><b>Готовность проекта:</b> ${h.project_readiness}</p>
    <p><b>Учится сам?</b> <span class="ok">${h.really_learns ? "Да — но эвристики, не ИИ" : "Нет"}</span> (${h.learning_kind})</p>
    <p><b>Рынков:</b> ${h.markets_active} / ${h.markets_configured} активны</p>
    <p class="warn"><b>Что реально:</b></p><ul>${(h.what_is_real || []).map(x => `<li class="ok">${x}</li>`).join("")}</ul>
    <p class="warn"><b>Чего нет:</b></p><ul>${(h.what_is_not || []).map(x => `<li>${x}</li>`).join("")}</ul>
  </div>`;
}

async function runBacktestTable() {
  const el = document.getElementById("table-backtest");
  if (!el) return;
  const sym = document.getElementById("backtest-symbol")?.value || activeSymbol;
  el.innerHTML = "<p class='muted'>⏱ Прогон стратегии по историческим свечам...</p>";
  try {
    const res = await apiFetch("/api/backtest", {
      method: "POST",
      body: JSON.stringify({ symbol: sym, limit: 500 }),
    });
    const r = await res.json();
    if (r.error) {
      el.innerHTML = `<p class="muted">Ошибка: ${r.error}</p>`;
      return;
    }
    const cls = r.pnl_pct >= 0 ? "up" : "down";
    const log = (r.trade_log || []).map(t =>
      `<tr><td>${t.side}</td><td>${fmtMoney(t.price)}</td><td>${fmtMoney(t.amount_quote)}</td><td>${t.reason?.slice(0, 40)}</td></tr>`
    ).join("");
    const m = r.metrics || {};
    el.innerHTML = `<div class="honesty-box ok">
      <p><b>${r.label}</b> · ${r.candles} свечей · ${r.trades} сделок (buy ${r.buys} / sell ${r.sells})</p>
      <p>P&L: <span class="${cls}"><b>${fmtPct(r.pnl_pct)}</b></span> · vs hold ${fmtPct(r.vs_hold_pct)} · портфель ${fmtMoney(r.portfolio_value)}</p>
      <p class="muted">${escapeHtml(r.metrics_summary || "")}</p>
      <p class="muted tiny">DD ${m.max_drawdown_pct ?? "—"}% · Sharpe ${m.sharpe ?? "—"} · Sortino ${m.sortino ?? "—"} · Calmar ${m.calmar ?? "—"} · Win ${m.win_rate_pct ?? "—"}%</p>
    </div>
    <table class="data-table"><thead><tr><th>Сторона</th><th>Цена</th><th>Сумма</th><th>Причина</th></tr></thead><tbody>${log || "<tr><td colspan=4>Нет сделок</td></tr>"}</tbody></table>
    <p class="muted" style="margin-top:0.5rem">Та же OHLC-логика что у live бота и Shadow Lab</p>`;
  } catch (e) {
    el.innerHTML = "<p class='muted'>Не удалось запустить бэктест</p>";
  }
}

async function runBacktestCompare() {
  const el = document.getElementById("table-backtest");
  if (!el) return;
  const sym = document.getElementById("backtest-symbol")?.value || activeSymbol;
  el.innerHTML = "<p class='muted'>⏱ Сравнение 5 стратегий на одних свечах...</p>";
  try {
    const res = await apiFetch("/api/backtest/compare", {
      method: "POST",
      body: JSON.stringify({ symbol: sym, limit: 500, strategies: ["dca", "grid", "momentum", "rsi", "scalper"] }),
    });
    const data = await res.json();
    if (data.error) {
      el.innerHTML = `<p class="muted">Ошибка: ${data.error}</p>`;
      return;
    }
    const rows = (data.results || []).map((r, i) => {
      const cls = r.pnl_pct >= 0 ? "up" : "down";
      const win = i === 0 ? " compare-winner" : "";
      const m = r.metrics || {};
      return `<tr class="${win}"><td><b>${r.strategy_type}</b>${i === 0 ? " 🏆" : ""}</td>
        <td class="${cls}">${fmtPct(r.pnl_pct)}</td><td>${fmtPct(r.vs_hold_pct)}</td>
        <td>${m.sharpe ?? "—"}</td><td>${m.sortino ?? "—"}</td><td>${m.max_drawdown_pct ?? "—"}%</td>
        <td>${r.trades}</td><td>${m.win_rate_pct ?? "—"}%</td></tr>`;
    }).join("");
    el.innerHTML = `<div class="honesty-box ok">
      <p><b>${data.label}</b> · ${data.candles} свечей · победитель: <b>${data.winner}</b> (по vs hold)</p>
    </div>
    <table class="data-table"><thead><tr>
      <th>Стратегия</th><th>P&L</th><th>vs hold</th><th>Sharpe</th><th>Sortino</th><th>Max DD</th><th>Сделок</th><th>Win%</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
  } catch (_) {
    el.innerHTML = "<p class='muted'>Не удалось сравнить стратегии</p>";
  }
}

async function renderShadowLeaderboard() {
  const el = document.getElementById("table-shadow");
  if (!el) return;
  el.innerHTML = "<p class='muted'>Загрузка Shadow Lab...</p>";
  try {
    const data = await (await fetch("/api/shadow-lab")).json();
    const rows = data.leaderboard || [];
    if (!rows.length) {
      el.innerHTML = "<p class='muted'>Shadow Lab копит данные...</p>";
      return;
    }
    el.innerHTML = `<table class="data-table"><thead><tr>
      <th>#</th><th>Рынок</th><th>Клон</th><th>vs hold</th><th>P&L</th><th>Сделок</th><th></th>
    </tr></thead><tbody>${rows.map((r, i) => `<tr>
      <td>${i + 1}</td><td><b>${r.label}</b></td><td>#${r.clone_id}</td>
      <td class="${r.vs_hold_pct >= 0 ? "up" : "down"}">${fmtPct(r.vs_hold_pct)}</td>
      <td>${fmtPct(r.pnl_pct)}</td><td>${r.trades}</td>
      <td><button class="shadow-apply-btn" data-sym="${r.symbol}" data-clone="${r.clone_id}">Применить</button></td>
    </tr>`).join("")}</tbody></table>`;
    el.querySelectorAll(".shadow-apply-btn").forEach(btn => {
      btn.onclick = async () => {
        const res = await apiFetch("/api/shadow-lab/apply", {
          method: "POST",
          body: JSON.stringify({ symbol: btn.dataset.sym, clone_id: Number(btn.dataset.clone) }),
        });
        const d = await res.json();
        if (d.error) showToast("⚠ " + d.error);
        else {
          showToast(`🔬 ${d.label}: клон #${d.clone_id} применён (vs hold ${fmtPct(d.vs_hold_pct)})`);
          await refreshStatus();
        }
      };
    });
  } catch (_) {
    el.innerHTML = "<p class='muted'>Shadow Lab недоступен</p>";
  }
}

async function loadAlerts() {
  try {
    const data = await (await fetch("/api/alerts")).json();
    const scroll = document.getElementById("alerts-scroll");
    if (!scroll) return;
    const items = data.alerts || [];
    if (!items.length) {
      scroll.innerHTML = "<span>Всё спокойно — агенты на связи</span>";
    } else {
      scroll.innerHTML = items.map(a => {
        const cls = a.level === "warn" ? "alert-warn" : a.level === "good" ? "alert-good" : a.level === "halt" ? "alert-halt" : "";
        return `<span class="${cls}">${escapeHtml(a.text)}</span>`;
      }).join("");
    }
    const vh = document.getElementById("vs-hold");
    const bm = data.benchmark;
    if (vh && bm) {
      vh.textContent = fmtPct(bm.vs_hold_pct);
      vh.className = "value " + (bm.vs_hold_pct >= 0 ? "positive" : "negative");
    }
  } catch (_) {}
}

async function applyStrategy() {
  const sel = document.getElementById("strategy-select");
  const stype = sel?.value;
  if (!stype) return;
  const res = await apiFetch("/api/strategy/switch", {
    method: "POST",
    body: JSON.stringify({ symbol: activeSymbol, strategy_type: stype }),
  });
  const data = await res.json();
  if (data.error) showToast("⚠ " + data.error);
  else {
    showToast(`🔄 ${labelFor(activeSymbol)} → стратегия ${stype}`);
    await refreshStatus();
  }
}

function renderAllTables(data) {
  renderMarketsTable(data?.markets_table);
  renderAnalyticsTable(data?.analytics || lastAnalytics);
  renderLearningTable(data?.learning, data?.strategy_history, data?.learning_honesty);
  renderDepositsTable(data?.deposits || []);
  renderHonestyTable(data?.learning_honesty);
}

async function syncAllMarkets() {
  try {
    const res = await apiFetch("/api/sync-markets", { method: "POST" });
    if (res.status === 401) {
      showToast("🔐 Нужен API-токен внизу страницы для sync-markets");
      return;
    }
    const data = await res.json();
    if (data.market_meta) applyMarketMeta(data.market_meta);
    if (data.markets) {
      for (const [sym, payload] of Object.entries(data.markets)) {
        mergeMarket(sym, payload);
      }
    }
    if (data.total) updateTotal(data.total);
    renderTabs();
    switchMarket(activeSymbol);
    const boot = await (await fetch("/api/bootstrap")).json();
    renderAllTables(boot);
    showToast(`✅ Рынков: ${data.markets_active} · добавлено: ${(data.added || []).join(", ") || "0"}`);
    document.getElementById("version-banner")?.classList.add("hidden");
  } catch (e) {
    showToast("Ошибка синхронизации рынков");
  }
}

function showVersionBanner(ping) {
  const el = document.getElementById("version-banner");
  if (!el || !ping) return;
  const expected = ping.markets_count || 17;
  const active = ping.sessions_active || Object.keys(marketsData).length;
  if (active < expected || marketMeta.length < expected) {
    el.classList.remove("hidden");
    el.innerHTML = `⚠️ Видно ${active} из ${expected} монет (сервер v${ping.version}). 
      <button type="button" id="btn-sync-markets" class="btn small">Подключить все ${expected}</button>
      · или git pull → python main.py → Ctrl+Shift+R`;
    document.getElementById("btn-sync-markets")?.addEventListener("click", syncAllMarkets);
  } else {
    el.classList.add("hidden");
  }
}

async function fetchWithTimeout(url, ms = 15000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function waitForServer(maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const res = await fetchWithTimeout("/api/ready", 3000);
      if (res.ok) {
        const ready = await res.json();
        if (ready.running) {
          return await (await fetchWithTimeout("/api/ping", 5000)).json();
        }
      }
    } catch (_) {}
    const banner = document.getElementById("version-banner");
    if (banner) {
      banner.classList.remove("hidden");
      banner.textContent = `⏳ Сервер стартует… (${i + 1}/${maxAttempts}) — дождись "HTTP ready" в терминале`;
    }
    await new Promise(r => setTimeout(r, 1000));
  }
  return null;
}

function applyServerVersion(v) {
  if (!v) return;
  const badge = document.getElementById("app-version-badge");
  if (badge) badge.textContent = `v${v}`;
  const foot = document.getElementById("app-version-footer");
  if (foot) foot.textContent = `TradeSim v${v}`;
  if (document.title.includes("TradeSim")) {
    document.title = document.title.replace(/v\d+/, `v${v}`);
  }
}

async function checkServerAndSync() {
  try {
    const ping = await waitForServer();
    if (!ping) {
      showError("Сервер не отвечает. Останови старый python (Ctrl+C) и запусти: python main.py");
      return null;
    }
    applyServerVersion(ping.version);
    if (ping.auth_required && !localStorage.getItem("tradesim_token")) {
      showToast("🔐 Для кнопок торговли нужен API-токен — введи внизу (данные грузятся без него)");
    }
    if (ping.market_meta?.length) applyMarketMeta(ping.market_meta);
    seedMarketsFromMeta();
    if (ping.total) updateTotal(ping.total);
    const expectedVer = ping.version;
    if (ping.version && ping.ui_cache_version && ping.ui_cache_version !== expectedVer) {
      const msg = `UI кэш v${ping.ui_cache_version}, сервер v${expectedVer} — Ctrl+Shift+R`;
      showToast("⚠️ " + msg, 12000);
    } else if (ping.version && ping.version < 44) {
      showToast(`⚠️ Старый сервер v${ping.version} — git pull и перезапуск`, 12000);
    }
    return ping;
  } catch (_) {
    return null;
  }
}

function seedMarketsFromMeta() {
  for (const m of marketMeta) {
    if (!marketsData[m.symbol]) {
      marketsData[m.symbol] = {
        symbol: m.symbol,
        label: m.label,
        volatile: m.volatile,
        growth: m.growth,
        viral: m.viral,
        price: 0,
        portfolio: {},
      };
    }
  }
}

function initChart() {
  const fallback = document.getElementById("chart-fallback");
  if (typeof LightweightCharts === "undefined") {
    if (fallback) fallback.textContent = "График не загрузился — Ctrl+F5";
    return false;
  }
  const el = document.getElementById("chart");
  if (!el) return false;
  if (fallback) fallback.style.display = "none";
  const w = el.clientWidth || document.getElementById("chart-wrap")?.clientWidth || 600;
  chart = LightweightCharts.createChart(el, {
    layout: { background: { color: "#080e18" }, textColor: "#a8b8d0" },
    grid: { vertLines: { color: "#1a2438" }, horzLines: { color: "#1a2438" } },
    timeScale: { timeVisible: true, secondsVisible: false },
    rightPriceScale: { borderColor: "rgba(0,229,192,0.15)" },
    width: w,
    height: 480,
  });
  candleSeries = chart.addCandlestickSeries({
    upColor: "#00f0b8",
    downColor: "#ff6b8a",
    borderUpColor: "#00f0b8",
    borderDownColor: "#ff6b8a",
    borderVisible: true,
    wickUpColor: "#00f0b8",
    wickDownColor: "#ff6b8a",
  });
  smaSeries = chart.addLineSeries({ color: "#ffb020", lineWidth: 2 });
  window.addEventListener("resize", () => {
    if (chart && el) chart.applyOptions({ width: el.clientWidth || w });
  });
  return true;
}

function initEquityChart() {
  const el = document.getElementById("equity-chart");
  if (!el || typeof LightweightCharts === "undefined") return false;
  equityChart = LightweightCharts.createChart(el, {
    layout: { background: { color: "transparent" }, textColor: "#8b9cb8" },
    grid: { vertLines: { visible: false }, horzLines: { color: "#141c2e" } },
    timeScale: { timeVisible: true, secondsVisible: false },
    rightPriceScale: { borderVisible: false },
    width: el.clientWidth || 400,
    height: 120,
  });
  equitySeries = equityChart.addAreaSeries({
    lineColor: "#63b3ff",
    topColor: "rgba(99, 179, 255, 0.28)",
    bottomColor: "rgba(99, 179, 255, 0.02)",
    lineWidth: 2,
    title: "Paper",
  });
  holdEquitySeries = equityChart.addLineSeries({
    color: "#b794f6",
    lineWidth: 2,
    lineStyle: 2,
    title: "Hold",
  });
  window.addEventListener("resize", () => {
    if (equityChart && el) equityChart.applyOptions({ width: el.clientWidth || 400 });
  });
  return true;
}

function renderEquityCurve(points) {
  if (!equitySeries || !points?.length) return;
  const data = points.map(p => ({ time: p.time, value: p.value }));
  equitySeries.setData(data);
  if (holdEquitySeries) {
    const holdData = points
      .filter(p => p.hold_value != null)
      .map(p => ({ time: p.time, value: p.hold_value }));
    if (holdData.length) holdEquitySeries.setData(holdData);
  }
  const last = points[points.length - 1];
  const lbl = document.getElementById("equity-label");
  if (lbl && last) {
    const hold = last.hold_value ? ` · hold ${fmtMoney(last.hold_value)}` : "";
    lbl.textContent = `48ч · ${fmtMoney(last.value)} (${fmtPct(last.pnl_pct ?? 0)})${hold}`;
  }
}

async function renderHeatmap() {
  const bar = document.getElementById("heatmap-bar");
  if (!bar) return;
  try {
    const data = await (await fetch("/api/portfolio/heatmap")).json();
    bar.innerHTML = (data.cells || []).map(c => {
      const cls = c.pnl_pct >= 0 ? "hm-up" : "hm-down";
      const stale = c.price_stale_sec > 30 ? " hm-stale" : "";
      return `<button type="button" class="hm-cell ${cls}${stale}" data-sym="${c.symbol}" title="${c.label}: P&L ${fmtPct(c.pnl_pct)} · vs hold ${fmtPct(c.vs_hold_pct)} · ${c.strategy_type}">
        <b>${c.label}</b><small>${fmtPct(c.pnl_pct)}</small>
      </button>`;
    }).join("");
    bar.querySelectorAll(".hm-cell").forEach(cell => {
      cell.onclick = () => switchMarket(cell.dataset.sym);
    });
  } catch (_) {}
}

async function renderStrategyReport() {
  const el = document.getElementById("table-strategies");
  if (!el) return;
  el.innerHTML = "<p class='muted'>Считаю рейтинг стратегий...</p>";
  try {
    const [r, outcomes, alloc] = await Promise.all([
      fetch("/api/strategy-report").then(res => res.json()),
      fetch("/api/strategy-outcomes?limit=12").then(res => res.json()),
      fetch("/api/capital-allocation").then(res => res.json()),
    ]);
    const risk = r.risk_gate || {};
    const corr = r.correlation_risk || {};
    const riskLine = risk.blocks_buys
      ? `<p class="warn">⚠️ Покупки заблокированы: ${escapeHtml(risk.reason || "риск")}</p>`
      : `<p class="muted">✅ Покупки разрешены · beating hold ${r.markets_beating_hold}/${r.markets_total}</p>`;
    const stratRows = (r.by_strategy || []).map(s =>
      `<tr><td><b>${s.strategy_type}</b></td><td>${s.markets}</td><td>${fmtPct(s.avg_vs_hold_pct)}</td><td>${fmtPct(s.avg_pnl_pct)}</td><td>${s.beating_hold}/${s.markets}</td><td>${s.win_rate_pct}%</td></tr>`
    ).join("");
    const mktRows = (r.markets || []).map(m =>
      `<tr data-sym="${m.symbol}"><td><b>${m.label}</b></td><td>${m.strategy_type}</td><td class="${m.vs_hold_pct >= 0 ? "up" : "down"}">${fmtPct(m.vs_hold_pct)}</td><td>${fmtPct(m.pnl_pct)}</td><td>${m.trade_count}</td><td>${m.win_rate_pct}%</td></tr>`
    ).join("");
    const outcomeRows = (outcomes.history || []).slice(0, 10).map(h => {
      const ev = h.evaluated ? fmtPct(h.outcome_pp || 0) : "…";
      const cls = h.evaluated && (h.outcome_pp || 0) >= 0 ? "up" : "down";
      return `<tr><td>${h.label || h.symbol}</td><td>${h.old_type}→${h.new_type}</td><td>${fmtPct(h.vs_hold_at || 0)}</td><td class="${cls}">${ev}</td></tr>`;
    }).join("");
    const allocRows = (alloc.markets || []).filter(m => m.multiplier !== 1).slice(0, 8).map(m =>
      `<li>${m.label}: ×${m.multiplier} (${m.strategy_type}, buy $${m.buy_amount})</li>`
    ).join("");
    el.innerHTML = `${riskLine}
      ${corr.bearish_markets ? `<p class="muted">🔗 Корреляция: падают ${corr.bearish_markets} рынков · sync-пар ${corr.sync_pairs || 0}</p>` : ""}
      <h4>🏆 По типу стратегии (avg vs hold)</h4>
      <table class="data-table"><thead><tr><th>Стратегия</th><th>Монет</th><th>vs hold</th><th>P&L</th><th>Beat hold</th><th>Win%</th></tr></thead>
      <tbody>${stratRows || "<tr><td colspan=6>—</td></tr>"}</tbody></table>
      <h4>📊 Все рынки</h4>
      <table class="data-table"><thead><tr><th>Монета</th><th>Стратегия</th><th>vs hold</th><th>P&L</th><th>Сделки</th><th>Win%</th></tr></thead>
      <tbody>${mktRows || "<tr><td colspan=6>—</td></tr>"}</tbody></table>
      <h4>🔄 Исходы смен стратегий ${outcomes.win_rate_pct != null ? `(win ${outcomes.win_rate_pct}%)` : ""}</h4>
      <table class="data-table compact"><thead><tr><th>Монета</th><th>Смена</th><th>vs hold до</th><th>Δ после</th></tr></thead>
      <tbody>${outcomeRows || "<tr><td colspan=4>Ещё нет смен</td></tr>"}</tbody></table>
      ${allocRows ? `<h4>⚖️ Аллокатор</h4><ul>${allocRows}</ul>` : ""}`;
    el.querySelectorAll("tr[data-sym]").forEach(row => {
      row.style.cursor = "pointer";
      row.onclick = () => switchMarket(row.dataset.sym);
    });
  } catch (_) {
    el.innerHTML = "<p class='muted'>Не удалось загрузить отчёт стратегий</p>";
  }
}

async function renderDailyReport() {
  const el = document.getElementById("table-report");
  if (!el) return;
  el.innerHTML = "<p class='muted'>Формирую отчёт...</p>";
  try {
    const r = await (await fetch("/api/daily-report")).json();
    const gainers = (r.top_gainers || []).map(g => `<li>${g.label}: ${fmtPct(g.pnl_pct)} (vs hold ${fmtPct(g.vs_hold_pct)})</li>`).join("");
    const losers = (r.top_losers || []).map(g => `<li>${g.label}: ${fmtPct(g.pnl_pct)}</li>`).join("");
    const brain = (r.brain_decisions || []).map(b =>
      `<tr><td>${new Date(b.ts * 1000).toLocaleTimeString("ru-RU")}</td><td>${b.decision}</td><td>${(b.verdict || "").slice(0, 60)}</td></tr>`
    ).join("");
    const strat = (r.strategy_leaderboard || []).map(s =>
      `<li>${s.strategy_type}: avg vs hold ${fmtPct(s.avg_vs_hold_pct)} (${s.beating_hold}/${s.markets} монет)</li>`
    ).join("");
    const corr = r.correlation_risk || {};
    const corrLine = corr.block_buys ? `<p class="warn">🔗 ${escapeHtml(corr.reason || "корреляционный риск")}</p>` : "";
    el.innerHTML = `<div class="honesty-box ok">
      <p><b>Отчёт 24ч</b> · v${r.version} · сделок: ${r.trades_count} · fees: $${Number(r.fees_24h || 0).toFixed(2)}</p>
      <p>Портфель: ${fmtMoney(r.total?.total_value)} (${fmtPct(r.total?.pnl_pct)}) · Alpha vs hold: ${fmtPct(r.benchmark?.vs_hold_pct)}</p>
      ${corrLine}
    </div>
    <h4>🏆 Стратегии (avg vs hold)</h4><ul>${strat || "<li>—</li>"}</ul>
    <div class="report-cols"><div><h4>🏆 Лидеры</h4><ul>${gainers || "<li>—</li>"}</ul></div>
    <div><h4>📉 Отстающие</h4><ul>${losers || "<li>—</li>"}</ul></div></div>
    <table class="data-table"><thead><tr><th>Время</th><th>Решение</th><th>Вердикт</th></tr></thead><tbody>${brain || "<tr><td colspan=3>—</td></tr>"}</tbody></table>`;
  } catch (_) {
    el.innerHTML = "<p class='muted'>Не удалось загрузить отчёт</p>";
  }
}

async function renderBrainTimeline() {
  const el = document.getElementById("table-brain-timeline");
  if (!el) return;
  try {
    const data = await (await fetch("/api/brain/timeline?limit=30")).json();
    const rows = (data.history || []).map(h => {
      const d = new Date(h.ts * 1000).toLocaleString("ru-RU");
      return `<tr><td>${d}</td><td><b>${h.decision}</b></td><td>${escapeHtml((h.verdict || "").slice(0, 100))}</td></tr>`;
    }).join("");
    el.innerHTML = `<table class="data-table"><thead><tr><th>Время</th><th>Решение</th><th>Вердикт мозга</th></tr></thead><tbody>${rows || "<tr><td colspan=3>Мозг ещё не думал</td></tr>"}</tbody></table>`;
  } catch (_) {
    el.innerHTML = "<p class='muted'>История мозга недоступна</p>";
  }
}

function renderAgentChatroom(data) {
  const sidebar = document.getElementById("agent-chatroom-body");
  const table = document.getElementById("table-agent-chatroom");
  const target = table && !table.classList.contains("hidden") ? table : sidebar;
  if (!target) return;
  if (!data?.messages?.length) {
    target.innerHTML = "<p class='muted'>Агенты ещё не обсуждали рынок — подожди цикл мозга (~45с)</p>";
    return;
  }
  window.lastChatroom = data;
  const bubbles = data.messages.map(m => {
    const cls = m.role === "brain" ? "chatroom-brain" : "chatroom-agent";
    const rec = m.recommendation ? `<span class="muted tiny"> → ${escapeHtml(m.recommendation)}</span>` : "";
    const conf = m.role === "agent" && m.confidence != null ? `<span class="muted tiny"> (${m.confidence})</span>` : "";
    return `<div class="chatroom-msg ${cls}">
      <div class="chatroom-head">${m.emoji || "🤖"} <b>${escapeHtml(m.name || "")}</b>${conf}</div>
      <div class="chatroom-text">${escapeHtml(m.text || m.action || "—")}${rec}</div>
    </div>`;
  }).join("");
  const html = `
    <div class="honesty-box ${data.decision === "emergency_halt" ? "bad" : data.decision === "continue" ? "ok" : "warn"}">
      <p><b>🧠 Решение: ${escapeHtml(data.decision || "—")}</b></p>
      <p class="muted">${escapeHtml(data.verdict || "")}</p>
    </div>
    <div class="chatroom-feed">${bubbles}</div>`;
  if (sidebar) sidebar.innerHTML = html;
  if (table && !table.classList.contains("hidden")) table.innerHTML = html;
}

async function loadAgentChatroom() {
  try {
    const data = await (await fetch("/api/brain/chatroom")).json();
    renderAgentChatroom(data);
    return data;
  } catch (_) {
    const el = document.getElementById("agent-chatroom-body");
    if (el) el.innerHTML = "<p class='muted'>Chatroom недоступен</p>";
    return null;
  }
}

function buildOrderPayload(side, amountUsd) {
  const orderType = document.getElementById("order-type-select")?.value || "market";
  const payload = { symbol: activeSymbol, side, amount_usd: amountUsd, order_type: orderType };
  const limitPrice = parseFloat(document.getElementById("limit-price-input")?.value || "0");
  const stopPrice = parseFloat(document.getElementById("stop-price-input")?.value || "0");
  if (orderType === "limit" || orderType === "stop_limit") {
    if (!limitPrice) return null;
    payload.limit_price = limitPrice;
  }
  if (orderType === "stop_limit") {
    if (!stopPrice) return null;
    payload.stop_price = stopPrice;
  }
  return payload;
}

async function loadOpenOrders(showModal = true) {
  const body = document.getElementById("orders-modal-body");
  const modal = document.getElementById("orders-modal");
  if (showModal && body) body.innerHTML = "<p class='muted'>Загрузка...</p>";
  if (showModal && modal) modal.classList.remove("hidden");
  try {
    const data = await (await fetch(`/api/orders/open?symbol=${activeSymbol}`)).json();
    const rows = [...(data.paper || []), ...(data.exchange || [])];
    window.lastOpenOrders = data;
    if (!rows.length) {
      if (body) body.innerHTML = "<p class='orders-empty'>Нет открытых ордеров на " + escapeHtml(labelFor(activeSymbol)) + "</p>";
      if (!showModal) showToast("📋 Нет открытых ордеров");
      return data;
    }
    const tableRows = rows.map(o => {
      const canCancel = o.source === "paper" || o.source === "exchange";
      const oid = o.id || o.order_id || "";
      return `<tr>
        <td>${o.source === "paper" ? "📄" : "🏦"}</td>
        <td><b>${escapeHtml(o.side || "")}</b></td>
        <td>${escapeHtml(o.order_type || "limit")}</td>
        <td>${fmtMoney(o.limit_price || 0)}</td>
        <td>${o.stop_price ? fmtMoney(o.stop_price) : "—"}</td>
        <td>$${Number(o.amount_usd || 0).toFixed(0)}</td>
        <td>${canCancel && oid ? `<button type="button" class="btn ghost small btn-cancel-order" data-id="${escapeHtml(String(oid))}" data-source="${o.source}" data-symbol="${escapeHtml(o.symbol || activeSymbol)}">✕</button>` : ""}</td>
      </tr>`;
    }).join("");
    if (body) {
      body.innerHTML = `<table class="orders-table"><thead><tr>
        <th></th><th>Сторона</th><th>Тип</th><th>Limit</th><th>Stop</th><th>$</th><th></th>
      </tr></thead><tbody>${tableRows}</tbody></table>
      <p class="muted tiny" style="margin-top:0.5rem">Всего: ${rows.length} · ${labelFor(activeSymbol)}</p>`;
      body.querySelectorAll(".btn-cancel-order").forEach(btn => {
        btn.onclick = async () => {
          const res = await apiFetch("/api/orders/cancel", {
            method: "POST",
            body: JSON.stringify({
              symbol: btn.dataset.symbol,
              order_id: btn.dataset.id,
              source: btn.dataset.source,
            }),
          });
          const r = await res.json();
          if (r.error || r.ok === false) showToast("⚠ " + (r.error || "отмена не удалась"));
          else {
            showToast("✕ Ордер отменён");
            loadOpenOrders(true);
          }
        };
      });
    }
    if (!showModal) showToast(`📋 ${rows.length} открытых ордер(ов)`);
    return data;
  } catch (_) {
    if (body) body.innerHTML = "<p class='orders-empty'>Не удалось загрузить ордера</p>";
    if (!showModal) showToast("Не удалось загрузить ордера");
    return null;
  }
}

function applyTheme(theme) {
  const t = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem("tradesim_theme", t);
  const btn = document.getElementById("btn-theme-toggle");
  if (btn) btn.textContent = t === "light" ? "☀️" : "🌙";
}

function initTheme() {
  const saved = localStorage.getItem("tradesim_theme") || "dark";
  applyTheme(saved);
  document.getElementById("btn-theme-toggle")?.addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || "dark";
    applyTheme(cur === "light" ? "dark" : "light");
  });
}

async function loadFees() {
  try {
    const f = await (await fetch("/api/fees?hours=168")).json();
    const el = document.getElementById("total-fees");
    if (el) el.textContent = "$" + Number(f.total_fees || 0).toFixed(2);
  } catch (_) {}
}

function renderShadowLab(data) {
  if (!data) return;
  lastShadowLab = data;
  const sum = document.getElementById("shadow-lab-summary");
  if (sum) {
    sum.textContent = `${data.total_clones || 0} mock-ботов · ${data.total_shadow_trades || 0} теневых сделок`;
  }
  const grid = document.getElementById("shadow-lab-grid");
  if (grid && data.markets?.length) {
    grid.innerHTML = data.markets.map(m => {
      const beat = m.best_vs_hold >= m.live_vs_hold ? "↑" : "·";
      return `<div class="shadow-cell">
        <b>${m.label} ×${m.clones}</b>
        <div class="sc-row"><span>Лучший клон #${m.best_clone}</span><span class="sc-val">${fmtPct(m.best_vs_hold)}</span></div>
        <div class="sc-row"><span>Живой бот ${beat}</span><span>${fmtPct(m.live_vs_hold)}</span></div>
        <div class="sc-row"><span>Теневых сделок</span><span>${m.shadow_trades}</span></div>
      </div>`;
    }).join("");
  }
  const prom = document.getElementById("shadow-promotions");
  if (prom) {
    const items = data.promotions || [];
    prom.innerHTML = items.length
      ? items.map(p => `<li>🔬 ${p.label} клон #${p.clone_id}: vs hold ${fmtPct(p.vs_hold_pct)} → ${(p.changes || []).join(", ")}</li>`).join("")
      : "<li>Пока нет переносов — лаборатория копит данные…</li>";
  }
}

async function loadShadowLab() {
  try {
    const data = await (await fetch("/api/shadow-lab")).json();
    if (data.enabled !== false) renderShadowLab(data);
  } catch (_) {}
}

function renderLearningPanel(learning, brainHistory, analytics) {
  const el = document.getElementById("learning-panel");
  if (!el) return;
  if (!learning && !analytics) {
    el.textContent = "Статистика появится после первых сделок.";
    return;
  }
  const pm = learning?.per_market || {};
  const markets = Object.entries(pm).map(([s, c]) => `${labelFor(s)}:${c}`).join(" · ") || "—";
  let tune = "";
  if (learning?.strategy_versions?.length) {
    const t = learning.strategy_versions[0];
    tune = `<div class="lp-tune">🔧 [${t.symbol?.replace("USDT", "") || "?"}] ${(t.reason || "").slice(0, 70)}…</div>`;
  }
  let bh = "";
  if (brainHistory?.length) {
    bh = `<ul class="brain-history">${brainHistory.slice(-4).map(h =>
      `<li>${new Date(h.ts * 1000).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })} · ${h.decision}: ${(h.verdict || "").slice(0, 45)}</li>`
    ).join("")}</ul>`;
  }
  const a = analytics || lastAnalytics;
  let metrics = "";
  if (a) {
    metrics = `
      <div class="lp-row"><span class="lp-label">Max drawdown</span><span class="lp-val">${a.max_drawdown_pct ?? 0}%</span></div>
      <div class="lp-row"><span class="lp-label">Опережают hold</span><span class="lp-val">${a.markets_beating_hold ?? 0}/${a.markets_total ?? 17}</span></div>
      <div class="lp-row"><span class="lp-label">Среднее vs hold</span><span class="lp-val">${fmtPct(a.avg_vs_hold_pct)}</span></div>
      ${a.sharpe_proxy != null ? `<div class="lp-row"><span class="lp-label">Sharpe (proxy)</span><span class="lp-val">${a.sharpe_proxy}</span></div>` : ""}
    `;
  }
  el.innerHTML = `
    <div class="lp-row"><span class="lp-label">Сделок в БД</span><span class="lp-val">${learning?.trade_count || a?.total_trades || 0}</span></div>
    <div class="lp-row"><span class="lp-label">Продаж / TP / SL</span><span class="lp-val">${a?.total_sells ?? "—"}</span></div>
    <div class="lp-row"><span class="lp-label">Мозг · 15 агентов</span><span class="lp-val">каждые 45 сек</span></div>
    <div class="lp-row"><span class="lp-label">По рынкам</span><span class="lp-val">${markets}</span></div>
    ${metrics}
    ${tune}${bh}
  `;
  renderActivityFeed();
}

function pushActivity(text) {
  activityLog.unshift({ ts: Date.now(), text });
  activityLog = activityLog.slice(0, 12);
  renderActivityFeed();
}

function renderActivityFeed() {
  const el = document.getElementById("activity-feed");
  if (!el) return;
  if (!activityLog.length) {
    el.innerHTML = "<li>Лента: сделки, автонастройки, решения мозга…</li>";
    return;
  }
  el.innerHTML = activityLog.map(a =>
    `<li>${new Date(a.ts).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })} · ${escapeHtml(a.text)}</li>`
  ).join("");
}

function updateSmaLegend(period) {
  const el = document.getElementById("sma-legend");
  if (el) el.textContent = `SMA-${period}`;
}

function updateSMA(candles, period = 20) {
  if (!smaSeries || !candles?.length || period < 2) return;
  updateSmaLegend(period);
  const smaData = [];
  for (let i = period - 1; i < candles.length; i++) {
    const slice = candles.slice(i - period + 1, i + 1);
    smaData.push({ time: candles[i].time, value: slice.reduce((s, c) => s + c.close, 0) / period });
  }
  smaSeries.setData(smaData);
}

function setLiveStatus(mode) {
  const el = document.getElementById("live-status");
  if (!el) return;
  if (mode === "live") {
    el.textContent = "● ЦЕНЫ";
    el.title = "Живые котировки (не режим Live с реальными деньгами)";
    el.className = "value live-dot";
  } else if (mode === "demo") {
    el.textContent = "○ DEMO";
    el.className = "value live-dot stale";
  } else if (mode === "stale") {
    el.textContent = "○ STALE";
    el.className = "value live-dot stale";
  } else {
    el.textContent = "○ пауза";
    el.className = "value live-dot stale";
  }
}

function feedLiveMode(source) {
  const src = String(source || "").toLowerCase();
  if (!src) return "live";
  if (src.includes("demo") || src.includes("fallback") || src.includes("coingecko")) return "demo";
  return "live";
}

function renderPortfolioGrid() {
  const grid = document.getElementById("portfolio-grid");
  if (!grid) return;
  grid.innerHTML = marketMeta.map(m => {
    const d = marketsData[m.symbol];
    const pnl = d?.portfolio?.pnl_pct;
    const vs = d?.portfolio?.vs_hold_pct;
    const cls = pnl == null ? "" : (pnl >= 0 ? "up" : "down");
    const active = m.symbol === activeSymbol ? " active" : "";
    const vol = m.volatile ? " volatile" : "";
    const viral = m.viral ? " viral" : "";
    const growth = m.growth ? " growth" : "";
    const badge = m.viral ? " 🔥" : m.growth ? " 📈" : m.volatile ? " ⚡" : "";
    return `<button type="button" class="pf-cell${active}${vol}${viral}${growth}" data-symbol="${m.symbol}">
      <span class="pf-label">${m.label}${badge}</span>
      <span class="pf-pnl ${cls}">${pnl != null ? fmtPct(pnl) : "…"}</span>
      <span class="pf-vs">${vs != null ? "vs hold " + fmtPct(vs) : ""}</span>
    </button>`;
  }).join("");
  grid.querySelectorAll(".pf-cell").forEach(btn => {
    btn.onclick = () => switchMarket(btn.dataset.symbol);
  });
}

function renderTabs() {
  const nav = document.getElementById("market-tabs");
  if (!nav) return;
  nav.innerHTML = marketMeta.map(m => {
    const d = marketsData[m.symbol];
    const price = d?.price != null && !isNaN(d.price) ? fmtMoney(d.price, priceDecimals(m.label)) : "…";
    const vol = m.volatile ? " volatile-tab" : "";
    const viral = m.viral ? " viral-tab" : "";
    const growth = m.growth ? " growth-tab" : "";
    const active = m.symbol === activeSymbol ? " active" : "";
    return `<button type="button" class="tab${active}${vol}${viral}${growth}" data-symbol="${m.symbol}">${m.label}${m.viral ? " 🔥" : m.growth ? " 📈" : ""}<span>${price}</span></button>`;
  }).join("");
  nav.querySelectorAll(".tab").forEach(btn => {
    btn.onclick = () => switchMarket(btn.dataset.symbol);
  });
  renderPortfolioGrid();
}

function formatCandleLag(sec) {
  if (sec == null || sec <= 90) return sec != null && sec <= 90 ? " · свечи актуальны" : "";
  if (sec > 86400) return " · ⚠️ отставание >24ч";
  const hours = Math.floor(sec / 3600);
  const mins = Math.round((sec % 3600) / 60);
  if (hours > 0) return ` · ⚠️ отставание ~${hours}ч ${mins}м`;
  return ` · ⚠️ отставание ~${mins} мин`;
}

function updateChartTitle(symbol) {
  const d = marketsData[symbol];
  const title = document.getElementById("chart-title");
  if (title) {
    let markerNote = "";
    if (lastTradeMarkerStats.shown > 0 || lastTradeMarkerStats.skipped > 0) {
      markerNote = lastTradeMarkerStats.skipped > 0
        ? ` · ▲▼ ${lastTradeMarkerStats.shown} в окне, ${lastTradeMarkerStats.skipped} старше графика`
        : ` · ▲▼ ${lastTradeMarkerStats.shown} сделок`;
    }
    title.textContent = `${d?.label || labelFor(symbol)}/USDT — свечи (${lastCandles.length})${formatCandleLag(marketsData[symbol]?.candle_lag_sec)}${markerNote}`;
  }
}

async function loadCandlesForSymbol(symbol, force = false) {
  try {
    const d = marketsData[symbol];
    const lag = d?.candle_lag_sec ?? 0;
    const refresh = force || lag > 90 || !d?.candles_ready || !(d?.candles?.length >= 40);
    const url = `/api/candles?symbol=${symbol}&limit=500${refresh ? "&refresh=1" : ""}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data.candles?.length) {
      const serverLag = data.candle_lag_sec ?? 0;
      const lastTs = data.candles[data.candles.length - 1]?.time || 0;
      const clientLag = data.server_time ? Math.max(0, data.server_time - lastTs - 60) : serverLag;
      if (marketsData[symbol]) {
        marketsData[symbol].candles = data.candles;
        marketsData[symbol].candle_lag_sec = serverLag;
        marketsData[symbol].candles_ready = data.candles_ready;
        marketsData[symbol].candle_source = data.candle_source;
      }
      if (serverLag > 120 || clientLag > 120) {
        console.warn(`[candles] ${symbol} lag server=${serverLag}s client=${clientLag}s src=${data.candle_source}`);
      }
      return data.candles;
    }
  } catch (e) {
    console.warn("loadCandles", symbol, e);
  }
  return marketsData[symbol]?.candles || [];
}

async function ensureFreshCandles(symbol) {
  for (let attempt = 0; attempt < 8; attempt++) {
    const candles = await loadCandlesForSymbol(symbol, true);
    const lag = marketsData[symbol]?.candle_lag_sec ?? 9999;
    const ready = marketsData[symbol]?.candles_ready !== false;
    if (candles.length >= 30 && lag <= 120 && ready) {
      lastCandles = candles;
      if (candleSeries) {
        candleSeries.setData(candles);
        updateSMA(candles, smaPeriod(symbol));
        if (chart) chart.timeScale().fitContent();
      }
      updateChartTitle(symbol);
      return candles;
    }
    if (attempt < 7) await new Promise(r => setTimeout(r, 1500));
  }
  const fallback = await loadCandlesForSymbol(symbol, true);
  if (fallback.length) {
    lastCandles = fallback;
    if (candleSeries) {
      candleSeries.setData(fallback);
      updateSMA(fallback, smaPeriod(symbol));
    }
    updateChartTitle(symbol);
    showToast("⚠️ Свечи отстают — проверь интернет или перезапусти сервер");
  }
  return lastCandles;
}

async function switchMarket(symbol) {
  activeSymbol = symbol;
  const d = marketsData[symbol];
  if (!d) {
    document.getElementById("bot-status").innerHTML = "<p>Загрузка данных с сервера...</p>";
    return;
  }
  lastCandles = await ensureFreshCandles(symbol);
  const period = smaPeriod(symbol);
  if (candleSeries && lastCandles.length) {
    await refreshTradeMarkers(symbol);
  }
  updateChartTitle(symbol);
  renderBotStatus(d);
  renderTabs();
  loadExchangePanel();
}

function clientChartLagSec() {
  if (!lastCandles.length) return 9999;
  const lastTs = lastCandles[lastCandles.length - 1]?.time || 0;
  return Math.max(0, Math.floor(Date.now() / 1000) - lastTs - 60);
}

async function syncChartIfStale() {
  const lag = clientChartLagSec();
  const serverLag = marketsData[activeSymbol]?.candle_lag_sec ?? 0;
  if (lag > 90 || serverLag > 90) {
    const c = await ensureFreshCandles(activeSymbol);
    if (c?.length && candleSeries) {
      lastCandles = c;
      candleSeries.setData(c);
      updateSMA(c, smaPeriod(activeSymbol));
      updateChartTitle(activeSymbol);
      await refreshTradeMarkers(activeSymbol);
    }
  }
}

function updateLiveCandle(candle) {
  if (!candle || !candleSeries) return;
  if (lastCandles.length && lastCandles[lastCandles.length - 1].time === candle.time) {
    lastCandles[lastCandles.length - 1] = candle;
  } else if (!lastCandles.length || candle.time > lastCandles[lastCandles.length - 1].time) {
    lastCandles.push(candle);
  } else {
    return;
  }
  candleSeries.update(candle);
  updateSMA(lastCandles, smaPeriod(activeSymbol));
  if (marketsData[activeSymbol]) {
    marketsData[activeSymbol].candles = lastCandles;
    marketsData[activeSymbol].candle_lag_sec = clientChartLagSec();
  }
  updateChartTitle(activeSymbol);
  if (clientChartLagSec() > 180) void syncChartIfStale();
}

function showVersionBanner(text, level = "info") {
  const el = document.getElementById("version-banner");
  if (!el || !text) return;
  el.textContent = text;
  el.className = "version-banner " + (level === "warn" ? "warn" : "ok");
  el.classList.remove("hidden");
}

function updateTotal(total) {
  if (!total) return;
  const valueElement = document.getElementById("total-value");
  const pnlElement = document.getElementById("total-pnl");
  if (valueElement) valueElement.textContent = fmtMoney(total.total_value);
  if (pnlElement) {
    pnlElement.textContent = fmtPct(total.pnl_pct);
    pnlElement.className = "value " + (total.pnl_pct >= 0 ? "positive" : "negative");
  }
  const benchmark = total.benchmark || {};
  const vsHoldPct = total.vs_hold_pct ?? benchmark.vs_hold_pct;
  if (vsHoldPct != null) {
    const vsHoldElement = document.getElementById("vs-hold");
    if (vsHoldElement) {
      vsHoldElement.textContent = fmtPct(vsHoldPct);
      vsHoldElement.className = "value " + (vsHoldPct >= 0 ? "positive" : "negative");
      const misleading = total.benchmark_misleading || benchmark.benchmark_misleading;
      const note = total.benchmark_note || benchmark.benchmark_note;
      if (misleading && note) {
        vsHoldElement.title = note;
        vsHoldElement.classList.add("warn-metric");
      } else {
        vsHoldElement.title = benchmark.hold_window || "";
        vsHoldElement.classList.remove("warn-metric");
      }
    }
  }
  if (benchmark.benchmark_note) {
    showVersionBanner(benchmark.benchmark_note, benchmark.benchmark_misleading ? "warn" : "info");
  }
}

function strategyParamsHtml(stype, p) {
  const spike = p.spike_threshold_pct
    ? `<p>SPIKE: +$${p.spike_extra_amount} при просадке ≥${p.spike_threshold_pct}%</p>`
    : "";
  const tp = p.take_profit_pct
    ? `<p>TAKE-PROFIT: ${Math.round((p.take_profit_fraction || 0.15) * 100)}% позиции при +${p.take_profit_pct}% над SMA</p>`
    : "";
  const sl = p.stop_loss_pct
    ? `<p>STOP-LOSS: −${p.stop_loss_pct}% от входа → продажа ${Math.round((p.stop_loss_fraction || 0.2) * 100)}%</p>`
    : "";
  switch (stype) {
    case "grid":
      return `<p>Grid: шаг ${p.grid_spacing_pct ?? 2.5}% · buy $${p.grid_buy_amount ?? 22} · sell ${Math.round((p.grid_sell_fraction ?? 0.18) * 100)}% (кд ${p.grid_cooldown_minutes ?? 12}м)</p>${tp}${sl}`;
    case "momentum":
      return `<p>Momentum: breakout +${p.breakout_pct ?? 1.8}% · trail −${p.trailing_stop_pct ?? 4.5}% · buy $${p.momentum_buy_amount ?? 38}</p>${sl}`;
    case "rsi":
      return `<p>RSI(${p.rsi_period ?? 14}): buy &lt;${p.rsi_oversold ?? 30} · sell &gt;${p.rsi_overbought ?? 70} · $${p.rsi_buy_amount ?? 28}</p>${tp}${sl}`;
    case "scalper":
      return `<p>Scalper: move ${p.scalp_move_pct ?? 0.55}% · TP ${p.scalp_tp_pct ?? 0.45}% · $${p.scalp_buy_amount ?? 16} (кд ${p.scalp_cooldown_seconds ?? 90}с)</p>${tp}${sl}`;
    default:
      return `<p>DCA: $${p.dca_amount ?? 25} / ${p.dca_interval_hours ?? 24}ч · DIP ${p.dip_threshold_pct ?? 3}% (кд ${p.dip_cooldown_minutes ?? 30}м)</p>${spike}${tp}${sl}`;
  }
}

function renderAutoTacticsPanel(data) {
  const el = document.getElementById("auto-tactics-panel");
  if (!el) return;
  if (!data) {
    el.innerHTML = "<p class='muted'>Авто-тактики выключены</p>";
    return;
  }
  window.lastAutoTactics = data;
  const badge = document.getElementById("auto-tactics-badge");
  if (badge) {
    const on = data.enabled || data.trader_copy;
    badge.style.opacity = on ? "1" : "0.35";
    badge.title = on
      ? `Авто-тактики: ${data.total_switches || 0} переключений · копирование трейдеров`
      : "Авто выключено";
  }
  const switches = data.markets?.filter(m => m.last_auto) || [];
  const switchLines = switches.slice(0, 5).map(m => {
    const la = m.last_auto;
    const icon = la.source === "trader" ? "👁️" : "🤖";
    return `<li><b>${m.label}</b> · ${m.strategy_type} · ${icon} ${(la.reason || "").slice(0, 60)}</li>`;
  }).join("") || "<li class='muted'>Пока без авто-переключений</li>";
  const plays = (data.trader_plays || []).slice(0, 4).map(p =>
    `<li><b>${p.trader || "?"}</b> → ${p.label || "?"}: ${(p.reason || "").slice(0, 55)}</li>`
  ).join("") || "<li class='muted'>Следопыт ищет идеи трейдеров…</li>";
  el.innerHTML = `
    <p>${data.enabled ? "✅" : "⏸"} Авто-стратегии · ${data.trader_copy ? "✅" : "⏸"} Копирование · <b>${data.total_switches || 0}</b> switch</p>
    <p class="muted">Последние авто-решения:</p>
    <ul class="auto-tactics-list">${switchLines}</ul>
    <p class="muted">Идеи трейдеров:</p>
    <ul class="auto-tactics-list">${plays}</ul>`;
}

function renderProfitFocusPanel(data) {
  const el = document.getElementById("profit-focus-panel");
  if (!el) return;
  if (!data) {
    el.innerHTML = "<p class='muted'>Profit Focus выключен</p>";
    return;
  }
  window.lastProfitFocus = data;
  const paused = (data.paused || []).map(p =>
    `<li><b>${p.label || p.symbol}</b> · ${escapeHtml(p.reason || "пауза")}</li>`
  ).join("") || "<li class='muted'>Нет пауз — все боты активны</li>";
  const leaders = (data.leaders || []).slice(0, 4).map(l =>
    `<li><b>${l.label}</b> · vs hold <span class="up">${fmtPct(l.vs_hold_pct)}</span>${l.bot_enabled ? "" : " ⏸"}</li>`
  ).join("") || "<li class='muted'>Лидеры появятся после сделок</li>";
  const laggards = (data.laggards || []).slice(0, 4).map(l =>
    `<li><b>${l.label}</b> · vs hold <span class="down">${fmtPct(l.vs_hold_pct)}</span></li>`
  ).join("") || "<li class='muted'>Отстающих нет</li>";
  const actions = (data.last_actions || []).slice(-4).map(a => {
    const icon = a.action === "pause" ? "⏸" : a.action === "resume" ? "▶️" : "🚀";
    return `<li>${icon} <b>${a.label}</b> · ${escapeHtml(a.reason || a.action)}</li>`;
  }).join("");
  const s = data.settings || {};
  el.innerHTML = `
    <p>${data.enabled ? "✅" : "⏸"} Profit Focus · пауза: <b>${data.paused_count || 0}</b> · порог ${s.pause_vs_hold ?? -2}%</p>
    <p class="muted">🏆 Лидеры (буст + aggressive):</p>
    <ul class="auto-tactics-list">${leaders}</ul>
    <p class="muted">📉 Отстают vs hold:</p>
    <ul class="auto-tactics-list">${laggards}</ul>
    <p class="muted">⏸ На паузе:</p>
    <ul class="auto-tactics-list">${paused}</ul>
    ${actions ? `<p class="muted">Последние действия:</p><ul class="auto-tactics-list">${actions}</ul>` : ""}`;
}

function renderScorecardPanel(data) {
  const el = document.getElementById("scorecard-panel");
  if (!el) return;
  if (!data?.metrics) {
    el.innerHTML = "<p class='muted'>Нет данных оценки</p>";
    return;
  }
  window.lastScorecard = data;
  const overallCls = data.overall_grade || "ok";
  const rows = (data.metrics || []).map(m => {
    const cls = m.grade === "good" ? "up" : m.grade === "bad" ? "down" : m.grade === "warn" ? "warn" : "";
    const star = m.priority ? " ★" : "";
    return `<tr class="${cls}"><td>${escapeHtml(m.label)}${star}</td><td><b>${escapeHtml(m.display)}</b></td><td>${escapeHtml(m.grade_label)}</td></tr>`;
  }).join("");
  const steps = (data.next_steps || []).map(s => `<li>${escapeHtml(s)}</li>`).join("");
  const bench = data.benchmarks || {};
  el.innerHTML = `
    <div class="honesty-box ${overallCls === "good" ? "ok" : overallCls}">
      <p><b>Итого: ${escapeHtml(data.overall_label || "")}</b> — ${escapeHtml(data.summary || "")}</p>
      <p class="muted">Режим: ${escapeHtml(data.trading_mode || "paper")}${data.paper_learn ? " · 📚 Paper Learn" : ""} · $${Number(data.total_value || 0).toLocaleString()}</p>
    </div>
    <table class="data-table scorecard-table">
      <thead><tr><th>Показатель</th><th>Сейчас</th><th>Оценка</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="muted tiny">Ориентиры: сделки ${bench.trades?.ok || "30–100"} · P&L ${bench.pnl?.ok || "−2…+3%"} · vs Hold ${bench.vs_hold?.ok || "0…+2%"} · просадка ${bench.drawdown?.ok || "5–8%"}</p>
    <p class="muted"><b>Дальше:</b></p>
    <ul class="auto-tactics-list">${steps}</ul>`;
}

function renderLivePrepPanel(data) {
  const el = document.getElementById("live-prep-panel");
  if (!el || !data) return;
  window.lastLivePrep = data;
  const phases = (data.phases || []).map(p => {
    const icon = p.done ? "✅" : p.current ? "▶️" : "⬜";
    return `<li class="${p.done ? "up" : p.current ? "warn" : ""}">${icon} <b>${escapeHtml(p.title)}</b>
      <span class="muted"> — ${escapeHtml(p.detail || "")}</span></li>`;
  }).join("");
  const warnings = (data.realism_warnings || []).slice(0, 4).map(w =>
    `<li><b>${escapeHtml(w.title)}</b>: ${escapeHtml(w.text)}</li>`
  ).join("");
  const stab = data.stability || {};
  const env = (data.recommended_env || []).map(l => `<code>${escapeHtml(l)}</code>`).join("<br>");
  el.innerHTML = `
    <div class="honesty-box ${data.readiness?.ready_for_live ? "ok" : "warn"}">
      <p><b>🎯 ${escapeHtml(data.summary || "")}</b></p>
      <p class="muted">Фазы: ${data.phase_progress || "?"} · sync ${stab.success_rate_pct ?? 100}% · биржа ${stab.exchange_orders ?? 0} ордеров</p>
      <p class="muted">${escapeHtml(data.fee_hint || "")}</p>
    </div>
    <p class="muted"><b>Путь (реальный трейдинг ≠ paper):</b></p>
    <ul class="auto-tactics-list">${phases}</ul>
    <p class="muted"><b>Что пойдёт не так на Live:</b></p>
    <ul class="auto-tactics-list">${warnings}</ul>
    <p class="muted"><b>.env для следующего шага:</b></p>
    <div class="muted" style="font-size:0.75rem;line-height:1.4">${env}</div>`;
}

async function loadLivePrep() {
  try {
    const data = await (await fetch("/api/live-prep")).json();
    renderLivePrepPanel(data);
    return data;
  } catch (_) {
    const el = document.getElementById("live-prep-panel");
    if (el) el.innerHTML = "<p class='muted'>Путь к Live: обнови страницу</p>";
    return null;
  }
}

function renderLivePlaybookPanel(data) {
  const el = document.getElementById("live-playbook-panel");
  if (!el || !data) return;
  window.lastLivePlaybook = data;
  const rules = (data.quick_rules || []).map(r => `<li>${escapeHtml(r)}</li>`).join("");
  const active = new Set(data.active_hints || []);
  const renderScenario = s => {
    const cls = [s.severity || "info", s.may_apply || active.has(s.id) ? "active" : ""].filter(Boolean).join(" ");
    const actions = (s.actions || []).map(a => `<code>${escapeHtml(a)}</code>`).join(" · ");
    return `<div class="playbook-scenario ${cls}">
      <p><b>${escapeHtml(s.title)}</b>${s.may_apply ? " <span class='warn'>← сейчас</span>" : ""}</p>
      <p class="muted">${escapeHtml(s.situation || "")}</p>
      <p class="muted"><b>Как узнать:</b> ${escapeHtml(s.detection || "")}</p>
      <p class="plan-a"><b>План А (бот):</b> ${escapeHtml(s.plan_a || "")}</p>
      <p class="plan-b"><b>План Б (ты):</b> ${escapeHtml(s.plan_b || "")}</p>
      ${actions ? `<p class="muted tiny">${actions}</p>` : ""}
    </div>`;
  };
  const marketBlock = (data.market_crises || []).map(renderScenario).join("");
  const otherCats = (data.categories || []).filter(c => c.id !== "market").map(cat => {
    const items = (cat.scenarios || []).map(renderScenario).join("");
    return `<details class="playbook-other-cat"><summary>${escapeHtml(cat.title || "")} (${cat.count || 0})</summary>${items}</details>`;
  }).join("");
  el.innerHTML = `
    <div class="honesty-box warn">
      <p><b>${escapeHtml(data.title || "Рыночные кризисы")}</b></p>
      <p class="muted">${escapeHtml(data.summary || "")}</p>
    </div>
    <ul class="auto-tactics-list">${rules}</ul>
    <p class="muted"><b>🔥 Обвалы, пампы, паника — план А / Б:</b></p>
    ${marketBlock}
    <p class="muted" style="margin-top:0.75rem"><b>Техническое (API, sync, Telegram):</b></p>
    ${otherCats}`;
}

async function loadLivePlaybook() {
  try {
    const data = await (await fetch("/api/live-playbook")).json();
    renderLivePlaybookPanel(data);
    return data;
  } catch (_) {
    const el = document.getElementById("live-playbook-panel");
    if (el) el.innerHTML = "<p class='muted'>Playbook: обнови страницу</p>";
    return null;
  }
}

function renderIntegrationsPanel(data) {
  const el = document.getElementById("integrations-panel-body");
  if (!el) return;
  if (!data) {
    el.innerHTML = "<p class='muted'>Интеграции: нет данных</p>";
    return;
  }
  window.lastIntegrations = data;
  const tg = data.telegram || {};
  const tv = data.tradingview || {};
  const prot = data.protections || {};
  const tgOk = tg.enabled && tg.chat_configured;
  const tvOk = tv.enabled && tv.secret_configured;
  const paused = Object.entries(prot.paused_symbols || {}).map(
    ([sym, min]) => `<li>⏸ ${escapeHtml(sym)} — ${min} мин</li>`
  ).join("");
  const rules = prot.rules || {};
  el.innerHTML = `
    <div class="honesty-box ${tgOk || tvOk ? "ok" : "warn"}">
      <p><b>Telegram:</b> ${tgOk ? "✅ активен" : tg.enabled ? "⚠ нет chat_id" : "выкл"} ·
         <b>TradingView:</b> ${tvOk ? "✅ webhook" : tv.enabled ? "⚠ нет secret" : "выкл"}</p>
      <p class="muted">Protections: ${prot.enabled ? "вкл" : "выкл"}
        ${prot.global_active ? ` · cooldown ${prot.global_cooldown_min} мин` : ""}</p>
    </div>
    <p class="muted"><b>TV endpoint:</b> <code>POST ${escapeHtml(tv.endpoint || "/api/webhook/tradingview")}</code></p>
    <p class="muted tiny">Пример: ${escapeHtml(JSON.stringify(tv.example_payload || {}))}</p>
    <p class="muted"><b>Правила:</b></p>
    <ul class="auto-tactics-list">
      <li>StoplossGuard: ${escapeHtml(rules.stoploss_guard || "—")}</li>
      <li>Cooldown: ${escapeHtml(rules.cooldown_period || "—")}</li>
      <li>Max trades: ${escapeHtml(rules.max_trades_per_day || "—")}</li>
    </ul>
    ${paused ? `<p class="muted"><b>Пауза protections:</b></p><ul class="auto-tactics-list">${paused}</ul>` : ""}`;
}

function renderSmokeTestPanel(data) {
  const el = document.getElementById("smoke-test-panel");
  if (!el) return;
  if (!data) {
    el.innerHTML = "";
    return;
  }
  window.lastSmokeTest = data;
  const cls = data.certified ? "ok" : "warn";
  const rows = (data.checks || []).map(c => {
    const icon = c.ok ? "✅" : c.required === false ? "⚪" : "❌";
    return `<li>${icon} <b>${escapeHtml(c.label)}</b> — <span class="muted">${escapeHtml(c.detail || "")}</span></li>`;
  }).join("");
  el.innerHTML = `
    <div class="honesty-box ${cls}">
      <p><b>${escapeHtml(data.summary || "")}</b></p>
      <p class="muted">Score ${data.score_pct ?? 0}% · ${data.passed ?? 0}/${data.total_required ?? 0} required · ${data.duration_sec ?? 0}s</p>
      <p class="muted"><b>Дальше:</b> ${escapeHtml(data.next_action || "")}</p>
    </div>
    <ul class="auto-tactics-list">${rows}</ul>`;
}

async function runSmokeTest() {
  const el = document.getElementById("smoke-test-panel");
  if (el) el.innerHTML = "<p class='muted'>🧪 Smoke test — проверка системы...</p>";
  try {
    const res = await apiFetch("/api/smoke-test", { method: "POST", body: "{}" });
    const data = await res.json();
    renderSmokeTestPanel(data);
    showToast(data.certified ? "✅ Smoke test пройден" : "⚠ Smoke test — есть проблемы", 6000);
    if (data.live_prep) renderLivePrepPanel(data.live_prep);
    return data;
  } catch (_) {
    if (el) el.innerHTML = "<p class='muted'>Smoke test не удался</p>";
    return null;
  }
}

async function loadSmokeTest() {
  try {
    const data = await (await fetch("/api/smoke-test")).json();
    if (data.checks) renderSmokeTestPanel(data);
  } catch (_) {}
}

async function loadIntegrations() {
  try {
    const data = await (await fetch("/api/integrations")).json();
    renderIntegrationsPanel(data);
    return data;
  } catch (_) {
    const el = document.getElementById("integrations-panel-body");
    if (el) el.innerHTML = "<p class='muted'>Интеграции: обнови страницу</p>";
    return null;
  }
}

function renderLiveReadinessPanel(data) {
  const el = document.getElementById("live-readiness-panel");
  if (!el) return;
  if (!data) {
    el.innerHTML = "<p class='muted'>Готовность к Live: нет данных</p>";
    return;
  }
  window.lastLiveReadiness = data;
  const score = data.score_pct ?? 0;
  const cls = data.ready_for_live ? "ok" : score >= 60 ? "warn" : "bad";
  const checks = (data.checks || []).map(c => {
    const icon = c.ok ? "✅" : c.required === false ? "⏳" : "❌";
    return `<li>${icon} <b>${escapeHtml(c.label)}</b> — <span class="muted">${escapeHtml(c.detail || "")}</span></li>`;
  }).join("");
  const plan = (data.week_plan || []).map(p =>
    `<li class="${p.done ? "up" : ""}"><b>День ${p.day}</b> · ${escapeHtml(p.task)}: ${escapeHtml(p.action)}</li>`
  ).join("");
  const lim = data.limits_if_live || {};
  const st = data.stats || {};
  let vsNote = "";
  if (Math.abs(st.live_pnl_pct || 0) < 2 && Math.abs(st.vs_hold_pct || 0) > 10) {
    vsNote = `<p class="warn">⚠ vs Hold ${fmtPct(st.vs_hold_pct)} при P&L ${fmtPct(st.pnl_pct)} — часто это «кэш лучше просевшего hold», не чистая прибыль.</p>`;
  }
  el.innerHTML = `
    <div class="honesty-box ${cls}">
      <p><b>Готовность к Live: ${score}%</b> ${data.ready_for_live ? "— можно включать 🏦 Live" : "— доработай пункты"}</p>
      <p class="muted">Paper ${st.paper_days ?? 0}д · Testnet ${st.testnet_days ?? 0}д · сделок ${st.trade_count ?? 0} · P&L ${fmtPct(st.pnl_pct)}</p>
      ${vsNote}
      <p class="muted">На Live: макс. $${lim.max_order_usd ?? 25}/ордер · дневной стоп ${lim.max_daily_loss_pct ?? 3}%</p>
    </div>
    <ul class="auto-tactics-list">${checks}</ul>
    <p class="muted">📅 План на неделю:</p>
    <ul class="auto-tactics-list">${plan}</ul>`;
}

function updateExchangeControls(tm) {
  const mode = tm?.mode || "paper";
  const enabled = tm?.exchange_enabled !== false;
  const show = enabled && mode !== "paper";
  document.querySelectorAll(".testnet-btn").forEach(btn => {
    btn.style.display = show ? "" : "none";
  });
}

function renderBotStatus(d) {
  const el = document.getElementById("bot-status");
  if (!el || !d) return;
  const st = d.strategy || {};
  const p = st.params || {};
  const lbl = d.label || labelFor(d.symbol);
  const vol = d.volatile ? " ⚡" : "";
  const viralTag = d.viral ? " 🔥 VIRAL" : d.growth ? " 📈 growth" : "";
  const avg = st.avg_entry || d.portfolio?.avg_entry;
  const stype = st.strategy_type || d.strategy_type || "dca";
  const autoInfo = window.lastAutoTactics?.markets?.find(m => m.symbol === d.symbol)?.last_auto;
  const autoLine = autoInfo
    ? `<p class="muted">🤖 ${autoInfo.source === "trader" ? "👁️" : "🤖"} ${autoInfo.reason || ""}</p>`
    : "";
  const title = document.getElementById("bot-card-title");
  if (title) title.textContent = `🤖 ${stype.toUpperCase()} · ${lbl}`;
  const sel = document.getElementById("strategy-select");
  if (sel && sel.value !== stype) sel.value = stype;
  el.innerHTML = `
    <p>Рынок: <strong>${lbl}</strong>${viralTag}${vol}${d.restored ? " · 💾 восстановлен" : ""} · ${st.enabled !== false ? "✅ активен" : "⏸ пауза"}</p>
    <p>Стратегия: <span class="strategy-tag">${stype}</span>${st.rsi != null ? ` · RSI ${st.rsi}` : ""}${st.in_trend ? " · 🚀 в тренде" : ""}</p>
    ${autoLine}
    <p>Цена: <strong>${fmtMoney(d.price, priceDecimals(lbl))}</strong>${avg ? ` · вход ~${fmtMoney(avg, priceDecimals(lbl))}` : ""}</p>
    <p>Портфель: <strong>${fmtMoney(d.portfolio?.portfolio_value)}</strong> (${fmtPct(d.portfolio?.pnl_pct)}) · vs hold ${fmtPct(d.portfolio?.vs_hold_pct)}</p>
    ${strategyParamsHtml(stype, p)}
    <p>SMA: <strong>${st.sma ? fmtMoney(st.sma, priceDecimals(lbl)) : "—"}</strong>${st.profit_pct > 0 ? ` · над SMA +${st.profit_pct}%` : st.dip_pct > 0 ? ` · ниже SMA ${st.dip_pct}%` : ""}${st.cost_profit_pct != null ? ` · от входа ${st.cost_profit_pct >= 0 ? "+" : ""}${st.cost_profit_pct}%` : ""}</p>
  `;
  const btn = document.getElementById("btn-toggle");
  if (btn) btn.textContent = st.enabled !== false ? "Пауза" : "Старт";
}

async function renderAllTrades() {
  const ul = document.getElementById("trades-list");
  if (!ul) return;
  let all = [];
  try {
    const res = await fetch("/api/trades?limit=500");
    const data = await res.json();
    all = data.trades || [];
  } catch (_) {}
  if (!all.length) {
    for (const sym of Object.keys(marketsData)) {
      const d = marketsData[sym];
      (d?.trades || []).forEach(t => all.push({ ...t, label: d.label || labelFor(sym) }));
    }
    all.sort((a, b) => b.ts - a.ts);
  }
  if (!all.length) {
    ul.innerHTML = "<li>Сделок пока нет — бот купит при старте или на просадке</li>";
    return;
  }
  ul.innerHTML = all.slice(0, 50).map(t => {
    const d = new Date(t.ts * 1000).toLocaleString("ru-RU");
    return `<li class="${t.side}"><b>${t.label}</b> ${d} · ${t.side.toUpperCase()} @ ${fmtMoney(t.price, priceDecimals(t.label))} · $${Number(t.amount_quote || 0).toFixed(0)} · ${t.reason}</li>`;
  }).join("");
}

function renderChat(messages) {
  if (messages?.length) chatHistory = messages;
  const box = document.getElementById("chat-messages");
  if (!box || !chatHistory.length) return;
  box.innerHTML = chatHistory.map(m => {
    const cls = m.role === "user" ? "chat-user" : "chat-bot";
    return `<div class="chat-bubble ${cls}">${escapeHtml(m.content).replace(/\n/g, "<br>")}</div>`;
  }).join("");
  box.scrollTop = box.scrollHeight;
}

function escapeHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function openAgentModal(key, data) {
  const modal = document.getElementById("agent-modal");
  const body = document.getElementById("agent-modal-body");
  if (!modal || !body || !data) return;
  let extra = "";
  if (data.insights?.length) extra += data.insights.map(i => `<li>[${i.market}] ${i.rule}: ${i.text}</li>`).join("");
  if (data.headlines?.length) extra += data.headlines.map(h => `<li>${h.title}</li>`).join("");
  if (data.proposals?.length) extra += data.proposals.map(p => `<li>${p.scheme}: ${p.desc}</li>`).join("");
  if (data.learned?.length) extra += data.learned.map(l => `<li>${l}</li>`).join("");
  if (data.hot?.length) extra += data.hot.map(h => `<li>🔥 ${h}</li>`).join("");
  if (data.spikes?.length) extra += data.spikes.map(s => `<li>📊 ${s}</li>`).join("");
  if (data.critical?.length) extra += data.critical.map(w => `<li>🚨 ${w}</li>`).join("");
  if (data.warnings?.length) extra += data.warnings.map(w => `<li>⚠️ ${w}</li>`).join("");
  if (data.trends?.length) extra += data.trends.map(t => `<li>📈 ${t}</li>`).join("");
  if (data.tips?.length) extra += data.tips.map(t => `<li>💡 ${t}</li>`).join("");
  if (data.ready?.length) extra += data.ready.map(r => `<li>🎯 ${r}</li>`).join("");
  if (data.pairs?.length) extra += data.pairs.map(p => `<li>🔗 ${p}</li>`).join("");
  if (data.leaders?.length) extra += data.leaders.map(l => `<li>🏆 ${l}</li>`).join("");
  if (data.laggards?.length) extra += data.laggards.map(l => `<li>📉 ${l}</li>`).join("");
  if (data.highlights?.length) extra += data.highlights.map(h => `<li>📊 ${h}</li>`).join("");
  if (data.alerts?.length) extra += data.alerts.map(a => `<li>⚠️ ${a}</li>`).join("");
  if (data.halts?.length) extra += data.halts.map(h => `<li>🛑 ${h}</li>`).join("");
  if (data.suggestions?.length) extra += data.suggestions.map(s => `<li>⚖️ ${s}</li>`).join("");
  if (data.overweight?.length) extra += data.overweight.map(o => `<li>📦 ${o}</li>`).join("");
  if (data.signals?.length) extra += data.signals.map(s => `<li>👁️ ${s.text || s.trader}</li>`).join("");
  if (data.warnings?.length && !data.critical) extra += data.warnings.map(w => `<li>🔴 ${w}</li>`).join("");
  body.innerHTML = `
    <h3>${data.emoji || ""} ${data.name || key}</h3>
    <p>${escapeHtml(data.summary || "")}</p>
    ${data.action ? `<p class="muted">${escapeHtml(data.action)}</p>` : ""}
    ${extra ? `<ul class="agent-detail-list">${extra}</ul>` : ""}
  `;
  modal.classList.remove("hidden");
}

function renderBrain(brain) {
  if (!brain) return;
  lastBrain = brain;
  const v = document.getElementById("brain-verdict");
  if (v) v.textContent = brain.verdict || "Мозг анализирует рынки...";
  [
    ["agent-mentor", brain.mentor],
    ["agent-news", brain.news],
    ["agent-schemer", brain.schemer],
    ["agent-volatility", brain.volatility],
    ["agent-risk", brain.risk],
    ["agent-trend", brain.trend],
    ["agent-profit", brain.profit],
    ["agent-correlation", brain.correlation],
    ["agent-analyst", brain.analyst],
    ["agent-guardian", brain.guardian],
    ["agent-allocator", brain.allocator],
    ["agent-trader-watch", brain.trader_watcher],
  ].forEach(([id, data]) => {
    const el = document.getElementById(id);
    if (!el || !data) return;
    el.classList.add("active");
    const sm = el.querySelector("small");
    if (sm && data.summary) sm.textContent = data.summary.slice(0, 75) + (data.summary.length > 75 ? "…" : "");
    el.onclick = () => openAgentModal(id, data);
    el.style.cursor = "pointer";
  });
}

const PRICE_RANGE = {
  BTC: [1000, 500000],
  ETH: [100, 50000],
  SOL: [1, 2000],
  BNB: [10, 5000],
  XRP: [0.1, 50],
  ADA: [0.01, 10],
  AVAX: [1, 500],
  LINK: [1, 200],
  ARB: [0.05, 20],
  SUI: [0.1, 50],
  NEAR: [0.1, 50],
  DOT: [0.5, 100],
  INJ: [1, 200],
  TON: [0.5, 50],
  DOGE: [0.001, 10],
  PEPE: [0.0000001, 0.01],
  WIF: [0.01, 50],
};

function priceOk(label, price) {
  if (price == null || isNaN(price)) return false;
  const r = PRICE_RANGE[label];
  if (!r) return price > 0;
  return price >= r[0] && price <= r[1];
}

function snapTradeToCandleTime(ts, candles) {
  if (!candles?.length) return null;
  const minT = candles[0].time;
  const maxT = candles[candles.length - 1].time;
  const bucket = Math.floor(ts / 60) * 60;
  if (bucket < minT - 60 || bucket > maxT + 60) return null;
  const times = candles.map(c => c.time);
  if (times.includes(bucket)) return bucket;
  let best = times[0];
  let bestDist = Math.abs(bucket - best);
  for (const t of times) {
    const d = Math.abs(bucket - t);
    if (d < bestDist) { best = t; bestDist = d; }
  }
  return bestDist <= 120 ? best : null;
}

function tradeMarkerLabel(t) {
  const buy = t.side === "buy";
  const usd = Number(t.amount_quote || 0);
  const short = usd >= 10 ? `$${Math.round(usd)}` : `$${usd.toFixed(1)}`;
  const tag = (t.reason || "").includes("MANUAL") ? "M" : "";
  return buy ? `▲${tag}${short}` : `▼${tag}${short}`;
}

function updateTradeMarkers(trades) {
  if (!candleSeries || !lastCandles.length) return;
  const list = (trades || []).slice(-80);
  const markers = [];
  let skipped = 0;
  for (const t of list) {
    const buy = t.side === "buy";
    const time = snapTradeToCandleTime(t.ts, lastCandles);
    if (time == null) {
      skipped += 1;
      continue;
    }
    const manual = (t.reason || "").includes("MANUAL");
    markers.push({
      time,
      position: buy ? "belowBar" : "aboveBar",
      color: buy ? (manual ? "#4de8ff" : "#00f0b8") : (manual ? "#ff9eb0" : "#ff5c7a"),
      shape: buy ? "arrowUp" : "arrowDown",
      text: tradeMarkerLabel(t),
      size: 2,
    });
  }
  markers.sort((a, b) => a.time - b.time);
  lastTradeMarkers = list;
  lastTradeMarkerStats = { shown: markers.length, skipped, total: list.length };
  candleSeries.setMarkers(markers);
  updateChartTitle(activeSymbol);
}

async function refreshTradeMarkers(symbol) {
  try {
    const tr = await (await fetch(`/api/trades?symbol=${symbol}&limit=120`)).json();
    updateTradeMarkers(tr.trades || []);
  } catch (_) {
    updateTradeMarkers(marketsData[symbol]?.trades || []);
  }
}

function mergeMarket(sym, patch) {
  const label = labelFor(sym);
  if (patch?.symbol && patch.symbol !== sym) return;
  const prev = marketsData[sym] || { symbol: sym, label };
  const safe = { ...patch };
  delete safe.candles;
  if (safe.price != null && !priceOk(label, safe.price)) {
    delete safe.price;
  }
  marketsData[sym] = { ...prev, ...safe, symbol: sym, label: prev.label || label };
}

function applyWsInit(msg) {
  if (msg.market_meta) applyMarketMeta(msg.market_meta);
  if (msg.markets) {
    for (const [sym, payload] of Object.entries(msg.markets)) {
      mergeMarket(sym, payload);
    }
  }
  updateTotal(msg.total);
  renderTabs();
  void ensureFreshCandles(activeSymbol);
  if (msg.brain) renderBrain(msg.brain);
  if (msg.assistant) renderChat([{ role: "assistant", content: msg.assistant }]);
  renderAllTrades();
  setLiveStatus("live");
}

function connectWs() {
  if (tradeSocket) {
    try { tradeSocket.close(); } catch (_) {}
  }
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const tok = localStorage.getItem("tradesim_token");
  const qs = tok ? `?token=${encodeURIComponent(tok)}` : "";
  tradeSocket = new WebSocket(`${proto}//${location.host}/ws${qs}`);
  const ws = tradeSocket;
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "init") applyWsInit(msg);
      if (msg.type === "markets_sync" && msg.markets) {
        if (msg.market_meta) applyMarketMeta(msg.market_meta);
        for (const [sym, payload] of Object.entries(msg.markets)) mergeMarket(sym, payload);
        renderTabs();
        updateTotal(msg.total || computeTotal());
        showToast(`Подключено рынков: ${Object.keys(msg.markets).length}`);
      }
      if (msg.type === "deposit" && msg.total) {
        updateTotal(msg.total);
        if (msg.total.start_balance) startBalance = msg.total.start_balance;
        showToast(`💵 Пополнено $${msg.amount} · всего ${fmtMoney(msg.total.total_value)}`);
        loadDepositsTable();
        loadMovementsTable();
      }
      if (msg.type === "withdraw" && msg.total) {
        updateTotal(msg.total);
        showToast(`💸 Выведено $${msg.amount} (${msg.wallet || "paper"})`);
        loadMovementsTable();
        loadExchangePanel();
      }
      if (msg.type === "brain_update" && msg.cycle) {
        renderBrain(msg.cycle);
        if (msg.cycle.verdict) {
          pushActivity(`Мозг: ${msg.cycle.verdict.slice(0, 80)}`);
        }
        loadAgentChatroom();
      }
      if (msg.type === "brain_chatroom" && msg.chatroom) {
        renderAgentChatroom(msg.chatroom);
      }
      if (msg.type === "candles_ready") {
        showToast(`📊 Свечи готовы: ${msg.ready}/${msg.total} рынков`);
        if (activeSymbol) {
          ensureFreshCandles(activeSymbol).then(c => {
            if (candleSeries && c?.length) {
              lastCandles = c;
              candleSeries.setData(c);
              updateSMA(c, smaPeriod(activeSymbol));
              updateChartTitle(activeSymbol);
            }
          });
        }
      }
      if (msg.type === "candles_refreshed" && msg.symbols?.length) {
        if (msg.symbols.includes(activeSymbol)) {
          loadCandlesForSymbol(activeSymbol, true).then(c => {
            if (candleSeries && c?.length) {
              lastCandles = c;
              candleSeries.setData(c);
              updateSMA(c, smaPeriod(activeSymbol));
            }
          });
        }
        showToast(`📊 Свечи обновлены (${msg.symbols.length} рынков)`);
      }
      if (msg.type === "tick" && msg.symbol) {
        mergeMarket(msg.symbol, {
          price: msg.price,
          portfolio: msg.portfolio,
          strategy: msg.strategy,
          source: msg.source,
        });
        if (msg.symbol === activeSymbol) {
          if (msg.candle) updateLiveCandle(msg.candle);
          setLiveStatus(feedLiveMode(msg.source));
          renderBotStatus(marketsData[msg.symbol]);
          const fs = document.getElementById("feed-source");
          if (fs && msg.source) fs.textContent = msg.source;
        }
        renderTabs();
        updateTotal(computeTotal());
        setLiveStatus("live");
      }
      if (msg.type === "strategy_update") {
        showToast(`🔧 ${msg.label || labelFor(msg.symbol)}: ${msg.reason || "автонастройка"}`);
        pushActivity(`🔧 ${msg.label}: ${(msg.reason || "").slice(0, 60)}`);
        if (msg.symbol) mergeMarket(msg.symbol, { strategy: { params: msg.params, enabled: true } });
        if (msg.symbol === activeSymbol) renderBotStatus(marketsData[msg.symbol]);
        loadLearning();
      }
      if (msg.type === "exchange_sync") {
        if (msg.paper_sync?.ok) {
          showToast(`🔗 ${msg.label}: testnet → paper синхронизирован`);
        } else if (msg.paper_to_exchange?.ok) {
          showToast(`📤 ${msg.label}: paper → testnet (${msg.paper_to_exchange.side} $${Number(msg.paper_to_exchange.amount_usd).toFixed(0)})`);
        } else if (msg.paper_to_exchange && !msg.paper_to_exchange.ok) {
          showToast(`⚠️ ${msg.label}: sync testnet — ${msg.paper_to_exchange.error || "ошибка"}`);
        } else if (msg.mirror?.ok) {
          showToast(`🔗 ${msg.label}: base mirrored (Δ ${msg.mirror.diff})`);
        }
        if (msg.total) updateTotal(msg.total);
        void refreshStatus();
        loadExchangePanel();
      }
      if (msg.type === "trading_mode") {
        renderTradingMode(msg);
        showToast(`Режим: ${msg.label || msg.mode}`);
        loadExchangePanel();
      }
      if (msg.type === "trade" && msg.trade) {
        const icon = msg.trade.side === "sell" ? "💵" : "💰";
        showToast(`${icon} ${msg.label || labelFor(msg.symbol)}: ${msg.trade.reason}`);
        pushActivity(`${msg.label || labelFor(msg.symbol)} ${msg.trade.side.toUpperCase()}: ${msg.trade.reason}`);
        renderAllTrades();
        if (msg.symbol === activeSymbol) void refreshTradeMarkers(activeSymbol);
        refreshStatus();
      }
      if (msg.type === "shadow_promote") {
        showToast(`🔬 ${msg.label}: клон #${msg.clone_id} → живой бот`);
        pushActivity(`🔬 ${msg.label}: клон #${msg.clone_id} победил`);
        loadShadowLab();
        if (msg.symbol) refreshStatus();
      }
      if (msg.type === "auto_tactic") {
        const icon = msg.source === "trader" ? "👁️" : "🤖";
        showToast(`${icon} ${msg.label}: ${msg.old_strategy}→${msg.strategy_type} (${msg.trader || "авто"})`);
        pushActivity(`${icon} ${msg.label}: ${msg.reason || msg.strategy_type}`);
        if (msg.symbol) {
          mergeMarket(msg.symbol, { strategy_type: msg.strategy_type, strategy: { strategy_type: msg.strategy_type, params: msg.params } });
          if (msg.symbol === activeSymbol) renderBotStatus(marketsData[msg.symbol]);
        }
        loadAutoTactics();
        loadLearning();
      }
      if (msg.type === "profit_focus") {
        const icon = msg.action === "pause" ? "⏸" : msg.action === "resume" ? "▶️" : "💎";
        showToast(`${icon} Profit Focus · ${msg.label}: ${msg.reason || msg.action}`);
        pushActivity(`${icon} ${msg.label}: ${msg.reason || msg.action}`);
        if (msg.symbol) {
          mergeMarket(msg.symbol, { strategy: { enabled: msg.action !== "pause" } });
          if (msg.symbol === activeSymbol) renderBotStatus(marketsData[msg.symbol]);
        }
        void loadProfitFocus();
        refreshStatus();
      }
      if (msg.type === "protection") {
        showToast(`🛡 ${msg.reason || msg.type || "protection"}`, 6000);
        void loadIntegrations();
      }
      if (msg.type === "limit_order") {
        showToast(`📋 Limit ${msg.order?.side || ""} @ ${msg.order?.limit_price || "?"}`);
        loadOpenOrders(false);
      }
      if (msg.type === "tradingview_signal") {
        showToast(`📡 TV ${msg.side || ""} ${msg.label || msg.symbol || ""}`, 5000);
      }
    } catch (e) { console.error(e); }
  };
  ws.onclose = () => setTimeout(connectWs, 3000);
}

function parseStatus(data) {
  if (!data) return null;
  // Старый API: один рынок { symbol, price, ... }
  if (!data.markets && data.symbol) {
    data.markets = { [data.symbol]: { ...data, label: data.symbol.replace("USDT", "") } };
  }
  if (!data.total && data.markets) {
    data.total = computeTotalFromMarkets(data.markets);
  }
  return data;
}

function computeTotalFromMarkets(markets) {
  let sum = 0;
  let start = 0;
  for (const sym of Object.keys(markets)) {
    const p = markets[sym]?.portfolio;
    sum += p?.portfolio_value || 0;
    start += p?.start_balance || 0;
  }
  if (sum <= 0) return null;
  if (start > 0) startBalance = start;
  const startVal = start > 0 ? start : startBalance;
  return {
    total_value: sum,
    pnl: sum - startVal,
    pnl_pct: ((sum - startVal) / startVal) * 100,
    start_balance: startVal,
  };
}

function applyBootstrap(data) {
  if (!data) return false;
  if (data.market_meta) applyMarketMeta(data.market_meta);
  if (data.total?.start_balance) startBalance = data.total.start_balance;
  const parsed = parseStatus(data);
  if (parsed?.markets) {
    for (const [sym, payload] of Object.entries(parsed.markets)) {
      mergeMarket(sym, payload);
    }
  }
  updateTotal(parsed?.total || computeTotal());
  renderTabs();
  if (parsed?.brain) renderBrain(parsed.brain);
  if (data.chat) renderChat([{ role: "assistant", content: data.chat }]);
  if (data.trades?.length) renderTradesList(data.trades);
  else renderAllTrades();
  if (data.paper_learn) {
    showToast("📚 Paper Learn: максимум сделок для обучения");
  }
  if (data.trading_mode) renderTradingMode(data.trading_mode);
  if (data.equity) renderEquityCurve(data.equity);
  if (data.learning) renderLearningPanel(data.learning, data.brain_history, data.analytics);
  if (data.analytics) lastAnalytics = data.analytics;
  if (data.strategy_history?.length) {
    data.strategy_history.slice(0, 3).forEach(h => {
      pushActivity(`🔧 ${h.symbol?.replace("USDT", "")}: ${(h.reason || "").slice(0, 50)}`);
    });
  }
  if (data.shadow_lab) renderShadowLab(data.shadow_lab);
  if (data.auto_tactics) renderAutoTacticsPanel(data.auto_tactics);
  if (data.profit_focus) renderProfitFocusPanel(data.profit_focus);
  if (data.scorecard) renderScorecardPanel(data.scorecard);
  if (data.live_readiness) renderLiveReadinessPanel(data.live_readiness);
  if (data.live_prep) renderLivePrepPanel(data.live_prep);
  renderAllTables(data);
  setLiveStatus("live");
  return Object.keys(marketsData).length > 0;
}

function renderTradesList(all) {
  const ul = document.getElementById("trades-list");
  if (!ul) return;
  if (!all?.length) {
    ul.innerHTML = "<li>Сделок пока нет</li>";
    return;
  }
  ul.innerHTML = all.slice(0, 40).map(t => {
    const d = new Date(t.ts * 1000).toLocaleString("ru-RU");
    return `<li class="${t.side}"><b>${t.label}</b> ${d} · ${t.side.toUpperCase()} @ ${fmtMoney(t.price, priceDecimals(t.label))} · $${Number(t.amount_quote || 0).toFixed(0)} · ${t.reason}</li>`;
  }).join("");
}

function loadEmbeddedData() {
  const el = document.getElementById("initial-data");
  if (!el?.textContent) return false;
  try {
    return applyBootstrap(JSON.parse(el.textContent));
  } catch (e) {
    console.error("embedded", e);
    return false;
  }
}

async function fetchBootstrap() {
  try {
    const res = await fetchWithTimeout("/api/bootstrap", 30000);
    if (res.ok) return applyBootstrap(await res.json());
  } catch (_) {}
  // Запасной вариант: загрузить каждый рынок отдельно
  for (const m of marketMeta) {
    try {
      const d = await (await fetch(`/api/status?symbol=${m.symbol}`)).json();
      if (d?.symbol || d?.price) mergeMarket(m.symbol, d);
    } catch (_) {}
  }
  renderTabs();
  switchMarket(activeSymbol);
  await renderAllTrades();
  return Object.keys(marketsData).length > 0;
}

function computeTotal() {
  return computeTotalFromMarkets(marketsData);
}

async function refreshStatus() {
  try {
    const data = parseStatus(await (await fetch("/api/status")).json());
    if (data?.markets) {
      for (const [sym, payload] of Object.entries(data.markets)) {
        mergeMarket(sym, payload);
      }
    }
    updateTotal(data?.total || computeTotal());
    renderTabs();
    const d = marketsData[activeSymbol];
    if (d) renderBotStatus(d);
    const lag = d?.candle_lag_sec ?? 9999;
    if (lag > 120 || !d?.candles_ready || lastCandles.length < 30) {
      await ensureFreshCandles(activeSymbol);
    }
    await renderAllTrades();
    setLiveStatus("live");
  } catch (e) {
    setLiveStatus(false);
  }
}

async function loadBrain() {
  try {
    const res = await fetch("/api/brain");
    if (!res.ok) return;
    const data = await res.json();
    if (data.cycle) renderBrain(data.cycle);
  } catch (_) {}
}

async function loadDepositsTable() {
  try {
    const data = await (await fetch("/api/deposits")).json();
    renderDepositsTable(data.deposits);
  } catch (_) {}
}

async function loadMovementsTable() {
  try {
    const data = await (await fetch("/api/wallet/movements")).json();
    renderMovementsTable(data.movements);
  } catch (_) {}
}

async function loadInitial() {
  const ping = await checkServerAndSync();
  let ok = loadEmbeddedData();
  if (!ok) ok = await fetchBootstrap();
  if (!ok) await refreshStatus();
  showVersionBanner(ping);
  renderTabs();
  switchMarket(activeSymbol);
  await loadBrain();
  if (!marketsData[activeSymbol]?.price) {
    await new Promise(r => setTimeout(r, 2500));
    await refreshStatus();
    switchMarket(activeSymbol);
  }
  if (!marketsData[activeSymbol]?.price) {
    showError("Цены ещё не пришли. Подожди 10 сек или перезапусти: Ctrl+C → python main.py → Ctrl+Shift+R");
  }
}

function bindUi() {
  document.getElementById("btn-toggle").onclick = async () => {
    await apiFetch(`/api/bot/toggle?symbol=${activeSymbol}`, { method: "POST" });
    await refreshStatus();
  };

  document.getElementById("chat-form").onsubmit = async (e) => {
    e.preventDefault();
    const input = document.getElementById("chat-input");
    const text = input?.value?.trim();
    if (!text) return;
    input.value = "";
    input.disabled = true;
    chatHistory.push({ role: "user", content: text });
    renderChat();
    try {
      const res = await apiFetch("/api/assistant/chat", {
        method: "POST",
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      if (data.chat) renderChat(data.chat);
      else if (data.reply) {
        chatHistory.push({ role: "assistant", content: data.reply });
        renderChat();
      } else if (data.error) {
        chatHistory.push({ role: "assistant", content: "Ошибка: " + data.error });
        renderChat();
      }
    } catch (_) {
      chatHistory.push({ role: "assistant", content: "Не удалось отправить — проверь сервер." });
      renderChat();
    } finally {
      input.disabled = false;
      input.focus();
    }
  };

  document.getElementById("btn-reset").onclick = async () => {
    if (!confirm(`Сбросить портфели ${marketMeta.length} рынков? (сделки в БД останутся)`)) return;
    await apiFetch("/api/reset", { method: "POST" });
    location.reload();
  };

  document.getElementById("btn-reset-full")?.addEventListener("click", async () => {
    if (!confirm("ПОЛНЫЙ сброс: портфели + все сделки и история в SQLite. Продолжить?")) return;
    await apiFetch("/api/reset?full=true", { method: "POST" });
    location.reload();
  });

  document.getElementById("btn-export")?.addEventListener("click", async () => {
    try {
      const data = await (await apiFetch("/api/export/trades")).json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `tradesim-trades-v${data.version || 19}.json`;
      a.click();
      showToast(`Экспорт: ${data.count || 0} сделок`);
    } catch (_) {
      showToast("Ошибка экспорта");
    }
  });

  document.getElementById("btn-testnet-order")?.addEventListener("click", async () => {
    const side = confirm("Testnet BUY $10? (Cancel = SELL $10)") ? "buy" : "sell";
    const orderType = document.getElementById("order-type-select")?.value || "market";
    const payload = buildOrderPayload(side, 10) || { symbol: activeSymbol, side, amount_usd: 10, order_type: "market" };
    payload.symbol = activeSymbol;
    payload.side = side;
    payload.amount_usd = 10;
    const res = await apiFetch("/api/exchange/order", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.error) showToast("⚠ " + data.error);
    else if (data.mode === "paper" || data.ok === false) showToast("📄 Paper: " + (data.note || "биржа выключена"));
    else if (data.paper_sync?.ok) {
      showToast(`🔗 Testnet→Paper: ${data.paper_sync.side} $${Number(data.paper_sync.amount_quote).toFixed(2)} синхронизировано`);
      await refreshStatus();
      loadExchangePanel();
    } else if (data.paper_sync && !data.paper_sync.ok) {
      showToast(`⚠ Testnet OK, paper sync failed: ${data.paper_sync.error || data.warning || "?"}`);
    } else showToast(`🏦 ${data.mode}: ${side} ${activeSymbol} — ${data.status || "ok"}`);
  });

  document.getElementById("btn-sync-paper")?.addEventListener("click", async () => {
    try {
      const res = await apiFetch(`/api/exchange/sync-paper?symbol=${activeSymbol}`, { method: "POST" });
      const data = await res.json();
      if (data.error) showToast("⚠ " + data.error);
      else if (data.note === "already aligned") showToast(`✅ ${labelFor(activeSymbol)}: paper = exchange`);
      else showToast(`🔗 Sync ${labelFor(activeSymbol)}: Δ base ${data.diff}`);
      await refreshStatus();
      loadExchangePanel();
    } catch (_) {
      showToast("Ошибка sync paper");
    }
  });

  document.getElementById("btn-save-token")?.addEventListener("click", () => {
    const t = document.getElementById("api-token-input")?.value?.trim();
    if (t) localStorage.setItem("tradesim_token", t);
    else localStorage.removeItem("tradesim_token");
    showToast(t ? "🔐 Токен сохранён — переподключение WS" : "Токен удалён");
    connectWs();
  });

  document.querySelectorAll(".manual-btn").forEach(btn => {
    btn.onclick = async () => {
      const side = btn.dataset.side;
      const payload = buildOrderPayload(side, 25);
      if (!payload) {
        showToast("⚠ Укажи limit/stop цену");
        return;
      }
      const res = await apiFetch("/api/trade", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.error) showToast("⚠ " + data.error);
      else if (data.pending) showToast(`📋 Limit ${side} @ ${payload.limit_price} — ждёт цену`);
      else {
        showToast(`${side === "buy" ? "💰" : "💵"} ${payload.order_type} ${side} на ${labelFor(activeSymbol)}`);
        await refreshStatus();
      }
    };
  });

  document.getElementById("order-type-select")?.addEventListener("change", (e) => {
    const t = e.target.value;
    const row = document.getElementById("limit-price-row");
    const stop = document.getElementById("stop-price-input");
    if (row) row.classList.toggle("hidden", t === "market");
    if (stop) stop.classList.toggle("hidden", t !== "stop_limit");
  });

  document.getElementById("btn-open-orders")?.addEventListener("click", () => loadOpenOrders(true));
  document.getElementById("orders-modal-close")?.addEventListener("click", () => {
    document.getElementById("orders-modal")?.classList.add("hidden");
  });
  document.getElementById("orders-modal")?.addEventListener("click", (e) => {
    if (e.target.id === "orders-modal") e.currentTarget.classList.add("hidden");
  });
  initTheme();
  document.getElementById("btn-chatroom-refresh")?.addEventListener("click", loadAgentChatroom);

  document.getElementById("agent-modal-close")?.addEventListener("click", () => {
    document.getElementById("agent-modal")?.classList.add("hidden");
  });
  document.getElementById("agent-modal")?.addEventListener("click", (e) => {
    if (e.target.id === "agent-modal") e.currentTarget.classList.add("hidden");
  });

  document.querySelectorAll(".tbl-tab").forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll(".tbl-tab").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const id = btn.dataset.table;
      document.querySelectorAll(".data-table-wrap").forEach(w => w.classList.add("hidden"));
      document.getElementById(`table-${id}`)?.classList.remove("hidden");
      if (id === "backtest") runBacktestTable();
      if (id === "trades") loadTradesTable("all");
      if (id === "shadow") renderShadowLeaderboard();
      if (id === "report") renderDailyReport();
      if (id === "strategies") renderStrategyReport();
      if (id === "brain-timeline") renderBrainTimeline();
      if (id === "agent-chatroom") loadAgentChatroom();
      if (id === "movements") loadMovementsTable();
      if (id === "deposits") loadDepositsTable();
    };
  });

  document.getElementById("btn-backtest-run")?.addEventListener("click", runBacktestTable);
  document.getElementById("btn-backtest-compare")?.addEventListener("click", runBacktestCompare);
  document.getElementById("btn-strategy-apply")?.addEventListener("click", applyStrategy);
  document.getElementById("btn-exchange-refresh")?.addEventListener("click", loadExchangePanel);
  document.getElementById("btn-live-readiness-refresh")?.addEventListener("click", loadLiveReadiness);
  document.getElementById("btn-live-prep-refresh")?.addEventListener("click", () => {
    loadLivePrep();
    loadLivePlaybook();
  });
  document.getElementById("btn-integrations-refresh")?.addEventListener("click", loadIntegrations);
  document.getElementById("btn-smoke-test")?.addEventListener("click", runSmokeTest);
  document.getElementById("btn-sync-paper-all")?.addEventListener("click", async () => {
    if (!confirm("Подогнать paper под баланс биржи на всех рынках? Paper-позиции изменятся.")) return;
    try {
      const res = await apiFetch("/api/exchange/sync-paper-all", { method: "POST", body: "{}" });
      const data = await res.json();
      if (data.ok) {
        showToast(`🔗 Sync: ${data.synced}/${data.total} рынков`, 5000);
        await runSmokeTest();
      } else {
        showToast(data.error || "Sync не удался", 5000);
      }
    } catch (_) {
      showToast("Sync paper (все) — ошибка", 4000);
    }
  });
  document.getElementById("btn-stability-check")?.addEventListener("click", async () => {
    const res = await apiFetch("/api/live-prep/stability-check", { method: "POST", body: "{}" });
    const data = await res.json();
    if (data.error) showToast("⚠ " + data.error);
    else {
      showToast(data.verify?.ok ? "🔌 API OK" : "⚠ API: " + (data.verify?.error || "?"));
      renderLivePrepPanel(data.live_prep);
    }
  });
  document.getElementById("btn-live-micro-testnet")?.addEventListener("click", async () => {
    if (!confirm("Micro Testnet: DCA ≥12ч, ордер ~$10, редкие сделки. Цель — стабильность API, не P&L. OK?")) return;
    const res = await apiFetch("/api/live-prep/start-micro?target=testnet", { method: "POST", body: "{}" });
    const data = await res.json();
    if (!data.ok) showToast("⚠ " + (data.error || data.trading_mode?.error || "?"), 8000);
    else {
      showToast("🎯 " + (data.hint || "Micro Testnet"));
      if (data.live_prep) renderLivePrepPanel(data.live_prep);
      await refreshStatus();
      loadExchangePanel();
    }
  });
  document.getElementById("btn-week-prep")?.addEventListener("click", async () => {
    if (!confirm("🚀 Неделя Testnet: активная торговля + режим Testnet. Продолжить?")) return;
    try {
      const res = await apiFetch("/api/week-prep/start", { method: "POST" });
      const data = await res.json();
      if (!data.ok) {
        showToast("⚠ " + (data.trading_mode?.error || data.hint || "ошибка"), 8000);
      } else {
        showToast("🚀 Testnet неделя запущена — " + (data.hint || "ok"));
        renderTradingMode(data.trading_mode);
        if (data.live_readiness) renderLiveReadinessPanel(data.live_readiness);
        await refreshStatus();
        loadExchangePanel();
      }
    } catch (_) {
      showToast("Ошибка запуска недели Testnet");
    }
  });
  document.getElementById("btn-auto-tactics-refresh")?.addEventListener("click", loadAutoTactics);
  document.getElementById("btn-scorecard-refresh")?.addEventListener("click", loadScorecard);
  document.getElementById("btn-profit-focus-refresh")?.addEventListener("click", loadProfitFocus);
  document.getElementById("btn-shadow-reset")?.addEventListener("click", async () => {
    if (!confirm("Сбросить все shadow-клоны? Текущие эксперименты начнутся заново.")) return;
    try {
      const res = await apiFetch("/api/shadow-lab/reset", { method: "POST" });
      const data = await res.json();
      if (data.status) renderShadowLab(data.status);
      showToast("♻️ Shadow Lab сброшен");
      await loadShadowLab();
    } catch (_) {
      showToast("Ошибка сброса Shadow Lab");
    }
  });
  document.querySelectorAll(".mode-btn").forEach(btn => {
    btn.addEventListener("click", () => setTradingMode(btn.dataset.mode));
  });

  document.getElementById("btn-paper-learn")?.addEventListener("click", async () => {
    try {
      const res = await apiFetch("/api/strategy/paper-learn", {
        method: "POST",
        body: JSON.stringify({ reset_timers: true }),
      });
      const data = await res.json();
      if (data.error) showToast("⚠ " + data.error);
      else {
        showToast(`📚 Paper учёба: ${data.count || 1} рынков — DCA ~1.5ч, scalp 20с`);
        await refreshStatus();
      }
    } catch (_) {
      showToast("Ошибка Paper учёбы");
    }
  });

  document.getElementById("btn-active-trades")?.addEventListener("click", async () => {
    try {
      const res = await apiFetch("/api/strategy/active", {
        method: "POST",
        body: JSON.stringify({ reset_timers: true }),
      });
      const data = await res.json();
      if (data.error) showToast("⚠ " + data.error);
      else {
        showToast(`📈 Активный режим: ${data.count} рынков — больше сделок`);
        await refreshStatus();
      }
    } catch (_) {
      showToast("Ошибка активного режима");
    }
  });

  document.querySelectorAll(".preset-btn").forEach(btn => {
    btn.onclick = async () => {
      const res = await apiFetch("/api/strategy/preset", {
        method: "POST",
        body: JSON.stringify({ symbol: activeSymbol, preset: btn.dataset.preset }),
      });
      const d = await res.json();
      if (d.error) showToast("⚠ " + d.error);
      else { showToast(`🎚 ${btn.dataset.preset} на ${labelFor(activeSymbol)}`); await refreshStatus(); }
    };
  });

  const depModal = document.getElementById("deposit-modal");
  const depTarget = document.getElementById("deposit-target");
  const depSym = document.getElementById("deposit-symbol");
  const depSymLabel = document.getElementById("deposit-symbol-label");

  function fillDepositSymbols() {
    if (!depSym) return;
    depSym.innerHTML = marketMeta.map(m => `<option value="${m.symbol}">${m.label}</option>`).join("");
    depSym.value = activeSymbol;
  }

  document.getElementById("btn-deposit")?.addEventListener("click", () => {
    fillDepositSymbols();
    depModal?.classList.remove("hidden");
  });
  document.getElementById("deposit-modal-close")?.addEventListener("click", () => {
    depModal?.classList.add("hidden");
  });
  depModal?.addEventListener("click", (e) => {
    if (e.target.id === "deposit-modal") depModal.classList.add("hidden");
  });
  depTarget?.addEventListener("change", () => {
    const one = depTarget.value === "symbol";
    depSym?.classList.toggle("hidden", !one);
    depSymLabel?.classList.toggle("hidden", !one);
  });

  document.getElementById("deposit-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const amount = Number(document.getElementById("deposit-amount")?.value);
    const target = depTarget?.value || "split";
    const symbol = target === "symbol" ? depSym?.value : null;
    const res = await apiFetch("/api/deposit", {
      method: "POST",
      body: JSON.stringify({ amount, target, symbol }),
    });
    const data = await res.json();
    if (data.error) showToast("⚠ " + data.error);
    else {
      updateTotal(data.total);
      depModal?.classList.add("hidden");
      showToast(`💵 +$${amount} · портфель ${fmtMoney(data.total.total_value)}`);
      await refreshStatus();
      renderDepositsTable(data.deposits);
      loadMovementsTable();
    }
  });

  const wdModal = document.getElementById("withdraw-modal");
  const wdWallet = document.getElementById("withdraw-wallet");
  const wdTarget = document.getElementById("withdraw-target");
  const wdSym = document.getElementById("withdraw-symbol");
  const wdSymLabel = document.getElementById("withdraw-symbol-label");
  const wdPaperFields = document.getElementById("withdraw-paper-fields");
  const wdExchangeFields = document.getElementById("withdraw-exchange-fields");

  function fillWithdrawSymbols() {
    if (!wdSym) return;
    wdSym.innerHTML = Object.keys(marketsMeta).map(s =>
      `<option value="${s}">${labelFor(s)}</option>`
    ).join("");
    if (activeSymbol) wdSym.value = activeSymbol;
  }

  function toggleWithdrawFields() {
    const ex = wdWallet?.value === "exchange";
    wdPaperFields?.classList.toggle("hidden", ex);
    wdExchangeFields?.classList.toggle("hidden", !ex);
  }

  document.getElementById("btn-withdraw")?.addEventListener("click", () => {
    fillWithdrawSymbols();
    toggleWithdrawFields();
    wdModal?.classList.remove("hidden");
  });
  document.getElementById("withdraw-modal-close")?.addEventListener("click", () => {
    wdModal?.classList.add("hidden");
  });
  wdModal?.addEventListener("click", (e) => {
    if (e.target.id === "withdraw-modal") wdModal.classList.add("hidden");
  });
  wdWallet?.addEventListener("change", toggleWithdrawFields);
  wdTarget?.addEventListener("change", () => {
    const one = wdTarget.value === "symbol";
    wdSym?.classList.toggle("hidden", !one);
    wdSymLabel?.classList.toggle("hidden", !one);
  });

  document.getElementById("withdraw-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const amount = Number(document.getElementById("withdraw-amount")?.value);
    const wallet = wdWallet?.value || "paper";
    const body = { amount, wallet };
    if (wallet === "exchange") {
      body.address = document.getElementById("withdraw-address")?.value?.trim() || "";
      body.network = document.getElementById("withdraw-network")?.value || "TRC20";
      body.confirm_live = !!document.getElementById("withdraw-confirm-live")?.checked;
      if (!confirm(`Вывести $${amount} USDT на биржу? Проверь адрес!`)) return;
    } else {
      body.target = wdTarget?.value || "split";
      body.symbol = body.target === "symbol" ? wdSym?.value : null;
    }
    const res = await apiFetch("/api/withdraw", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.error) showToast("⚠ " + data.error);
    else {
      if (data.total) updateTotal(data.total);
      wdModal?.classList.add("hidden");
      showToast(`💸 −$${data.withdrawn || amount} · ${wallet}`);
      await refreshStatus();
      loadMovementsTable();
      loadExchangePanel();
    }
  });
}

async function loadLearning() {
  try {
    const [sum, eq, bh, an] = await Promise.all([
      fetch("/api/learning/summary").then(r => r.json()),
      fetch("/api/learning/equity").then(r => r.json()),
      fetch("/api/brain/history").then(r => r.json()),
      fetch("/api/analytics").then(r => r.json()),
    ]);
    lastAnalytics = an;
    renderLearningPanel(sum, bh.history, an);
    if (eq.curve) renderEquityCurve(eq.curve);
  } catch (_) {
    const el = document.getElementById("learning-panel");
    if (el) el.textContent = "Статистика временно недоступна — нажми Ctrl+Shift+R";
  }
}

async function loadExchangePanel() {
  const el = document.getElementById("exchange-panel-body");
  if (!el) return;
  try {
    const [st, bal, rec, pnl, wallet, depInfo] = await Promise.all([
      fetch("/api/exchange/status").then(r => r.json()),
      fetch("/api/exchange/balances").then(r => r.json()),
      fetch(`/api/exchange/reconcile?symbol=${activeSymbol}`).then(r => r.json()),
      fetch("/api/exchange/pnl").then(r => r.json()),
      fetch("/api/wallet/summary").then(r => r.json()),
      fetch("/api/wallet/deposit-info").then(r => r.json()),
    ]);
    const walletBlock = `
      <div class="honesty-box ok" style="margin-bottom:0.5rem">
        <p><b>💳 Кошелёк бота</b> · режим <b>${wallet.mode?.toUpperCase() || "PAPER"}</b></p>
        <p>Paper USDT <b>${fmtMoney(wallet.paper_quote_usd)}</b> · кредит биржи <b>${fmtMoney(wallet.wallet_credit_usd)}</b></p>
        <p class="muted">Доступно боту: <b>${fmtMoney(wallet.bot_available_usd)}</b> · биржа USDT ${fmtMoney(wallet.exchange_usdt || 0)}</p>
        <div style="margin-top:0.4rem;display:flex;gap:0.35rem;flex-wrap:wrap">
          <button type="button" id="btn-wallet-sync-usdt" class="btn ghost small">↔️ Синхр. USDT → paper</button>
          <button type="button" id="btn-wallet-bridge" class="btn ghost small">🔗 Обновить мост</button>
        </div>
      </div>`;
    const depBlock = depInfo.ok && depInfo.address
      ? `<p class="muted">Депозит USDT (${depInfo.network || "TRC20"}): <code style="word-break:break-all">${depInfo.address}</code>${depInfo.tag ? ` · tag: ${depInfo.tag}` : ""}</p>`
      : depInfo.faucet_url
        ? `<p class="muted">Testnet faucet: <a href="${depInfo.faucet_url}" target="_blank" rel="noopener">${depInfo.faucet_url}</a></p>`
        : `<p class="muted">${depInfo.note || depInfo.error || ""}</p>`;
    if (!st.enabled) {
      const paperLine = pnl.paper_total_usd
        ? `<p>Paper: <b>${fmtMoney(pnl.paper_total_usd)}</b> · vs hold <b>${fmtPct(pnl.paper_vs_hold_pct || 0)}</b></p>`
        : "";
      el.innerHTML = `${walletBlock}<p>Paper режим. Задай <code>BINANCE_API_KEY</code> + <code>EXCHANGE_ENABLED=true</code> для testnet.</p>${paperLine}`;
      wireWalletPanelButtons();
      return;
    }
    const syncParts = [];
    if (st.sync_to_paper) syncParts.push("testnet → paper");
    if (st.sync_from_paper) syncParts.push("paper → testnet");
    const syncNote = syncParts.length
      ? `<p class='muted'>🔗 Sync: ${syncParts.join(" · ")}</p>`
      : "";
    const delta = pnl.delta_usd != null ? pnl.delta_usd : 0;
    const deltaCls = delta >= 0 ? "up" : "down";
    const pnlBlock = `
      <div class="honesty-box ok" style="margin-bottom:0.5rem">
        <p><b>Testnet PnL</b> · ${pnl.mode?.toUpperCase() || "TESTNET"}</p>
        <p>Биржа <b>${fmtMoney(pnl.exchange_total_usd)}</b> · Paper <b>${fmtMoney(pnl.paper_total_usd)}</b>
          <span class="${deltaCls}">Δ ${fmtMoney(delta)}</span></p>
        <p class="muted">Paper vs hold ${fmtPct(pnl.paper_vs_hold_pct || 0)} · USDT ${fmtMoney(pnl.usdt_free || 0)} · ордеров ${pnl.orders_today || 0}</p>
      </div>`;
    const rows = (bal.balances || []).slice(0, 8).map(b =>
      `<tr><td><b>${b.asset}</b></td><td>${Number(b.free).toFixed(6)}</td><td>${Number(b.locked).toFixed(6)}</td></tr>`
    ).join("") || "<tr><td colspan=3>Нет балансов</td></tr>";
    const syncCls = (rec.base_synced ?? rec.synced) ? "up" : "down";
    el.innerHTML = `
      ${walletBlock}
      ${depBlock}
      ${pnlBlock}
      ${syncNote}
      <p><b>${st.testnet ? "TESTNET" : "LIVE"}</b> · лимит $${st.max_order_usd} · daily loss ${st.max_daily_loss_pct}%</p>
      <table class="data-table compact"><thead><tr><th>Asset</th><th>Free</th><th>Locked</th></tr></thead><tbody>${rows}</tbody></table>
      <p class="muted" style="margin-top:0.5rem">Reconcile <b>${labelFor(activeSymbol)}</b>:</p>
      <p>Base paper <b>${rec.paper_base ?? "—"}</b> · exchange <b>${rec.exchange_base ?? "—"}</b>
        <span class="${syncCls}">Δ ${rec.base_diff ?? "—"}</span></p>
      <p class="muted">${rec.note || ""}</p>`;
    wireWalletPanelButtons();
  } catch (_) {
    el.textContent = "Не удалось загрузить данные биржи";
  }
}

function wireWalletPanelButtons() {
  document.getElementById("btn-wallet-sync-usdt")?.addEventListener("click", async () => {
    if (!confirm("Подтянуть USDT с биржи в paper-кошельки ботов?")) return;
    const res = await apiFetch("/api/wallet/sync-usdt", { method: "POST", body: "{}" });
    const data = await res.json();
    if (data.error) showToast("⚠ " + data.error);
    else {
      showToast(`↔️ Синхр. $${data.mirrored_usdt || 0} USDT → paper`);
      await refreshStatus();
      loadExchangePanel();
      loadMovementsTable();
    }
  }, { once: true });
  document.getElementById("btn-wallet-bridge")?.addEventListener("click", async () => {
    const res = await apiFetch("/api/wallet/bridge", { method: "POST", body: "{}" });
    const data = await res.json();
    if (data.summary) {
      showToast(`🔗 Мост: +$${data.summary.wallet_credit_usd || 0} кредит боту`);
      loadExchangePanel();
    }
  }, { once: true });
}

async function loadScorecard() {
  try {
    const data = await (await fetch("/api/scorecard")).json();
    renderScorecardPanel(data);
  } catch (_) {
    const el = document.getElementById("scorecard-panel");
    if (el) el.innerHTML = "<p class='muted'>Оценка: обнови страницу (Ctrl+Shift+R)</p>";
  }
}

async function loadProfitFocus() {
  try {
    const data = await (await fetch("/api/profit-focus")).json();
    renderProfitFocusPanel(data);
  } catch (_) {
    const el = document.getElementById("profit-focus-panel");
    if (el) el.innerHTML = "<p class='muted'>Profit Focus: обнови страницу (Ctrl+Shift+R)</p>";
  }
}

async function loadAutoTactics() {
  try {
    const data = await (await fetch("/api/auto-tactics")).json();
    renderAutoTacticsPanel(data);
  } catch (_) {
    const el = document.getElementById("auto-tactics-panel");
    if (el) el.innerHTML = "<p class='muted'>Авто-тактики: обнови страницу (Ctrl+Shift+R)</p>";
  }
}

function renderTradingMode(tm) {
  if (!tm?.mode) return;
  document.querySelectorAll(".mode-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.mode === tm.mode);
  });
  const el = document.getElementById("exchange-badge");
  if (el) {
    const labels = { paper: "PAPER", testnet: "TESTNET", live: "LIVE" };
    const classes = { paper: "paper", testnet: "testnet", live: "live-exchange" };
    el.textContent = labels[tm.mode] || "PAPER";
    el.className = "stat badge " + (classes[tm.mode] || "paper");
    el.title = tm.note || "";
  }
  updateExchangeControls(tm);
}

async function loadLiveReadiness() {
  try {
    const data = await (await fetch("/api/live-readiness")).json();
    renderLiveReadinessPanel(data);
    return data;
  } catch (_) {
    const el = document.getElementById("live-readiness-panel");
    if (el) el.innerHTML = "<p class='muted'>Не удалось загрузить готовность к Live</p>";
    return null;
  }
}

async function setTradingMode(mode) {
  if (mode === "live") {
    const rd = await loadLiveReadiness();
    if (rd && !rd.ready_for_live) {
      const fails = (rd.checks || []).filter(c => c.required && !c.ok).map(c => c.label).slice(0, 3).join(", ");
      showToast(`⚠ Live заблокирован (${rd.score_pct}%): ${fails}`, 9000);
      return;
    }
    const lim = rd?.limits_if_live?.max_order_usd ?? 25;
    if (!confirm(`⚠️ LIVE — РЕАЛЬНЫЕ ДЕНЬГИ на Binance.\n\nЛимит $${lim}/ордер.\nДневной стоп ${rd?.limits_if_live?.max_daily_loss_pct ?? 3}%.\n\nТы уверен?`)) return;
  }
  try {
    const res = await apiFetch("/api/trading-mode", {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
    const data = await res.json();
    if (!data.ok && data.error) {
      showToast("⚠ " + data.error, 8000);
      if (data.live_readiness) renderLiveReadinessPanel(data.live_readiness);
      return;
    }
    renderTradingMode(data);
    showToast(`Режим: ${data.label || mode} — ${data.warning || data.note || ""}`);
    loadExchangePanel();
    loadLiveReadiness();
  } catch (_) {
    showToast("Ошибка смены режима");
  }
}

async function loadExchangeBadge() {
  try {
    const tm = await (await fetch("/api/trading-mode")).json();
    renderTradingMode(tm);
  } catch (_) {}
}

async function main() {
  try {
    bindUi();
    if (!initChart()) showError("График: проверь интернет, нажми Ctrl+F5");
    initEquityChart();
    await loadInitial();
    await loadExchangeBadge();
    await loadExchangePanel();
    await loadLiveReadiness();
    await loadLivePrep();
    await loadLivePlaybook();
    await loadSmokeTest();
    await loadAgentChatroom();
    await loadIntegrations();
    await loadScorecard();
    await loadAutoTactics();
    await loadProfitFocus();
    await loadAlerts();
    await loadFees();
    await renderHeatmap();
    await loadShadowLab();
    connectWs();
    setInterval(refreshStatus, 5000);
    setInterval(syncChartIfStale, 20000);
    setInterval(loadBrain, 15000);
    setInterval(loadLearning, 60000);
    setInterval(loadShadowLab, 30000);
    setInterval(loadAlerts, 20000);
    setInterval(renderHeatmap, 25000);
  } catch (e) {
    showError(e.message);
  }
}

main();
