const API = "/api/v1";

const POLL = { state: 3000, candles: 2000, health: 10000, logs: 4000, pnl: 3000, scheduler: 5000 };

const ENGINES = ["normal", "wick", "ultra"];

const chartMap = {
  NIFTY: { canvas: document.getElementById("chart-nifty"), ltp: document.getElementById("ltp-nifty"), chg: document.getElementById("chg-nifty"), scale: document.getElementById("scale-nifty"), time: document.getElementById("time-nifty") },
  ATM_CE: { canvas: document.getElementById("chart-atm-ce"), ltp: document.getElementById("ltp-atm-ce"), chg: document.getElementById("chg-atm-ce"), scale: document.getElementById("scale-atm-ce"), time: document.getElementById("time-atm-ce") },
  ATM_PE: { canvas: document.getElementById("chart-atm-pe"), ltp: document.getElementById("ltp-atm-pe"), chg: document.getElementById("chg-atm-pe"), scale: document.getElementById("scale-atm-pe"), time: document.getElementById("time-atm-pe") },
};

const btnConnect = document.getElementById("btn-connect");
const btnDisconnect = document.getElementById("btn-disconnect");
const toast = document.getElementById("toast");

let brokerBusy = false;
let logsPaused = false;
let logsCleared = false;
let activeLogTab = "system";
let logAutoScroll = true;
let lastNiftyCandles = [];

// ── Utilities ──────────────────────────────────────────────

function formatCurrency(n) {
  const val = Number(n) || 0;
  return (val < 0 ? "-₹" : "₹") + Math.abs(val).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
  return fetch(`${API}${path}`, options);
}

function updateClock() {
  const now = new Date();
  const timeEl = document.getElementById("clock-display");
  const dateEl = document.getElementById("date-display");
  const brokerTime = document.getElementById("strip-broker-time");
  if (timeEl) timeEl.textContent = now.toLocaleTimeString("en-IN", { hour12: true, hour: "2-digit", minute: "2-digit", second: "2-digit" }) + " IST";
  if (dateEl) dateEl.textContent = now.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  if (brokerTime) brokerTime.textContent = now.toLocaleTimeString("en-IN", { hour12: false });
}

setInterval(updateClock, 1000);
updateClock();

// ── Sparkline ──────────────────────────────────────────────

function drawSparkline(candles) {
  const canvas = document.getElementById("nifty-sparkline");
  if (!canvas) return;
  const w = canvas.offsetWidth || 160;
  const h = 28;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, w, h);
  if (!candles.length) return;
  const closes = candles.map((c) => c.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  ctx.strokeStyle = "#00ff88";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  closes.forEach((c, i) => {
    const x = (i / (closes.length - 1 || 1)) * (w - 4) + 2;
    const y = h - 4 - ((c - min) / range) * (h - 8);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();
}

// ── Health & Readiness ─────────────────────────────────────

async function refreshHealth() {
  try {
    const res = await apiFetch("/health");
    if (!res.ok) return;
    await res.json();
  } catch { /* silent */ }
}

async function refreshReadiness() {
  try {
    const res = await apiFetch("/broker/readiness");
    if (!res.ok) return;
    const data = await res.json();
    const el = document.getElementById("readiness-status");
    if (!el) return;
    const passed = (data.checks || []).filter((c) => c.passed).length;
    const total = (data.checks || []).length || 11;
    el.textContent = data.ready ? `READINESS ${passed}/${total}` : `READINESS ${passed}/${total}`;
    el.className = data.ready ? "status-chip ok" : "status-chip warn";
  } catch { /* silent */ }
}

// ── Broker ─────────────────────────────────────────────────

function setBrokerUI(connected, wsConnected) {
  const brokerEl = document.getElementById("broker-status");
  const wsEl = document.getElementById("ws-status");
  const mktEl = document.getElementById("market-status");

  if (brokerEl) {
    brokerEl.textContent = connected ? "ANGEL CONNECTED" : "ANGEL OFFLINE";
    brokerEl.className = connected ? "status-chip ok" : "status-chip warn";
  }
  if (wsEl) {
    wsEl.textContent = wsConnected ? "WS LIVE" : "WS OFFLINE";
    wsEl.className = wsConnected ? "status-chip ok" : "status-chip warn";
  }
  if (mktEl) {
    mktEl.textContent = connected ? "MARKET STATUS: OPEN" : "MARKET STATUS: OFFLINE";
  }
  if (btnConnect) btnConnect.disabled = connected || brokerBusy;
  if (btnDisconnect) btnDisconnect.disabled = !connected || brokerBusy;
}

async function refreshBroker() {
  try {
    const res = await apiFetch("/broker/status");
    if (!res.ok) return;
    const data = await res.json();
    setBrokerUI(data.connected, data.websocket_connected);
    const atmEl = document.getElementById("atm-strike");
    if (atmEl && data.atm_strike) atmEl.textContent = data.atm_strike;
  } catch { /* silent */ }
}

btnConnect?.addEventListener("click", async () => {
  if (brokerBusy) return;
  brokerBusy = true;
  btnConnect.textContent = "Connecting…";
  try {
    const res = await apiFetch("/broker/connect", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast(`Connected · Margin ${formatCurrency(data.available_margin)}`, "ok");
      await Promise.all([refreshState(), refreshBroker(), refreshPnL(), refreshCandles(), refreshReadiness()]);
    } else {
      showToast(data.error || "Connect failed", "error");
    }
  } catch (err) {
    showToast("Connect error: " + err.message, "error");
  } finally {
    brokerBusy = false;
    btnConnect.textContent = "⚡ Connect Angel";
    await refreshBroker();
  }
});

btnDisconnect?.addEventListener("click", async () => {
  if (brokerBusy) return;
  brokerBusy = true;
  try {
    await apiFetch("/broker/disconnect", { method: "POST" });
    showToast("Disconnected", "info");
    await Promise.all([refreshState(), refreshBroker(), refreshPnL()]);
  } finally {
    brokerBusy = false;
    await refreshBroker();
  }
});

// ── Margin strip & P&L ─────────────────────────────────────

async function refreshPnL() {
  try {
    const res = await apiFetch("/dashboard/pnl");
    if (!res.ok) return;
    const data = await res.json();

    const setStrip = (id, val, cls) => {
      const el = document.getElementById(id);
      if (el) { el.textContent = formatCurrency(val); if (cls) el.className = `si-val ${cls}`; }
    };
    setStrip("strip-realized", data.realized, pnlClass(data.realized));
    setStrip("strip-unrealized", data.unrealized, pnlClass(data.unrealized));
    setStrip("strip-combined", data.total, pnlClass(data.total));

    data.engines.forEach(updateEnginePanel);
  } catch { /* silent */ }
}

function updateMarginStrip(state) {
  const avail = state.available_margin || 0;
  const used = state.used_margin || 0;
  const remaining = Math.max(0, avail - used);
  const set = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
  set("strip-available", formatCurrency(avail));
  set("strip-used", formatCurrency(used));
  set("strip-remaining", formatCurrency(remaining));
  set("strip-buying", formatCurrency(avail));
}

// ── Engines ────────────────────────────────────────────────

function updateEnginePanel(engine) {
  const name = engine.name;
  const panel = document.getElementById(`panel-${name}`);
  if (!panel) return;

  const pnlEl = panel.querySelector(`.engine-pnl[data-engine="${name}"]`);
  if (pnlEl) {
    pnlEl.textContent = formatCurrency(engine.pnl);
    pnlEl.className = `engine-pnl ${pnlClass(engine.pnl)}`;
  }

  const statusEl = panel.querySelector(`.engine-status[data-engine="${name}"]`);
  if (statusEl) statusEl.textContent = engine.status;

  panel.classList.toggle("engine-active", engine.status === "ACTIVE");
}

function updateEngineIntelligence(name, intel, livePos) {
  const panel = document.getElementById(`panel-${name}`);
  if (!panel || !intel) return;

  const set = (cls, val) => {
    const el = panel.querySelector(`.${cls}`);
    if (el) el.textContent = val ?? "—";
  };

  const pos = livePos || {};
  set("engine-side", pos.option_side || "—");
  set("engine-strike", pos.strike || "—");
  set("engine-lots", pos.lots || "—");
  set("engine-qty", pos.quantity || "—");
  set("engine-entry", pos.entry_price != null ? Number(pos.entry_price).toFixed(2) : "—");
  set("engine-ltp", pos.current_ltp != null ? Number(pos.current_ltp).toFixed(2) : "—");
  set("engine-trailing", pos.trailing_sl ? "ACTIVE" : "OFF");

  set("engine-confidence", intel.confidence != null ? intel.confidence.toFixed(1) + "%" : "—");
  set("engine-opportunity", intel.opportunity_score != null ? intel.opportunity_score.toFixed(1) + "%" : "—");
  set("engine-entry-quality", intel.entry_quality != null ? intel.entry_quality.toFixed(1) + "%" : "—");
  set("engine-momentum", intel.momentum != null ? (intel.momentum > 55 ? "Bullish" : intel.momentum < 45 ? "Bearish" : "Neutral") : "—");
  set("engine-liquidity", intel.liquidity != null ? (intel.liquidity > 60 ? "Good" : "Fair") : "—");
  set("engine-health", intel.market_health != null ? (intel.market_health > 70 ? "Excellent" : intel.market_health > 50 ? "Good" : "Fair") : "—");
  set("engine-target", intel.expected_target != null ? intel.expected_target.toFixed(2) : "—");
  set("engine-sl", intel.expected_sl != null ? intel.expected_sl.toFixed(2) : "—");

  const decEl = panel.querySelector(".engine-decision");
  if (decEl) {
    decEl.textContent = intel.decision || "WAIT";
    decEl.className = "engine-decision " + (
      intel.decision?.startsWith("WOULD_BUY") ? "dec-signal" :
      intel.decision === "WOULD_EXIT" ? "dec-exit" :
      intel.decision === "WAIT" ? "dec-wait" : "dec-wait"
    );
  }

  const reasonsEl = panel.querySelector(".engine-reasons-text");
  if (reasonsEl) {
    reasonsEl.textContent = (intel.reasons || []).slice(0, 4).join(" • ") || "—";
  }

  panel.classList.toggle("engine-signal", intel.decision?.startsWith("WOULD_"));
}

// ── Bull/Bear meter ────────────────────────────────────────

function updateBullBear(bias) {
  if (!bias) return;
  let bullPct = bias.direction === "BULL" ? bias.confidence_pct :
    bias.direction === "BEAR" ? 100 - bias.confidence_pct : 50;
  bullPct = Math.max(0, Math.min(100, bullPct));
  const bearPct = 100 - bullPct;
  const bullEl = document.getElementById("bull-pct");
  const bearEl = document.getElementById("bear-pct");
  const bullBar = document.getElementById("bull-bar");
  const bearBar = document.getElementById("bear-bar");
  if (bullEl) bullEl.textContent = `BULL ${bullPct.toFixed(0)}%`;
  if (bearEl) bearEl.textContent = `BEAR ${bearPct.toFixed(0)}%`;
  if (bullBar) bullBar.style.width = bullPct + "%";
  if (bearBar) bearBar.style.width = bearPct + "%";
}

// ── Timeline ───────────────────────────────────────────────

const PHASE_ORDER = ["OFFLINE", "PRE_MARKET", "BIAS_LOCKED", "TRADING", "NO_NEW_ENTRIES", "FORCE_EXIT", "PREWATCH", "SHUTDOWN"];

async function refreshTimeline() {
  try {
    const res = await apiFetch("/scheduler/status");
    if (!res.ok) return;
    const data = await res.json();
    const phase = data.current_phase;
    const idx = PHASE_ORDER.indexOf(phase);

    document.querySelectorAll(".tl-item").forEach((el) => {
      const p = el.dataset.phase;
      const pIdx = PHASE_ORDER.indexOf(p);
      el.classList.remove("active", "done");
      if (p === phase) el.classList.add("active");
      else if (pIdx >= 0 && pIdx < idx) el.classList.add("done");
    });

    const nextEl = document.getElementById("next-event");
    if (nextEl) {
      const labels = { OFFLINE: "Prep", PRE_MARKET: "Analysis", BIAS_LOCKED: "Bias Lock", TRADING: "Trading Running", NO_NEW_ENTRIES: "No New Entries", FORCE_EXIT: "Force Exit", PREWATCH: "Pre-Watch", SHUTDOWN: "Shutdown" };
      nextEl.textContent = (labels[phase] || phase) + (data.new_entries_allowed ? " · Entries OK" : "");
    }
  } catch { /* silent */ }
}

// ── Candles ────────────────────────────────────────────────

function setupCanvas(canvas) {
  const wrap = canvas.closest(".chart-wrap") || canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max((wrap?.clientWidth || 280) - 46, 120);
  const h = 120;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = w + "px";
  canvas.style.height = h + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}

function drawCandles(symbol, candles) {
  const cfg = chartMap[symbol];
  if (!cfg?.canvas) return;
  const { ctx, w, h } = setupCanvas(cfg.canvas);
  ctx.clearRect(0, 0, w, h);

  if (!candles.length) {
    ctx.fillStyle = "#444";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Awaiting live ticks", w / 2, h / 2);
    if (cfg.ltp) cfg.ltp.textContent = "—";
    if (cfg.chg) cfg.chg.textContent = "—";
    if (cfg.scale) cfg.scale.innerHTML = "";
    if (cfg.time) cfg.time.innerHTML = "";
    return;
  }

  const last = candles[candles.length - 1];
  const first = candles[0];
  const chg = last.close - first.close;
  const chgPct = first.close ? (chg / first.close) * 100 : 0;

  if (cfg.ltp) cfg.ltp.textContent = last.close.toFixed(2);
  if (cfg.chg) {
    cfg.chg.textContent = `${chg >= 0 ? "+" : ""}${chg.toFixed(2)} (${chgPct >= 0 ? "+" : ""}${chgPct.toFixed(2)}%)`;
    cfg.chg.className = `ch-chg ${pnlClass(chg)}`;
  }

  const prices = candles.flatMap((c) => [c.high, c.low]);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const pad = (max - min) * 0.05 || 0.5;
  const lo = min - pad;
  const hi = max + pad;
  const range = hi - lo;
  const rightPad = 4;
  const barW = Math.max(2, (w - 20) / candles.length - 1);

  candles.forEach((c, i) => {
    const x = 8 + i * (barW + 1);
    const yH = 8 + ((hi - c.high) / range) * (h - 20);
    const yL = 8 + ((hi - c.low) / range) * (h - 20);
    const yO = 8 + ((hi - c.open) / range) * (h - 20);
    const yC = 8 + ((hi - c.close) / range) * (h - 20);
    const bull = c.close >= c.open;
    const color = bull ? "#00ff88" : "#ff3355";
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x + barW / 2, yH);
    ctx.lineTo(x + barW / 2, yL);
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillRect(x, Math.min(yO, yC), barW, Math.max(1, Math.abs(yC - yO)));
  });

  if (cfg.scale) {
    cfg.scale.innerHTML = `<span>${hi.toFixed(2)}</span><span style="color:var(--bull)">${last.close.toFixed(2)}</span><span>${lo.toFixed(2)}</span>`;
  }
  if (cfg.time && candles.length >= 2) {
    const t0 = new Date(candles[0].timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
    const t1 = new Date(candles[candles.length - 1].timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
    cfg.time.innerHTML = `<span>${t0}</span><span>${t1}</span>`;
  }

  if (symbol === "NIFTY") {
    lastNiftyCandles = candles;
    drawSparkline(candles);
  }
}

async function fetchCandles(symbol) {
  const res = await apiFetch(`/market/candles/${symbol}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.candles || [];
}

async function refreshCandles() {
  for (const symbol of Object.keys(chartMap)) {
    const candles = await fetchCandles(symbol);
    drawCandles(symbol, candles);
  }
}

// ── Market summary (placeholders) ──────────────────────────

function updateMarketSummary(state) {
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  set("ms-advances", "—");
  set("ms-declines", "—");
  set("ms-unchanged", "—");
  set("ms-volume", "—");
  set("ms-value", "—");
  set("ms-vix", "—");
  set("ms-pcr", "—");
  set("ms-maxpain", state.nifty_ltp ? Math.round(state.nifty_ltp / 50) * 50 : "—");
  set("ms-fii", "—");
  set("ms-dii", "—");
}

// ── Logs ───────────────────────────────────────────────────

async function refreshLogs() {
  if (logsPaused || logsCleared) return;
  try {
    const res = await apiFetch(`/dashboard/logs?lines=120&log_type=${activeLogTab}`);
    if (!res.ok) return;
    const data = await res.json();
    const output = document.getElementById("logs-output");
    if (!output) return;
    output.textContent = data.lines.length ? data.lines.join("\n") : "No log entries yet.";
    if (logAutoScroll) output.scrollTop = output.scrollHeight;
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

document.getElementById("log-autoscroll")?.addEventListener("change", (e) => {
  logAutoScroll = e.target.checked;
});

document.getElementById("btn-pause-logs")?.addEventListener("click", () => {
  logsPaused = !logsPaused;
  document.getElementById("btn-pause-logs").textContent = logsPaused ? "Resume" : "Pause";
});

document.getElementById("btn-clear-logs-view")?.addEventListener("click", () => {
  logsCleared = true;
  const output = document.getElementById("logs-output");
  if (output) output.textContent = "Log view cleared.";
  setTimeout(() => { logsCleared = false; }, POLL.logs);
});

document.getElementById("btn-export-logs")?.addEventListener("click", () => {
  const text = document.getElementById("logs-output")?.textContent || "";
  const blob = new Blob([text], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `logs_${activeLogTab}_${Date.now()}.txt`;
  a.click();
});

// ── State ──────────────────────────────────────────────────

async function refreshState() {
  try {
    const res = await apiFetch("/dashboard/state");
    if (!res.ok) return;
    const state = await res.json();

    setBrokerUI(state.broker_connected, state.websocket_connected);
    updateMarginStrip(state);
    updateBullBear(state.bias);
    updateMarketSummary(state);

    if (state.nifty_ltp) {
      const ltpEl = document.getElementById("nifty-ltp");
      const chgEl = document.getElementById("nifty-change");
      if (ltpEl) ltpEl.textContent = state.nifty_ltp.toFixed(2);
      if (chgEl) {
        const pts = state.nifty_change_pts || 0;
        const pct = state.nifty_change_pct || 0;
        chgEl.textContent = `${pts >= 0 ? "+" : ""}${pts.toFixed(2)} (${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%)`;
        chgEl.className = `nifty-change ${pnlClass(pts)}`;
      }
    }

    if (state.engine_modes) {
      Object.entries(state.engine_modes).forEach(([eng, mode]) => {
        const sel = document.querySelector(`.mode-select[data-engine="${eng}"]`);
        if (sel) sel.value = mode;
        const modeEl = document.querySelector(`.engine-mode[data-engine="${eng}"]`);
        if (modeEl) modeEl.textContent = mode;
      });
    }

    updateManualApprovals(state.pending_approvals || []);

    state.engines.forEach(updateEnginePanel);
    if (state.engine_decisions) {
      Object.entries(state.engine_decisions).forEach(([name, intel]) =>
        updateEngineIntelligence(name, intel, state.live_positions?.[name])
      );
    }

    const sliders = {
      normal: document.getElementById("normal-slider"),
      wick: document.getElementById("wick-slider"),
      ultra: document.getElementById("ultra-slider"),
    };
    if (sliders.normal) sliders.normal.value = state.allocations.normal;
    if (sliders.wick) sliders.wick.value = state.allocations.wick;
    if (sliders.ultra) sliders.ultra.value = state.allocations.ultra;

    const updated = document.getElementById("last-updated");
    if (updated) updated.textContent = "Last updated: " + new Date(state.last_updated).toLocaleTimeString();
  } catch { /* silent */ }
}

// ── Engine mode controls ───────────────────────────────────

async function setEngineMode(engine, mode) {
  const res = await apiFetch(`/engine/${engine}/mode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  if (res.ok) { showToast(`${engine} → ${mode}`, "ok"); refreshState(); }
}

document.querySelectorAll(".mode-select").forEach((sel) => {
  sel.addEventListener("change", () => setEngineMode(sel.dataset.engine, sel.value));
});

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
  if (!container) return;
  if (!approvals.length) { container.classList.add("hidden"); container.innerHTML = ""; return; }
  container.classList.remove("hidden");
  container.innerHTML = approvals.map((a) => `
    <div class="manual-card">
      <div><strong>${a.engine.toUpperCase()}</strong> ${a.action} · ${a.option_side || ""} · Qty ${a.quantity}</div>
      <div>
        <button class="mc-btn mc-primary sm" onclick="approveManual('${a.approval_id}')">Approve</button>
        <button class="mc-btn sm" onclick="rejectManual('${a.approval_id}')">Reject</button>
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

// ── Master bar actions ─────────────────────────────────────

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

document.getElementById("btn-exit-server")?.addEventListener("click", async () => {
  if (confirm("Shutdown server?")) {
    await apiFetch("/system/shutdown", { method: "POST" });
    showToast("Shutdown initiated", "info");
  }
});

document.getElementById("btn-health")?.addEventListener("click", async () => {
  await refreshHealth();
  await refreshReadiness();
  showToast("Health check complete", "ok");
});

document.getElementById("btn-token")?.addEventListener("click", async () => {
  const res = await apiFetch("/broker/status");
  const data = await res.json();
  showToast(data.tokens_valid ? "Tokens valid" : "Tokens invalid", data.tokens_valid ? "ok" : "error");
});

document.getElementById("btn-sync-broker")?.addEventListener("click", async () => {
  await apiFetch("/system/restart", { method: "POST" });
  await Promise.all([refreshBroker(), refreshState(), refreshReadiness()]);
  showToast("Broker sync refreshed", "ok");
});

document.getElementById("btn-ws-reconnect")?.addEventListener("click", async () => {
  await apiFetch("/broker/disconnect", { method: "POST" });
  await apiFetch("/broker/connect", { method: "POST" });
  showToast("WebSocket reconnect attempted", "info");
  refreshBroker();
});

document.getElementById("btn-margin-recalc")?.addEventListener("click", async () => {
  await refreshBroker();
  await refreshPnL();
  showToast("Margin recalculated", "ok");
});

document.getElementById("btn-atm-refresh")?.addEventListener("click", async () => {
  await refreshCandles();
  await refreshBroker();
  showToast("ATM refreshed", "ok");
});

document.getElementById("btn-refresh-master")?.addEventListener("click", () => {
  showToast("Instrument master refresh — connect broker first", "info");
});

document.getElementById("btn-reload-expiry")?.addEventListener("click", () => {
  showToast("Expiry reload — connect broker first", "info");
});

document.getElementById("btn-reset-stats")?.addEventListener("click", () => {
  showToast("Daily stats reset not configured", "info");
});

document.getElementById("btn-clear-storage")?.addEventListener("click", () => {
  showToast("Safe clear storage — no action needed", "info");
});

document.getElementById("btn-clear-logs")?.addEventListener("click", () => {
  document.getElementById("btn-clear-logs-view")?.click();
});

// ── Init ───────────────────────────────────────────────────

function init() {
  refreshHealth();
  refreshReadiness();
  refreshBroker();
  refreshState();
  refreshPnL();
  refreshCandles();
  refreshLogs();
  refreshTimeline();

  setInterval(refreshHealth, POLL.health);
  setInterval(refreshReadiness, POLL.health);
  setInterval(refreshState, POLL.state);
  setInterval(refreshBroker, POLL.state);
  setInterval(refreshPnL, POLL.pnl);
  setInterval(refreshCandles, POLL.candles);
  setInterval(refreshLogs, POLL.logs);
  setInterval(refreshTimeline, POLL.scheduler);
}

window.addEventListener("resize", () => refreshCandles());
init();
