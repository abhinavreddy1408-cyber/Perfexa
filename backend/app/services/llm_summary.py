"""
Step 8: Post-Run Diagnostic Summary LLM Call.
Takes final aggregated load-test statistics (p50/p95/p99, error rate, throughput, pass/fail vs criteria)
and prompts the fast model (meta/llama-3.2-11b-vision-instruct) to generate a plain-English
diagnostic report: verdict, what happened, likely root cause if failed, and recommendations.
"""

import json
import logging
from typing import Dict, Any, Optional

from backend.app.config import MODEL_FAST
from backend.app.schemas.intent import TestIntent
from backend.app.services.nim_client import default_nim_client

logger = logging.getLogger("llm_summary")

SUMMARY_SYSTEM_PROMPT = """You are a senior site reliability and performance engineering AI.
Your job is to analyze the final aggregated results of a performance load test against the original test intent and verified target application behavior, and produce an authoritative, strictly fact-grounded diagnostic report in Markdown format.

THE REPORT MUST CONTAIN EXACTLY THESE 4 LABELED SECTIONS:

### Verdict
- Clearly declare whether the test PASSED or FAILED based strictly on whether thresholds were met.
- State the explicit threshold limits (e.g. p95 <= X ms, max error rate <= Y%) and compare them directly against the actual achieved numbers.
- STRICT COHERENCE & LOGICAL CONSISTENCY RULE:
  * The Verdict and numbers MUST logically agree. NEVER produce self-contradictory text like "within the limit, but... exceeded the threshold" or "error rate was 0.0%, which exceeded the 0.0% limit".
  * If Pass/Fail Status is PASSED (0 threshold breaches), state unequivocally that the test PASSED because all observed metrics satisfied their respective limits.
  * If actual error rate is 0.0% and failed requests is 0, this is a 100% successful error-free run that fully satisfies the error rate requirement.
  * Only declare FAILED if there are actual threshold breaches listed in "Threshold Failures" or if an observed metric strictly exceeded its target.

### What Happened (Observed Performance)
- Quantify throughput (req/sec), total requests executed, failed requests, and the full latency spectrum: median (p50), 95th percentile (p95), and tail latency (p99).
- Describe the observed system behavior over the test window under the specific virtual user concurrency.

### Root Cause Analysis
- If the test PASSED:
  * State that no root cause analysis is required because the system operated within healthy limits and met all predefined thresholds.
  * Summarize the positive stability factors (e.g. healthy sub-10ms response times, zero failed requests, stable throughput).
- If the test FAILED:
  * Only describe mechanisms you have direct evidence for from the provided metrics and context.
  * STRICTLY FORBIDDEN: Do NOT invent infrastructure details (thread pools, connection pools, sockets, databases, worker thread starvation) that are not confirmed to exist in the system under test.
  * STRICTLY FORBIDDEN: Do NOT claim an endpoint has a concurrency limit, rate limit, or 503 error mechanism unless that exact endpoint is explicitly stated as having one in the verified architecture notes below.
  * NEVER transpose limits between endpoints (for example, never claim /api/login, /api/fast, or /api/delayed has the 50 in-flight concurrency limit from /api/heavy).
  * If error rate is 0.0% but latency is high under heavy concurrency on an endpoint without a concurrency cap, the root cause is request queueing saturation on the single-process asyncio event loop handling too many concurrent connections, NOT an intentional concurrency cap or 503 mechanism.
  * Do not restate symptoms in different words (e.g., stating "the system couldn't handle the load, so it failed" is not a root cause).
  * State exact numbers: Compare actual p95, p99, throughput, and error rate against criteria.
  * Explicitly reference the specific endpoint(s) under test by name.

### Recommendations
- Provide 3 to 4 prioritized, concrete engineering recommendations.
- If the test PASSED:
  * Provide proactive recommendations for continuous benchmarking, capacity planning, and scaling targets (e.g. baseline established, proceed to soak testing or higher-concurrency stress testing to find actual capacity boundaries).
  * Do NOT recommend emergency fixes, horizontal scaling, or rate limiting for an endpoint that performed flawlessly with 0% errors and healthy latencies!
- If the test FAILED:
  1. Tie each recommendation directly to the specific failure pattern observed in this run's numbers and the verified endpoint architecture.
  2. Reference the exact endpoint(s) and threshold values by name and exact value.
  3. STRICTLY FORBIDDEN: Do NOT recommend tuning a concurrency limit on an endpoint that has no concurrency limit (such as /api/login).
  4. STRICTLY FORBIDDEN: Do NOT give generic infrastructure advice (e.g., "add more CPU/RAM" or "install APM tools"). For event-loop queueing saturation with 0% errors, recommend horizontal scaling (running multiple worker processes behind a load balancer), client-side rate limiting/backoff, or endpoint optimization.

Keep the tone expert, rigorous, concise, and technically precise.
"""


def _get_endpoint_context(endpoints: list) -> str:
    """Generate architecture notes strictly scoped to the endpoints tested."""
    notes = []
    known_matched = set()

    for ep in endpoints:
        ep_str = str(ep).lower()
        if any(k in ep_str for k in ["heavy", "order", "checkout"]):
            if "heavy" not in known_matched:
                known_matched.add("heavy")
                notes.append(
                    "- /api/heavy (also /api/checkout, /api/orders): Enforces a hardcoded in-memory concurrency limit "
                    "of exactly 50 in-flight requests. Under normal concurrency (<= 50 concurrent requests), latency is ~80-140ms. "
                    "When active in-flight requests exceed 50, excess requests experience an intentional backlog delay (~2.5s) "
                    "and return HTTP 503 Service Unavailable by design. There are no external databases, thread pools, or socket subsystems."
                )
        elif "delayed" in ep_str:
            if "delayed" not in known_matched:
                known_matched.add("delayed")
                notes.append(
                    "- /api/delayed: Simulates artificial random latency between 150ms and 400ms. "
                    "Has NO concurrency limit, NO 50-request limit, and never returns 503 errors."
                )
        elif any(k in ep_str for k in ["fast", "health"]):
            if "fast" not in known_matched:
                known_matched.add("fast")
                notes.append(
                    "- /api/fast (and /api/health): Healthy baseline endpoint with near-zero latency (< 5ms). "
                    "Has NO concurrency limit, NO 50-request limit, and never returns 503 errors."
                )
        elif any(k in ep_str for k in ["login", "auth", "user"]):
            if "login" not in known_matched:
                known_matched.add("login")
                notes.append(
                    "- /api/login: Auth endpoint with light simulated delay (30-60ms). "
                    "Has NO hardcoded concurrency limit, NO 50-request limit, and never returns 503 errors. "
                    "Under heavy virtual user concurrency (e.g. 100-1000 VUs), latency increases purely due to "
                    "request queueing saturation on the single-process asyncio event loop. "
                    "Error rate remains 0% because the server does not reject requests."
                )
        else:
            notes.append(
                f"- {ep}: Custom or generic endpoint. No hardcoded concurrency limits or simulated 503 failures exist. "
                "Do NOT invent or assume any internal limits, thread pools, or database bottlenecks. "
                "Base all conclusions strictly on the observed latency, error rate, and throughput numbers."
            )

    if not notes:
        return "No specific architectural constraints known. Base all conclusions strictly on the observed metrics without assuming internal limits."

    return "\n".join(notes)


def generate_performance_summary(
    intent: TestIntent,
    final_metrics: Dict[str, Any]
) -> str:
    """
    Calls fast LLM to generate the post-run diagnostic summary.
    """
    crit = intent.success_criteria
    endpoints = [ep.path for ep in intent.endpoints_involved]

    # Ensure consistency between numbers and verdict before passing to LLM
    total_reqs = final_metrics.get("total_requests", 0)
    failed_reqs = final_metrics.get("failed_requests", 0)
    p95_ms = final_metrics.get("p95_ms", 0.0)
    err_rate = final_metrics.get("error_rate", 0.0)

    # Sanity safeguard: if total requests > 0, 0 failed requests, and p95 <= limit, this MUST be PASSED
    if total_reqs > 0 and failed_reqs == 0 and p95_ms <= crit.p95_ms:
        final_metrics["passed"] = True
        # Filter out any false "0.0% exceeded limit" artifacts
        final_metrics["threshold_failures"] = [
            tf for tf in final_metrics.get("threshold_failures", [])
            if not ("0.0%" in tf and "exceeded" in tf)
        ]

    # Contextual knowledge strictly scoped to the endpoints under test
    target_behavior_notes = _get_endpoint_context(endpoints)

    user_content = f"""Please analyze these completed performance test results:

TEST INTENT:
- Test Type: {intent.test_type.upper()}
- Target URL: {intent.target_url}
- Endpoints Tested: {endpoints}
- Virtual Users (Load): {intent.virtual_users}
- Duration: {intent.duration}
- Success Criteria:
  * Maximum acceptable p95 latency: {crit.p95_ms} ms
  * Maximum acceptable error rate: {crit.max_error_rate * 100:.1f}%

ACTUAL OBSERVED RESULTS:
- Pass/Fail Status: {"PASSED" if final_metrics.get("passed") else "FAILED"}
- Total Requests Executed: {final_metrics.get("total_requests", 0)}
- Failed Requests: {final_metrics.get("failed_requests", 0)} ({final_metrics.get("error_percentage", 0)}% error rate)
- Average Throughput: {final_metrics.get("avg_rps", 0)} req/sec
- Latency p50: {final_metrics.get("p50_ms", 0)} ms
- Latency p95: {final_metrics.get("p95_ms", 0)} ms
- Latency p99: {final_metrics.get("p99_ms", 0)} ms
- Average Latency: {final_metrics.get("avg_latency_ms", 0)} ms
- Threshold Failures: {final_metrics.get("threshold_failures", [])}

KNOWN TARGET APPLICATION BEHAVIOR & CONTEXT FOR TESTED ENDPOINTS:
{target_behavior_notes}

Provide the complete 4-section Markdown report. Adhere strictly to the grounding rules: only describe mechanisms confirmed in the context for these specific endpoints, and do NOT invent unverified infrastructure details.
"""

    messages = [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]

    logger.info(f"Generating post-run performance summary with model {MODEL_FAST}...")
    report = default_nim_client.call_with_retry(
        model=MODEL_FAST,
        messages=messages,
        max_tokens=1500,
        temperature=0.0
    )
    return report
