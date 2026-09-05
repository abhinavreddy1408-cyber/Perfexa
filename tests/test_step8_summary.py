"""
Verification for Step 8: Post-Run Diagnostic Summary LLM Call.
Tests summary generation for:
1. Healthy PASSED run.
2. Degraded FAILED stress run (breaking point crossed).
"""

import time
import pytest
from backend.app.schemas.intent import TestIntent, EndpointConfig, SuccessCriteria
from backend.app.services.llm_summary import generate_performance_summary


def test_passed_baseline_summary():
    print("\n--- Testing Summary Generation for PASSED Baseline Run ---")
    intent = TestIntent(
        test_type="baseline",
        target_url="http://localhost:8001",
        virtual_users=10,
        duration="30s",
        endpoints_involved=[EndpointConfig(path="/api/fast", method="GET")],
        success_criteria=SuccessCriteria(p95_ms=200, max_error_rate=0.01),
        summary_description="Baseline test on /api/fast"
    )
    metrics = {
        "total_requests": 300,
        "failed_requests": 0,
        "error_rate": 0.0,
        "error_percentage": 0.0,
        "p50_ms": 1.5,
        "p95_ms": 3.8,
        "p99_ms": 5.2,
        "avg_latency_ms": 1.9,
        "avg_rps": 10.0,
        "passed": True,
        "threshold_failures": []
    }

    report = generate_performance_summary(intent, metrics)
    print("Report Output:\n", report[:300], "...\n")

    assert "Verdict" in report or "PASSED" in report
    assert "Recommendation" in report or "Recommendations" in report
    print("PASS: Baseline PASSED summary generated successfully.")


def test_failed_stress_summary():
    print("\n--- Testing Summary Generation for FAILED Stress Run (Breaking Point) ---")
    time.sleep(1.8) # Rate limit safety
    intent = TestIntent(
        test_type="stress",
        target_url="http://localhost:8001",
        virtual_users=200,
        duration="2m",
        endpoints_involved=[EndpointConfig(path="/api/heavy", method="POST")],
        success_criteria=SuccessCriteria(p95_ms=500, max_error_rate=0.05),
        summary_description="Stress test on /api/heavy with 200 VUs"
    )
    metrics = {
        "total_requests": 1250,
        "failed_requests": 210,
        "error_rate": 0.168,
        "error_percentage": 16.8,
        "p50_ms": 240.0,
        "p95_ms": 2200.0,
        "p99_ms": 2800.0,
        "avg_latency_ms": 480.0,
        "avg_rps": 10.4,
        "passed": False,
        "threshold_failures": [
            "p95 latency (2200.0ms) exceeded limit (500ms)",
            "Error rate (16.8%) exceeded limit (5.0%)"
        ]
    }

    report = generate_performance_summary(intent, metrics)
    print("Report Output:\n", report[:400], "...\n")

    assert "FAILED" in report or "Failed" in report or "Verdict" in report
    assert "Root Cause" in report
    assert "Recommendation" in report
    print("PASS: Stress FAILED summary diagnosed breaking point and generated recommendations.")


if __name__ == "__main__":
    test_passed_baseline_summary()
    test_failed_stress_summary()
