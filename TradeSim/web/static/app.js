let chart, candleSeries, smaSeries;
let equityChart, equitySeries;
let lastCandles = [];
let marketsData = {};
let activeSymbol = "BTCUSDT";
let marketMeta = [
  { symbol: "BTCUSDT", label: "BTC" },
  { symbol: "ETHUSDT", label: "ETH" },
  { symbol: "SOLUSDT", label: "SOL" },
  { symbol: "BNBUSDT", label: "BNB" },
  { symbol: "DOGEUSDT", label: "DOGE", volatile: true },
  { symbol: "PEPEUSDT", label: "PEPE", volatile: true },
];
let startBalance = 10000;
let chatHistory = [];
let lastBrain = null;
let activityLog = [];
let lastAnalytics = null;

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
    height: 400,
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
    lineColor: "#00e5c0",
    topColor: "rgba(0, 229, 192, 0.28)",
    bottomColor: "rgba(0, 229, 192, 0.02)",
    lineWidth: 2,
  });
  window.addEventListener("resize", () => {
    if (equityChart && el) equityChart.applyOptions({ width: el.clientWidth || 400 });
  });
  return true;
}

function renderEquityCurve(points) {
  if (!equitySeries || !points?.length) return;
  const data = points.map(p => ({
    time: p.time,
    value: p.value,
  }));
  equitySeries.setData(data);
  const last = points[points.length - 1];
  const lbl = document.getElementById("equity-label");
  if (lbl && last) {
    lbl.textContent = `48ч · ${fmtMoney(last.value)} (${fmtPct(last.pnl_pct ?? 0)})`;
  }
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
      <div class="lp-row"><span class="lp-label">Опережают hold</span><span class="lp-val">${a.markets_beating_hold ?? 0}/${a.markets_total ?? 6}</span></div>
      <div class="lp-row"><span class="lp-label">Среднее vs hold</span><span class="lp-val">${fmtPct(a.avg_vs_hold_pct)}</span></div>
      ${a.sharpe_proxy != null ? `<div class="lp-row"><span class="lp-label">Sharpe (proxy)</span><span class="lp-val">${a.sharpe_proxy}</span></div>` : ""}
    `;
  }
  el.innerHTML = `
    <div class="lp-row"><span class="lp-label">Сделок в БД</span><span class="lp-val">${learning?.trade_count || a?.total_trades || 0}</span></div>
    <div class="lp-row"><span class="lp-label">Продаж / TP / SL</span><span class="lp-val">${a?.total_sells ?? "—"}</span></div>
    <div class="lp-row"><span class="lp-label">Мозг · 11 агентов</span><span class="lp-val">каждые 45 сек</span></div>
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
    return `<button type="button" class="pf-cell${active}${vol}" data-symbol="${m.symbol}">
      <span class="pf-label">${m.label}${m.volatile ? " ⚡" : ""}</span>
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
    const active = m.symbol === activeSymbol ? " active" : "";
    return `<button type="button" class="tab${active}${vol}" data-symbol="${m.symbol}">${m.label}<span>${price}</span></button>`;
  }).join("");
  nav.querySelectorAll(".tab").forEach(btn => {
    btn.onclick = () => switchMarket(btn.dataset.symbol);
  });
  renderPortfolioGrid();
}

function switchMarket(symbol) {
  activeSymbol = symbol;
  const d = marketsData[symbol];
  if (!d) {
    document.getElementById("bot-status").innerHTML = "<p>Загрузка данных с сервера...</p>";
    return;
  }
  lastCandles = d.candles || [];
  const period = smaPeriod(symbol);
  if (candleSeries && lastCandles.length) {
    candleSeries.setData(lastCandles);
    updateSMA(lastCandles, period);
    updateTradeMarkers(d.trades || []);
  }
  const title = document.getElementById("chart-title");
  if (title) title.textContent = `${d.label || labelFor(symbol)}/USDT — свечи`;
  renderBotStatus(d);
  renderTabs();
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
}

function renderBotStatus(d) {
  const el = document.getElementById("bot-status");
  if (!el || !d) return;
  const st = d.strategy || {};
  const p = st.params || {};
  const lbl = d.label || labelFor(d.symbol);
  const vol = d.volatile ? " ⚡ волатильный" : "";
  let spike = "";
  if (p.spike_threshold_pct) {
    spike = `<p>SPIKE: +$${p.spike_extra_amount} при просадке ≥${p.spike_threshold_pct}%</p>`;
  }
  let tp = "";
  if (p.take_profit_pct) {
    tp = `<p>TAKE-PROFIT: ${Math.round((p.take_profit_fraction || 0.15) * 100)}% позиции при +${p.take_profit_pct}% над SMA</p>`;
  }
  let sl = "";
  if (p.stop_loss_pct) {
    sl = `<p>STOP-LOSS: −${p.stop_loss_pct}% от входа → продажа ${Math.round((p.stop_loss_fraction || 0.2) * 100)}%</p>`;
  }
  const avg = st.avg_entry || d.portfolio?.avg_entry;
  el.innerHTML = `
    <p>Рынок: <strong>${lbl}</strong>${vol}${d.restored ? " · 💾 восстановлен" : ""} · ${st.enabled !== false ? "✅ активен" : "⏸ пауза"}</p>
    <p>Цена: <strong>${fmtMoney(d.price, priceDecimals(lbl))}</strong>${avg ? ` · вход ~${fmtMoney(avg, priceDecimals(lbl))}` : ""}</p>
    <p>Портфель: <strong>${fmtMoney(d.portfolio?.portfolio_value)}</strong> (${fmtPct(d.portfolio?.pnl_pct)}) · vs hold ${fmtPct(d.portfolio?.vs_hold_pct)}</p>
    <p>DCA: $${p.dca_amount ?? 25} / ${p.dca_interval_hours ?? 24}ч · DIP ${p.dip_threshold_pct ?? 3}% (кд ${p.dip_cooldown_minutes ?? 30}м)</p>
    ${spike}${tp}${sl}
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
  ul.innerHTML = all.slice(0, 20).map(t => {
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
  DOGE: [0.001, 10],
  PEPE: [0.0000001, 0.01],
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
  if (patch?.symbol && patch.symbol !== sym) return; // не подмешивать чужой рынок
  if (patch?.price != null && !priceOk(label, patch.price)) return; // ETH не может стоить $62000
  const prev = marketsData[sym] || { symbol: sym, label };
  marketsData[sym] = { ...prev, ...patch, symbol: sym, label: prev.label || label };
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
      if (msg.type === "trade" && msg.trade) {
        const icon = msg.trade.side === "sell" ? "💵" : "💰";
        showToast(`${icon} ${msg.label || labelFor(msg.symbol)}: ${msg.trade.reason}`);
        pushActivity(`${msg.label || labelFor(msg.symbol)} ${msg.trade.side.toUpperCase()}: ${msg.trade.reason}`);
      }
      if (msg.type === "trade") {
        renderAllTrades();
        refreshStatus();
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
  for (const sym of Object.keys(markets)) {
    sum += markets[sym]?.portfolio?.portfolio_value || 0;
  }
  if (sum <= 0) return null;
  const start = startBalance;
  return { total_value: sum, pnl_pct: ((sum - start) / start) * 100, start_balance: start };
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
  ul.innerHTML = all.slice(0, 20).map(t => {
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
    const res = await fetch("/api/bootstrap");
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

async function loadInitial() {
  let ok = loadEmbeddedData();
  if (!ok) ok = await fetchBootstrap();
  if (!ok) await refreshStatus();
  await loadBrain();
  if (!marketsData[activeSymbol]?.price) {
    showError("Обнови код: git pull → Ctrl+C → python main.py → Ctrl+Shift+R");
  }
}

function bindUi() {
  document.getElementById("btn-toggle").onclick = async () => {
    await fetch(`/api/bot/toggle?symbol=${activeSymbol}`, { method: "POST" });
    await refreshStatus();
  };

  document.getElementById("chat-form").onsubmit = async (e) => {
    e.preventDefault();
    const input = document.getElementById("chat-input");
    const text = input?.value?.trim();
    if (!text) return;
    input.value = "";
    chatHistory.push({ role: "user", content: text });
    renderChat();
    const res = await fetch("/api/assistant/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    if (data.chat) renderChat(data.chat);
    else if (data.reply) {
      chatHistory.push({ role: "assistant", content: data.reply });
      renderChat();
    }
  };

  document.getElementById("btn-reset").onclick = async () => {
    if (!confirm(`Сбросить портфели ${marketMeta.length} рынков? (сделки в БД останутся)`)) return;
    await fetch("/api/reset", { method: "POST" });
    location.reload();
  };

  document.getElementById("btn-reset-full")?.addEventListener("click", async () => {
    if (!confirm("ПОЛНЫЙ сброс: портфели + все сделки и история в SQLite. Продолжить?")) return;
    await fetch("/api/reset?full=true", { method: "POST" });
    location.reload();
  });

  document.getElementById("btn-export")?.addEventListener("click", async () => {
    try {
      const data = await (await fetch("/api/export/trades")).json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `tradesim-trades-v${data.version || 9}.json`;
      a.click();
      showToast(`Экспорт: ${data.count || 0} сделок`);
    } catch (_) {
      showToast("Ошибка экспорта");
    }
  });

  document.querySelectorAll(".manual-btn").forEach(btn => {
    btn.onclick = async () => {
      const side = btn.dataset.side;
      const res = await fetch("/api/trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
  } catch (_) {}
}

async function main() {
  try {
    bindUi();
    if (!initChart()) showError("График: проверь интернет, нажми Ctrl+F5");
    initEquityChart();
    await loadInitial();
    connectWs();
    setInterval(refreshStatus, 5000);
    setInterval(loadBrain, 15000);
    setInterval(loadLearning, 60000);
  } catch (e) {
    showError(e.message);
  }
}

main();
