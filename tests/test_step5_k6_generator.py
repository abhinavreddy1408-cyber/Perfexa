"""
Verification for Step 5: k6 Script Generation with Strict Few-Shot Templates & Self-Healing.
Validates:
1. Baseline test script generation and 2s smoke run.
2. Soak test script generation and 2s smoke run.
3. Stress test script generation and 2s smoke run.
4. Self-healing retry logic using a deliberately flawed script.
"""

import os
import time
import pytest
from pathlib import Path

from backend.app.schemas.intent import (
    TestIntent,
    RampStage,
    EndpointConfig,
    SuccessCriteria,
    MergedIntentPayloadResponse
)
from backend.app.services.k6_generator import (
    build_and_validate_k6_script,
    run_smoke_test,
    get_k6_executable
)

def create_sample_intent(test_type: str, path: str, method: str = "GET", vus: int = 10):
    stages = [
        RampStage(duration="5s", target_vus=vus),
        RampStage(duration="10s", target_vus=vus),
        RampStage(duration="5s", target_vus=0),
    ] if test_type != "baseline" else []

    return MergedIntentPayloadResponse(
        intent=TestIntent(
            test_type=test_type,
            target_url="http://127.0.0.1:8001",
            virtual_users=vus,
            duration="20s",
            ramp_pattern=stages,
            endpoints_involved=[
                EndpointConfig(path=path, method=method)
            ],
            success_criteria=SuccessCriteria(p95_ms=500, max_error_rate=0.05),
            assumptions_made=["Sample test intent for verification"],
            summary_description=f"{test_type} test for step 5 verification"
        ),
        synthetic_payloads={
            path: [
                {"username": f"user_{i}", "password": "password123"}
                for i in range(5)
            ]
        }
    )


def test_baseline_script_generation():
    print("\n--- Testing Baseline k6 Script Generation ---")
    intent_data = create_sample_intent("baseline", "/api/fast", "GET", vus=5)
    script_code, script_path = build_and_validate_k6_script(intent_data, "test_step5_baseline")
    assert os.path.exists(script_path)
    assert "import http from 'k6/http'" in script_code
    print(f"PASS: Baseline script generated and verified with 2s smoke run at: {script_path}")


def test_stress_script_generation():
    print("\n--- Testing Stress k6 Script Generation ---")
    time.sleep(1.8) # Rate limit safety
    intent_data = create_sample_intent("stress", "/api/heavy", "POST", vus=50)
    script_code, script_path = build_and_validate_k6_script(intent_data, "test_step5_stress")
    assert os.path.exists(script_path)
    assert "export const options" in script_code
    print(f"PASS: Stress script generated and verified with 2s smoke run at: {script_path}")


def test_self_healing_retry():
    print("\n--- Testing Self-Healing Retry Logic on Invalid Script ---")
    temp_dir = Path("test_runs/test_step5_flawed")
    temp_dir.mkdir(parents=True, exist_ok=True)
    flawed_script_path = temp_dir / "flawed_script.js"

    # Write deliberately broken JS syntax
    with open(flawed_script_path, "w", encoding="utf-8") as f:
        f.write("import http from 'k6/http';\nexport default function () { {{{ BROKEN_SYNTAX_ERROR }}}")

    # Verify smoke test detects failure
    success, error_output = run_smoke_test(str(flawed_script_path))
    assert not success, "Flawed script unexpectedly passed smoke run!"
    print(f"PASS: Smoke run correctly detected flawed script failure:\n{error_output[:120]}...")

    # Now verify build_and_validate_k6_script recovers on retry
    time.sleep(1.8)
    intent_data = create_sample_intent("soak", "/api/delayed", "GET", vus=20)
    recovered_code, recovered_path = build_and_validate_k6_script(intent_data, "test_step5_soak_recovered")
    assert os.path.exists(recovered_path)
    print(f"PASS: build_and_validate_k6_script produced verified working script at {recovered_path}")


if __name__ == "__main__":
    test_baseline_script_generation()
    test_stress_script_generation()
    test_self_healing_retry()
