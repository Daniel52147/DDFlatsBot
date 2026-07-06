let chart, candleSeries, smaSeries;
let lastCandles = [];
let marketsData = {};
let activeSymbol = "BTCUSDT";
let marketMeta = [
  { symbol: "BTCUSDT", label: "BTC" },
  { symbol: "ETHUSDT", label: "ETH" },
  { symbol: "SOLUSDT", label: "SOL" },
  { symbol: "BNBUSDT", label: "BNB" },
];
let chatHistory = [];

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
    layout: { background: { color: "#161b22" }, textColor: "#8b949e" },
    grid: { vertLines: { color: "#21262d" }, horzLines: { color: "#21262d" } },
    timeScale: { timeVisible: true, secondsVisible: false },
    rightPriceScale: { borderColor: "#30363d" },
    width: w,
    height: 400,
  });
  candleSeries = chart.addCandlestickSeries({
    upColor: "#3fb950", downColor: "#f85149", borderVisible: false,
    wickUpColor: "#3fb950", wickDownColor: "#f85149",
  });
  smaSeries = chart.addLineSeries({ color: "#a371f7", lineWidth: 2 });
  window.addEventListener("resize", () => {
    if (chart && el) chart.applyOptions({ width: el.clientWidth || w });
  });
  return true;
}

function updateSMA(candles, period = 20) {
  if (!smaSeries || !candles?.length) return;
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

function renderTabs() {
  const nav = document.getElementById("market-tabs");
  if (!nav) return;
  nav.innerHTML = marketMeta.map(m => {
    const d = marketsData[m.symbol];
    const price = d?.price != null && !isNaN(d.price) ? fmtMoney(d.price, m.label === "BTC" ? 0 : 2) : "…";
    const active = m.symbol === activeSymbol ? " active" : "";
    return `<button type="button" class="tab${active}" data-symbol="${m.symbol}">${m.label}<span>${price}</span></button>`;
  }).join("");
  nav.querySelectorAll(".tab").forEach(btn => {
    btn.onclick = () => switchMarket(btn.dataset.symbol);
  });
}

function switchMarket(symbol) {
  activeSymbol = symbol;
  const d = marketsData[symbol];
  if (!d) {
    document.getElementById("bot-status").innerHTML = "<p>Загрузка данных с сервера...</p>";
    return;
  }
  lastCandles = d.candles || [];
  if (candleSeries) {
    if (lastCandles.length) {
      candleSeries.setData(lastCandles);
      updateSMA(lastCandles);
    }
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
  updateSMA(lastCandles);
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
  el.innerHTML = `
    <p>Рынок: <strong>${d.label || labelFor(d.symbol)}</strong> · ${st.enabled !== false ? "✅ активен" : "⏸ пауза"}</p>
    <p>Цена: <strong>${fmtMoney(d.price, d.label === "BTC" ? 2 : 4)}</strong></p>
    <p>Портфель: <strong>${fmtMoney(d.portfolio?.portfolio_value)}</strong> (${fmtPct(d.portfolio?.pnl_pct)})</p>
    <p>DCA: $${p.dca_amount ?? 25} / ${p.dca_interval_hours ?? 24}ч</p>
    <p>SMA-20: <strong>${st.sma ? fmtMoney(st.sma) : "—"}</strong></p>
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
    return `<li class="${t.side}"><b>${t.label}</b> ${d} · ${t.side.toUpperCase()} @ ${fmtMoney(t.price, 4)} · ${t.reason}</li>`;
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

function renderBrain(brain) {
  if (!brain) return;
  const v = document.getElementById("brain-verdict");
  if (v) v.textContent = brain.verdict || "Мозг анализирует рынки...";
  [["agent-mentor", brain.mentor], ["agent-news", brain.news], ["agent-schemer", brain.schemer]].forEach(([id, data]) => {
    const el = document.getElementById(id);
    if (!el || !data) return;
    el.classList.add("active");
    const sm = el.querySelector("small");
    if (sm && data.summary) sm.textContent = data.summary.slice(0, 75) + (data.summary.length > 75 ? "…" : "");
  });
}

const PRICE_RANGE = {
  BTC: [1000, 500000],
  ETH: [100, 50000],
  SOL: [1, 2000],
  BNB: [10, 5000],
};

function priceOk(label, price) {
  if (price == null || isNaN(price)) return false;
  const r = PRICE_RANGE[label];
  if (!r) return price > 0;
  return price >= r[0] && price <= r[1];
}

function mergeMarket(sym, patch) {
  const label = labelFor(sym);
  if (patch?.symbol && patch.symbol !== sym) return; // не подмешивать чужой рынок
  if (patch?.price != null && !priceOk(label, patch.price)) return; // ETH не может стоить $62000
  const prev = marketsData[sym] || { symbol: sym, label };
  marketsData[sym] = { ...prev, ...patch, symbol: sym, label: prev.label || label };
}

function applyWsInit(msg) {
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
        if (msg.cycle.summary) {
          chatHistory.push({ role: "assistant", content: msg.cycle.summary });
          renderChat();
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
  const start = 10000;
  return { total_value: sum, pnl_pct: ((sum - start) / start) * 100, start_balance: start };
}

function applyBootstrap(data) {
  if (!data) return false;
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
    return `<li class="${t.side}"><b>${t.label}</b> ${d} · ${t.side.toUpperCase()} @ ${fmtMoney(t.price, 4)} · ${t.reason}</li>`;
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
  // DCA $100 = старая версия, должно быть $25
  const dca = marketsData[activeSymbol]?.strategy?.params?.dca_amount;
  if (dca && dca >= 100) {
    showError("Старая версия бота (DCA $100). Сделай git pull и перезапусти python main.py");
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
    if (!confirm("Сбросить все 4 счёта?")) return;
    await fetch("/api/reset", { method: "POST" });
    location.reload();
  };
}

async function main() {
  try {
    bindUi();
    if (!initChart()) showError("График: проверь интернет, нажми Ctrl+F5");
    await loadInitial();
    connectWs();
    setInterval(refreshStatus, 5000);
    setInterval(loadBrain, 15000);
  } catch (e) {
    showError(e.message);
  }
}

main();
