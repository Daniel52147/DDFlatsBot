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
    const price = d?.price > 0 ? fmtMoney(d.price, m.label === "BTC" ? 0 : 2) : "…";
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
  try {
    const res = await fetch("/api/trades");
    const data = await res.json();
    const all = data.trades || [];
    if (!all.length) {
      ul.innerHTML = "<li>Сделок пока нет — появятся после DCA-покупки</li>";
      return;
    }
    ul.innerHTML = all.slice(0, 20).map(t => {
      const d = new Date(t.ts * 1000).toLocaleString("ru-RU");
      return `<li class="${t.side}"><b>${t.label}</b> ${d} · ${t.side.toUpperCase()} @ ${fmtMoney(t.price, 4)} · ${t.reason}</li>`;
    }).join("");
  } catch (_) {
    ul.innerHTML = "<li>Не удалось загрузить сделки</li>";
  }
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

function mergeMarket(sym, patch) {
  const prev = marketsData[sym] || { symbol: sym, label: labelFor(sym) };
  marketsData[sym] = { ...prev, ...patch, symbol: sym, label: prev.label || labelFor(sym) };
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

function computeTotal() {
  let sum = 0;
  for (const sym of Object.keys(marketsData)) {
    sum += marketsData[sym]?.portfolio?.portfolio_value || 0;
  }
  if (sum <= 0) return null;
  const start = 10000;
  return { total_value: sum, pnl_pct: ((sum - start) / start) * 100, start_balance: start };
}

async function refreshStatus() {
  try {
    const data = await (await fetch("/api/status")).json();
    if (data.markets) {
      for (const [sym, payload] of Object.entries(data.markets)) {
        mergeMarket(sym, payload);
      }
    }
    updateTotal(data.total || computeTotal());
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
    const data = await res.json();
    if (data.cycle) renderBrain(data.cycle);
  } catch (_) {}
}

async function checkServer() {
  try {
    const res = await fetch("/api/ping");
    const data = await res.json();
    if (!data.markets || data.markets.length < 4) {
      showError("Старый сервер! Останови (Ctrl+C) и снова: python main.py");
    }
    return data;
  } catch (_) {
    showError("Сервер не отвечает — запусти python main.py");
    return null;
  }
}

async function loadInitial() {
  await checkServer();
  await refreshStatus();

  try {
    const chatRes = await fetch("/api/assistant");
    const chatData = await chatRes.json();
    if (chatData.briefing) {
      renderChat([{ role: "assistant", content: chatData.briefing }]);
    }
    if (chatData.brain) renderBrain(chatData.brain);
  } catch (_) {}

  await loadBrain();
  await renderAllTrades();

  if (!marketsData[activeSymbol]?.price) {
    showError("Данные грузятся... если через 30 сек пусто — Ctrl+C и python main.py заново");
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
    setInterval(loadBrain, 60000);
  } catch (e) {
    showError(e.message);
  }
}

main();
