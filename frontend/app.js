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
const aboutSection = document.getElementById("about-section");
const btnAboutToggle = document.getElementById("btn-about-toggle");
const btnCloseAbout = document.getElementById("btn-close-about");

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
  if (vusChart && latencyChart) return;
  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    scales: {
      x: { grid: { color: 'rgba(247, 168, 160, 0.08)' }, ticks: { color: '#a595a0' } },
      y: { grid: { color: 'rgba(247, 168, 160, 0.08)' }, ticks: { color: '#a595a0' } }
    },
    plugins: {
      legend: { labels: { color: '#faeade', font: { family: 'Space Grotesk' } } }
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
        borderColor: '#f7a8a0',
        backgroundColor: 'rgba(247, 168, 160, 0.18)',
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
          borderColor: '#faeade',
          backgroundColor: 'rgba(250, 234, 222, 0.12)',
          tension: 0.3
        },
        {
          label: 'Error %',
          data: [],
          borderColor: '#ef4444',
          backgroundColor: 'rgba(239, 68, 68, 0.18)',
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
  if (window.PerfexaAnimations) PerfexaAnimations.revealIntentCard();
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
  if (window.PerfexaAnimations) PerfexaAnimations.revealLiveDashboard();
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

  // Animated stat tweens (falls back to direct assignment if animations.js not loaded)
  if (window.PerfexaAnimations) {
    PerfexaAnimations.tweenStatValue("stat-vus", snapshot.vus, { suffix: "", decimals: 0 });
    PerfexaAnimations.tweenStatValue("stat-rps", snapshot.rps, { suffix: "", decimals: 1 });
    PerfexaAnimations.tweenStatValue("stat-p95", snapshot.p95_ms, { suffix: " ms", decimals: 0 });
    PerfexaAnimations.tweenStatValue("stat-error-rate", parseFloat((snapshot.error_rate * 100).toFixed(1)), { suffix: "%", decimals: 1 });
  } else {
    document.getElementById("stat-vus").textContent = snapshot.vus;
    document.getElementById("stat-rps").textContent = snapshot.rps;
    document.getElementById("stat-p95").textContent = `${snapshot.p95_ms} ms`;
    document.getElementById("stat-error-rate").textContent = `${(snapshot.error_rate * 100).toFixed(1)}%`;
  }
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
      if (window.PerfexaAnimations) PerfexaAnimations.pulseChartContainer();

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
  if (window.PerfexaAnimations) PerfexaAnimations.revealResultsSection();

  const metrics = run.metrics || {};
  const isPipelineFailure = run.status === "FAILED";
  const passed = metrics.passed;
  const noData = metrics.no_data === true || (!isPipelineFailure && metrics.total_requests === 0);
  const maxErrLimit = (run.intent && run.intent.success_criteria && run.intent.success_criteria.max_error_rate !== undefined)
    ? run.intent.success_criteria.max_error_rate
    : 0.05;
  const isErrorRateBreached = (metrics.threshold_failures || []).some(tf => tf.toLowerCase().includes("error rate")) || ((metrics.error_rate || 0) > maxErrLimit);
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
  if (window.PerfexaAnimations) PerfexaAnimations.animateVerdictBanner(verdictBanner);

  // Scorecards
  const scorecardGrid = document.getElementById("scorecard-grid");
  if ((isPipelineFailure || noData) && (!metrics.total_requests || metrics.total_requests === 0)) {
    scorecardGrid.innerHTML = `
      <div class="stat-card" style="grid-column: 1 / -1; text-align: left; background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); padding: 16px;">
        <div style="font-weight: 600; color: #f87171; margin-bottom: 4px;">No Load-Test Metrics Collected</div>
        <div style="font-size: 0.85rem; color: #94a3b8;">${isPipelineFailure ? 'The test run encountered a pipeline error before load metrics could be recorded.' : 'k6 completed but recorded zero requests — the target may have been unreachable or the script may have failed.'} See error details below.</div>
      </div>
    `;
  } else {
    let failureReasonsHtml = "";
    if (metrics.threshold_failures && metrics.threshold_failures.length > 0) {
      failureReasonsHtml = `
        <div class="threshold-failures-box" style="grid-column: 1 / -1; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 8px; padding: 12px 16px; margin-bottom: 8px;">
          <div style="color: #ef4444; font-weight: 600; margin-bottom: 6px;">Threshold Breaches Detected:</div>
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
        <div class="stat-value" style="color: ${isErrorRateBreached ? '#ef4444' : '#10b981'}">
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

// About Section Toggle
if (btnAboutToggle && aboutSection) {
  btnAboutToggle.addEventListener("click", () => {
    aboutSection.classList.toggle("hidden");
    const isExpanded = !aboutSection.classList.contains("hidden");
    btnAboutToggle.setAttribute("aria-expanded", String(isExpanded));
    if (isExpanded) {
      const navOffset = 90;
      const elementPos = aboutSection.getBoundingClientRect().top + window.pageYOffset;
      window.scrollTo({ top: Math.max(0, elementPos - navOffset), behavior: 'smooth' });
    }
  });
}
if (btnCloseAbout && aboutSection) {
  btnCloseAbout.addEventListener("click", () => {
    aboutSection.classList.add("hidden");
    if (btnAboutToggle) btnAboutToggle.setAttribute("aria-expanded", "false");
  });
}

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
  void autoLoadLatest;
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
        const verdictTag = cr.metrics.passed ? "PASS" : "FAIL (THR)";
        btn.innerHTML = `<strong>${cr.test_type.toUpperCase()}</strong> <span>(${cr.virtual_users} VUs)</span> <span class="badge ${cr.metrics.passed ? 'badge-baseline' : 'badge-stress'}" style="padding: 1px 6px; font-size: 10px;">${verdictTag}</span>`;
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

      const rMaxErrLimit = (r.intent && r.intent.success_criteria && r.intent.success_criteria.max_error_rate !== undefined)
        ? r.intent.success_criteria.max_error_rate
        : 0.05;
      const rErrBreached = (m.threshold_failures || []).some(tf => tf.toLowerCase().includes("error rate")) || ((m.error_rate || 0) > rMaxErrLimit);

      tr.innerHTML = `
        <td>${dateStr}</td>
        <td><span class="badge badge-${r.test_type}">${r.test_type}</span></td>
        <td>${escapeHtml(r.prompt.substring(0, 35))}...</td>
        <td>${r.virtual_users}</td>
        <td>${r.duration}</td>
        <td>${statusBadge}</td>
        <td style="color: ${rErrBreached ? '#ef4444' : '#10b981'}">${errText}</td>
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
    if (window.PerfexaAnimations) PerfexaAnimations.animateHistoryRows();
  } catch (e) {
    console.warn("Could not refresh run history", e);
  }
}

/* ==========================================================================
   Codebase Corrector Logic (Single-file static analysis + AI quality review)
   ========================================================================== */
const btnModeLoadTest = document.getElementById("btn-mode-loadtest");
const btnModeCorrector = document.getElementById("btn-mode-corrector");
const chipToCorrector = document.getElementById("chip-to-corrector");
const correctorSection = document.getElementById("corrector-section");
const loadtestInputSection = document.getElementById("loadtest-input-section");

const codeFileInput = document.getElementById("code-file-input");
const uploadDropzone = document.getElementById("upload-dropzone");
const selectedFileInfo = document.getElementById("selected-file-info");
const selectedFileName = document.getElementById("selected-file-name");
const selectedFileSize = document.getElementById("selected-file-size");
const btnRemoveFile = document.getElementById("btn-remove-file");
const btnAnalyzeCode = document.getElementById("btn-analyze-code");
const correctorSpinner = document.getElementById("corrector-spinner");
const correctorResults = document.getElementById("corrector-results");

const correctorStatLang = document.getElementById("corrector-stat-lang");
const correctorStatLines = document.getElementById("corrector-stat-lines");
const correctorStatTotal = document.getElementById("corrector-stat-total");
const correctorStatErrors = document.getElementById("corrector-stat-errors");
const correctorStatWarnings = document.getElementById("corrector-stat-warnings");
const correctorStatVerdict = document.getElementById("corrector-stat-verdict");
const correctorStatStatus = document.getElementById("corrector-stat-status");
const correctorAiSummary = document.getElementById("corrector-ai-summary");
const findingsCountBadge = document.getElementById("findings-count-badge");
const findingsEnginePill = document.getElementById("findings-engine-pill");
const findingsList = document.getElementById("findings-list");

let selectedCodeFile = null;

function switchToLoadTesting() {
  if (correctorSection) correctorSection.classList.add("hidden");
  if (loadtestInputSection) loadtestInputSection.classList.remove("hidden");
  if (btnModeLoadTest) {
    btnModeLoadTest.classList.add("btn-primary");
    btnModeLoadTest.classList.remove("btn-outline");
  }
  if (btnModeCorrector) {
    btnModeCorrector.classList.add("btn-outline");
    btnModeCorrector.classList.remove("btn-primary");
  }
}

function switchToCorrector() {
  if (loadtestInputSection) loadtestInputSection.classList.add("hidden");
  if (intentSection) intentSection.classList.add("hidden");
  if (liveDashboardSection) liveDashboardSection.classList.add("hidden");
  if (resultsSection) resultsSection.classList.add("hidden");
  if (correctorSection) {
    correctorSection.classList.remove("hidden");
    correctorSection.style.opacity = "1";
    correctorSection.style.transform = "none";
    if (window.gsap) {
      window.gsap.fromTo(
        correctorSection,
        { opacity: 0, y: 12 },
        { opacity: 1, y: 0, duration: 0.35, ease: "power2.out", clearProps: "transform,opacity" }
      );
    }
  }
  if (btnModeCorrector) {
    btnModeCorrector.classList.add("btn-primary");
    btnModeCorrector.classList.remove("btn-outline");
  }
  if (btnModeLoadTest) {
    btnModeLoadTest.classList.add("btn-outline");
    btnModeLoadTest.classList.remove("btn-primary");
  }
}

function clearSelectedCodeFile() {
  selectedCodeFile = null;
  if (codeFileInput) codeFileInput.value = "";
  if (selectedFileInfo) selectedFileInfo.classList.add("hidden");
  if (btnAnalyzeCode) btnAnalyzeCode.disabled = true;
}

function handleFileSelection(file) {
  if (!file) return;

  const name = file.name || "";
  const ext = name.includes(".") ? name.substring(name.lastIndexOf(".")).toLowerCase() : "";

  if (ext !== ".py" && ext !== ".js") {
    showError("Language not yet supported — currently supports Python and JavaScript");
    clearSelectedCodeFile();
    return;
  }

  if (file.size === 0) {
    showError("Uploaded file is empty.");
    clearSelectedCodeFile();
    return;
  }

  hideError();
  selectedCodeFile = file;

  if (selectedFileName) selectedFileName.textContent = file.name;
  if (selectedFileSize) {
    const sizeKb = (file.size / 1024).toFixed(1);
    selectedFileSize.textContent = `(${sizeKb} KB)`;
  }
  if (selectedFileInfo) selectedFileInfo.classList.remove("hidden");
  if (btnAnalyzeCode) btnAnalyzeCode.disabled = false;
}

// Dropzone & Input Listeners
if (codeFileInput) {
  codeFileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelection(e.target.files[0]);
    }
  });
}

if (uploadDropzone) {
  uploadDropzone.addEventListener("click", (e) => {
    if (e.target === codeFileInput) return;
    if (e.target && e.target.closest && e.target.closest("#btn-remove-file")) return;
    if (codeFileInput) codeFileInput.click();
  });

  ["dragenter", "dragover"].forEach(evtName => {
    uploadDropzone.addEventListener(evtName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      uploadDropzone.classList.add("dragover");
    });
  });

  ["dragleave", "dragend", "drop"].forEach(evtName => {
    uploadDropzone.addEventListener(evtName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      uploadDropzone.classList.remove("dragover");
    });
  });

  uploadDropzone.addEventListener("drop", (e) => {
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelection(e.dataTransfer.files[0]);
    }
  });

  uploadDropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (codeFileInput) codeFileInput.click();
    }
  });
}

if (btnRemoveFile) {
  btnRemoveFile.addEventListener("click", (e) => {
    e.stopPropagation();
    clearSelectedCodeFile();
  });
}

if (btnModeLoadTest) {
  btnModeLoadTest.addEventListener("click", switchToLoadTesting);
}

if (btnModeCorrector) {
  btnModeCorrector.addEventListener("click", switchToCorrector);
}

if (chipToCorrector) {
  chipToCorrector.addEventListener("click", switchToCorrector);
}

// Run Code Review
if (btnAnalyzeCode) {
  btnAnalyzeCode.addEventListener("click", async () => {
    if (!selectedCodeFile) return;

    hideError();
    btnAnalyzeCode.disabled = true;
    if (correctorSpinner) correctorSpinner.classList.remove("hidden");

    try {
      const formData = new FormData();
      formData.append("file", selectedCodeFile);
      formData.append("run_ai_summary", "true");

      const response = await fetch("/api/code-review", {
        method: "POST",
        body: formData
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        showError(data.detail || "Code analysis failed. Please try again.");
        btnAnalyzeCode.disabled = false;
        if (correctorSpinner) correctorSpinner.classList.add("hidden");
        return;
      }

      // Populate Scorecards
      const lang = (data.language || "code").toUpperCase();
      if (correctorStatLang) correctorStatLang.textContent = lang;
      if (correctorStatLines) correctorStatLines.textContent = `${data.total_lines || 0} lines`;
      if (correctorStatTotal) correctorStatTotal.textContent = data.total_findings || 0;
      if (correctorStatErrors) correctorStatErrors.textContent = data.error_count || 0;
      if (correctorStatWarnings) correctorStatWarnings.textContent = data.warning_count || 0;

      if (correctorStatVerdict) {
        if (data.total_findings === 0) {
          correctorStatVerdict.innerHTML = '<span style="color: var(--success);">CLEAN</span>';
          if (correctorStatStatus) correctorStatStatus.textContent = "0 defects";
        } else if (data.error_count > 0) {
          correctorStatVerdict.innerHTML = '<span style="color: var(--danger);">NEEDS FIXES</span>';
          if (correctorStatStatus) correctorStatStatus.textContent = `${data.error_count} critical`;
        } else {
          correctorStatVerdict.innerHTML = '<span style="color: #f59e0b;">WARNINGS</span>';
          if (correctorStatStatus) correctorStatStatus.textContent = `${data.warning_count} stylistic`;
        }
      }

      // Render AI Summary
      if (correctorAiSummary) {
        if (data.ai_summary && window.marked) {
          correctorAiSummary.innerHTML = marked.parse(data.ai_summary);
        } else {
          correctorAiSummary.textContent = data.ai_summary || "No summary available.";
        }
      }

      // Render Findings List
      if (findingsCountBadge) findingsCountBadge.textContent = data.total_findings || 0;
      if (findingsEnginePill) {
        findingsEnginePill.textContent = data.language === "python" ? "Engine: Flake8" : "Engine: ESLint";
      }

      if (findingsList) {
        findingsList.innerHTML = "";
        if (data.total_findings === 0) {
          findingsList.innerHTML = `
            <div class="finding-clean-card">
              <h4 style="font-size: 15px; margin-bottom: 4px;">All Clean</h4>
              <p style="font-size: 13px; opacity: 0.9;">No syntax errors, undeclared variables, or style violations detected. This file satisfies standard quality benchmarks.</p>
            </div>
          `;
        } else {
          (data.findings || []).forEach(f => {
            const isErr = f.severity === "error";
            const item = document.createElement("div");
            item.className = "finding-item";
            const location = f.location || `${data.filename || selectedCodeFile.name}:${f.line}:${f.column}`;
            const contextSnippet = f.context_snippet || f.line_content || "";
            item.innerHTML = `
              <div class="finding-meta">
                <span class="finding-line-pill">${escapeHtml(location)}</span>
                <span class="finding-badge ${isErr ? 'finding-badge-error' : 'finding-badge-warning'}">${f.severity.toUpperCase()}</span>
                <span class="finding-rule">${escapeHtml(f.rule)}</span>
              </div>
              <div class="finding-message">${escapeHtml(f.message)}</div>
              ${contextSnippet ? `<pre class="finding-snippet">${escapeHtml(contextSnippet)}</pre>` : ''}
            `;
            findingsList.appendChild(item);
          });
        }
      }

      // Reveal Results
      if (correctorResults) {
        correctorResults.classList.remove("hidden");
        correctorResults.style.opacity = "1";
        correctorResults.style.transform = "none";
        if (window.gsap) {
          window.gsap.fromTo(
            correctorResults,
            { opacity: 0, y: 16 },
            { opacity: 1, y: 0, duration: 0.4, ease: "power2.out", clearProps: "transform,opacity" }
          );
        }
        correctorResults.scrollIntoView({ behavior: "smooth", block: "start" });
      }

    } catch (err) {
      showError("Unexpected error during code review: " + err.message);
    } finally {
      btnAnalyzeCode.disabled = false;
      if (correctorSpinner) correctorSpinner.classList.add("hidden");
    }
  });
}

// Initialize on page load
window.addEventListener("DOMContentLoaded", () => {
  initCharts();
  refreshHistoryList();
  if (window.location.hash === "#corrector") {
    switchToCorrector();
  }
});
