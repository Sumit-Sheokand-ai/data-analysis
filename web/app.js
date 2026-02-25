const state = {
  auth: null,
  dashboard: null,
  activeView: "overview",
  optimizer: null,
};

function byId(id) {
  return document.getElementById(id);
}

function setStatus(message, level = "info") {
  const banner = byId("statusBanner");
  if (!banner) return;
  if (!message) {
    banner.hidden = true;
    banner.textContent = "";
    return;
  }
  banner.hidden = false;
  banner.className = `status-banner ${level}`;
  banner.textContent = message;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch (_err) {
    payload = {};
  }
  if (!response.ok) {
    const message = payload.message || `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value);
}

function formatCurrency(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function renderMetrics(containerId, metrics) {
  const root = byId(containerId);
  if (!root) return;
  root.innerHTML = "";
  if (!metrics || Object.keys(metrics).length === 0) {
    root.innerHTML = `<p class="hint">No metric snapshot available yet.</p>`;
    return;
  }
  Object.entries(metrics).forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "metric";
    item.innerHTML = `
      <div class="label">${label.replaceAll("_", " ")}</div>
      <div class="value">${formatValue(value)}</div>
    `;
    root.appendChild(item);
  });
}

function renderTable(containerId, rows, preferredOrder = []) {
  const root = byId(containerId);
  if (!root) return;
  root.innerHTML = "";
  if (!rows || rows.length === 0) {
    root.innerHTML = `<p class="hint">No rows available.</p>`;
    return;
  }
  const allColumns = new Set();
  rows.forEach((row) => Object.keys(row).forEach((key) => allColumns.add(key)));
  const remaining = [...allColumns].filter((col) => !preferredOrder.includes(col));
  const columns = [...preferredOrder.filter((col) => allColumns.has(col)), ...remaining];
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const tbody = document.createElement("tbody");
  const headerRow = document.createElement("tr");
  columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col.replaceAll("_", " ");
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((col) => {
      const td = document.createElement("td");
      const value = row[col];
      if (typeof value === "number" && col.includes("price")) {
        td.textContent = formatCurrency(value);
      } else {
        td.textContent = formatValue(value);
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(thead);
  table.appendChild(tbody);
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  wrap.appendChild(table);
  root.appendChild(wrap);
}

function renderOverviewSignals() {
  const root = byId("overviewSignals");
  if (!root) return;
  root.innerHTML = "";
  const overview = state.dashboard?.overview || {};
  const alerts = state.dashboard?.alerts || [];
  const messages = [];
  if (typeof overview.avg_ltv_cac_ratio === "number") {
    messages.push(`Average LTV:CAC is ${overview.avg_ltv_cac_ratio.toFixed(2)}.`);
  }
  if (typeof overview.avg_cac === "number") {
    messages.push(`Average CAC is ${overview.avg_cac.toFixed(2)}.`);
  }
  if (alerts.length > 0) {
    const warn = alerts.filter((r) => String(r.severity || "").toLowerCase() === "warn").length;
    const error = alerts.filter((r) => String(r.severity || "").toLowerCase() === "error").length;
    messages.push(`Active monitoring rows: ${alerts.length} (${warn} warnings, ${error} errors).`);
  }
  if (messages.length === 0) {
    messages.push("No actionable signals yet. Run pipeline with complete data to populate insights.");
  }
  messages.forEach((message) => {
    const li = document.createElement("li");
    li.textContent = message;
    root.appendChild(li);
  });
}

function renderBilling() {
  const summary = byId("billingSummary");
  const usageRoot = byId("billingUsage");
  if (!summary || !usageRoot) return;
  summary.innerHTML = "";
  usageRoot.innerHTML = "";
  const billing = state.dashboard?.billing;
  if (!billing) {
    summary.innerHTML = `<p class="hint">Billing data not available.</p>`;
    return;
  }
  const plan = billing.plan || {};
  const usage = billing.usage || {};
  const entries = [
    ["Plan", plan.display_name || "Unknown"],
    ["Monthly Price", typeof plan.monthly_price_usd === "number" ? formatCurrency(plan.monthly_price_usd) : "—"],
    ["Exports Left", formatValue(billing.report_exports_left)],
  ];
  entries.forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "metric";
    item.innerHTML = `<div class="label">${label}</div><div class="value">${value}</div>`;
    summary.appendChild(item);
  });
  renderTable("billingUsage", Object.entries(usage).map(([metric, value]) => ({ metric, value })), ["metric", "value"]);
}

function renderReadiness() {
  const summary = byId("readinessSummary");
  if (!summary) return;
  const readiness = state.dashboard?.readiness;
  if (!readiness) {
    summary.innerHTML = `<p class="hint">Readiness unavailable.</p>`;
    return;
  }
  summary.innerHTML = `
    <p><strong>Status:</strong> ${formatValue(readiness.status)}</p>
    <p><strong>Message:</strong> ${formatValue(readiness.message)}</p>
    <p class="hint">Missing outputs: ${(readiness.missing_outputs || []).join(", ") || "none"}</p>
  `;
  renderTable("rawFileTable", readiness.raw_files || [], ["dataset", "file", "exists", "rows"]);
}

function renderRetentionAndLtv() {
  renderTable(
    "retentionTable",
    state.dashboard?.retention || [],
    ["cohort_month", "month_index", "retention_rate", "active_customers", "cohort_size"],
  );
  renderTable(
    "ltvTable",
    state.dashboard?.ltv_customers || [],
    ["customer_id", "realized_ltv", "predicted_ltv", "prediction_method", "order_count"],
  );
}

function renderWhatChanged() {
  const changed = state.dashboard?.what_changed || {};
  renderTable("overviewDeltaTable", changed.overview_deltas || [], ["metric", "value_previous", "value_current", "delta", "delta_pct"]);
  renderTable("cacDeltaTable", changed.cac_deltas || [], ["channel", "cac_previous", "cac_current", "delta", "delta_pct"]);
  renderTable("ltvCacDeltaTable", changed.ltv_cac_deltas || [], ["channel", "ltv_cac_ratio_previous", "ltv_cac_ratio_current", "delta", "delta_pct"]);
}

function renderRecommendations() {
  renderTable(
    "recommendationTable",
    state.dashboard?.recommendations || [],
    ["priority", "theme", "action", "rationale", "expected_impact"],
  );
}

function setOptimizerDefaults() {
  const defaults = state.dashboard?.optimizer_defaults || {};
  const budget = byId("optimizerBudget");
  const targetCac = byId("optimizerTargetCac");
  const reserve = byId("optimizerReserve");
  if (!budget || !targetCac || !reserve) return;
  budget.value = String(defaults.total_budget ?? 10000);
  targetCac.value = String(defaults.target_max_cac ?? 80);
  reserve.value = String(defaults.reserve_pct ?? 10);
}

function renderOptimizer() {
  const root = byId("optimizerSummary");
  if (!root) return;
  root.innerHTML = "";
  const result = state.optimizer;
  if (!result) {
    root.innerHTML = `<p class="hint">Set your constraints and run optimizer.</p>`;
    renderTable("optimizerTable", [], []);
    return;
  }
  const summary = result.summary || {};
  const entries = [
    ["Usable Budget", formatCurrency(summary.usable_budget)],
    ["Projected Customers", formatValue(summary.projected_customers)],
    ["Projected Value", formatCurrency(summary.projected_value)],
    ["Blended CAC", formatValue(summary.blended_cac)],
    ["Value / Spend", formatValue(summary.blended_value_to_spend)],
  ];
  entries.forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "metric";
    item.innerHTML = `<div class="label">${label}</div><div class="value">${value}</div>`;
    root.appendChild(item);
  });
  renderTable(
    "optimizerTable",
    result.allocations || [],
    ["channel", "recommended_spend", "projected_customers", "projected_value", "projected_value_to_spend", "cac"],
  );
}

function renderDashboard() {
  renderMetrics("overviewMetrics", state.dashboard?.overview || {});
  renderOverviewSignals();
  renderTable(
    "channelTable",
    state.dashboard?.channel_performance || [],
    ["channel", "cac", "avg_predicted_ltv", "ltv_cac_ratio", "payback_months_est", "customers"],
  );
  renderTable(
    "alertTable",
    state.dashboard?.alerts || [],
    ["date", "severity", "check", "channel", "metric", "value", "threshold", "detail"],
  );
  renderRetentionAndLtv();
  renderWhatChanged();
  renderRecommendations();
  renderBilling();
  renderReadiness();
  if (!state.optimizer) {
    setOptimizerDefaults();
  }
  renderOptimizer();
}

function switchView(nextView) {
  state.activeView = nextView;
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === `view-${nextView}`);
  });
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === nextView);
  });
}

function setAuthSummary(auth) {
  const summary = byId("authSummary");
  const logoutButton = byId("logoutButton");
  if (!summary || !logoutButton) return;
  if (auth?.authenticated) {
    summary.textContent = `${auth.user_id} • ${auth.workspace_id} • ${auth.plan?.display_name || "Plan"}`;
    logoutButton.hidden = false;
    return;
  }
  summary.textContent = auth?.require_auth ? "Signed out" : "Guest session";
  logoutButton.hidden = true;
}

function setLoginVisibility(showLogin) {
  byId("loginSection").hidden = !showLogin;
  byId("appSection").hidden = showLogin;
}

async function loadSession() {
  const payload = await api("/api/auth/me");
  state.auth = {
    require_auth: Boolean(payload.require_auth),
    authenticated: Boolean(payload.authenticated),
    user_id: payload.user_id,
    workspace_id: payload.workspace_id,
    role: payload.role,
    plan: payload.plan || {},
  };
  setAuthSummary(state.auth);
  const needsLogin = state.auth.require_auth && !state.auth.authenticated;
  setLoginVisibility(needsLogin);
  return !needsLogin;
}

async function loadDashboard() {
  const payload = await api("/api/dashboard");
  state.dashboard = payload.dashboard || {};
  renderDashboard();
  const readiness = state.dashboard?.readiness;
  if (readiness?.status === "blocked") {
    setStatus(readiness.message, "warning");
  } else if (readiness?.status === "pending") {
    setStatus(readiness.message, "info");
  } else if (readiness?.status === "ready") {
    setStatus(readiness.message, "success");
  } else {
    setStatus("");
  }
}

async function runOptimizer(event) {
  event.preventDefault();
  const totalBudget = Number(byId("optimizerBudget")?.value || 0);
  const targetMaxCac = Number(byId("optimizerTargetCac")?.value || 0);
  const reservePct = Number(byId("optimizerReserve")?.value || 0);
  if (Number.isNaN(totalBudget) || Number.isNaN(targetMaxCac) || Number.isNaN(reservePct)) {
    setStatus("Optimizer values must be numeric.", "warning");
    return;
  }
  try {
    const payload = await api("/api/optimizer/run", {
      method: "POST",
      body: JSON.stringify({
        total_budget: totalBudget,
        target_max_cac: targetMaxCac,
        reserve_pct: reservePct,
      }),
    });
    state.optimizer = payload.optimizer || null;
    renderOptimizer();
    setStatus("Optimizer scenario completed.", "success");
  } catch (err) {
    setStatus(err.message || "Optimizer run failed.", "warning");
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const username = byId("loginUsername").value.trim();
  const password = byId("loginPassword").value;
  if (!username || !password) return;
  try {
    await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setStatus("Sign-in successful.", "success");
    const canUseApp = await loadSession();
    if (canUseApp) {
      await loadDashboard();
    }
  } catch (err) {
    setStatus(err.message || "Sign-in failed.", "warning");
  }
}

async function handleLogout() {
  try {
    await api("/api/auth/logout", { method: "POST", body: JSON.stringify({}) });
  } catch (_err) {
    // ignore logout errors and continue with signed-out UI
  }
  state.auth = null;
  state.dashboard = null;
  setStatus("Signed out.", "info");
  await initialize();
}

async function runPipeline() {
  const button = byId("runPipelineButton");
  const mode = byId("pipelineMode").value;
  const output = byId("pipelineResult");
  button.disabled = true;
  output.textContent = "Running pipeline...";
  try {
    const payload = await api("/api/pipeline/run", {
      method: "POST",
      body: JSON.stringify({ validation_mode: mode }),
    });
    output.textContent = payload.result?.status || "Pipeline completed.";
    await loadDashboard();
    setStatus("Pipeline run completed successfully.", "success");
  } catch (err) {
    output.textContent = "Pipeline failed.";
    setStatus(err.message || "Pipeline run failed.", "warning");
  } finally {
    button.disabled = false;
  }
}

function registerEvents() {
  byId("loginForm").addEventListener("submit", handleLogin);
  byId("logoutButton").addEventListener("click", handleLogout);
  byId("refreshButton").addEventListener("click", async () => {
    try {
      await loadDashboard();
      setStatus("Dashboard refreshed.", "success");
    } catch (err) {
      setStatus(err.message || "Could not refresh dashboard.", "warning");
    }
  });
  byId("runPipelineButton").addEventListener("click", runPipeline);
  const optimizerForm = byId("optimizerForm");
  if (optimizerForm) {
    optimizerForm.addEventListener("submit", runOptimizer);
  }
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchView(tab.dataset.view));
  });
}

async function initialize() {
  setStatus("");
  try {
    const canUseApp = await loadSession();
    if (canUseApp) {
      await loadDashboard();
    }
  } catch (err) {
    if (err.status === 401) {
      setLoginVisibility(true);
      setStatus("Sign in to continue.", "info");
      return;
    }
    setStatus(err.message || "Initialization failed.", "warning");
  }
}

registerEvents();
initialize();

