const API = "/api/v1";

const sliders = {
  normal: document.getElementById("normal-slider"),
  wick: document.getElementById("wick-slider"),
  ultra: document.getElementById("ultra-slider"),
};

const labels = {
  normal: document.getElementById("normal-val"),
  wick: document.getElementById("wick-val"),
  ultra: document.getElementById("ultra-val"),
};

const allocTotal = document.getElementById("alloc-total");
const allocError = document.getElementById("alloc-error");
const saveBtn = document.getElementById("save-alloc");

const chartMap = {
  NIFTY: document.getElementById("chart-nifty"),
  ATM_CE: document.getElementById("chart-atm-ce"),
  ATM_PE: document.getElementById("chart-atm-pe"),
};

function formatCurrency(n) {
  return "₹" + Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function updateAllocationUI() {
  const n = Number(sliders.normal.value);
  const w = Number(sliders.wick.value);
  const u = Number(sliders.ultra.value);
  const total = n + w + u;

  labels.normal.textContent = n + "%";
  labels.wick.textContent = w + "%";
  labels.ultra.textContent = u + "%";
  allocTotal.textContent = total + "%";

  const valid = Math.abs(total - 100) < 0.01;
  allocError.classList.toggle("hidden", valid);
  saveBtn.disabled = !valid;
}

Object.values(sliders).forEach((s) => s.addEventListener("input", updateAllocationUI));

saveBtn.addEventListener("click", async () => {
  const body = {
    normal: Number(sliders.normal.value),
    wick: Number(sliders.wick.value),
    ultra: Number(sliders.ultra.value),
  };
  const res = await fetch(`${API}/engines/allocations`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    saveBtn.textContent = "Saved ✓";
    setTimeout(() => { saveBtn.textContent = "Save Allocation"; }, 2000);
  }
});

function applyBias(bias) {
  const display = document.getElementById("bias-display");
  const direction = document.getElementById("bias-direction");
  const confidence = document.getElementById("bias-confidence");
  const locked = document.getElementById("bias-locked");

  direction.textContent = bias.direction;
  confidence.textContent = bias.confidence_pct.toFixed(1) + "%";

  display.className = "bias-display " + bias.direction.toLowerCase();
  locked.classList.toggle("hidden", !bias.locked);
}

function renderEngines(engines) {
  const list = document.getElementById("engines-list");
  list.innerHTML = engines.map((e) => `
    <div class="engine-item">
      <span class="name">${e.name} Engine</span>
      <span>
        <span class="status">${e.status}</span>
        · ${e.allocation_pct}% · ${formatCurrency(e.allocated_margin)}
      </span>
    </div>
  `).join("");
}

function drawCandles(canvas, candles) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  if (!candles.length) {
    ctx.fillStyle = "#444";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Awaiting live ticks", w / 2, h / 2);
    return;
  }

  const prices = candles.flatMap((c) => [c.high, c.low]);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const barW = Math.max(2, (w - 20) / candles.length - 2);

  candles.forEach((c, i) => {
    const x = 10 + i * (barW + 2);
    const yHigh = 10 + ((max - c.high) / range) * (h - 20);
    const yLow = 10 + ((max - c.low) / range) * (h - 20);
    const yOpen = 10 + ((max - c.open) / range) * (h - 20);
    const yClose = 10 + ((max - c.close) / range) * (h - 20);

    const bullish = c.close >= c.open;
    ctx.strokeStyle = bullish ? "#00ff9d" : "#ff4466";
    ctx.fillStyle = bullish ? "#00ff9d" : "#ff4466";

    ctx.beginPath();
    ctx.moveTo(x + barW / 2, yHigh);
    ctx.lineTo(x + barW / 2, yLow);
    ctx.stroke();

    const top = Math.min(yOpen, yClose);
    const bodyH = Math.max(1, Math.abs(yClose - yOpen));
    ctx.fillRect(x, top, barW, bodyH);
  });
}

async function fetchCandles(symbol) {
  const res = await fetch(`${API}/market/candles/${symbol}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.candles || [];
}

async function refreshCandles() {
  for (const [symbol, canvas] of Object.entries(chartMap)) {
    const candles = await fetchCandles(symbol);
    drawCandles(canvas, candles);
  }
}

async function refreshState() {
  const res = await fetch(`${API}/dashboard/state`);
  if (!res.ok) return;
  const state = await res.json();

  document.getElementById("session-phase").textContent = state.session_phase;
  const brokerPill = document.getElementById("broker-status");
  if (state.broker_connected) {
    brokerPill.textContent = "BROKER ONLINE";
    brokerPill.className = "pill pill-ok";
  } else {
    brokerPill.textContent = "BROKER OFFLINE";
    brokerPill.className = "pill pill-warn";
  }

  document.getElementById("available-margin").textContent = formatCurrency(state.available_margin);
  applyBias(state.bias);
  renderEngines(state.engines);

  sliders.normal.value = state.allocations.normal;
  sliders.wick.value = state.allocations.wick;
  sliders.ultra.value = state.allocations.ultra;
  updateAllocationUI();

  document.getElementById("last-updated").textContent =
    "Last updated: " + new Date(state.last_updated).toLocaleTimeString();
}

updateAllocationUI();
refreshState();
refreshCandles();
setInterval(refreshState, 3000);
setInterval(refreshCandles, 5000);
