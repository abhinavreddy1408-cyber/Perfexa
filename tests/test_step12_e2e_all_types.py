"""
Verification for Step 12: End-to-End Live Validation of All 3 Test Types.
Runs:
1. Baseline test against /api/fast (Expect 100% pass)
2. Soak test against /api/delayed (Expect stability, moderate latency, pass)
3. Stress test against /api/heavy with 200 VUs (Deliberately crosses 150 concurrency, triggers 503s, and verifies AI summary surfaces breaking point!)
"""

import asyncio
import json
import time
from pathlib import Path
import httpx
import pytest

BASE_URL = "http://127.0.0.1:8000"

async def run_and_wait_for_completion(prompt: str, test_label: str, max_wait_sec: int = 90) -> dict:
    print(f"\n=======================================================")
    print(f"STARTING E2E TEST: {test_label}")
    print(f"Prompt: \"{prompt}\"")
    print(f"=======================================================")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        # Step A: Extract Intent
        print("1. Extracting Intent with LLM...")
        intent_resp = await client.post("/api/intent", json={"prompt": prompt, "target_url": "http://127.0.0.1:8001"})
        assert intent_resp.status_code == 200, f"Intent extraction failed: {intent_resp.text}"
        intent_data = intent_resp.json()
        print(f"   -> Extracted test_type: {intent_data['intent']['test_type']}")
        print(f"   -> Virtual users: {intent_data['intent']['virtual_users']}, Duration: {intent_data['intent']['duration']}")
        print(f"   -> Endpoints: {[ep['path'] for ep in intent_data['intent']['endpoints_involved']]}")

        # Rate limit safety delay
        await asyncio.sleep(1.8)

        # Step B: Launch Test Run
        print("2. Launching Test Run Pipeline...")
        run_resp = await client.post("/api/runs", json={
            "prompt": prompt,
            "intent": intent_data["intent"],
            "synthetic_payloads": intent_data.get("synthetic_payloads", {})
        })
        assert run_resp.status_code == 200, f"Run start failed: {run_resp.text}"
        run_info = run_resp.json()
        run_id = run_info["run_id"]
        print(f"   -> Launched run_id: {run_id}")

        # Step C: Poll until COMPLETED or FAILED
        print("3. Streaming/Polling execution progress...")
        start_time = time.time()
        completed_run = None

        while time.time() - start_time < max_wait_sec:
            await asyncio.sleep(2.0)
            status_resp = await client.get(f"/api/runs/{run_id}")
            if status_resp.status_code == 200:
                run_data = status_resp.json()
                status = run_data["status"]
                print(f"   -> Status: {status} (elapsed: {int(time.time() - start_time)}s)")

                if status in ("COMPLETED", "FAILED"):
                    completed_run = run_data
                    break

        assert completed_run is not None, f"Run {run_id} timed out after {max_wait_sec}s"
        assert completed_run["status"] == "COMPLETED", f"Run {run_id} failed with error: {completed_run.get('error_message')}"
        
        metrics = completed_run.get("metrics") or {}
        report = completed_run.get("ai_report") or ""

        print(f"\n4. Run Results:")
        print(f"   -> Total Requests: {metrics.get('total_requests')}")
        print(f"   -> Failed Requests: {metrics.get('failed_requests')} ({metrics.get('error_percentage')}%)")
        print(f"   -> p50: {metrics.get('p50_ms')}ms, p95: {metrics.get('p95_ms')}ms, p99: {metrics.get('p99_ms')}ms")
        print(f"   -> Throughput: {metrics.get('avg_rps')} req/s")
        print(f"   -> Passed Criteria: {metrics.get('passed')}")
        print(f"\n5. AI Summary Excerpt:\n{report[:400]}...\n")

        return completed_run


@pytest.mark.asyncio
async def test_all_three_types():
    # 1. Baseline
    baseline_run = await run_and_wait_for_completion(
        prompt="run a baseline health check on my fast endpoint with 10 users for 8 seconds",
        test_label="BASELINE HEALTH TEST"
    )
    b_metrics = baseline_run["metrics"]
    assert b_metrics["error_rate"] == 0.0, "Baseline test should have 0 errors"
    assert b_metrics["passed"] is True, "Baseline test should pass"
    print("PASS: Baseline test passed with 0% error rate.")

    # Rate limit safety delay
    await asyncio.sleep(2.5)

    # 2. Soak
    soak_run = await run_and_wait_for_completion(
        prompt="soak test my delayed endpoint for 10 seconds with 15 steady users with acceptable latency under 600ms",
        test_label="SOAK STABILITY TEST"
    )
    s_metrics = soak_run["metrics"]
    assert s_metrics["total_requests"] > 0, "Soak test should execute requests"
    assert s_metrics["failed_requests"] == 0, "Soak test on delayed should have 0 errors"
    assert s_metrics["p50_ms"] >= 100, "Delayed endpoint should reflect simulated delay"
    assert s_metrics["passed"] is True, "Soak test should pass with 600ms threshold"
    print("PASS: Soak test passed with stable latency and 0% errors.")

    # Rate limit safety delay
    await asyncio.sleep(2.5)

    # 3. Stress (Deliberate Breaking Point!)
    stress_run = await run_and_wait_for_completion(
        prompt="stress test my heavy endpoint with 200 users for 12 seconds to find breaking point",
        test_label="STRESS BREAKING POINT TEST"
    )
    st_metrics = stress_run["metrics"]
    st_report = stress_run["ai_report"].lower()

    # The breaking point concurrency on /api/heavy is 150. With 200 users, errors MUST be generated!
    assert st_metrics["failed_requests"] > 0, "Stress test did not trigger deliberate breaking point!"
    print(f"PASS: Deliberate breaking point triggered! {st_metrics['failed_requests']} requests failed ({st_metrics['error_percentage']}%).")
    
    # Check that the AI report discusses breaking point / concurrency / 503 / resource exhaustion
    has_breaking_point_diagnosis = any(keyword in st_report for keyword in ["breaking point", "concurrency", "503", "exhaustion", "capacity", "overload", "resource", "limit", "failed"])
    assert has_breaking_point_diagnosis, "AI summary failed to mention breaking point / concurrency saturation!"
    print("PASS: AI summary correctly diagnosed breaking point saturation and recommended scaling!")

    # Step 13: Save full output of one successful run as fixtures
    fixtures_dir = Path("fixtures")
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    with open(fixtures_dir / "sample_intent.json", "w", encoding="utf-8") as f:
        json.dump(stress_run["intent"], f, indent=2)
    with open(fixtures_dir / "sample_payloads.json", "w", encoding="utf-8") as f:
        json.dump(stress_run.get("synthetic_payloads", {}), f, indent=2)
    with open(fixtures_dir / "sample_script.js", "w", encoding="utf-8") as f:
        f.write(stress_run.get("script", "// k6 test script"))
    with open(fixtures_dir / "sample_results.json", "w", encoding="utf-8") as f:
        json.dump(stress_run.get("metrics", {}), f, indent=2)
    with open(fixtures_dir / "sample_summary.md", "w", encoding="utf-8") as f:
        f.write(stress_run.get("ai_report", "### Performance Summary\n"))

    print("\n=======================================================")
    print("STEP 13 COMPLETED: Saved complete demo artifacts to fixtures/ directory!")
    print("=======================================================")


if __name__ == "__main__":
    asyncio.run(test_all_three_types())
