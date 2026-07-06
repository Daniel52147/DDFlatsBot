let chart, candleSeries, smaSeries;
let smaData = [];
let botEnabled = true;

function fmtMoney(n) {
  if (n == null || isNaN(n)) return "—";
  return "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(n) {
  if (n == null || isNaN(n)) return "—";
  const sign = n >= 0 ? "+" : "";
  return sign + Number(n).toFixed(2) + "%";
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
    upColor: "#3fb950",
    downColor: "#f85149",
    borderVisible: false,
    wickUpColor: "#3fb950",
    wickDownColor: "#f85149",
  });
  smaSeries = chart.addLineSeries({ color: "#a371f7", lineWidth: 2, title: "SMA" });
  window.addEventListener("resize", () => chart.applyOptions({ width: el.clientWidth }));
}

function updateSMA(candles, period = 20) {
  smaData = [];
  for (let i = period - 1; i < candles.length; i++) {
    const slice = candles.slice(i - period + 1, i + 1);
    const avg = slice.reduce((s, c) => s + c.close, 0) / period;
    smaData.push({ time: candles[i].time, value: avg });
  }
  smaSeries.setData(smaData);
}

function updatePortfolio(p) {
  document.getElementById("live-price").textContent = fmtMoney(p.price);
  document.getElementById("portfolio-value").textContent = fmtMoney(p.portfolio_value);
  const pnlEl = document.getElementById("pnl");
  pnlEl.textContent = fmtPct(p.pnl_pct) + " (vs hold " + fmtPct(p.vs_hold_pct) + ")";
  pnlEl.className = "value " + (p.pnl_pct >= 0 ? "positive" : "negative");
}

function renderBotStatus(strategy) {
  const el = document.getElementById("bot-status");
  const p = strategy.params || {};
  el.innerHTML = `
    <p>Статус: <strong>${strategy.enabled ? "активен" : "пауза"}</strong></p>
    <p>DCA: <strong>$${p.dca_amount}</strong> каждые <strong>${p.dca_interval_hours}ч</strong></p>
    <p>DIP: +$${p.dip_extra_amount} если ниже SMA на <strong>${p.dip_threshold_pct}%</strong></p>
    <p>SMA-${p.sma_period}: <strong>${strategy.sma ? fmtMoney(strategy.sma) : "—"}</strong></p>
    <p>След. DCA: ~<strong>${strategy.next_dca_in_hours}ч</strong></p>
  `;
  botEnabled = strategy.enabled;
  document.getElementById("btn-toggle").textContent = strategy.enabled ? "Пауза" : "Старт";
}

function renderTrades(trades) {
  const ul = document.getElementById("trades-list");
  if (!trades || !trades.length) {
    ul.innerHTML = "<li>Пока нет сделок — бот учится...</li>";
    return;
  }
  ul.innerHTML = trades.slice().reverse().map(t => {
    const d = new Date(t.ts * 1000).toLocaleString("ru-RU");
    return `<li class="${t.side}">${d} · ${t.side.toUpperCase()} @ ${fmtMoney(t.price)} · ${t.reason}</li>`;
  }).join("");
}

function connectWs() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "init") {
      candleSeries.setData(msg.candles || []);
      updateSMA(msg.candles || []);
      updatePortfolio({ ...msg.portfolio, price: msg.price });
      renderBotStatus(msg.strategy);
      document.getElementById("assistant-text").textContent = msg.assistant || "";
    }
    if (msg.type === "tick") {
      updatePortfolio({ ...msg.portfolio, price: msg.price });
    }
    if (msg.type === "candle") {
      candleSeries.update(msg.candle);
      fetch("/api/status").then(r => r.json()).then(d => {
        updateSMA(d.candles);
        renderTrades(d.trades);
        renderBotStatus(d.strategy);
      });
    }
    if (msg.type === "trade") {
      fetch("/api/status").then(r => r.json()).then(d => renderTrades(d.trades));
    }
    if (msg.type === "strategy_update") {
      document.getElementById("assistant-text").textContent =
        "🧠 " + msg.reason + "\n\n" + document.getElementById("assistant-text").textContent;
    }
  };

  ws.onclose = () => setTimeout(connectWs, 3000);
  setInterval(() => { if (ws.readyState === 1) ws.send("ping"); }, 25000);
}

async function loadInitial() {
  const res = await fetch("/api/status");
  const data = await res.json();
  candleSeries.setData(data.candles || []);
  updateSMA(data.candles || []);
  updatePortfolio({ ...data.portfolio, price: data.price });
  renderBotStatus(data.strategy);
  renderTrades(data.trades);
  document.getElementById("assistant-text").textContent = data.assistant_briefing || "";
}

document.getElementById("btn-toggle").onclick = async () => {
  await fetch("/api/bot/toggle", { method: "POST" });
  const d = await (await fetch("/api/status")).json();
  renderBotStatus(d.strategy);
};

document.getElementById("btn-refresh-assistant").onclick = async () => {
  const d = await (await fetch("/api/assistant")).json();
  document.getElementById("assistant-text").textContent = d.briefing;
};

document.getElementById("btn-reset").onclick = async () => {
  if (!confirm("Сбросить виртуальный счёт на $10,000?")) return;
  await fetch("/api/reset", { method: "POST" });
  location.reload();
};

initChart();
loadInitial().then(connectWs);
