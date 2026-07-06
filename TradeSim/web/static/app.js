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
  if (el) { el.style.display = "block"; el.textContent = "Ошибка: " + msg; }
}

function fmtMoney(n, decimals = 2) {
  if (n == null || isNaN(n)) return "—";
  return "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtPct(n) {
  if (n == null || isNaN(n)) return "—";
  return (n >= 0 ? "+" : "") + Number(n).toFixed(2) + "%";
}

function initChart() {
  const fallback = document.getElementById("chart-fallback");
  if (typeof LightweightCharts === "undefined") {
    if (fallback) fallback.textContent = "График не загрузился. Нажми Ctrl+F5 или проверь интернет.";
    return false;
  }
  const el = document.getElementById("chart");
  if (!el) return false;
  if (fallback) fallback.style.display = "none";
  chart = LightweightCharts.createChart(el, {
    layout: { background: { color: "#161b22" }, textColor: "#8b949e" },
    grid: { vertLines: { color: "#21262d" }, horzLines: { color: "#21262d" } },
    timeScale: { timeVisible: true, secondsVisible: false },
    rightPriceScale: { borderColor: "#30363d" },
    width: el.clientWidth || 600,
    height: 400,
  });
  candleSeries = chart.addCandlestickSeries({
    upColor: "#3fb950", downColor: "#f85149", borderVisible: false,
    wickUpColor: "#3fb950", wickDownColor: "#f85149",
  });
  smaSeries = chart.addLineSeries({ color: "#a371f7", lineWidth: 2 });
  window.addEventListener("resize", () => {
    if (chart && el) chart.applyOptions({ width: el.clientWidth });
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
    const d = marketsData[m.symbol] || {};
    const price = d.price ? fmtMoney(d.price, m.label === "BTC" ? 0 : 2) : "—";
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
  if (!d) return;
  lastCandles = d.candles || [];
  if (candleSeries && lastCandles.length) {
    candleSeries.setData(lastCandles);
    updateSMA(lastCandles);
  }
  const title = document.getElementById("chart-title");
  if (title) title.textContent = `${d.label || symbol}/USDT — свечи`;
  renderBotStatus(d);
  renderAllTrades();
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
    <p>Рынок: <strong>${d.label || "?"}</strong> · ${st.enabled !== false ? "✅ активен" : "⏸ пауза"}</p>
    <p>Цена: <strong>${fmtMoney(d.price, d.label === "BTC" ? 2 : 4)}</strong></p>
    <p>Портфель: <strong>${fmtMoney(d.portfolio?.portfolio_value)}</strong> (${fmtPct(d.portfolio?.pnl_pct)})</p>
    <p>DCA: $${p.dca_amount || "?"} / ${p.dca_interval_hours || "?"}ч</p>
    <p>SMA-20: <strong>${st.sma ? fmtMoney(st.sma) : "—"}</strong></p>
  `;
  const btn = document.getElementById("btn-toggle");
  if (btn) btn.textContent = st.enabled !== false ? "Пауза" : "Старт";
}

function renderAllTrades() {
  const ul = document.getElementById("trades-list");
  if (!ul) return;
  const all = [];
  for (const sym of Object.keys(marketsData)) {
    const d = marketsData[sym];
    (d.trades || []).forEach(t => all.push({ ...t, label: d.label || sym }));
  }
  all.sort((a, b) => b.ts - a.ts);
  if (!all.length) {
    ul.innerHTML = "<li>Пока нет сделок — бот купит при старте или на просадке</li>";
    return;
  }
  ul.innerHTML = all.slice(0, 20).map(t => {
    const d = new Date(t.ts * 1000).toLocaleString("ru-RU");
    return `<li class="${t.side}"><b>${t.label}</b> ${d} · ${t.side.toUpperCase()} @ ${fmtMoney(t.price, 4)} · ${t.reason}</li>`;
  }).join("");
}

function renderChat(messages) {
  if (messages) chatHistory = messages;
  const box = document.getElementById("chat-messages");
  if (!box) return;
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
  if (v) v.textContent = brain.verdict || "Мозг думает...";
  const setAgent = (id, data) => {
    const el = document.getElementById(id);
    if (!el || !data) return;
    el.classList.add("active");
    const sm = el.querySelector("small");
    if (sm && data.summary) sm.textContent = data.summary.slice(0, 70) + (data.summary.length > 70 ? "…" : "");
  };
  setAgent("agent-mentor", brain.mentor);
  setAgent("agent-news", brain.news);
  setAgent("agent-schemer", brain.schemer);
}

function applyWsInit(msg) {
  marketsData = msg.markets || {};
  updateTotal(msg.total);
  renderTabs();
  switchMarket(activeSymbol);
  if (msg.brain) renderBrain(msg.brain);
  if (msg.assistant) {
    renderChat([{ role: "assistant", content: msg.assistant }]);
  }
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
        const prev = marketsData[msg.symbol] || { label: msg.symbol.replace("USDT", "") };
        marketsData[msg.symbol] = {
          ...prev, symbol: msg.symbol, price: msg.price,
          portfolio: msg.portfolio, strategy: msg.strategy,
          candles: prev.candles || [],
        };
        if (msg.symbol === activeSymbol && msg.candle) updateLiveCandle(msg.candle);
        if (msg.symbol === activeSymbol) renderBotStatus(marketsData[msg.symbol]);
        renderTabs();
        setLiveStatus(true);
      }
      if (msg.type === "trade") refreshStatus();
    } catch (e) { console.error(e); }
  };
  ws.onclose = () => setTimeout(connectWs, 3000);
}

async function refreshStatus() {
  const data = await (await fetch("/api/status")).json();
  marketsData = data.markets || marketsData;
  updateTotal(data.total);
  switchMarket(activeSymbol);
  renderAllTrades();
}

async function loadInitial() {
  const res = await fetch("/api/status");
  const data = await res.json();
  marketsData = data.markets || {};
  if (Object.keys(marketsData).length) {
    marketMeta = Object.values(marketsData).map(m => ({ symbol: m.symbol, label: m.label }));
  }
  updateTotal(data.total);
  activeSymbol = marketMeta[0]?.symbol || "BTCUSDT";
  renderTabs();
  switchMarket(activeSymbol);
  renderAllTrades();

  try {
    const chatRes = await fetch("/api/assistant");
    const chatData = await chatRes.json();
    if (chatData.chat?.length) renderChat(chatData.chat);
    else if (chatData.briefing) renderChat([{ role: "assistant", content: chatData.briefing }]);
    if (chatData.brain) renderBrain(chatData.brain);
  } catch (_) {}
}

function bindUi() {
  const toggle = document.getElementById("btn-toggle");
  if (toggle) toggle.onclick = async () => {
    await fetch(`/api/bot/toggle?symbol=${activeSymbol}`, { method: "POST" });
    await refreshStatus();
  };

  const form = document.getElementById("chat-form");
  if (form) form.onsubmit = async (e) => {
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

  const reset = document.getElementById("btn-reset");
  if (reset) reset.onclick = async () => {
    if (!confirm("Сбросить все 4 счёта?")) return;
    await fetch("/api/reset", { method: "POST" });
    location.reload();
  };
}

async function main() {
  try {
    bindUi();
    if (!initChart()) showError("библиотека графика не загрузилась");
    await loadInitial();
    connectWs();
    setInterval(refreshStatus, 8000);
  } catch (e) {
    showError(e.message);
    console.error(e);
  }
}

main();
