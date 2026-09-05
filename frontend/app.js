/**
 * Frontend logic for AutoPerf Autonomous Performance Testing Platform.
 */

// State
let currentIntentData = null;
let currentRunId = null;
let activeWebSocket = null;
let pollingInterval = null;
let vusChart = null;
let latencyChart = null;

// Elements
const promptForm = document.getElementById("prompt-form");
const promptInput = document.getElementById("prompt-input");
const btnAnalyze = document.getElementById("btn-analyze");
const analyzeSpinner = document.getElementById("analyze-spinner");
const intentSection = document.getElementById("intent-section");
const btnRunTest = document.getElementById("btn-run-test");
const liveDashboardSection = document.getElementById("live-dashboard-section");
const resultsSection = document.getElementById("results-section");
const historySection = document.getElementById("history-section");
const btnHistoryToggle = document.getElementById("btn-history-toggle");
const historyCountSpan = document.getElementById("history-count");
const historyTableBody = document.getElementById("history-table-body");
const btnViewScript = document.getElementById("btn-view-script");
const scriptDrawer = document.getElementById("script-drawer");
const btnCloseScript = document.getElementById("btn-close-script");
const scriptCodeBlock = document.getElementById("script-code-block");
const alertBanner = document.getElementById("alert-banner");
const alertMessage = document.getElementById("alert-message");
const btnCloseAlert = document.getElementById("btn-close-alert");

function showError(msg) {
  if (alertBanner && alertMessage) {
    alertMessage.textContent = msg;
    alertBanner.classList.remove("hidden");
    alertBanner.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

function hideError() {
  if (alertBanner) alertBanner.classList.add("hidden");
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

if (btnCloseAlert) {
  btnCloseAlert.addEventListener("click", hideError);
}

// Initialize Charts
function initCharts() {
  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    scales: {
      x: { grid: { color: 'rgba(255, 255, 255, 0.08)' }, ticks: { color: '#8e8e8a' } },
      y: { grid: { color: 'rgba(255, 255, 255, 0.08)' }, ticks: { color: '#8e8e8a' } }
    },
    plugins: {
      legend: { labels: { color: '#b3b3ae' } }
    }
  };

  const ctxVus = document.getElementById("vusChart").getContext("2d");
  vusChart = new Chart(ctxVus, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'Active VUs',
        data: [],
        borderColor: '#ffffff',
        backgroundColor: 'rgba(255, 255, 255, 0.12)',
        tension: 0.3,
        fill: true
      }]
    },
    options: commonOptions
  });

  const ctxLatency = document.getElementById("latencyChart").getContext("2d");
  latencyChart = new Chart(ctxLatency, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'p95 Latency (ms)',
          data: [],
          borderColor: '#f3f3f1',
          backgroundColor: 'rgba(243, 243, 241, 0.08)',
          tension: 0.3
        },
        {
          label: 'Error %',
          data: [],
          borderColor: '#ef4444',
          backgroundColor: 'rgba(239, 68, 68, 0.15)',
          tension: 0.3,
          yAxisID: 'y1'
        }
      ]
    },
    options: {
      ...commonOptions,
      scales: {
        ...commonOptions.scales,
        y1: {
          position: 'right',
          grid: { drawOnChartArea: false },
          ticks: { color: '#ef4444' }
        }
      }
    }
  });
}

function resetCharts() {
  if (vusChart) {
    vusChart.data.labels = [];
    vusChart.data.datasets[0].data = [];
    vusChart.update();
  }
  if (latencyChart) {
    latencyChart.data.labels = [];
    latencyChart.data.datasets[0].data = [];
    latencyChart.data.datasets[1].data = [];
    latencyChart.update();
  }
}

// Preset button handlers
document.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => {
    promptInput.value = chip.getAttribute("data-prompt");
    // Clear any previous stale test results when switching to a new prompt
    resultsSection.classList.add("hidden");
    liveDashboardSection.classList.add("hidden");
    intentSection.classList.add("hidden");
    currentIntentData = null;
    currentRunId = null;
    promptInput.focus();
  });
});

// Clear stale results when user starts typing a new query
promptInput.addEventListener("input", () => {
  // If the prompt changed, clear stale intent and previous results
  if (currentIntentData || !resultsSection.classList.contains("hidden")) {
    resultsSection.classList.add("hidden");
    intentSection.classList.add("hidden");
    currentIntentData = null;
    currentRunId = null;
  }
});

// Keyboard shortcut: Ctrl+Enter or Cmd+Enter to immediately analyze intent
promptInput.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    promptForm.dispatchEvent(new Event("submit", { cancelable: true }));
  }
});

// Prompt submission -> Intent analysis
promptForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();
  const promptText = promptInput.value.trim();
  if (!promptText) {
    showError("Please enter a test description (e.g. 'stress test my heavy endpoint with 50 users').");
    return;
  }

  // Clear previous test reports immediately so user never sees stale data
  resultsSection.classList.add("hidden");
  liveDashboardSection.classList.add("hidden");
  intentSection.classList.add("hidden");
  currentRunId = null;

  btnAnalyze.disabled = true;
  analyzeSpinner.classList.remove("hidden");

  try {
    const res = await fetch("/api/intent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: promptText })
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: "Intent analysis failed" }));
      throw new Error(errData.detail || "Intent analysis failed");
    }
    
    currentIntentData = await res.json();
    renderIntentCard(currentIntentData);
  } catch (err) {
    showError("Intent Extraction Error: " + err.message);
  } finally {
    btnAnalyze.disabled = false;
    analyzeSpinner.classList.add("hidden");
  }
});

function renderIntentCard(data) {
  const intent = data.intent;
  document.getElementById("intent-badge-type").textContent = intent.test_type.toUpperCase();
  document.getElementById("intent-badge-type").className = `badge badge-${intent.test_type}`;
  document.getElementById("intent-badge-vus").textContent = `${intent.virtual_users} VUs`;
  document.getElementById("intent-badge-duration").textContent = intent.duration;
  document.getElementById("intent-summary-title").textContent = intent.summary_description;

  // Endpoints
  const endpointsList = document.getElementById("intent-endpoints-list");
  endpointsList.innerHTML = "";
  intent.endpoints_involved.forEach(ep => {
    const tag = document.createElement("span");
    tag.className = "tag-item";
    tag.textContent = `${ep.method} ${ep.path}`;
    endpointsList.appendChild(tag);
  });

  // Criteria
  const crit = intent.success_criteria;
  document.getElementById("intent-criteria").innerHTML = `
    <div><strong>Target URL:</strong> <code>${intent.target_url}</code></div>
    <div><strong>p95 Latency Threshold:</strong> &le; ${crit.p95_ms} ms</div>
    <div><strong>Max Error Rate:</strong> &le; ${(crit.max_error_rate * 100).toFixed(1)}%</div>
  `;

  // Assumptions
  const assumptionsList = document.getElementById("intent-assumptions");
  assumptionsList.innerHTML = "";
  (intent.assumptions_made || []).forEach(asmp => {
    const li = document.createElement("li");
    li.textContent = asmp;
    assumptionsList.appendChild(li);
  });

  // Payloads Preview
  const payloadPreview = document.getElementById("intent-payload-preview");
  payloadPreview.textContent = JSON.stringify(data.synthetic_payloads, null, 2);

  intentSection.classList.remove("hidden");
  intentSection.scrollIntoView({ behavior: 'smooth' });
}

// Run Test Confirmation Click
btnRunTest.addEventListener("click", async () => {
  if (!currentIntentData) return;
  hideError();
  btnRunTest.disabled = true;

  try {
    const res = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: promptInput.value,
        intent: currentIntentData.intent,
        synthetic_payloads: currentIntentData.synthetic_payloads
      })
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: "Launch failed" }));
      throw new Error(errData.detail || "Launch failed");
    }
    
    const runInfo = await res.json();
    currentRunId = runInfo.run_id;
    startLiveExecution(currentRunId);
  } catch (err) {
    showError("Could not launch load test: " + err.message);
    btnRunTest.disabled = false;
  }
});

function startLiveExecution(runId) {
  // Switch sections
  intentSection.classList.add("hidden");
  resultsSection.classList.add("hidden");
  liveDashboardSection.classList.remove("hidden");
  liveDashboardSection.scrollIntoView({ behavior: 'smooth' });

  document.getElementById("run-id-display").textContent = `run_id: ${runId}`;
  document.getElementById("run-status-text").textContent = "INITIALIZING SCRIPT...";

  resetCharts();
  connectWebSocket(runId);
}

function connectWebSocket(runId) {
  if (activeWebSocket) {
    activeWebSocket.close();
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/runs/${runId}`;
  activeWebSocket = new WebSocket(wsUrl);

  activeWebSocket.onopen = () => {
    console.log("WebSocket connected for run", runId);
  };

  activeWebSocket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "metric_snapshot") {
        updateLiveDashboardMetrics(msg.data, "websocket");
      } else if (msg.type === "status_update") {
        handleStatusUpdate(msg.status, msg.data);
      }
    } catch (e) {
      console.error("Error handling WS message:", e);
    }
  };

  activeWebSocket.onerror = (e) => {
    console.warn("WebSocket error, enabling polling fallback", e);
    startPollingFallback(runId);
  };

  activeWebSocket.onclose = (e) => {
    console.log("WebSocket closed", e);
    // If closed while the test is still actively running, fall back to HTTP polling
    const statusText = document.getElementById("run-status-text")?.textContent || "";
    if (statusText !== "COMPLETED" && statusText !== "FAILED" && !liveDashboardSection.classList.contains("hidden")) {
      console.warn("WebSocket closed mid-run, falling back to HTTP polling");
      startPollingFallback(runId);
    }
  };
}

function startPollingFallback(runId) {
  if (pollingInterval) clearInterval(pollingInterval);
  console.log("[POLLING FALLBACK] Started HTTP polling fallback for run:", runId);
  pollingInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/runs/${runId}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.status === "COMPLETED" || data.status === "FAILED") {
        clearInterval(pollingInterval);
        loadRunResults(data);
      } else {
        const metricRes = await fetch(`/api/runs/${runId}/metrics`);
        if (metricRes.ok) {
          const m = await metricRes.json();
          if (m.vus !== undefined) updateLiveDashboardMetrics(m, "polling");
        }
      }
    } catch (e) {
      console.error("Polling error:", e);
    }
  }, 1000);
}

function updateLiveDashboardMetrics(snapshot, source = "websocket") {
  // Expose global history for test assertion and console logging
  window.__liveMetricUpdates = window.__liveMetricUpdates || [];
  window.__liveMetricUpdates.push({
    ...snapshot,
    receivedAt: Date.now(),
    source
  });

  console.log(`[LIVE METRIC ${source.toUpperCase()}] ${snapshot.elapsed_sec}s | VUs: ${snapshot.vus} | RPS: ${snapshot.rps} | p95: ${snapshot.p95_ms}ms | Err%: ${(snapshot.error_rate * 100).toFixed(1)}%`);

  document.getElementById("live-elapsed").textContent = `${snapshot.elapsed_sec}s`;
  document.getElementById("stat-vus").textContent = snapshot.vus;
  document.getElementById("stat-rps").textContent = snapshot.rps;
  document.getElementById("stat-p95").textContent = `${snapshot.p95_ms} ms`;
  document.getElementById("stat-error-rate").textContent = `${(snapshot.error_rate * 100).toFixed(1)}%`;
  document.getElementById("stat-failed-count").textContent = `${snapshot.failed_requests} failed (${snapshot.total_requests} total)`;

  // Update chart
  if (vusChart && latencyChart) {
    const timeLabel = `${snapshot.elapsed_sec}s`;
    if (!vusChart.data.labels.includes(timeLabel)) {
      vusChart.data.labels.push(timeLabel);
      vusChart.data.datasets[0].data.push(snapshot.vus);
      if (vusChart.data.labels.length > 100) {
        vusChart.data.labels.shift();
        vusChart.data.datasets[0].data.shift();
      }
      vusChart.update();

      latencyChart.data.labels.push(timeLabel);
      latencyChart.data.datasets[0].data.push(snapshot.p95_ms);
      latencyChart.data.datasets[1].data.push((snapshot.error_rate * 100).toFixed(1));
      if (latencyChart.data.labels.length > 100) {
        latencyChart.data.labels.shift();
        latencyChart.data.datasets[0].data.shift();
        latencyChart.data.datasets[1].data.shift();
      }
      latencyChart.update();
    }
  }
}

function handleStatusUpdate(status, data) {
  document.getElementById("run-status-text").textContent = status.replace(/_/g, ' ');
  if (data && data.script) {
    scriptCodeBlock.textContent = data.script;
  }
  if (status === "FAILED") {
    const err = data && data.error ? data.error : "Load test run failed during execution.";
    showError("Execution Failure: " + err);
    btnRunTest.disabled = false;
  }
  if (status === "COMPLETED" || status === "FAILED") {
    if (activeWebSocket) activeWebSocket.close();
    if (pollingInterval) clearInterval(pollingInterval);
    setTimeout(() => {
      fetchRunAndShowResults(currentRunId);
    }, 500);
  }
}


function loadRunResults(run, shouldScroll = true) {
  liveDashboardSection.classList.add("hidden");
  resultsSection.classList.remove("hidden");
  btnRunTest.disabled = false;

  const metrics = run.metrics || {};
  const isPipelineFailure = run.status === "FAILED";
  const passed = metrics.passed;
  const noData = metrics.no_data === true || (!isPipelineFailure && metrics.total_requests === 0);
  const verdictBanner = document.getElementById("verdict-banner");

  if (isPipelineFailure) {
    verdictBanner.textContent = "RUN FAILED: PIPELINE ERROR";
    verdictBanner.className = "verdict-banner verdict-fail";
  } else if (noData) {
    verdictBanner.textContent = "NO DATA COLLECTED (TEST INCONCLUSIVE)";
    verdictBanner.className = "verdict-banner verdict-fail";
  } else if (passed === true) {
    verdictBanner.textContent = "TEST PASSED (ALL THRESHOLDS MET)";
    verdictBanner.className = "verdict-banner verdict-pass";
  } else {
    verdictBanner.textContent = "TEST FAILED (THRESHOLDS BREACHED)";
    verdictBanner.className = "verdict-banner verdict-fail";
  }

  // Scorecards
  const scorecardGrid = document.getElementById("scorecard-grid");
  if ((isPipelineFailure || noData) && (!metrics.total_requests || metrics.total_requests === 0)) {
    scorecardGrid.innerHTML = `
      <div class="stat-card" style="grid-column: 1 / -1; text-align: left; background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); padding: 16px;">
        <div style="font-weight: 600; color: #f87171; margin-bottom: 4px;">⚠️ No Load-Test Metrics Collected</div>
        <div style="font-size: 0.85rem; color: #94a3b8;">${isPipelineFailure ? 'The test run encountered a pipeline error before load metrics could be recorded.' : 'k6 completed but recorded zero requests — the target may have been unreachable or the script may have failed.'} See error details below.</div>
      </div>
    `;
  } else {
    let failureReasonsHtml = "";
    if (metrics.threshold_failures && metrics.threshold_failures.length > 0) {
      failureReasonsHtml = `
        <div class="threshold-failures-box" style="grid-column: 1 / -1; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 8px; padding: 12px 16px; margin-bottom: 8px;">
          <div style="color: #ef4444; font-weight: 600; margin-bottom: 6px;">❌ Threshold Breaches Detected:</div>
          <ul style="margin: 0; padding-left: 20px; color: #fca5a5; font-size: 0.88rem;">
            ${metrics.threshold_failures.map(tf => `<li>${escapeHtml(tf)}</li>`).join("")}
          </ul>
        </div>
      `;
    }

    scorecardGrid.innerHTML = `
      ${failureReasonsHtml}
      <div class="stat-card">
        <span class="stat-label">Total Requests</span>
        <div class="stat-value">${metrics.total_requests !== undefined ? metrics.total_requests : 'N/A'}</div>
      </div>
      <div class="stat-card">
        <span class="stat-label">Throughput</span>
        <div class="stat-value">${metrics.avg_rps !== undefined ? metrics.avg_rps + ' req/s' : 'N/A'}</div>
      </div>
      <div class="stat-card">
        <span class="stat-label">p50 Latency</span>
        <div class="stat-value">${metrics.p50_ms !== undefined ? metrics.p50_ms + ' ms' : 'N/A'}</div>
      </div>
      <div class="stat-card">
        <span class="stat-label">p95 Latency</span>
        <div class="stat-value">${metrics.p95_ms !== undefined ? metrics.p95_ms + ' ms' : 'N/A'}</div>
      </div>
      <div class="stat-card">
        <span class="stat-label">Error Rate</span>
        <div class="stat-value" style="color: ${(metrics.error_rate || 0) >= 0.05 ? '#ef4444' : '#10b981'}">
          ${metrics.error_percentage !== undefined ? metrics.error_percentage + '%' : 'N/A'}
        </div>
        <span class="stat-sub" style="color: #94a3b8;">${metrics.failed_requests !== undefined ? metrics.failed_requests + ' failed' : ''}</span>
      </div>
    `;
  }

  // Render markdown report or explicit error state
  const reportBody = document.getElementById("ai-report-body");
  if (run.ai_report && window.marked) {
    reportBody.innerHTML = marked.parse(run.ai_report);
  } else if (isPipelineFailure) {
    reportBody.innerHTML = `
      <div class="pipeline-error-box" style="background: rgba(239, 68, 68, 0.06); border-left: 4px solid #ef4444; padding: 16px; border-radius: 4px;">
        <h4 style="color: #ef4444; margin-top: 0; margin-bottom: 8px;">Pipeline Execution Failure</h4>
        <p style="color: #cbd5e1; font-size: 0.9rem; margin-bottom: 8px;">The load test pipeline was aborted before AI diagnostics could be generated. Error details:</p>
        <pre style="background: #090d16; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 0.82rem; color: #fca5a5; white-space: pre-wrap; font-family: monospace;">${escapeHtml(run.error_message || "Unknown execution error occurred.")}</pre>
      </div>
    `;
  } else {
    reportBody.innerHTML = `<div style="color: #94a3b8; font-style: italic; padding: 12px 0;">Report generation in progress...</div>`;
  }

  // Script preview
  if (run.script) {
    scriptCodeBlock.textContent = run.script;
  }

  if (shouldScroll) {
    resultsSection.scrollIntoView({ behavior: 'smooth' });
  }
}

async function fetchRunAndShowResults(runId, shouldScroll = true) {
  try {
    const res = await fetch(`/api/runs/${runId}`);
    if (!res.ok) return;
    const run = await res.json();
    if (run.prompt && promptInput) {
      promptInput.value = run.prompt;
    }
    loadRunResults(run, shouldScroll);
    refreshHistoryList();
  } catch (e) {
    console.error("Error fetching results:", e);
  }
}

// Script Drawer toggles
btnViewScript.addEventListener("click", () => {
  scriptDrawer.classList.toggle("hidden");
  const isExpanded = !scriptDrawer.classList.contains("hidden");
  btnViewScript.setAttribute("aria-expanded", String(isExpanded));
});
btnCloseScript.addEventListener("click", () => {
  scriptDrawer.classList.add("hidden");
  btnViewScript.setAttribute("aria-expanded", "false");
});

// Run History
btnHistoryToggle.addEventListener("click", () => {
  historySection.classList.toggle("hidden");
  const isExpanded = !historySection.classList.contains("hidden");
  btnHistoryToggle.setAttribute("aria-expanded", String(isExpanded));
  if (isExpanded) {
    refreshHistoryList(false);
    historySection.scrollIntoView({ behavior: 'smooth' });
  }
});
document.getElementById("btn-refresh-history").addEventListener("click", () => refreshHistoryList(false));

async function refreshHistoryList(autoLoadLatest = false) {
  try {
    const res = await fetch("/api/runs");
    if (!res.ok) return;
    const runs = await res.json();
    historyCountSpan.textContent = runs.length;

    const telemetryRuns = document.getElementById("telemetry-runs-count");
    if (telemetryRuns) {
      telemetryRuns.textContent = `${runs.length} Benchmarks Saved`;
    }

    // Populate recent benchmark quick-load pills
    const recentPillsContainer = document.getElementById("recent-runs-pills");
    if (recentPillsContainer) {
      recentPillsContainer.innerHTML = "";
      const completedRuns = runs.filter(r => r.status === "COMPLETED" && r.metrics).slice(0, 3);
      completedRuns.forEach(cr => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "recent-pill-btn";
        const icon = cr.test_type === "stress" ? "🔥" : cr.test_type === "soak" ? "⏳" : "✅";
        const verdictTag = cr.metrics.passed ? "PASS" : "FAIL (THR)";
        btn.innerHTML = `<span>${icon}</span> <strong>${cr.test_type.toUpperCase()}</strong> <span>(${cr.virtual_users} VUs)</span> <span class="badge ${cr.metrics.passed ? 'badge-baseline' : 'badge-stress'}" style="padding: 1px 6px; font-size: 10px;">${verdictTag}</span>`;
        btn.addEventListener("click", () => fetchRunAndShowResults(cr.id, true));
        recentPillsContainer.appendChild(btn);
      });
    }

    historyTableBody.innerHTML = "";
    runs.forEach(r => {
      const tr = document.createElement("tr");
      const dateStr = new Date(r.created_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const m = r.metrics || {};
      const errText = m.error_percentage !== undefined ? `${m.error_percentage}%` : '-';
      const p95Text = m.p95_ms !== undefined ? `${m.p95_ms}ms` : '-';

      let statusBadge = `<span class="badge">${r.status}</span>`;
      if (r.status === "FAILED") {
        statusBadge = `<span class="badge" style="background: rgba(239,68,68,0.2); color: #ef4444; border: 1px solid rgba(239,68,68,0.4);">ERROR</span>`;
      } else if (r.status === "COMPLETED") {
        if (m.passed === false) {
          statusBadge = `<span class="badge" style="background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.3);">FAIL (THR)</span>`;
        } else {
          statusBadge = `<span class="badge" style="background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.3);">PASS</span>`;
        }
      }

      tr.innerHTML = `
        <td>${dateStr}</td>
        <td><span class="badge badge-${r.test_type}">${r.test_type}</span></td>
        <td>${escapeHtml(r.prompt.substring(0, 35))}...</td>
        <td>${r.virtual_users}</td>
        <td>${r.duration}</td>
        <td>${statusBadge}</td>
        <td style="color: ${m.error_rate > 0.05 ? '#ef4444' : '#10b981'}">${errText}</td>
        <td>${p95Text}</td>
        <td><button class="btn btn-sm btn-outline btn-load-run" data-id="${r.id}">View</button></td>
      `;
      historyTableBody.appendChild(tr);
    });

    document.querySelectorAll(".btn-load-run").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-id");
        fetchRunAndShowResults(id, true);
      });
    });
  } catch (e) {}
}

// Initialize on page load
window.addEventListener("DOMContentLoaded", () => {
  initCharts();
  refreshHistoryList();
});
