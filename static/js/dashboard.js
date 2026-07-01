const API = "/api/v1";

const POLL = { state: 3000, candles: 2000, health: 10000, logs: 4000, pnl: 3000, scheduler: 5000 };

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
  jwt_valid: "JWT",
  feed_token_valid: "Feed Token",
  websocket_connected: "WebSocket",
  nifty_tick_fresh: "NIFTY Tick",
  atm_ce_tick_fresh: "ATM CE",
  atm_pe_tick_fresh: "ATM PE",
  margin_fetched: "Margin",
  instrument_master_loaded: "Instrument Master",
  expiry_selected: "Expiry / ATM",
  no_rate_limit: "API Rate",
};

const chartState = {};
const chartCrosshair = {};

let brokerBusy = false;
let logsPaused = false;
let logsCleared = false;
let activeLogTab = "system";
let logAutoScroll = true;
let lastNiftyCandles = [];
let lastAtmCeCandles = [];
let lastAtmPeCandles = [];
let currentSchedulerPhase = "OFFLINE";

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

function updateNiftyCard(state, candles) {
  const ltpEl = document.getElementById("nifty-ltp");
  const chgEl = document.getElementById("nifty-change");
  const pctEl = document.getElementById("nifty-change-pct");
  const openEl = document.getElementById("nifty-open");
  const highEl = document.getElementById("nifty-high");
  const lowEl = document.getElementById("nifty-low");
  const prevEl = document.getElementById("nifty-prev-close");

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
  }

  if (candles?.length) {
    const dayHigh = Math.max(...candles.map((c) => c.high));
    const dayLow = Math.min(...candles.map((c) => c.low));
    if (openEl) openEl.textContent = candles[0].open.toFixed(2);
    if (highEl) highEl.textContent = dayHigh.toFixed(2);
    if (lowEl) lowEl.textContent = dayLow.toFixed(2);
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
  if (d === "BLOCKED") return { text: "BLOCKED", cls: "badge-blocked" };
  if (d.startsWith("WOULD_BUY") || d === "READY") return { text: "READY", cls: "badge-ready" };
  if (d === "WOULD_EXIT") return { text: "BLOCKED", cls: "badge-blocked" };
  if (d === "WAIT" && m === "MONITOR") return { text: "MONITOR", cls: "badge-monitor" };
  if (d === "WAIT") return { text: "WAIT", cls: "badge-wait" };
  return { text: d.replace(/_/g, " "), cls: "badge-wait" };
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
  const wrap = canvas.closest(".chart-wrap") || canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max((wrap?.clientWidth || 280) - 40, 120);
  const h = canvas.offsetHeight || parseInt(getComputedStyle(canvas).height, 10) || 220;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = w + "px";
  canvas.style.height = h + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
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
    chartState[symbol] = null;
    return;
  }

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
  const barW = Math.max(2, (w - leftPad * 2) / candles.length - 1);
  const vols = candles.map((c) => c.volume || 0);
  const maxVol = Math.max(...vols, 1);

  const yPrice = (price) => topPad + ((hi - price) / range) * priceH;

  for (let g = 0; g <= 4; g++) {
    const y = topPad + (g / 4) * priceH;
    ctx.strokeStyle = "rgba(255,255,255,0.06)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(leftPad, y);
    ctx.lineTo(w - leftPad, y);
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
  ctx.lineTo(w - leftPad, yLast);
  ctx.stroke();
  ctx.setLineDash([]);

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
    ctx.lineTo(w - leftPad, yPrice(c.close));
    ctx.stroke();
    ctx.setLineDash([]);
    if (cfg.ohlc) {
      cfg.ohlc.textContent = `O ${c.open.toFixed(2)}  H ${c.high.toFixed(2)}  L ${c.low.toFixed(2)}  C ${c.close.toFixed(2)}`;
    }
  }

  if (cfg.scale) {
    cfg.scale.innerHTML = `<span>${hi.toFixed(2)}</span><span style="color:var(--bull)">${last.close.toFixed(2)}</span><span>${lo.toFixed(2)}</span>`;
  }
  if (cfg.time && candles.length >= 2) {
    const t0 = new Date(candles[0].timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
    const t1 = new Date(candles[candles.length - 1].timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
    cfg.time.innerHTML = `<span>${t0}</span><span>${t1}</span>`;
  }

  chartState[symbol] = { candles, w, h, lo, hi, range, barW, leftPad, topPad, priceH, volH };

  if (symbol === "NIFTY") {
    lastNiftyCandles = candles;
    drawSparkline(candles);
    updateNiftyCard(window.__lastDashboardState || {}, candles);
    updateMarketSummary(window.__lastDashboardState || {});
  } else if (symbol === "ATM_CE") {
    lastAtmCeCandles = candles;
    updateMarketSummary(window.__lastDashboardState || {});
  } else if (symbol === "ATM_PE") {
    lastAtmPeCandles = candles;
    updateMarketSummary(window.__lastDashboardState || {});
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
    drawCandles(symbol, candles);
  }
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

function updateMarketSummary(state) {
  const empty = "—";
  msSet("ms-advances", empty);
  msSet("ms-declines", empty);
  msSet("ms-unchanged", empty);
  msSet("ms-fii", empty);
  msSet("ms-dii", empty);
  msSet("ms-vix", empty);

  if (lastNiftyCandles.length) {
    const vol = lastNiftyCandles.reduce((s, c) => s + (c.volume || 0), 0);
    if (vol > 0) msSet("ms-volume", vol.toLocaleString("en-IN"));
    const dayHigh = Math.max(...lastNiftyCandles.map((c) => c.high));
    const dayLow = Math.min(...lastNiftyCandles.map((c) => c.low));
    msSet("ms-day-range", `${dayLow.toFixed(0)} – ${dayHigh.toFixed(0)}`);
    const turnover = lastNiftyCandles.reduce((s, c) => s + ((c.volume || 0) * c.close), 0);
    if (turnover > 0) msSet("ms-value", `₹${(turnover / 1e7).toFixed(1)} Cr`);
  }

  if (state?.nifty_ltp) {
    msSet("ms-nifty-ltp", state.nifty_ltp.toFixed(2));
    msSet("ms-maxpain", String(Math.round(state.nifty_ltp / 50) * 50));
  }

  if (lastAtmCeCandles.length && lastAtmPeCandles.length) {
    const ce = lastAtmCeCandles[lastAtmCeCandles.length - 1].close;
    const pe = lastAtmPeCandles[lastAtmPeCandles.length - 1].close;
    if (ce > 0 && pe > 0) msSet("ms-pcr", (pe / ce).toFixed(2));
  }

  syncMarketSummaryRows();
}

// ── Logs ───────────────────────────────────────────────────

function logLineClass(line) {
  const u = line.toUpperCase();
  if (u.includes("ERROR") || u.includes("CRITICAL") || u.includes("FAILED") || u.includes("EXCEPTION")) return "log-error";
  if (u.includes("WARNING") || u.includes("WARN")) return "log-warning";
  if (u.includes("SUCCESS") || u.includes("CONNECTED") || u.includes("APPROVED") || u.includes("FILLED")) return "log-success";
  if (u.includes("INFO")) return "log-info";
  return "log-dim";
}

function renderLogLines(lines) {
  if (!lines.length) return "No log entries yet.";
  return lines.map((line) => {
    const safe = line.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<span class="log-line ${logLineClass(line)}">${safe}</span>`;
  }).join("");
}

async function refreshLogs() {
  if (logsPaused || logsCleared) return;
  try {
    const res = await apiFetch(`/dashboard/logs?lines=120&log_type=${activeLogTab}`);
    if (!res.ok) return;
    const data = await res.json();
    const output = document.getElementById("logs-output");
    if (!output) return;
    output.innerHTML = renderLogLines(data.lines || []);
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
  try {
    const res = await apiFetch("/dashboard/state");
    if (!res.ok) return;
    const state = await res.json();
    window.__lastDashboardState = state;

    setBrokerUI(state.broker_connected, state.websocket_connected);
    updateMarginStrip(state);
    updateBullBear(state.bias);
    updateMarketSummary(state);
    updateNiftyCard(state, lastNiftyCandles);

    if (state.nifty_ltp) {
      const ltpEl = document.getElementById("nifty-ltp");
      if (ltpEl) ltpEl.textContent = state.nifty_ltp.toFixed(2);
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
  initChartCrosshair();
  refreshHealth();
  refreshReadiness();
  refreshBroker();
  refreshState();
  refreshPnL();
  refreshCandles();
  refreshLogs();
  refreshTimeline();
  syncMarketSummaryRows();

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
