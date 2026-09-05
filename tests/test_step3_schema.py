"""
Test verification for Step 3: Locked Test Intent Schema.
"""

import json
from backend.app.schemas.intent import (
    TestIntent,
    RampStage,
    EndpointConfig,
    SuccessCriteria,
    MergedIntentPayloadResponse
)

def test_baseline_intent():
    intent = TestIntent(
        test_type="baseline",
        target_url="http://localhost:8001",
        virtual_users=10,
        duration="30s",
        ramp_pattern=[
            RampStage(duration="5s", target_vus=10),
            RampStage(duration="20s", target_vus=10),
            RampStage(duration="5s", target_vus=0),
        ],
        endpoints_involved=[
            EndpointConfig(path="/api/fast", method="GET")
        ],
        success_criteria=SuccessCriteria(p95_ms=200, max_error_rate=0.01),
        assumptions_made=["Defaulted target to localhost:8001", "Set 10 VUs for baseline test"],
        summary_description="Baseline steady test with 10 VUs hitting /api/fast for 30 seconds"
    )
    assert intent.test_type == "baseline"
    assert intent.virtual_users == 10
    assert intent.success_criteria.p95_ms == 200
    print("PASS: Baseline intent validated successfully.")

def test_stress_intent_with_payloads():
    response = MergedIntentPayloadResponse(
        intent=TestIntent(
            test_type="stress",
            target_url="http://localhost:8001",
            virtual_users=200,
            duration="1m",
            ramp_pattern=[
                RampStage(duration="15s", target_vus=50),
                RampStage(duration="20s", target_vus=150),
                RampStage(duration="20s", target_vus=200),
                RampStage(duration="5s", target_vus=0),
            ],
            endpoints_involved=[
                EndpointConfig(path="/api/login", method="POST", payload_template={"username": "user", "password": "pwd"}),
                EndpointConfig(path="/api/heavy", method="POST", payload_template={"item": "heavy_task"})
            ],
            success_criteria=SuccessCriteria(p95_ms=800, max_error_rate=0.05),
            assumptions_made=["Ramped from 50 to 200 VUs to identify breaking point"],
            summary_description="Stress test ramping to 200 VUs across login and heavy endpoints"
        ),
        synthetic_payloads={
            "/api/login": [
                {"username": f"user_{i}", "password": f"pass_{i}!"} for i in range(5)
            ],
            "/api/heavy": [
                {"user_id": f"u_{i}", "item_id": f"item_{i}", "quantity": i + 1} for i in range(5)
            ]
        }
    )
    dumped = json.loads(response.model_dump_json())
    assert dumped["intent"]["test_type"] == "stress"
    assert len(dumped["synthetic_payloads"]["/api/login"]) == 5
    print("PASS: Stress intent with synthetic payloads validated and serializable.")

def test_schema_file_matches():
    with open("backend/app/schemas/intent_schema.json", "r") as f:
        schema = json.load(f)
    assert "MergedIntentPayloadResponse" in schema["title"]
    assert "intent" in schema["required"]
    print("PASS: Locked intent_schema.json verified against model.")

if __name__ == "__main__":
    test_baseline_intent()
    test_stress_intent_with_payloads()
    test_schema_file_matches()
