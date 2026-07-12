let chart, candleSeries, smaSeries;
let equityChart, equitySeries, holdEquitySeries;
let lastCandles = [];
let marketsData = {};
let activeSymbol = "BTCUSDT";
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

async function loadTradesTable(symbol) {
  const el = document.getElementById("table-trades");
  if (!el) return;
  el.innerHTML = "<p class='muted'>Загрузка сделок из SQLite...</p>";
  try {
    const sym = symbol || "";
    const url = sym ? `/api/trades?limit=150&symbol=${sym}` : "/api/trades?limit=150";
    const data = await (await fetch(url)).json();
    const trades = data.trades || [];
    if (!trades.length) {
      el.innerHTML = "<p class='muted'>Сделок пока нет — бот купит при DCA или просадке.</p>";
      return;
    }
    el.innerHTML = `<p class="muted" style="margin-bottom:0.5rem">Всего в БД: <b>${data.count}</b> · источник: ${data.source || "sqlite"}</p>
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
  if (history?.length) {
    hist = `<h4 style="margin:0.75rem 0 0.35rem;font-size:0.8rem">Последние автонастройки</h4>
    <table class="data-table"><thead><tr><th>Время</th><th>Рынок</th><th>Причина</th></tr></thead><tbody>
    ${(learning?.strategy_versions || history).slice(0, 10).map(t => {
      const d = new Date((t.ts || 0) * 1000).toLocaleString("ru-RU");
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
    ${deposits.map(d => `<tr><td>${new Date(d.ts * 1000).toLocaleString("ru-RU")}</td>
      <td><b>$${Number(d.amount).toLocaleString()}</b></td><td>${d.note || d.target}</td>
      <td>${fmtMoney(d.total_after)}</td></tr>`).join("")}
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
    el.innerHTML = `<div class="honesty-box ok">
      <p><b>${r.label}</b> · ${r.candles} свечей · ${r.trades} сделок (buy ${r.buys} / sell ${r.sells})</p>
      <p>P&L: <span class="${cls}"><b>${fmtPct(r.pnl_pct)}</b></span> · vs hold ${fmtPct(r.vs_hold_pct)} · портфель ${fmtMoney(r.portfolio_value)}</p>
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
      return `<tr class="${win}"><td><b>${r.strategy_type}</b>${i === 0 ? " 🏆" : ""}</td>
        <td class="${cls}">${fmtPct(r.pnl_pct)}</td><td>${fmtPct(r.vs_hold_pct)}</td>
        <td>${r.trades}</td><td>${fmtMoney(r.portfolio_value)}</td></tr>`;
    }).join("");
    el.innerHTML = `<div class="honesty-box ok">
      <p><b>${data.label}</b> · ${data.candles} свечей · победитель: <b>${data.winner}</b></p>
    </div>
    <table class="data-table"><thead><tr>
      <th>Стратегия</th><th>P&L</th><th>vs hold</th><th>Сделок</th><th>Портфель</th>
    </tr></thead><tbody>${rows}</tbody></table>
    <div class="backtest-controls" style="margin-top:0.75rem">
      <button type="button" id="btn-backtest-run" class="btn small">Один прогон</button>
      <button type="button" id="btn-backtest-compare" class="btn small ghost">Сравнить 5 стратегий</button>
    </div>`;
    document.getElementById("btn-backtest-run")?.addEventListener("click", runBacktestTable);
    document.getElementById("btn-backtest-compare")?.addEventListener("click", runBacktestCompare);
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

async function checkServerAndSync() {
  try {
    const ping = await waitForServer();
    if (!ping) {
      showError("Сервер не отвечает. Останови старый python (Ctrl+C) и запусти: python main.py");
      return null;
    }
    if (ping.auth_required && !localStorage.getItem("tradesim_token")) {
      showToast("🔐 Для кнопок торговли нужен API-токен — введи внизу (данные грузятся без него)");
    }
    if (ping.market_meta?.length) applyMarketMeta(ping.market_meta);
    seedMarketsFromMeta();
    if (ping.total) updateTotal(ping.total);
    const expectedVer = 24;
    if (ping.version && ping.version < expectedVer) {
      showError(`Старый сервер v${ping.version} на порту 8765. Ctrl+C → python main.py → Ctrl+Shift+R`);
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
    layout: { background: { color: "#0c1220" }, textColor: "#8b9cb8" },
    grid: { vertLines: { color: "#141c2e" }, horzLines: { color: "#141c2e" } },
    timeScale: { timeVisible: true, secondsVisible: false },
    rightPriceScale: { borderColor: "rgba(0,229,192,0.15)" },
    width: w,
    height: 420,
  });
  candleSeries = chart.addCandlestickSeries({
    upColor: "#00e5a8", downColor: "#ff5c7a", borderVisible: false,
    wickUpColor: "#00e5a8", wickDownColor: "#ff5c7a",
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
    el.innerHTML = `<div class="honesty-box ok">
      <p><b>Отчёт 24ч</b> · v${r.version} · сделок: ${r.trades_count} · fees: $${Number(r.fees_24h || 0).toFixed(2)}</p>
      <p>Портфель: ${fmtMoney(r.total?.total_value)} (${fmtPct(r.total?.pnl_pct)}) · Alpha vs hold: ${fmtPct(r.benchmark?.vs_hold_pct)}</p>
    </div>
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
    <div class="lp-row"><span class="lp-label">Мозг · 12 агентов</span><span class="lp-val">каждые 45 сек</span></div>
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

function setLiveStatus(ok) {
  const el = document.getElementById("live-status");
  if (!el) return;
  el.textContent = ok ? "● LIVE" : "○ пауза";
  el.className = "value live-dot" + (ok ? "" : " stale");
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

async function loadCandlesForSymbol(symbol) {
  try {
    const res = await fetch(`/api/candles?symbol=${symbol}&limit=200`);
    const data = await res.json();
    if (data.candles?.length) {
      if (marketsData[symbol]) marketsData[symbol].candles = data.candles;
      return data.candles;
    }
  } catch (_) {}
  return marketsData[symbol]?.candles || [];
}

async function switchMarket(symbol) {
  activeSymbol = symbol;
  const d = marketsData[symbol];
  if (!d) {
    document.getElementById("bot-status").innerHTML = "<p>Загрузка данных с сервера...</p>";
    return;
  }
  lastCandles = d.candles || [];
  if (lastCandles.length < 40) {
    lastCandles = await loadCandlesForSymbol(symbol);
  }
  const period = smaPeriod(symbol);
  if (candleSeries && lastCandles.length) {
    candleSeries.setData(lastCandles);
    updateSMA(lastCandles, period);
    try {
      const tr = await (await fetch(`/api/trades?symbol=${symbol}&limit=30`)).json();
      updateTradeMarkers(tr.trades || d.trades || []);
    } catch (_) {
      updateTradeMarkers(d.trades || []);
    }
    if (chart) chart.timeScale().fitContent();
  }
  const title = document.getElementById("chart-title");
  if (title) title.textContent = `${d.label || labelFor(symbol)}/USDT — свечи (${lastCandles.length})`;
  renderBotStatus(d);
  renderTabs();
  loadExchangePanel();
}

function updateLiveCandle(candle) {
  if (!candle || !candleSeries) return;
  if (lastCandles.length && lastCandles[lastCandles.length - 1].time === candle.time) {
    lastCandles[lastCandles.length - 1] = candle;
  } else {
    lastCandles.push(candle);
  }
  candleSeries.update(candle);
  updateSMA(lastCandles, smaPeriod(activeSymbol));
  if (marketsData[activeSymbol]) marketsData[activeSymbol].candles = lastCandles;
}

function updateTotal(total) {
  if (!total) return;
  const v = document.getElementById("total-value");
  const p = document.getElementById("total-pnl");
  if (v) v.textContent = fmtMoney(total.total_value);
  if (p) {
    p.textContent = fmtPct(total.pnl_pct);
    p.className = "value " + (total.pnl_pct >= 0 ? "positive" : "negative");
  }
  if (total.benchmark?.vs_hold_pct != null) {
    const vh = document.getElementById("vs-hold");
    if (vh) {
      vh.textContent = fmtPct(total.benchmark.vs_hold_pct);
      vh.className = "value " + (total.benchmark.vs_hold_pct >= 0 ? "positive" : "negative");
    }
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

function updateExchangeControls(enabled) {
  document.querySelectorAll(".testnet-btn").forEach(btn => {
    btn.style.display = enabled ? "" : "none";
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
    const res = await fetch("/api/trades");
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
  ul.innerHTML = all.slice(0, 40).map(t => {
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

function updateTradeMarkers(trades) {
  if (!candleSeries || !trades?.length || !lastCandles.length) return;
  const times = new Set(lastCandles.map(c => c.time));
  const markers = trades.slice(-20).map(t => {
    const bucket = Math.floor(t.ts / 60) * 60;
    const time = times.has(bucket) ? bucket : lastCandles[0]?.time;
    if (!time) return null;
    const buy = t.side === "buy";
    return {
      time,
      position: buy ? "belowBar" : "aboveBar",
      color: buy ? "#00e5a8" : "#ff5c7a",
      shape: buy ? "arrowUp" : "arrowDown",
      text: buy ? "B" : "S",
    };
  }).filter(Boolean);
  candleSeries.setMarkers(markers);
}

function mergeMarket(sym, patch) {
  const label = labelFor(sym);
  if (patch?.symbol && patch.symbol !== sym) return;
  const prev = marketsData[sym] || { symbol: sym, label };
  const safe = { ...patch };
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
  switchMarket(activeSymbol);
  if (msg.brain) renderBrain(msg.brain);
  if (msg.assistant) renderChat([{ role: "assistant", content: msg.assistant }]);
  renderAllTrades();
  setLiveStatus(true);
}

function connectWs() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws`);
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
      }
      if (msg.type === "brain_update" && msg.cycle) {
        renderBrain(msg.cycle);
        if (msg.cycle.verdict) {
          pushActivity(`Мозг: ${msg.cycle.verdict.slice(0, 80)}`);
        }
      }
      if (msg.type === "tick" && msg.symbol) {
        mergeMarket(msg.symbol, {
          price: msg.price,
          portfolio: msg.portfolio,
          strategy: msg.strategy,
        });
        if (msg.symbol === activeSymbol) {
          if (msg.candle) updateLiveCandle(msg.candle);
          renderBotStatus(marketsData[msg.symbol]);
          const fs = document.getElementById("feed-source");
          if (fs && msg.source) fs.textContent = msg.source;
        }
        renderTabs();
        updateTotal(computeTotal());
        setLiveStatus(true);
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
        } else if (msg.mirror?.ok) {
          showToast(`🔗 ${msg.label}: base mirrored (Δ ${msg.mirror.diff})`);
        }
        if (msg.total) updateTotal(msg.total);
        void refreshStatus();
        loadExchangePanel();
      }
      if (msg.type === "trade" && msg.trade) {
        const icon = msg.trade.side === "sell" ? "💵" : "💰";
        showToast(`${icon} ${msg.label || labelFor(msg.symbol)}: ${msg.trade.reason}`);
        pushActivity(`${msg.label || labelFor(msg.symbol)} ${msg.trade.side.toUpperCase()}: ${msg.trade.reason}`);
        renderAllTrades();
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
  switchMarket(activeSymbol);
  if (parsed?.brain) renderBrain(parsed.brain);
  if (data.chat) renderChat([{ role: "assistant", content: data.chat }]);
  if (data.trades?.length) renderTradesList(data.trades);
  else renderAllTrades();
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
  renderAllTables(data);
  setLiveStatus(true);
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
    switchMarket(activeSymbol);
    await renderAllTrades();
    setLiveStatus(true);
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
    const res = await apiFetch("/api/exchange/order", {
      method: "POST",
      body: JSON.stringify({ symbol: activeSymbol, side, amount_usd: 10 }),
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
    showToast(t ? "🔐 Токен сохранён" : "Токен удалён");
  });

  document.querySelectorAll(".manual-btn").forEach(btn => {
    btn.onclick = async () => {
      const side = btn.dataset.side;
      const res = await apiFetch("/api/trade", {
        method: "POST",
        body: JSON.stringify({ symbol: activeSymbol, side, amount_usd: 25 }),
      });
      const data = await res.json();
      if (data.error) showToast("⚠ " + data.error);
      else {
        showToast(`${side === "buy" ? "💰" : "💵"} Ручная ${side} на ${labelFor(activeSymbol)}`);
        await refreshStatus();
      }
    };
  });

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
      if (id === "trades") loadTradesTable(activeSymbol);
      if (id === "shadow") renderShadowLeaderboard();
      if (id === "report") renderDailyReport();
      if (id === "brain-timeline") renderBrainTimeline();
    };
  });

  document.getElementById("btn-backtest-run")?.addEventListener("click", runBacktestTable);
  document.getElementById("btn-backtest-compare")?.addEventListener("click", runBacktestCompare);
  document.getElementById("btn-strategy-apply")?.addEventListener("click", applyStrategy);
  document.getElementById("btn-exchange-refresh")?.addEventListener("click", loadExchangePanel);
  document.getElementById("btn-auto-tactics-refresh")?.addEventListener("click", loadAutoTactics);
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
    const [st, bal, rec] = await Promise.all([
      fetch("/api/exchange/status").then(r => r.json()),
      fetch("/api/exchange/balances").then(r => r.json()),
      fetch(`/api/exchange/reconcile?symbol=${activeSymbol}`).then(r => r.json()),
    ]);
    if (!st.enabled) {
      el.innerHTML = `<p>Paper режим. Задай <code>BINANCE_API_KEY</code> + <code>EXCHANGE_ENABLED=true</code> для testnet.</p>`;
      return;
    }
    const syncParts = [];
    if (st.sync_to_paper) syncParts.push("testnet → paper");
    if (st.sync_from_paper) syncParts.push("paper → testnet");
    const syncNote = syncParts.length
      ? `<p class='muted'>🔗 Sync: ${syncParts.join(" · ")}</p>`
      : "";
    const rows = (bal.balances || []).slice(0, 8).map(b =>
      `<tr><td><b>${b.asset}</b></td><td>${Number(b.free).toFixed(6)}</td><td>${Number(b.locked).toFixed(6)}</td></tr>`
    ).join("") || "<tr><td colspan=3>Нет балансов</td></tr>";
    const syncCls = (rec.base_synced ?? rec.synced) ? "up" : "down";
    el.innerHTML = `
      ${syncNote}
      <p><b>${st.testnet ? "TESTNET" : "LIVE"}</b> · ордер до $${st.max_order_usd} · сегодня ${st.orders_today || 0}</p>
      <table class="data-table compact"><thead><tr><th>Asset</th><th>Free</th><th>Locked</th></tr></thead><tbody>${rows}</tbody></table>
      <p class="muted" style="margin-top:0.5rem">Reconcile <b>${labelFor(activeSymbol)}</b>:</p>
      <p>Base paper <b>${rec.paper_base ?? "—"}</b> · exchange <b>${rec.exchange_base ?? "—"}</b>
        <span class="${syncCls}">Δ ${rec.base_diff ?? "—"}</span></p>
      <p class="muted">${rec.note || ""}</p>`;
  } catch (_) {
    el.textContent = "Не удалось загрузить данные биржи";
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

async function loadExchangeBadge() {
  try {
    const st = await (await fetch("/api/exchange/status")).json();
    updateExchangeControls(!!st.enabled);
    const el = document.getElementById("exchange-badge");
    if (!el) return;
    if (st.enabled) {
      el.textContent = st.testnet ? "TESTNET" : "LIVE";
      el.className = "stat badge " + (st.testnet ? "testnet" : "live-exchange");
      el.title = `Биржа: ${st.exchange} · ордер до $${st.max_order_usd}`;
    } else {
      el.textContent = "PAPER";
      el.className = "stat badge paper";
      el.title = "Paper режим — задай BINANCE_API_KEY для testnet";
    }
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
    await loadAutoTactics();
    await loadAlerts();
    await loadFees();
    await renderHeatmap();
    await loadShadowLab();
    connectWs();
    setInterval(refreshStatus, 5000);
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
