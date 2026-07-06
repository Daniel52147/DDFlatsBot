let chart, candleSeries, smaSeries;
let lastCandles = [];
let marketsData = {};
let activeSymbol = "BTCUSDT";
let marketMeta = [];

function fmtMoney(n, decimals = 2) {
  if (n == null || isNaN(n)) return "—";
  return "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtPct(n) {
  if (n == null || isNaN(n)) return "—";
  return (n >= 0 ? "+" : "") + Number(n).toFixed(2) + "%";
}

function initChart() {
  const el = document.getElementById("chart");
  chart = LightweightCharts.createChart(el, {
    layout: { background: { color: "#161b22" }, textColor: "#8b949e" },
    grid: { vertLines: { color: "#21262d" }, horzLines: { color: "#21262d" } },
    timeScale: { timeVisible: true, secondsVisible: false },
    rightPriceScale: { borderColor: "#30363d" },
  });
  candleSeries = chart.addCandlestickSeries({
    upColor: "#3fb950", downColor: "#f85149", borderVisible: false,
    wickUpColor: "#3fb950", wickDownColor: "#f85149",
  });
  smaSeries = chart.addLineSeries({ color: "#a371f7", lineWidth: 2 });
  window.addEventListener("resize", () => chart.applyOptions({ width: el.clientWidth }));
}

function updateSMA(candles, period = 20) {
  const smaData = [];
  for (let i = period - 1; i < candles.length; i++) {
    const slice = candles.slice(i - period + 1, i + 1);
    smaData.push({ time: candles[i].time, value: slice.reduce((s, c) => s + c.close, 0) / period });
  }
  smaSeries.setData(smaData);
}

function setLiveStatus(ok) {
  const el = document.getElementById("live-status");
  el.textContent = ok ? "● LIVE" : "○ пауза";
  el.className = "value live-dot" + (ok ? "" : " stale");
}

function renderTabs() {
  const nav = document.getElementById("market-tabs");
  nav.innerHTML = marketMeta.map(m => {
    const d = marketsData[m.symbol];
    const price = d ? fmtMoney(d.price, m.label === "BTC" ? 0 : 2) : "—";
    const active = m.symbol === activeSymbol ? " active" : "";
    return `<button class="tab${active}" data-symbol="${m.symbol}">${m.label} <span>${price}</span></button>`;
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
  candleSeries.setData(lastCandles);
  updateSMA(lastCandles);
  document.getElementById("chart-title").textContent = `${d.label}/USDT — свечи`;
  renderBotStatus(d);
  renderTrades(d.trades);
  renderTabs();
}

function updateLiveCandle(candle) {
  if (!candle || activeSymbol && marketsData[activeSymbol]) {
    const d = marketsData[activeSymbol];
    if (d && candle) {
      if (lastCandles.length && lastCandles[lastCandles.length - 1].time === candle.time) {
        lastCandles[lastCandles.length - 1] = candle;
      } else {
        lastCandles.push(candle);
      }
      candleSeries.update(candle);
      updateSMA(lastCandles);
    }
  }
}

function updateTotal(total) {
  if (!total) return;
  document.getElementById("total-value").textContent = fmtMoney(total.total_value);
  const el = document.getElementById("total-pnl");
  el.textContent = fmtPct(total.pnl_pct);
  el.className = "value " + (total.pnl_pct >= 0 ? "positive" : "negative");
}

function renderBotStatus(d) {
  const st = d.strategy || {};
  const p = st.params || {};
  document.getElementById("bot-status").innerHTML = `
    <p>Рынок: <strong>${d.label}</strong> · ${st.enabled ? "активен" : "пауза"}</p>
    <p>Цена: <strong>${fmtMoney(d.price, 4)}</strong></p>
    <p>Портфель: <strong>${fmtMoney(d.portfolio?.portfolio_value)}</strong> (${fmtPct(d.portfolio?.pnl_pct)})</p>
    <p>DCA: $${p.dca_amount} / ${p.dca_interval_hours}ч · DIP: ${p.dip_threshold_pct}%</p>
    <p>SMA-${p.sma_period}: <strong>${st.sma ? fmtMoney(st.sma) : "—"}</strong></p>
  `;
  document.getElementById("btn-toggle").textContent = st.enabled ? "Пауза" : "Старт";
}

function renderTrades(trades) {
  const ul = document.getElementById("trades-list");
  if (!trades?.length) {
    ul.innerHTML = "<li>Пока нет сделок на этом рынке</li>";
    return;
  }
  ul.innerHTML = trades.slice().reverse().map(t => {
    const d = new Date(t.ts * 1000).toLocaleString("ru-RU");
    return `<li class="${t.side}">${d} · ${t.side.toUpperCase()} @ ${fmtMoney(t.price, 4)} · ${t.reason}</li>`;
  }).join("");
}

function renderChat(messages) {
  const box = document.getElementById("chat-messages");
  box.innerHTML = (messages || []).map(m => {
    const cls = m.role === "user" ? "chat-user" : "chat-bot";
    return `<div class="chat-bubble ${cls}">${escapeHtml(m.content).replace(/\n/g, "<br>")}</div>`;
  }).join("");
  box.scrollTop = box.scrollHeight;
}

function escapeHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function applyMarketUpdate(symbol, data) {
  marketsData[symbol] = { ...marketsData[symbol], ...data };
  if (symbol === activeSymbol) {
    if (data.candle) updateLiveCandle(data.candle);
    if (data.portfolio) renderBotStatus(marketsData[symbol]);
    if (data.strategy) renderBotStatus(marketsData[symbol]);
  }
  renderTabs();
}

function renderBrain(brain) {
  if (!brain) return;
  const v = document.getElementById("brain-verdict");
  if (v) v.textContent = brain.verdict || "—";
  const setAgent = (id, data) => {
    const el = document.getElementById(id);
    if (!el || !data) return;
    el.classList.add("active");
    const sm = el.querySelector("small");
    if (sm) sm.textContent = (data.summary || "").slice(0, 60) + "...";
  };
  setAgent("agent-mentor", brain.mentor);
  setAgent("agent-news", brain.news);
  setAgent("agent-schemer", brain.schemer);
}

function connectWs() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws`);
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "init") {
      marketsData = msg.markets || {};
      updateTotal(msg.total);
      switchMarket(activeSymbol);
      if (msg.assistant) renderChat([{ role: "assistant", content: msg.assistant }]);
      if (msg.brain) renderBrain(msg.brain);
      setLiveStatus(true);
    }
    if (msg.type === "brain_update") {
      renderBrain(msg.cycle);
      if (msg.cycle?.summary) {
        renderChat([{ role: "assistant", content: msg.cycle.summary }]);
      }
    }
    if (msg.type === "tick" && msg.symbol) {
      const prev = marketsData[msg.symbol] || {};
      marketsData[msg.symbol] = {
        ...prev,
        symbol: msg.symbol,
        label: prev.label || msg.symbol.replace("USDT", ""),
        price: msg.price,
        portfolio: msg.portfolio,
        strategy: msg.strategy,
        candle: msg.candle,
      };
      if (msg.symbol === activeSymbol && msg.candle) updateLiveCandle(msg.candle);
      if (msg.symbol === activeSymbol && msg.portfolio) renderBotStatus(marketsData[msg.symbol]);
      renderTabs();
      setLiveStatus(true);
    }
    if (msg.type === "trade" && msg.symbol === activeSymbol) {
      fetch(`/api/status?symbol=${activeSymbol}`).then(r => r.json()).then(d => {
        marketsData[activeSymbol] = d;
        renderTrades(d.trades);
      });
    }
  };
  ws.onclose = () => setTimeout(connectWs, 3000);
}

async function loadInitial() {
  const res = await fetch("/api/status");
  const data = await res.json();
  marketsData = data.markets || {};
  marketMeta = Object.values(marketsData).map(m => ({ symbol: m.symbol, label: m.label }));
  if (!marketMeta.length) {
    const mr = await fetch("/api/markets");
    const md = await mr.json();
    marketMeta = md.markets.map(m => ({ symbol: m.symbol, label: m.label }));
  }
  updateTotal(data.total);
  activeSymbol = marketMeta[0]?.symbol || "BTCUSDT";
  switchMarket(activeSymbol);
  const chatRes = await fetch("/api/assistant");
  const chatData = await chatRes.json();
  renderChat(chatData.chat || [{ role: "assistant", content: chatData.briefing }]);
  if (chatData.brain) renderBrain(chatData.brain);
}

document.getElementById("btn-toggle").onclick = async () => {
  await fetch(`/api/bot/toggle?symbol=${activeSymbol}`, { method: "POST" });
  const d = await (await fetch(`/api/status?symbol=${activeSymbol}`)).json();
  marketsData[activeSymbol] = d;
  renderBotStatus(d);
};

document.getElementById("chat-form").onsubmit = async (e) => {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  const prev = await (await fetch("/api/assistant")).json();
  const interim = [...(prev.chat || []), { role: "user", content: text }];
  renderChat(interim);
  const res = await fetch("/api/assistant/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text }),
  });
  const data = await res.json();
  renderChat(data.chat);
};

document.getElementById("btn-reset").onclick = async () => {
  if (!confirm("Сбросить все 4 счёта по $2 500?")) return;
  await fetch("/api/reset", { method: "POST" });
  location.reload();
};

setInterval(async () => {
  try {
    const data = await (await fetch("/api/status")).json();
    marketsData = data.markets || marketsData;
    updateTotal(data.total);
    const d = marketsData[activeSymbol];
    if (d?.candles?.length) {
      const last = d.candles[d.candles.length - 1];
      updateLiveCandle(last);
    }
    renderTabs();
    setLiveStatus(true);
  } catch (_) { setLiveStatus(false); }
}, 5000);

initChart();
loadInitial().then(connectWs);
