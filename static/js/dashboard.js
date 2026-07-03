const API = "/api/v1";

const POLL = { state: 3000, candles: 2000, health: 10000, logs: 4000, pnl: 3000, scheduler: 5000, operator: 4000 };

const ENGINES = ["normal", "wick", "ultra"];

const chartMap = {
  NIFTY: {
    canvas: document.getElementById("chart-nifty"),
    ltp: document.getElementById("ltp-nifty"),
    chg: document.getElementById("chg-nifty"),
    ohlc: document.getElementById("ohlc-nifty"),
    scale: document.getElementById("scale-nifty"),
    time: document.getElementById("time-nifty"),
  },
  ATM_CE: {
    canvas: document.getElementById("chart-atm-ce"),
    ltp: document.getElementById("ltp-atm-ce"),
    chg: document.getElementById("chg-atm-ce"),
    ohlc: document.getElementById("ohlc-atm-ce"),
    scale: document.getElementById("scale-atm-ce"),
    time: document.getElementById("time-atm-ce"),
  },
  ATM_PE: {
    canvas: document.getElementById("chart-atm-pe"),
    ltp: document.getElementById("ltp-atm-pe"),
    chg: document.getElementById("chg-atm-pe"),
    ohlc: document.getElementById("ohlc-atm-pe"),
    scale: document.getElementById("scale-atm-pe"),
    time: document.getElementById("time-atm-pe"),
  },
};

const READINESS_LABELS = {
  angel_connected: "Angel Login",
  jwt_valid: "JWT Valid",
  feed_token_valid: "Feed Token Valid",
  websocket_connected: "WebSocket Connected",
  margin_fetched: "Margin Fetched",
  instrument_master_loaded: "Instrument Master Loaded",
  expiry_selected: "Expiry Selected",
  nifty_tick_fresh: "NIFTY Tick Fresh",
  atm_ce_tick_fresh: "ATM CE Tick Fresh",
  atm_pe_tick_fresh: "ATM PE Tick Fresh",
  no_rate_limit: "No Rate Limit Issue",
};

const CHART_COUNTDOWN_IDS = {
  NIFTY: "countdown-nifty",
  ATM_CE: "countdown-atm-ce",
  ATM_PE: "countdown-atm-pe",
};

const CHART_WAIT_NOTE_IDS = {
  NIFTY: "wait-note-nifty",
  ATM_CE: "wait-note-atm-ce",
  ATM_PE: "wait-note-atm-pe",
};

const chartState = {};
const chartCrosshair = {};
const cachedCandles = { NIFTY: [], ATM_CE: [], ATM_PE: [] };
let chartResizeTimer = null;

let brokerBusy = false;
let logsPaused = false;
let logsCleared = false;
let activeLogTab = "system";
let logAutoScroll = true;
let lastNiftyCandles = [];
let lastAtmCeCandles = [];
let lastAtmPeCandles = [];
let currentSchedulerPhase = "OFFLINE";
let lastOperatorData = null;
let logFilterText = "";
let cachedLogLines = [];
let pendingApprovalsMap = {};
let passwordModalResolver = null;
let stateFetchSeq = 0;
const pendingModeChanges = {};

function syncEngineModeUI(engine, mode) {
  const sel = document.querySelector(`.mode-select[data-engine="${engine}"]`);
  if (sel) {
    sel.value = mode;
    sel.dataset.confirmedMode = mode;
    sel.dataset.lastMode = mode;
  }
  const modeEl = document.querySelector(`.engine-mode[data-engine="${engine}"]`);
  if (modeEl) modeEl.textContent = mode;
}

const btnConnect = document.getElementById("btn-connect");
const btnDisconnect = document.getElementById("btn-disconnect");
const toast = document.getElementById("toast");

function combinedPnlClass(n) {
  const val = Number(n) || 0;
  if (val > 0) return "positive";
  if (val < 0) return "negative";
  return "pnl-zero";
}

function getISTNow() {
  return new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
}

function formatDurationSec(sec) {
  if (sec == null || Number.isNaN(sec)) return "—";
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${r}s`;
  return `${r}s`;
}

function formatHoldingTime(entryAtIso) {
  if (!entryAtIso) return "—";
  const start = new Date(entryAtIso);
  if (Number.isNaN(start.getTime())) return "—";
  const mins = Math.floor((Date.now() - start.getTime()) / 60000);
  return formatDuration(mins);
}

function candleCountdownSec() {
  return 60 - getISTNow().getSeconds();
}

function updateCandleCountdowns() {
  const sec = candleCountdownSec();
  Object.values(CHART_COUNTDOWN_IDS).forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.textContent = `1m · ${sec}s`;
  });
}
function formatDuration(totalMins) {
  const h = Math.floor(totalMins / 60);
  const m = totalMins % 60;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function updateMarketCountdown() {
  const el = document.getElementById("market-countdown");
  if (!el) return;
  const now = getISTNow();
  const day = now.getDay();
  const mins = now.getHours() * 60 + now.getMinutes();
  const openMins = 9 * 60 + 15;
  const closeMins = 15 * 60 + 30;
  const isWeekend = day === 0 || day === 6;

  if (isWeekend) {
    el.textContent = "Market Opens Mon 09:15 IST";
    return;
  }
  if (mins < openMins) {
    el.textContent = `Market Opens In ${formatDuration(openMins - mins)}`;
    return;
  }
  if (mins >= openMins && mins < closeMins) {
    el.textContent = `Market Closes In ${formatDuration(closeMins - mins)}`;
    return;
  }
  el.textContent = "Market Opens Tomorrow 09:15 IST";
}

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
  const toast = document.getElementById("toast");
  if (!toast) return;
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
  updateMarketCountdown();
  updateCandleCountdowns();
}

setInterval(updateClock, 1000);
updateClock();

// ── Sparkline ──────────────────────────────────────────────

function drawSparkline(candles) {
  const canvas = document.getElementById("nifty-sparkline");
  if (!canvas) return;
  const w = canvas.offsetWidth || 200;
  const h = 36;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, w, h);
  if (!candles.length) return;
  const closes = candles.map((c) => c.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const first = closes[0];
  const last = closes[closes.length - 1];
  const up = last >= first;
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, up ? "rgba(0,230,118,0.18)" : "rgba(255,61,90,0.18)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = grad;
  ctx.beginPath();
  closes.forEach((c, i) => {
    const x = (i / (closes.length - 1 || 1)) * (w - 4) + 2;
    const y = h - 4 - ((c - min) / range) * (h - 8);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.lineTo(w - 2, h);
  ctx.lineTo(2, h);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = up ? "#00e676" : "#ff3d5a";
  ctx.lineWidth = 1.75;
  ctx.beginPath();
  closes.forEach((c, i) => {
    const x = (i / (closes.length - 1 || 1)) * (w - 4) + 2;
    const y = h - 4 - ((c - min) / range) * (h - 8);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();
}

function updateNiftyCard(state, candles, operator) {
  const ltpEl = document.getElementById("nifty-ltp");
  const chgEl = document.getElementById("nifty-change");
  const pctEl = document.getElementById("nifty-change-pct");
  const openEl = document.getElementById("nifty-open");
  const highEl = document.getElementById("nifty-high");
  const lowEl = document.getElementById("nifty-low");
  const prevEl = document.getElementById("nifty-prev-close");
  const todayHighEl = document.getElementById("nifty-today-high");
  const todayLowEl = document.getElementById("nifty-today-low");
  const trendEl = document.getElementById("nifty-trend");
  const atmEl = document.getElementById("nifty-atm-strike");
  const expiryEl = document.getElementById("nifty-expiry");
  const spreadEl = document.getElementById("nifty-prem-spread");

  if (state?.nifty_ltp && ltpEl) {
    ltpEl.textContent = state.nifty_ltp.toFixed(2);
    const pts = state.nifty_change_pts || 0;
    const pct = state.nifty_change_pct || 0;
    const cls = pnlClass(pts);
    if (chgEl) {
      chgEl.textContent = `${pts >= 0 ? "+" : ""}${pts.toFixed(2)}`;
      chgEl.className = `nifty-change ${cls}`;
    }
    if (pctEl) {
      pctEl.textContent = `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
      pctEl.className = `nifty-change-pct ${cls}`;
    }
    if (prevEl) prevEl.textContent = (state.nifty_ltp - pts).toFixed(2);
    if (trendEl) {
      trendEl.textContent = pts > 5 ? "Bullish" : pts < -5 ? "Bearish" : "Neutral";
      trendEl.className = `mono ${pnlClass(pts)}`;
    }
  }

  if (candles?.length) {
    const dayHigh = Math.max(...candles.map((c) => c.high));
    const dayLow = Math.min(...candles.map((c) => c.low));
    if (openEl) openEl.textContent = candles[0].open.toFixed(2);
    if (highEl) highEl.textContent = dayHigh.toFixed(2);
    if (lowEl) lowEl.textContent = dayLow.toFixed(2);
    if (todayHighEl) todayHighEl.textContent = (operator?.nifty_day_high ?? dayHigh).toFixed(2);
    if (todayLowEl) todayLowEl.textContent = (operator?.nifty_day_low ?? dayLow).toFixed(2);
  }

  if (operator) {
    if (atmEl && operator.atm_strike) atmEl.textContent = operator.atm_strike;
    if (expiryEl && operator.expiry) expiryEl.textContent = operator.expiry;
    if (spreadEl && operator.premium_spread != null) spreadEl.textContent = operator.premium_spread.toFixed(2);
  }
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
    const checks = data.checks || [];
    const passed = checks.filter((c) => c.passed).length;
    const total = checks.length || 11;
    const label = `READINESS ${passed}/${total}`;

    const toggle = document.getElementById("readiness-toggle");
    const legacy = document.getElementById("readiness-status");
    const target = toggle || legacy;
    if (target) {
      target.textContent = label;
      target.className = data.ready ? "status-chip readiness-toggle ok" : "status-chip readiness-toggle warn";
    }

    const list = document.getElementById("readiness-checklist");
    if (list) {
      list.innerHTML = checks.map((c) => {
        const name = READINESS_LABELS[c.name] || c.name;
        const icon = c.passed ? "✓" : "✗";
        const iconCls = c.passed ? "rc-pass" : "rc-fail";
        const msg = c.message ? `<span class="rc-msg">${c.message}</span>` : "";
        return `<div class="rc-item"><span class="${iconCls}">${icon}</span><div><span class="rc-label">${name}</span>${msg}</div></div>`;
      }).join("");
    }
  } catch { /* silent */ }
}

document.getElementById("readiness-toggle")?.addEventListener("click", (e) => {
  e.stopPropagation();
  const list = document.getElementById("readiness-checklist");
  const btn = document.getElementById("readiness-toggle");
  if (!list || !btn) return;
  list.classList.toggle("hidden");
  btn.setAttribute("aria-expanded", list.classList.contains("hidden") ? "false" : "true");
});

document.addEventListener("click", (e) => {
  const wrap = document.querySelector(".readiness-wrap");
  const list = document.getElementById("readiness-checklist");
  if (!wrap || !list || list.classList.contains("hidden")) return;
  if (!wrap.contains(e.target)) {
    list.classList.add("hidden");
    document.getElementById("readiness-toggle")?.setAttribute("aria-expanded", "false");
  }
});

// ── Broker ─────────────────────────────────────────────────

function setBrokerUI(connected, wsConnected, reconnectStatus) {
  const brokerEl = document.getElementById("broker-status");
  const wsEl = document.getElementById("ws-status");
  const mktEl = document.getElementById("market-status");
  const rs = reconnectStatus || lastOperatorData?.reconnect_status;

  if (brokerEl) {
    brokerEl.textContent = connected ? "ANGEL CONNECTED" : "ANGEL OFFLINE";
    brokerEl.className = connected ? "status-chip ok" : "status-chip warn";
  }
  if (wsEl) {
    if (rs?.status === "retrying") {
      wsEl.textContent = `WS RETRY ${rs.attempt || ""}`.trim();
      wsEl.className = "status-chip warn";
    } else if (rs?.status === "failed" || rs?.status === "error") {
      wsEl.textContent = "WS RECONNECT FAILED";
      wsEl.className = "status-chip bad";
    } else {
      wsEl.textContent = wsConnected ? "WS LIVE" : "WS OFFLINE";
      wsEl.className = wsConnected ? "status-chip ok" : "status-chip warn";
    }
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
      await refreshDashboardPanels();
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

    const setStrip = (id, val, cls, extra = "") => {
      const el = document.getElementById(id);
      if (el) {
        el.textContent = formatCurrency(val);
        if (cls) el.className = `si-val ${extra}${cls}`.trim();
      }
    };
    setStrip("strip-realized", data.realized, pnlClass(data.realized));
    setStrip("strip-unrealized", data.unrealized, pnlClass(data.unrealized));
    setStrip("strip-combined", data.total, combinedPnlClass(data.total), "combined-pnl ");

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

function engineStatusBadge(decision, mode) {
  const d = (decision || "WAIT").toUpperCase();
  const m = (mode || "MONITOR").toUpperCase();
  if (m === "MANUAL") return { text: "🟣 MANUAL", cls: "badge-manual" };
  if (m === "AUTO" && d === "WAIT") return { text: "🟠 AUTO", cls: "badge-auto" };
  if (d === "BLOCKED" || d === "WOULD_EXIT") return { text: "🔴 BLOCKED", cls: "badge-blocked" };
  if (d.startsWith("WOULD_BUY") || d === "READY") return { text: "🟢 READY", cls: "badge-ready" };
  if (d === "WAIT" && m === "MONITOR") return { text: "🔵 MONITOR", cls: "badge-monitor" };
  if (d === "WAIT") return { text: "🟡 WAIT", cls: "badge-wait" };
  return { text: `🟡 ${d.replace(/_/g, " ")}`, cls: "badge-wait" };
}

function updateEngineIntelligence(name, intel, livePos) {
  const panel = document.getElementById(`panel-${name}`);
  if (!panel || !intel) return;

  const set = (cls, val) => {
    const el = panel.querySelector(`.${cls}`);
    if (el) el.textContent = val ?? "—";
  };

  const pos = livePos || {};
  const hasPos = pos && (pos.quantity || pos.entry_price);
  set("engine-side", pos.action_label || (pos.option_side ? `BUY ${pos.option_side}` : "—"));
  set("engine-strike", pos.strike || "—");
  set("engine-lots", pos.lots || "—");
  set("engine-qty", pos.quantity || "—");
  set("engine-entry", pos.entry_price != null ? Number(pos.entry_price).toFixed(2) : "—");
  set("engine-ltp", pos.current_ltp != null ? Number(pos.current_ltp).toFixed(2) : "—");
  set("engine-trailing", pos.trailing_sl ? String(Number(pos.trailing_sl).toFixed(2)) : "OFF");

  set("engine-pos-status", hasPos ? `${pos.action_label || pos.option_side || ""} OPEN`.trim() : "FLAT");
  set("engine-pos-premium", pos.current_ltp != null ? Number(pos.current_ltp).toFixed(2) : "—");
  set("engine-pos-target", pos.target != null ? Number(pos.target).toFixed(2) : (intel.expected_target != null ? intel.expected_target.toFixed(2) : "—"));
  set("engine-pos-sl", pos.stop_loss != null ? Number(pos.stop_loss).toFixed(2) : (intel.expected_sl != null ? intel.expected_sl.toFixed(2) : "—"));
  set("engine-pos-trail", pos.trailing_sl != null ? Number(pos.trailing_sl).toFixed(2) : "—");

  const livePnlEl = panel.querySelector(".engine-live-pnl");
  if (livePnlEl) {
    if (hasPos && pos.unrealized_pnl != null) {
      const pnl = Number(pos.unrealized_pnl);
      livePnlEl.textContent = formatCurrency(pnl);
      livePnlEl.className = `engine-live-pnl ${pnlClass(pnl)}`;
    } else if (hasPos && pos.entry_price != null && pos.current_ltp != null && pos.quantity) {
      const pnl = (Number(pos.current_ltp) - Number(pos.entry_price)) * Number(pos.quantity);
      livePnlEl.textContent = formatCurrency(pnl);
      livePnlEl.className = `engine-live-pnl ${pnlClass(pnl)}`;
    } else {
      livePnlEl.textContent = "—";
      livePnlEl.className = "engine-live-pnl neutral";
    }
  }

  const pts = pos.points;
  set("engine-points", hasPos && pts != null ? Number(pts).toFixed(2) : "—");

  const peak = pos.peak_profit;
  set("engine-peak-profit", peak != null && hasPos ? formatCurrency(peak) : "—");
  const rollbackEl = panel.querySelector(".engine-rollback");
  if (rollbackEl) {
    if (hasPos && peak != null && pos.entry_price != null && pos.current_ltp != null && pos.quantity) {
      const current = (Number(pos.current_ltp) - Number(pos.entry_price)) * Number(pos.quantity);
      const rollback = Math.max(0, Number(peak) - current);
      rollbackEl.textContent = rollback > 0 ? formatCurrency(rollback) : "—";
    } else {
      rollbackEl.textContent = "—";
    }
  }
  set("engine-holding-time", formatHoldingTime(pos.entry_at));
  set("engine-last-decision-time", intel.updated_at ? new Date(intel.updated_at).toLocaleTimeString("en-IN", { hour12: false }) : "—");

  set("engine-confidence", intel.confidence != null ? intel.confidence.toFixed(1) + "%" : "—");
  set("engine-opportunity", intel.opportunity_score != null ? intel.opportunity_score.toFixed(1) + "%" : "—");
  set("engine-entry-quality", intel.entry_quality != null ? intel.entry_quality.toFixed(1) + "%" : "—");
  set("engine-momentum", intel.momentum != null ? (intel.momentum > 55 ? "Bullish" : intel.momentum < 45 ? "Bearish" : "Neutral") : "—");
  set("engine-liquidity", intel.liquidity != null ? (intel.liquidity > 60 ? "Good" : "Fair") : "—");
  set("engine-health", intel.market_health != null ? (intel.market_health > 70 ? "Excellent" : intel.market_health > 50 ? "Good" : "Fair") : "—");
  set("engine-target", intel.expected_target != null ? intel.expected_target.toFixed(2) : "—");
  set("engine-sl", intel.expected_sl != null ? intel.expected_sl.toFixed(2) : "—");

  const modeEl = panel.querySelector(`.engine-mode[data-engine="${name}"]`);
  const mode = modeEl?.textContent || document.querySelector(`.mode-select[data-engine="${name}"]`)?.value || "MONITOR";
  const badge = engineStatusBadge(intel.decision, mode);
  const badgeEl = panel.querySelector(".engine-status-badge");
  if (badgeEl) {
    badgeEl.textContent = badge.text;
    badgeEl.className = `engine-status-badge ${badge.cls}`;
  }

  const decEl = panel.querySelector(".engine-decision");
  if (decEl) {
    decEl.textContent = intel.decision || "WAIT";
    const d = intel.decision || "WAIT";
    decEl.className = "engine-decision " + (
      d.startsWith("WOULD_BUY") ? "dec-signal" :
      d === "WOULD_EXIT" ? "dec-exit" :
      d === "BLOCKED" ? "dec-exit" :
      d === "WAIT" ? "dec-wait" : "dec-wait"
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
  const confEl = document.getElementById("bias-confidence-hdr");
  const bullBar = document.getElementById("bull-bar");
  const bearBar = document.getElementById("bear-bar");
  if (bullEl) bullEl.textContent = `BULL ${bullPct.toFixed(0)}%`;
  if (bearEl) bearEl.textContent = `BEAR ${bearPct.toFixed(0)}%`;
  if (confEl) confEl.textContent = `${bias.confidence_pct?.toFixed?.(0) ?? "—"}%`;
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
    currentSchedulerPhase = phase;
    const idx = PHASE_ORDER.indexOf(phase);

    const labels = {
      OFFLINE: "Prep", PRE_MARKET: "Analysis", BIAS_LOCKED: "Bias Lock",
      TRADING: "Trading Running", NO_NEW_ENTRIES: "No New Entries",
      FORCE_EXIT: "Force Exit", PREWATCH: "Pre-Watch", SHUTDOWN: "Shutdown",
    };
    const nextText = (labels[phase] || phase) + (data.new_entries_allowed ? " · Entries OK" : "");

    document.querySelectorAll(".tl-item").forEach((el) => {
      const p = el.dataset.phase;
      const pIdx = PHASE_ORDER.indexOf(p);
      el.classList.remove("active", "done", "future");
      if (p === phase) el.classList.add("active");
      else if (pIdx >= 0 && pIdx < idx) el.classList.add("done");
      else if (pIdx > idx) el.classList.add("future");
    });

    const nextEl = document.getElementById("next-event");
    if (nextEl) nextEl.textContent = nextText;
    const stripNext = document.getElementById("strip-next-event");
    if (stripNext) stripNext.textContent = nextText;
  } catch { /* silent */ }
}

// ── Candles ────────────────────────────────────────────────

function setupCanvas(canvas) {
  const wrap = canvas.closest(".chart-wrap");
  const dpr = window.devicePixelRatio || 1;
  const h = canvas.offsetHeight || parseInt(getComputedStyle(canvas).height, 10) || 220;
  const w = Math.max(wrap?.clientWidth || canvas.clientWidth || 120, 60);

  canvas.width = Math.floor(w * dpr);
  canvas.height = Math.floor(h * dpr);
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}

function redrawAllCharts() {
  Object.keys(chartMap).forEach((symbol) => {
    const candles = cachedCandles[symbol] || [];
    const hover = chartCrosshair[symbol] ?? null;
    drawCandles(symbol, candles, hover);
  });
}

function scheduleChartResize() {
  clearTimeout(chartResizeTimer);
  chartResizeTimer = setTimeout(redrawAllCharts, 80);
}

function updateChartHeader(cfg, candles) {
  if (!candles.length) {
    if (cfg.ltp) cfg.ltp.textContent = "—";
    if (cfg.chg) { cfg.chg.textContent = "—"; cfg.chg.className = "ch-chg neutral"; }
    if (cfg.ohlc) cfg.ohlc.textContent = "O — H — L — C —";
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
  if (cfg.ohlc) {
    cfg.ohlc.textContent = `O ${last.open.toFixed(2)}  H ${last.high.toFixed(2)}  L ${last.low.toFixed(2)}  C ${last.close.toFixed(2)}`;
  }
}

function drawCandles(symbol, candles, hoverIdx = null) {
  const cfg = chartMap[symbol];
  if (!cfg?.canvas) return;
  const { ctx, w, h } = setupCanvas(cfg.canvas);
  ctx.clearRect(0, 0, w, h);

  if (!candles.length) {
    ctx.fillStyle = "#5a5a6e";
    ctx.font = "12px JetBrains Mono, monospace";
    ctx.textAlign = "center";
    ctx.fillText("Awaiting live ticks", w / 2, h / 2);
    updateChartHeader(cfg, []);
    if (cfg.scale) cfg.scale.innerHTML = "";
    if (cfg.time) cfg.time.innerHTML = "";
    const waitNote = document.getElementById(CHART_WAIT_NOTE_IDS[symbol]);
    if (waitNote) waitNote.classList.add("hidden");
    chartState[symbol] = null;
    return;
  }

  const waitNote = document.getElementById(CHART_WAIT_NOTE_IDS[symbol]);
  if (waitNote) waitNote.classList.toggle("hidden", candles.length > 1);

  updateChartHeader(cfg, candles);

  const last = candles[candles.length - 1];
  const prices = candles.flatMap((c) => [c.high, c.low]);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const pad = (max - min) * 0.05 || 0.5;
  const lo = min - pad;
  const hi = max + pad;
  const range = hi - lo;
  const volH = Math.floor(h * 0.2);
  const topPad = 10;
  const priceH = h - volH - topPad - 8;
  const leftPad = 8;
  const rightEdge = w - 2;
  const drawW = rightEdge - leftPad;
  const barW = Math.max(2, drawW / candles.length - 1);
  const vols = candles.map((c) => c.volume || 0);
  const maxVol = Math.max(...vols, 1);

  const yPrice = (price) => topPad + ((hi - price) / range) * priceH;

  ctx.save();
  ctx.beginPath();
  ctx.rect(leftPad, 0, drawW, h);
  ctx.clip();

  for (let g = 0; g <= 4; g++) {
    const y = topPad + (g / 4) * priceH;
    ctx.strokeStyle = "rgba(255,255,255,0.06)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(leftPad, y);
    ctx.lineTo(rightEdge, y);
    ctx.stroke();
  }

  candles.forEach((c, i) => {
    const x = leftPad + i * (barW + 1);
    const yH = yPrice(c.high);
    const yL = yPrice(c.low);
    const yO = yPrice(c.open);
    const yC = yPrice(c.close);
    const bull = c.close >= c.open;
    const color = bull ? "#00e676" : "#ff3d5a";
    const isLast = i === candles.length - 1;
    const isHover = hoverIdx === i;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x + barW / 2, yH);
    ctx.lineTo(x + barW / 2, yL);
    ctx.lineWidth = isLast || isHover ? 2 : 1;
    ctx.stroke();
    const bodyTop = Math.min(yO, yC);
    const bodyH = Math.max(1, Math.abs(yC - yO));
    if (isLast) {
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1;
      ctx.strokeRect(x - 0.5, bodyTop - 0.5, barW + 1, bodyH + 1);
    }
    ctx.fillStyle = color;
    ctx.fillRect(x, bodyTop, barW, bodyH);

    const volBarH = (vols[i] / maxVol) * (volH - 4);
    const volY = h - volBarH - 2;
    ctx.fillStyle = bull ? "rgba(0,230,118,0.35)" : "rgba(255,61,90,0.35)";
    ctx.fillRect(x, volY, barW, volBarH);
  });

  const yLast = yPrice(last.close);
  ctx.strokeStyle = "rgba(0,230,118,0.55)";
  ctx.setLineDash([5, 4]);
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(leftPad, yLast);
  ctx.lineTo(rightEdge, yLast);
  ctx.stroke();
  ctx.setLineDash([]);

  const bubbleX = rightEdge - 2;
  const bubbleY = yLast;
  ctx.fillStyle = last.close >= last.open ? "#00e676" : "#ff3d5a";
  ctx.beginPath();
  ctx.arc(bubbleX, bubbleY, 4, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#0a0a0e";
  ctx.font = "bold 9px JetBrains Mono, monospace";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  const label = last.close.toFixed(2);
  const tw = ctx.measureText(label).width + 8;
  ctx.fillStyle = last.close >= last.open ? "rgba(0,230,118,0.9)" : "rgba(255,61,90,0.9)";
  ctx.fillRect(bubbleX - tw - 6, bubbleY - 8, tw, 16);
  ctx.fillStyle = "#000";
  ctx.fillText(label, bubbleX - 10, bubbleY);

  if (candles.length === 1) {
    ctx.fillStyle = "rgba(255,255,255,0.55)";
    ctx.font = "10px JetBrains Mono, monospace";
    ctx.textAlign = "center";
    ctx.fillText("waiting for more ticks", w / 2, h - volH - 14);
  }

  if (hoverIdx != null && candles[hoverIdx]) {
    const c = candles[hoverIdx];
    const x = leftPad + hoverIdx * (barW + 1) + barW / 2;
    ctx.strokeStyle = "rgba(255,255,255,0.35)";
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x, topPad);
    ctx.lineTo(x, h - volH);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(leftPad, yPrice(c.close));
    ctx.lineTo(rightEdge, yPrice(c.close));
    ctx.stroke();
    ctx.setLineDash([]);
    if (cfg.ohlc) {
      cfg.ohlc.textContent = `O ${c.open.toFixed(2)}  H ${c.high.toFixed(2)}  L ${c.low.toFixed(2)}  C ${c.close.toFixed(2)}`;
    }
  }

  ctx.restore();

  if (cfg.scale) {
    cfg.scale.innerHTML = `<span>${hi.toFixed(2)}</span><span style="color:var(--bull)">${last.close.toFixed(2)}</span><span>${lo.toFixed(2)}</span>`;
  }
  if (cfg.time && candles.length >= 2) {
    const t0 = new Date(candles[0].timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
    const t1 = new Date(candles[candles.length - 1].timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
    cfg.time.innerHTML = `<span>${t0}</span><span>${t1}</span>`;
  }

  chartState[symbol] = { candles, w, h, lo, hi, range, barW, leftPad, topPad, priceH, volH, rightEdge };

  if (symbol === "NIFTY") {
    lastNiftyCandles = candles;
    drawSparkline(candles);
    updateNiftyCard(window.__lastDashboardState || {}, candles, lastOperatorData);
    updateMarketSummary(window.__lastDashboardState || {}, lastOperatorData);
  } else if (symbol === "ATM_CE") {
    lastAtmCeCandles = candles;
    updateMarketSummary(window.__lastDashboardState || {}, lastOperatorData);
  } else if (symbol === "ATM_PE") {
    lastAtmPeCandles = candles;
    updateMarketSummary(window.__lastDashboardState || {}, lastOperatorData);
  }
}

function initChartCrosshair() {
  Object.entries(chartMap).forEach(([symbol, cfg]) => {
    if (!cfg.canvas) return;
    cfg.canvas.addEventListener("mousemove", (e) => {
      const st = chartState[symbol];
      if (!st?.candles?.length) return;
      const rect = cfg.canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const idx = Math.max(0, Math.min(st.candles.length - 1, Math.floor((x - st.leftPad) / (st.barW + 1))));
      if (chartCrosshair[symbol] !== idx) {
        chartCrosshair[symbol] = idx;
        drawCandles(symbol, st.candles, idx);
      }
    });
    cfg.canvas.addEventListener("mouseleave", () => {
      chartCrosshair[symbol] = null;
      const st = chartState[symbol];
      if (st?.candles) drawCandles(symbol, st.candles);
    });
  });
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
    cachedCandles[symbol] = candles;
    drawCandles(symbol, candles, chartCrosshair[symbol] ?? null);
  }
  scheduleChartResize();
}

// ── Market summary (placeholders) ──────────────────────────

function msSet(id, val) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = val;
}

function syncMarketSummaryRows() {
  let visible = 0;
  document.querySelectorAll(".ms-table tr[data-ms]").forEach((row) => {
    const cells = row.querySelectorAll("[id^='ms-']");
    const hasVal = [...cells].some((c) => c.textContent && c.textContent !== "—");
    row.classList.toggle("ms-empty", !hasVal);
    if (hasVal) visible += 1;
  });
  const note = document.getElementById("ms-empty-note");
  if (note) note.classList.toggle("hidden", visible > 0);
}

function updateMarketSummary(state, operator) {
  const empty = "—";
  const op = operator || lastOperatorData || {};

  msSet("ms-advances", empty);
  msSet("ms-declines", empty);
  msSet("ms-vix", empty);
  msSet("ms-oi-ce", empty);
  msSet("ms-oi-pe", empty);
  msSet("ms-call-writing", empty);
  msSet("ms-put-writing", empty);
  msSet("ms-breadth", empty);

  if (state?.bias) {
    let bullPct = state.bias.direction === "BULL" ? state.bias.confidence_pct :
      state.bias.direction === "BEAR" ? 100 - state.bias.confidence_pct : 50;
    bullPct = Math.max(0, Math.min(100, bullPct));
    msSet("ms-bull-pct", `${bullPct.toFixed(0)}%`);
    msSet("ms-bear-pct", `${(100 - bullPct).toFixed(0)}%`);
  } else {
    msSet("ms-bull-pct", empty);
    msSet("ms-bear-pct", empty);
  }

  if (lastNiftyCandles.length) {
    const vol = lastNiftyCandles.reduce((s, c) => s + (c.volume || 0), 0);
    if (vol > 0) msSet("ms-volume", vol.toLocaleString("en-IN"));
    const dayHigh = Math.max(...lastNiftyCandles.map((c) => c.high));
    const dayLow = Math.min(...lastNiftyCandles.map((c) => c.low));
    msSet("ms-day-range", `${dayLow.toFixed(0)} – ${dayHigh.toFixed(0)}`);
  }

  if (state?.nifty_ltp) {
    msSet("ms-nifty-ltp", state.nifty_ltp.toFixed(2));
    msSet("ms-maxpain", String(Math.round(state.nifty_ltp / 50) * 50));
  }

  if (op.atm_strike) msSet("ms-atm-strike", String(op.atm_strike));
  if (op.expiry) msSet("ms-expiry", op.expiry);
  if (op.pcr != null) msSet("ms-pcr", op.pcr.toFixed(2));
  if (op.ce_premium) msSet("ms-ce-prem", Number(op.ce_premium).toFixed(2));
  if (op.pe_premium) msSet("ms-pe-prem", Number(op.pe_premium).toFixed(2));
  if (op.premium_spread != null) msSet("ms-prem-spread", op.premium_spread.toFixed(2));

  if (!op.pcr && lastAtmCeCandles.length && lastAtmPeCandles.length) {
    const ce = lastAtmCeCandles[lastAtmCeCandles.length - 1].close;
    const pe = lastAtmPeCandles[lastAtmPeCandles.length - 1].close;
    if (ce > 0 && pe > 0) msSet("ms-pcr", (pe / ce).toFixed(2));
  }

  syncMarketSummaryRows();
}

function updateEngineHealth(op, state) {
  const data = op || {};
  const st = state || window.__lastDashboardState || {};
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val ?? "—"; };

  const recent = data.execution_recent || [];
  const lastExec = recent.length ? recent[recent.length - 1] : null;
  const brokerLat = lastExec?.latency_ms != null ? `${Math.round(lastExec.latency_ms)} ms` : "—";

  const tickAges = data.tick_ages || {};
  const niftyAge = tickAges.NIFTY;
  const maxAge = Math.max(...Object.values(tickAges).filter((v) => v != null), 0);

  let lastDecision = "—";
  if (st.engine_decisions) {
    const times = Object.values(st.engine_decisions)
      .map((d) => d.updated_at)
      .filter(Boolean)
      .sort()
      .reverse();
    if (times[0]) lastDecision = new Date(times[0]).toLocaleTimeString("en-IN", { hour12: false });
  }

  set("eh-decision-latency", "—");
  set("eh-broker-latency", brokerLat);
  set("eh-ws-latency", st.websocket_connected ? "< 100 ms" : "—");
  set("eh-tick-delay", niftyAge != null ? `${niftyAge}s` : "—");
  set("eh-tick-age", maxAge ? `${maxAge}s` : "—");
  set("eh-last-decision", lastDecision);
  set("eh-last-order", data.last_order_at ? new Date(data.last_order_at).toLocaleTimeString("en-IN", { hour12: false }) : "—");
  set("eh-scheduler-phase", data.scheduler_phase || currentSchedulerPhase || "—");
  const nextEv = (data.next_events || [])[0];
  set("eh-next-event", nextEv ? `${nextEv.label || nextEv.time || "—"}` : "—");
  set("eh-uptime", formatDurationSec(data.uptime_sec));
}

function updateOrderMonitor(op) {
  const order = op?.latest_order;
  const emptyEl = document.getElementById("order-monitor-empty");
  const tableEl = document.getElementById("order-monitor-table");
  if (!order) {
    emptyEl?.classList.remove("hidden");
    tableEl?.classList.add("hidden");
    return;
  }
  emptyEl?.classList.add("hidden");
  tableEl?.classList.remove("hidden");
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val ?? "—"; };
  const br = order.broker_response || {};
  const sideLabel = br.action_label || (br.option_side ? `BUY ${br.option_side}` : br.symbol || "—");
  set("om-engine", (order.engine || "—").toUpperCase());
  set("om-action", order.state || "—");
  set("om-side", sideLabel);
  set("om-strike", br.strike ?? "—");
  set("om-qty", order.quantity || "—");
  set("om-price", order.executed_price != null ? Number(order.executed_price).toFixed(2) : "—");
  set("om-order-id", order.order_id || "—");
  set("om-broker-status", br.status || order.state || "—");
  set("om-latency", order.latency_ms != null ? `${Math.round(order.latency_ms)} ms` : "—");
  set("om-result", order.message || "—");
  set("om-updated", order.updated_at ? new Date(order.updated_at).toLocaleTimeString("en-IN", { hour12: false }) : "—");
}

function updateAlertTicker(state, op, readiness) {
  const el = document.getElementById("alert-ticker");
  if (!el) return;
  const parts = [];
  const st = state || {};
  const rd = readiness || op?.readiness || st.readiness;

  if (st.broker_connected) parts.push("Angel Connected");
  else parts.push("Angel Offline");
  if (st.websocket_connected) parts.push("WebSocket Stable");
  else parts.push("WebSocket Offline");
  if (st.available_margin > 0) parts.push("Margin Updated");
  if (op?.atm_strike) parts.push(`ATM Strike ${op.atm_strike}`);
  if (st.new_entries_allowed === false) parts.push("No New Entries");
  else if (st.broker_connected) parts.push("Waiting for Entry");

  const failed = (rd?.checks || []).filter((c) => !c.passed);
  if (failed.length) {
    const label = READINESS_LABELS[failed[0].name] || failed[0].name;
    parts.push(`Readiness Missing: ${label}`);
    el.className = "alert-ticker warn";
  } else if (rd?.ready) {
    el.className = "alert-ticker ok";
  } else {
    el.className = "alert-ticker";
  }

  const lastOrder = op?.latest_order;
  if (lastOrder?.state?.includes("CONFIRMED")) {
    if (lastOrder.state.includes("EXIT")) parts.push("EXIT Confirmed");
    else parts.push("BUY Confirmed");
  }

  el.textContent = parts.join(" · ");
}

function updateValidationStrip(op) {
  const val = op?.validation_status || {};
  const manual = op?.manual_validation_status || {};
  const autoMap = op?.auto_allowed_by_engine || {};
  const recovery = op?.recovery_status || {};

  const set = (id, text, cls) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = `val-chip ${cls || ""}`.trim();
  };

  const monitorOk = val.ready_for_manual_validation;
  set("val-monitor-status", `Monitor Val: ${monitorOk ? "READY" : "INCOMPLETE"}`, monitorOk ? "ok" : "warn");

  const passed = ["normal", "wick", "ultra"].filter((e) => manual[`${e}_manual_cycle_passed`]).length;
  set("val-manual-status", `Manual: ${passed}/3 passed`, passed > 0 ? "ok" : "warn");

  const anyAuto = Object.values(autoMap).some((v) => v?.allowed);
  const blocked = Object.entries(autoMap).find(([, v]) => !v?.allowed);
  set(
    "val-auto-status",
    anyAuto ? "AUTO: ALLOWED (per engine)" : `AUTO: BLOCKED${blocked ? " — " + blocked[1].reason : ""}`,
    anyAuto ? "ok" : "blocked"
  );

  const recClean = recovery.status === "clean" || recovery.status === "unknown";
  set("val-recovery-status", `Recovery: ${(recovery.status || "unknown").toUpperCase()}`, recClean ? "ok" : "warn");

  const desync = op?.broker_desync || {};
  if (desync.critical) {
    set("val-recovery-status", "CRITICAL DESYNC — app/broker mismatch", "warn");
  }
}

function renderTradeLogEntries(entries) {
  if (!entries?.length) return "No log entries yet.";
  return entries.map((row) => {
    const at = row.at ? new Date(row.at).toLocaleTimeString("en-IN", { hour12: false }) : "—";
    const sym = row.symbol || "";
    const side = row.side || "";
    const evt = row.event || "—";
    const qty = row.qty != null ? row.qty : "—";
    const px = row.price != null ? Number(row.price).toFixed(2) : "—";
    const oid = row.order_id || "";
  const line = `${at} | ${(row.engine || "").toUpperCase()} | ${evt} | ${side} ${sym} | qty ${qty} @ ${px}${oid ? ` | ${oid}` : ""}`;
    return `<span class="log-line log-exec">${line.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</span>`;
  }).join("");
}

function updateTradeLogPanel(op) {
  if (activeLogTab !== "trade" || logsPaused || logsCleared) return;
  const output = document.getElementById("logs-output");
  if (!output) return;
  const entries = op?.trade_log || [];
  output.innerHTML = renderTradeLogEntries(entries);
}

async function refreshOperator() {
  try {
    const res = await apiFetch("/dashboard/operator");
    if (!res.ok) return;
    const data = await res.json();
    lastOperatorData = data;
    updateValidationStrip(data);
    updateEngineHealth(data, window.__lastDashboardState);
    updateOrderMonitor(data);
    updateTradeLogPanel(data);
    updateAlertTicker(window.__lastDashboardState, data, data.readiness);
    updateMarketSummary(window.__lastDashboardState, data);
    updateNiftyCard(window.__lastDashboardState, lastNiftyCandles, data);
    if (window.__lastDashboardState) {
      setBrokerUI(
        window.__lastDashboardState.broker_connected,
        window.__lastDashboardState.websocket_connected,
        data.reconnect_status
      );
    }
  } catch (err) {
    console.warn("refreshOperator failed", err);
  }
}

async function refreshValidation() {
  try {
    const [valRes, manualRes] = await Promise.all([
      apiFetch("/validation/status"),
      apiFetch("/validation/manual"),
    ]);
    if (!valRes.ok) return;
    const val = await valRes.json();
    const manual = manualRes.ok ? await manualRes.json() : {};
    updateValidationStrip({
      validation_status: val,
      manual_validation_status: manual,
      auto_allowed_by_engine: lastOperatorData?.auto_allowed_by_engine || {},
      recovery_status: lastOperatorData?.recovery_status || { status: "unknown" },
    });
  } catch (err) {
    console.warn("refreshValidation failed", err);
  }
}

async function refreshDashboardPanels() {
  await Promise.all([
    refreshState(),
    refreshBroker(),
    refreshPnL(),
    refreshCandles(),
    refreshReadiness(),
    refreshOperator(),
    refreshTimeline(),
    refreshLogs(),
    refreshValidation(),
  ]);
}

// ── Logs ───────────────────────────────────────────────────

function logLineClass(line) {
  const u = line.toUpperCase();
  if (u.includes("ERROR") || u.includes("CRITICAL") || u.includes("FAILED") || u.includes("EXCEPTION")) return "log-error";
  if (u.includes("WARNING") || u.includes("WARN")) return "log-warning";
  if (u.includes("EXECUTION") || u.includes("ORDER_SENT") || u.includes("ORDER_CONFIRMED") || u.includes("EXIT_CONFIRMED")) return "log-exec";
  if (u.includes("SUCCESS") || u.includes("CONNECTED") || u.includes("APPROVED") || u.includes("FILLED")) return "log-success";
  if (u.includes("INFO")) return "log-info";
  return "log-dim";
}

function applyLogFilter(lines) {
  const q = (logFilterText || "").trim().toLowerCase();
  if (!q) return lines;
  return lines.filter((line) => line.toLowerCase().includes(q));
}

function renderLogLines(lines) {
  const filtered = applyLogFilter(lines);
  if (!filtered.length) return logFilterText ? "No matching log entries." : "No log entries yet.";
  return filtered.map((line) => {
    const safe = line.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<span class="log-line ${logLineClass(line)}">${safe}</span>`;
  }).join("");
}

async function refreshLogs() {
  if (logsPaused || logsCleared) return;
  if (activeLogTab === "trade" && lastOperatorData?.trade_log) {
    updateTradeLogPanel(lastOperatorData);
    return;
  }
  try {
    const res = await apiFetch(`/dashboard/logs?lines=120&log_type=${activeLogTab}`);
    if (!res.ok) return;
    const data = await res.json();
    cachedLogLines = data.lines || [];
    const output = document.getElementById("logs-output");
    if (!output) return;
    output.innerHTML = renderLogLines(cachedLogLines);
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

document.getElementById("log-search")?.addEventListener("input", (e) => {
  logFilterText = e.target.value || "";
  const output = document.getElementById("logs-output");
  if (output) output.innerHTML = renderLogLines(cachedLogLines);
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
  if (output) output.innerHTML = '<span class="log-line log-dim">Log view cleared.</span>';
  setTimeout(() => { logsCleared = false; }, POLL.logs);
});

document.getElementById("btn-export-logs")?.addEventListener("click", () => {
  const output = document.getElementById("logs-output");
  const text = output?.innerText || output?.textContent || "";
  const blob = new Blob([text], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `logs_${activeLogTab}_${Date.now()}.txt`;
  a.click();
});

// ── State ──────────────────────────────────────────────────

async function refreshState() {
  const seq = ++stateFetchSeq;
  try {
    const res = await apiFetch("/dashboard/state");
    if (!res.ok || seq !== stateFetchSeq) return;
    const state = await res.json();
    if (seq !== stateFetchSeq) return;
    window.__lastDashboardState = state;

    setBrokerUI(state.broker_connected, state.websocket_connected, lastOperatorData?.reconnect_status);
    updateMarginStrip(state);
    updateBullBear(state.bias);
    updateMarketSummary(state, lastOperatorData);
    updateNiftyCard(state, lastNiftyCandles, lastOperatorData);
    updateAlertTicker(state, lastOperatorData, state.readiness);

    if (state.nifty_ltp) {
      const ltpEl = document.getElementById("nifty-ltp");
      if (ltpEl) ltpEl.textContent = state.nifty_ltp.toFixed(2);
    }

    if (state.engine_modes) {
      Object.entries(state.engine_modes).forEach(([eng, mode]) => {
        if (pendingModeChanges[eng]) return;
        syncEngineModeUI(eng, mode);
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
    if (state.allocations) {
      if (sliders.normal) sliders.normal.value = state.allocations.normal ?? 30;
      if (sliders.wick) sliders.wick.value = state.allocations.wick ?? 30;
      if (sliders.ultra) sliders.ultra.value = state.allocations.ultra ?? 40;
    }

    const updated = document.getElementById("last-updated");
    if (updated) updated.textContent = "Last updated: " + new Date(state.last_updated).toLocaleTimeString();
  } catch { /* silent */ }
}

// ── Password confirmation modal ────────────────────────────

function formatEstimatedAmount(premium, qty) {
  if (!premium || !qty) return "—";
  return formatCurrency(premium * qty);
}

function setPasswordModalError(message) {
  const err = document.getElementById("pwd-modal-error");
  if (!err) return;
  if (message) {
    err.textContent = message;
    err.classList.remove("hidden");
  } else {
    err.textContent = "";
    err.classList.add("hidden");
  }
}

function closePasswordModal(result = null) {
  const modal = document.getElementById("password-modal");
  const input = document.getElementById("pwd-modal-input");
  if (modal) modal.classList.add("hidden");
  if (input) input.value = "";
  setPasswordModalError("");
  if (passwordModalResolver) {
    const resolve = passwordModalResolver;
    passwordModalResolver = null;
    resolve(result);
  }
}

function showPasswordModal({ title, summary, details = [], hideCancel = false, error = "" }) {
  return new Promise((resolve) => {
    const modal = document.getElementById("password-modal");
    const titleEl = document.getElementById("pwd-modal-title");
    const summaryEl = document.getElementById("pwd-modal-summary");
    const detailsEl = document.getElementById("pwd-modal-details");
    const input = document.getElementById("pwd-modal-input");
    const cancelBtn = document.getElementById("pwd-modal-cancel");
    if (!modal || !titleEl || !summaryEl || !detailsEl || !input) {
      resolve(null);
      return;
    }
    passwordModalResolver = resolve;
    titleEl.textContent = title || "Confirm Action";
    summaryEl.textContent = summary || "—";
    detailsEl.innerHTML = details.length
      ? details.map((d) => `
      <div class="pwd-detail"><span>${d.label}</span><b>${d.value ?? "—"}</b></div>
    `).join("")
      : "";
    if (cancelBtn) cancelBtn.classList.toggle("hidden", hideCancel);
    input.value = "";
    setPasswordModalError(error);
    modal.classList.remove("hidden");
    setTimeout(() => input.focus(), 50);
  });
}

document.getElementById("pwd-modal-cancel")?.addEventListener("click", () => closePasswordModal(null));
document.getElementById("pwd-modal-backdrop")?.addEventListener("click", () => closePasswordModal(null));
document.getElementById("pwd-modal-confirm")?.addEventListener("click", () => {
  const input = document.getElementById("pwd-modal-input");
  const password = input?.value || "";
  if (!password) {
    setPasswordModalError("Password verification failed");
    return;
  }
  closePasswordModal(password);
});
document.getElementById("pwd-modal-input")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("pwd-modal-confirm")?.click();
  if (e.key === "Escape") closePasswordModal(null);
});
document.addEventListener("keydown", (e) => {
  const modal = document.getElementById("password-modal");
  if (e.key === "Escape" && modal && !modal.classList.contains("hidden")) {
    closePasswordModal(null);
  }
});

async function requestDashboardPassword(options) {
  return showPasswordModal(options);
}

async function postDashboardPassword(path, password) {
  const res = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (res.status === 403) {
    return false;
  }
  return res.ok;
}

async function requireDashboardWakeup() {
  document.body.classList.add("dashboard-locked");
  let lastError = "";
  while (true) {
    const password = await requestDashboardPassword({
      title: "Start PENTAGON5 Dashboard?",
      summary: "Enter Dashboard Password.",
      hideCancel: true,
      error: lastError,
    });
    if (!password) {
      lastError = "Password verification failed";
      continue;
    }
    const ok = await postDashboardPassword("/system/wakeup", password);
    if (ok) {
      document.body.classList.remove("dashboard-locked");
      return true;
    }
    lastError = "Password verification failed";
  }
}

// ── Engine mode controls ───────────────────────────────────

async function setEngineMode(engine, mode, previousMode = null) {
  const priorMode =
    previousMode ||
    document.querySelector(`.mode-select[data-engine="${engine}"]`)?.dataset.confirmedMode ||
    window.__lastDashboardState?.engine_modes?.[engine] ||
    "MONITOR";

  pendingModeChanges[engine] = true;
  syncEngineModeUI(engine, mode);

  try {
    const res = await apiFetch(`/engine/${engine}/mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });
    if (res.status === 403) {
      const data = await res.json();
      const reason = data.detail?.reason || data.detail || "Action blocked";
      syncEngineModeUI(engine, priorMode);
      showToast(`${engine}: ${reason}`, "error");
      await refreshState();
      return false;
    }
    if (res.ok) {
      const data = await res.json();
      syncEngineModeUI(engine, data.mode || mode);
      showToast(`${engine} → ${data.mode || mode}`, "ok");
      await refreshState();
      return true;
    }
    syncEngineModeUI(engine, priorMode);
    showToast(`${engine}: mode change failed`, "error");
    return false;
  } finally {
    delete pendingModeChanges[engine];
  }
}

document.querySelectorAll(".mode-select").forEach((sel) => {
  sel.addEventListener("change", () => {
    const mode = sel.value;
    const previousMode = sel.dataset.confirmedMode || sel.dataset.lastMode || "MONITOR";
    setEngineMode(sel.dataset.engine, mode, previousMode);
  });
});

document.querySelectorAll(".eng-btn-auto").forEach((btn) => {
  btn.addEventListener("click", () => {
    const engine = btn.dataset.engine;
    const previousMode =
      document.querySelector(`.mode-select[data-engine="${engine}"]`)?.dataset.confirmedMode || "MONITOR";
    setEngineMode(engine, "AUTO", previousMode);
  });
});
document.querySelectorAll(".eng-btn-manual").forEach((btn) => {
  btn.addEventListener("click", () => {
    const engine = btn.dataset.engine;
    setEngineMode(engine, "MANUAL");
  });
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
    await setEngineMode(btn.dataset.engine, "MONITOR");
  });
});
document.querySelectorAll(".eng-btn-exit").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const engine = btn.dataset.engine;
    const res = await apiFetch(`/engine/${engine}/exit`, { method: "POST" });
    if (res.ok) {
      showToast(`${engine} exit sent`, "info");
      refreshState();
    }
  });
});

function updateManualApprovals(approvals) {
  const container = document.getElementById("manual-approvals");
  pendingApprovalsMap = {};
  if (!container) return;
  if (!approvals.length) { container.classList.add("hidden"); container.innerHTML = ""; return; }
  container.classList.remove("hidden");
  approvals.forEach((a) => { pendingApprovalsMap[a.approval_id] = a; });
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

const EXECUTION_SUCCESS_STATES = new Set(["POSITION_ACTIVE", "EXIT_CONFIRMED"]);
const EXECUTION_ERROR_STATES = new Set([
  "ORDER_REJECTED",
  "UNKNOWN_ORDER_STATE",
  "BLOCKED_BY_RISK",
  "BLOCKED_BY_BROKER",
  "BLOCKED_BY_TIME",
  "BLOCKED_BY_MARGIN",
  "BLOCKED_BY_ENGINE_MODE",
  "ORDER_TIMEOUT",
  "RECOVERY_REQUIRED",
]);

function formatExecutionToast(data) {
  const state = data?.state || "ERROR";
  const message = data?.message || "Execution failed";
  if (EXECUTION_SUCCESS_STATES.has(state)) {
    return { type: "ok", text: `${state}: ${message}` };
  }
  if (EXECUTION_ERROR_STATES.has(state)) {
    return { type: "error", text: `${state}: ${message}` };
  }
  return { type: "error", text: `${state}: ${message}` };
}

async function approveManual(id) {
  const res = await apiFetch("/execution/manual/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approval_id: id }),
  });
  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    data = { state: "ERROR", message: "Invalid server response" };
  }
  const toast = formatExecutionToast(data);
  showToast(toast.text, toast.type);
  refreshState();
}
async function rejectManual(id) {
  await apiFetch("/execution/manual/reject", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approval_id: id }) });
  showToast("Signal rejected", "info"); refreshState();
}
window.approveManual = approveManual;
window.rejectManual = rejectManual;

// ── Master bar actions ─────────────────────────────────────

document.getElementById("btn-exit-all")?.addEventListener("click", async () => {
  const res = await apiFetch("/execution/exit-all", { method: "POST" });
  if (res.ok) {
    showToast("Emergency exit all triggered", "error");
    refreshState();
  }
});

document.getElementById("btn-download-report")?.addEventListener("click", () => {
  window.open(`${API}/reports/download`, "_blank");
});

document.getElementById("btn-restart")?.addEventListener("click", async () => {
  await apiFetch("/system/restart", { method: "POST" });
  showToast("Engine restart / recovery", "info");
});

document.getElementById("btn-exit-server")?.addEventListener("click", async () => {
  const password = await requestDashboardPassword({
    title: "Stop PENTAGON5 Dashboard?",
    summary: "Enter Dashboard Password.",
  });
  if (!password) return;
  const ok = await postDashboardPassword("/system/shutdown", password);
  if (!ok) {
    showToast("Password verification failed", "error");
    return;
  }
  showToast("Shutdown initiated — server stopping", "info");
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
  await refreshDashboardPanels();
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

document.getElementById("btn-reset-stats")?.addEventListener("click", async () => {
  const res = await apiFetch("/validation/reset", { method: "POST" });
  if (!res.ok) {
    showToast("Validation reset failed", "error");
    return;
  }
  const data = await res.json();
  const passed = data.manual_passed_count ?? 0;
  showToast(`Manual validation reset — ${passed}/3 passed`, "ok");
  await refreshDashboardPanels();
});

document.getElementById("btn-clear-storage")?.addEventListener("click", () => {
  showToast("Safe clear storage — no action needed", "info");
});

document.getElementById("btn-clear-logs")?.addEventListener("click", () => {
  document.getElementById("btn-clear-logs-view")?.click();
});

// ── Init ───────────────────────────────────────────────────

function init() {
  try {
    initChartCrosshair();
    refreshHealth();
    refreshReadiness();
    refreshBroker();
    refreshState();
    refreshPnL();
    refreshCandles();
    refreshLogs();
    refreshTimeline();
    refreshOperator();
    refreshValidation();
    syncMarketSummaryRows();
  } catch (err) {
    console.error("dashboard init failed", err);
  }
  requestAnimationFrame(() => scheduleChartResize());
  setTimeout(scheduleChartResize, 250);

  setInterval(refreshHealth, POLL.health);
  setInterval(refreshReadiness, POLL.health);
  setInterval(refreshState, POLL.state);
  setInterval(refreshPnL, POLL.pnl);
  setInterval(refreshCandles, POLL.candles);
  setInterval(refreshLogs, POLL.logs);
  setInterval(refreshTimeline, POLL.scheduler);
  setInterval(refreshOperator, POLL.operator);
}

window.addEventListener("resize", scheduleChartResize);
requireDashboardWakeup().then((unlocked) => {
  if (unlocked) init();
});
