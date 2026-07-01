const API = "/api/v1";

const POLL = {
  state: 3000,
  candles: 2000,
  health: 10000,
  logs: 4000,
  pnl: 3000,
};

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

const chartMap = {
  NIFTY: { canvas: document.getElementById("chart-nifty"), ltp: document.getElementById("ltp-nifty") },
  ATM_CE: { canvas: document.getElementById("chart-atm-ce"), ltp: document.getElementById("ltp-atm-ce") },
  ATM_PE: { canvas: document.getElementById("chart-atm-pe"), ltp: document.getElementById("ltp-atm-pe") },
};

const btnConnect = document.getElementById("btn-connect");
const btnDisconnect = document.getElementById("btn-disconnect");
const toast = document.getElementById("toast");

let brokerBusy = false;
let logsCleared = false;
let activeLogTab = "system";

function updateClock() {
  const now = new Date();
  const el = document.getElementById("clock-display");
  const dateEl = document.getElementById("date-display");
  if (el) el.textContent = now.toLocaleTimeString("en-IN", { hour12: false });
  if (dateEl) dateEl.textContent = now.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}
setInterval(updateClock, 1000);
updateClock();

// ── Utilities ──────────────────────────────────────────────

function formatCurrency(n) {
  const val = Number(n) || 0;
  const prefix = val < 0 ? "-₹" : "₹";
  return prefix + Math.abs(val).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function pnlClass(n) {
  const val = Number(n) || 0;
  if (val > 0) return "positive";
  if (val < 0) return "negative";
  return "neutral";
}

function showToast(msg, type = "info") {
  toast.textContent = msg;
  toast.className = `toast toast-${type}`;
  setTimeout(() => toast.classList.add("hidden"), 4000);
}

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  return res;
}

// ── Health & Ready ─────────────────────────────────────────

async function refreshHealth() {
  try {
    const res = await apiFetch("/health");
    if (!res.ok) return;
    const data = await res.json();
    const el = document.getElementById("health-status");
    el.textContent = `HEALTH ${data.status.toUpperCase()}`;
    el.className = "pill pill-ok";
  } catch {
    const el = document.getElementById("health-status");
    el.textContent = "HEALTH ERR";
    el.className = "pill pill-warn";
  }
}

async function refreshReady() {
  try {
    const res = await apiFetch("/ready");
    if (!res.ok) return;
    const data = await res.json();
    const el = document.getElementById("ready-status");
    el.textContent = data.ready ? "READY OK" : "READY WAIT";
    el.className = data.ready ? "pill pill-ok" : "pill pill-warn";
  } catch {
    const el = document.getElementById("ready-status");
    el.textContent = "READY ERR";
    el.className = "pill pill-warn";
  }
}

// ── Broker ─────────────────────────────────────────────────

function setBrokerUI(connected, wsConnected) {
  const brokerPill = document.getElementById("broker-status");
  const wsPill = document.getElementById("ws-status");

  if (connected) {
    brokerPill.textContent = "BROKER ONLINE";
    brokerPill.className = "pill pill-ok";
    btnConnect.disabled = true;
    btnDisconnect.disabled = brokerBusy;
  } else {
    brokerPill.textContent = "BROKER OFFLINE";
    brokerPill.className = "pill pill-warn";
    btnConnect.disabled = brokerBusy;
    btnDisconnect.disabled = true;
  }

  if (wsConnected) {
    wsPill.textContent = "WS LIVE";
    wsPill.className = "pill pill-ok";
  } else {
    wsPill.textContent = "WS OFFLINE";
    wsPill.className = "pill pill-warn";
  }
}

async function refreshBroker() {
  try {
    const res = await apiFetch("/broker/status");
    if (!res.ok) return;
    const data = await res.json();
    setBrokerUI(data.connected, data.websocket_connected);

    const tokensEl = document.getElementById("broker-tokens");
    tokensEl.textContent = data.tokens_valid ? "Tokens: Valid" : "Tokens: Invalid";
    tokensEl.className = data.tokens_valid ? "meta-tag tag-ok" : "meta-tag tag-warn";

    const atmEl = document.getElementById("atm-strike");
    atmEl.textContent = data.atm_strike ? `ATM: ${data.atm_strike}` : "ATM: —";
  } catch { /* silent */ }
}

btnConnect.addEventListener("click", async () => {
  if (brokerBusy) return;
  brokerBusy = true;
  btnConnect.textContent = "Connecting…";
  btnConnect.disabled = true;

  try {
    const res = await apiFetch("/broker/connect", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast(`Broker connected · Margin ${formatCurrency(data.available_margin)}`, "ok");
      await Promise.all([refreshState(), refreshBroker(), refreshPnL(), refreshCandles()]);
    } else {
      showToast(data.error || "Broker connect failed", "error");
    }
  } catch (err) {
    showToast("Broker connect error: " + err.message, "error");
  } finally {
    brokerBusy = false;
    btnConnect.textContent = "Connect Broker";
    await refreshBroker();
  }
});

btnDisconnect.addEventListener("click", async () => {
  if (brokerBusy) return;
  brokerBusy = true;
  btnDisconnect.textContent = "Disconnecting…";
  btnDisconnect.disabled = true;

  try {
    const res = await apiFetch("/broker/disconnect", { method: "POST" });
    if (res.ok) {
      showToast("Broker disconnected", "info");
      await Promise.all([refreshState(), refreshBroker(), refreshPnL()]);
    }
  } catch (err) {
    showToast("Disconnect error: " + err.message, "error");
  } finally {
    brokerBusy = false;
    btnDisconnect.textContent = "Disconnect";
    await refreshBroker();
  }
});

// ── Bias ───────────────────────────────────────────────────

function applyBias(bias) {
  const display = document.getElementById("bias-display");
  document.getElementById("bias-direction").textContent = bias.direction;
  document.getElementById("bias-confidence").textContent = bias.confidence_pct.toFixed(1) + "%";
  display.className = "bias-display " + bias.direction.toLowerCase();
  document.getElementById("bias-locked").classList.toggle("hidden", !bias.locked);
}

// ── Engines ────────────────────────────────────────────────

function updateEnginePanel(engine) {
  const name = engine.name;
  const statusEl = document.querySelector(`.engine-status[data-engine="${name}"]`);
  const allocEl = document.querySelector(`.engine-alloc[data-engine="${name}"]`);
  const marginEl = document.querySelector(`.engine-margin[data-engine="${name}"]`);
  const pnlEl = document.querySelector(`.engine-pnl[data-engine="${name}"]`);
  const posEl = document.querySelector(`.engine-positions[data-engine="${name}"]`);
  const panel = document.getElementById(`panel-${name}`);

  if (!statusEl) return;

  statusEl.textContent = engine.status;
  statusEl.className = `engine-status status-${engine.status.toLowerCase()}`;
  allocEl.textContent = engine.allocation_pct + "%";
  marginEl.textContent = formatCurrency(engine.allocated_margin);

  pnlEl.textContent = formatCurrency(engine.pnl);
  pnlEl.className = `engine-pnl ${pnlClass(engine.pnl)}`;
  posEl.textContent = engine.open_positions;

  panel.classList.toggle("engine-active", engine.status === "ACTIVE");
}

function updateEngineIntelligence(name, intel) {
  const block = document.querySelector(`.engine-intel[data-engine="${name}"]`);
  if (!block || !intel) return;

  const set = (cls, val) => {
    const el = block.querySelector(`.${cls}`);
    if (el) el.textContent = val ?? "—";
  };

  set("engine-phase", intel.phase);
  set("engine-decision", intel.decision);
  set("engine-confidence", intel.confidence != null ? intel.confidence.toFixed(1) + "%" : "—");
  set("engine-opportunity", intel.opportunity_score != null ? intel.opportunity_score.toFixed(1) : "—");
  set("engine-entry-quality", intel.entry_quality != null ? intel.entry_quality.toFixed(1) : "—");
  set("engine-momentum", intel.momentum != null ? intel.momentum.toFixed(1) : "—");
  set("engine-liquidity", intel.liquidity != null ? intel.liquidity.toFixed(1) : "—");
  set("engine-health", intel.market_health != null ? intel.market_health.toFixed(1) : "—");
  set("engine-target", intel.expected_target != null ? intel.expected_target.toFixed(2) : "—");
  set("engine-sl", intel.expected_sl != null ? intel.expected_sl.toFixed(2) : "—");

  const reasons = block.querySelector(".engine-reasons");
  if (reasons) {
    reasons.innerHTML = (intel.reasons || []).map((r) => `<li>${r}</li>`).join("");
  }

  const panel = document.getElementById(`panel-${name}`);
  if (panel && intel.decision) {
    panel.classList.toggle("engine-signal", intel.decision.startsWith("WOULD_"));
  }
}

// ── Allocation ─────────────────────────────────────────────

const allocTotal = document.getElementById("alloc-total");
const allocError = document.getElementById("alloc-error");
const saveBtn = document.getElementById("save-alloc");

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
  const res = await apiFetch("/engines/allocations", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    saveBtn.textContent = "Saved ✓";
    showToast("Allocation saved", "ok");
    setTimeout(() => { saveBtn.textContent = "Save Allocation"; }, 2000);
    refreshState();
  } else {
    showToast("Allocation save failed", "error");
  }
});

// ── P&L ────────────────────────────────────────────────────

async function refreshPnL() {
  try {
    const res = await apiFetch("/dashboard/pnl");
    if (!res.ok) return;
    const data = await res.json();

    const totalEl = document.getElementById("pnl-total");
    totalEl.textContent = formatCurrency(data.total);
    totalEl.className = `pnl-total ${pnlClass(data.total)}`;

    document.getElementById("pnl-realized").textContent = formatCurrency(data.realized);
    document.getElementById("pnl-unrealized").textContent = formatCurrency(data.unrealized);
    const hdrPnl = document.getElementById("hdr-total-pnl");
    if (hdrPnl) { hdrPnl.textContent = formatCurrency(data.total); hdrPnl.className = pnlClass(data.total); }

    const container = document.getElementById("pnl-engines");
    container.innerHTML = data.engines.map((e) => `
      <div class="pnl-engine-row">
        <span class="pnl-engine-name">${e.name}</span>
        <span class="${pnlClass(e.pnl)}">${formatCurrency(e.pnl)}</span>
        <span class="pnl-engine-pos">${e.open_positions} pos</span>
      </div>
    `).join("");

    data.engines.forEach(updateEnginePanel);
  } catch { /* silent */ }
}

// ── Candles ────────────────────────────────────────────────

function setupCanvas(canvas) {
  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(rect.width - 16, 280);
  const h = 180;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = w + "px";
  canvas.style.height = h + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}

function drawCandles(canvas, candles, ltpEl) {
  const { ctx, w, h } = setupCanvas(canvas);
  ctx.clearRect(0, 0, w, h);

  if (!candles.length) {
    ctx.fillStyle = "#555";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Awaiting live ticks", w / 2, h / 2);
    if (ltpEl) ltpEl.textContent = "—";
    return;
  }

  const last = candles[candles.length - 1];
  if (ltpEl) ltpEl.textContent = last.close.toFixed(2);

  const prices = candles.flatMap((c) => [c.high, c.low]);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const pad = (max - min) * 0.05 || 1;
  const lo = min - pad;
  const hi = max + pad;
  const range = hi - lo;
  const barW = Math.max(3, (w - 30) / candles.length - 2);

  candles.forEach((c, i) => {
    const x = 15 + i * (barW + 2);
    const yHigh = 12 + ((hi - c.high) / range) * (h - 28);
    const yLow = 12 + ((hi - c.low) / range) * (h - 28);
    const yOpen = 12 + ((hi - c.open) / range) * (h - 28);
    const yClose = 12 + ((hi - c.close) / range) * (h - 28);

    const bullish = c.close >= c.open;
    const color = bullish ? "#00ff9d" : "#ff4466";
    ctx.strokeStyle = color;
    ctx.fillStyle = color;

    ctx.beginPath();
    ctx.moveTo(x + barW / 2, yHigh);
    ctx.lineTo(x + barW / 2, yLow);
    ctx.lineWidth = 1;
    ctx.stroke();

    const top = Math.min(yOpen, yClose);
    const bodyH = Math.max(1.5, Math.abs(yClose - yOpen));
    ctx.fillRect(x, top, barW, bodyH);
  });

  ctx.fillStyle = "#666";
  ctx.font = "10px sans-serif";
  ctx.textAlign = "left";
  ctx.fillText(max.toFixed(2), 4, 14);
  ctx.fillText(min.toFixed(2), 4, h - 6);
}

async function fetchCandles(symbol) {
  const res = await apiFetch(`/market/candles/${symbol}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.candles || [];
}

async function refreshCandles() {
  for (const [symbol, { canvas, ltp }] of Object.entries(chartMap)) {
    const candles = await fetchCandles(symbol);
    drawCandles(canvas, candles, ltp);
  }
}

// ── Logs ───────────────────────────────────────────────────

async function refreshLogs() {
  if (logsCleared) return;
  try {
    const res = await apiFetch(`/dashboard/logs?lines=100&log_type=${activeLogTab}`);
    if (!res.ok) return;
    const data = await res.json();
    const output = document.getElementById("logs-output");
    output.textContent = data.lines.length ? data.lines.join("\n") : "No log entries yet.";
    output.scrollTop = output.scrollHeight;
  } catch { /* silent */ }
}

document.querySelectorAll(".log-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".log-tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    activeLogTab = tab.dataset.log;
    logsCleared = false;
    refreshLogs();
  });
});

document.getElementById("btn-clear-logs-view").addEventListener("click", () => {
  logsCleared = true;
  document.getElementById("logs-output").textContent = "Log view cleared. Will resume on next poll cycle.";
  setTimeout(() => { logsCleared = false; }, POLL.logs);
});

// ── State ──────────────────────────────────────────────────

async function refreshState() {
  try {
    const res = await apiFetch("/dashboard/state");
    if (!res.ok) return;
    const state = await res.json();

    document.getElementById("session-phase").textContent = state.session_phase;
    setBrokerUI(state.broker_connected, state.websocket_connected);
    document.getElementById("available-margin").textContent = formatCurrency(state.available_margin);
    document.getElementById("hdr-available-margin").textContent = formatCurrency(state.available_margin);
    document.getElementById("hdr-used-margin").textContent = formatCurrency(state.used_margin || 0);

    if (state.nifty_ltp) {
      document.getElementById("nifty-ltp").textContent = state.nifty_ltp.toFixed(2);
      const chg = document.getElementById("nifty-change");
      const pts = state.nifty_change_pts || 0;
      const pct = state.nifty_change_pct || 0;
      chg.textContent = `${pts >= 0 ? "+" : ""}${pts.toFixed(2)} (${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%)`;
      chg.className = `nifty-change ${pnlClass(pts)}`;
    }

    const bullPct = state.bias?.direction === "BULL" ? state.bias.confidence_pct : 100 - (state.bias?.confidence_pct || 50);
    const bearPct = 100 - bullPct;
    document.getElementById("bull-pct").textContent = `Bull ${bullPct.toFixed(0)}%`;
    document.getElementById("bear-pct").textContent = `Bear ${bearPct.toFixed(0)}%`;

    if (state.engine_modes) {
      Object.entries(state.engine_modes).forEach(([eng, mode]) => {
        const el = document.querySelector(`.engine-mode[data-engine="${eng}"]`);
        if (el) el.textContent = mode;
      });
    }

    updateManualApprovals(state.pending_approvals || []);
    applyBias(state.bias);

    document.getElementById("market-mode").textContent = "Mode: " + (state.market_mode || "—");
    document.getElementById("ai-recommendation").textContent = "AI: " + (state.ai_recommendation || "—");
    document.getElementById("preferred-engine").textContent =
      "Preferred: " + (state.preferred_engine || "—").toUpperCase();

    state.engines.forEach(updateEnginePanel);
    if (state.engine_decisions) {
      Object.entries(state.engine_decisions).forEach(([name, intel]) => updateEngineIntelligence(name, intel));
    }

    sliders.normal.value = state.allocations.normal;
    sliders.wick.value = state.allocations.wick;
    sliders.ultra.value = state.allocations.ultra;
    updateAllocationUI();

    document.getElementById("last-updated").textContent =
      "Last updated: " + new Date(state.last_updated).toLocaleTimeString();
  } catch { /* silent */ }
}

// ── Master controls & engine modes ─────────────────────────

async function setEngineMode(engine, mode) {
  const res = await apiFetch(`/engine/${engine}/mode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  if (res.ok) { showToast(`${engine} → ${mode}`, "ok"); refreshState(); }
}

document.querySelectorAll(".eng-btn-auto").forEach((btn) => {
  btn.addEventListener("click", () => setEngineMode(btn.dataset.engine, "AUTO"));
});
document.querySelectorAll(".eng-btn-manual").forEach((btn) => {
  btn.addEventListener("click", () => setEngineMode(btn.dataset.engine, "MANUAL"));
});
document.querySelectorAll(".eng-btn-stop").forEach((btn) => {
  btn.addEventListener("click", async () => {
    await apiFetch(`/engine/${btn.dataset.engine}/stop`, { method: "POST" });
    refreshState();
  });
});
document.querySelectorAll(".eng-btn-start").forEach((btn) => {
  btn.addEventListener("click", async () => {
    await apiFetch(`/engine/${btn.dataset.engine}/start`, { method: "POST" });
    setEngineMode(btn.dataset.engine, "MONITOR");
  });
});
document.querySelectorAll(".eng-btn-exit").forEach((btn) => {
  btn.addEventListener("click", async () => {
    await apiFetch(`/engine/${btn.dataset.engine}/exit`, { method: "POST" });
    showToast(`${btn.dataset.engine} exit sent`, "info");
    refreshState();
  });
});

function updateManualApprovals(approvals) {
  const container = document.getElementById("manual-approvals");
  if (!approvals.length) { container.classList.add("hidden"); container.innerHTML = ""; return; }
  container.classList.remove("hidden");
  container.innerHTML = approvals.map((a) => `
    <div class="manual-card">
      <div><strong>${a.engine.toUpperCase()}</strong> ${a.action} · ${a.option_side || ""} · Qty ${a.quantity}</div>
      <div>
        <button class="btn-primary btn-xs" onclick="approveManual('${a.approval_id}')">Approve</button>
        <button class="btn-ghost btn-xs" onclick="rejectManual('${a.approval_id}')">Reject</button>
      </div>
    </div>
  `).join("");
}

async function approveManual(id) {
  await apiFetch("/execution/manual/approve", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approval_id: id }) });
  showToast("Order approved", "ok"); refreshState();
}
async function rejectManual(id) {
  await apiFetch("/execution/manual/reject", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approval_id: id }) });
  showToast("Signal rejected", "info"); refreshState();
}
window.approveManual = approveManual;
window.rejectManual = rejectManual;

document.getElementById("btn-exit-all")?.addEventListener("click", async () => {
  await apiFetch("/execution/exit-all", { method: "POST" });
  showToast("Emergency exit all triggered", "error");
});
document.getElementById("btn-download-report")?.addEventListener("click", () => {
  window.open(`${API}/reports/download`, "_blank");
});
document.getElementById("btn-restart")?.addEventListener("click", async () => {
  await apiFetch("/system/restart", { method: "POST" });
  showToast("Engine restart / recovery", "info");
});
document.getElementById("btn-health")?.addEventListener("click", () => refreshHealth());
document.getElementById("btn-token")?.addEventListener("click", async () => {
  const res = await apiFetch("/broker/status");
  const data = await res.json();
  showToast(data.tokens_valid ? "Tokens valid" : "Tokens invalid", data.tokens_valid ? "ok" : "error");
});

// ── Init & polling ─────────────────────────────────────────

function init() {
  updateAllocationUI();
  refreshHealth();
  refreshReady();
  refreshBroker();
  refreshState();
  refreshPnL();
  refreshCandles();
  refreshLogs();

  setInterval(refreshHealth, POLL.health);
  setInterval(refreshReady, POLL.health);
  setInterval(refreshState, POLL.state);
  setInterval(refreshBroker, POLL.state);
  setInterval(refreshPnL, POLL.pnl);
  setInterval(refreshCandles, POLL.candles);
  setInterval(refreshLogs, POLL.logs);
}

window.addEventListener("resize", () => refreshCandles());
init();
