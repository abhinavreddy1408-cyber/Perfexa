import asyncio
import time
import httpx

async def test_live_dual_mode_run():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=60.0) as client:
        # Step 1: Extract intent with no explicit target_url
        prompt = "run a quick baseline check on my fast endpoint with 10 users for 5 seconds"
        intent_resp = await client.post("/api/intent", json={"prompt": prompt})
        assert intent_resp.status_code == 200
        data = intent_resp.json()
        target_url = data["intent"]["target_url"]
        print(f"Extracted target_url: {target_url}")
        assert "target-app" not in target_url, f"target-app should have been normalized, got {target_url}"
        assert "127.0.0.1:8001" in target_url or "localhost:8001" in target_url

        # Step 2: Launch Run
        run_resp = await client.post("/api/runs", json={
            "prompt": prompt,
            "intent": data["intent"],
            "synthetic_payloads": data.get("synthetic_payloads", {})
        })
        assert run_resp.status_code == 200
        run_id = run_resp.json()["run_id"]
        print(f"Launched run_id: {run_id}")

        # Step 3: Poll for completion
        for _ in range(30):
            await asyncio.sleep(2.0)
            status_resp = await client.get(f"/api/runs/{run_id}")
            assert status_resp.status_code == 200
            run_data = status_resp.json()
            status = run_data["status"]
            print(f"Status: {status}")
            if status in ("COMPLETED", "FAILED"):
                break

        assert run_data["status"] == "COMPLETED", f"Run failed: {run_data.get('error_message')}"
        assert run_data["metrics"] is not None
        assert run_data["metrics"]["total_requests"] > 0
        print(f"SUCCESS: Run completed with {run_data['metrics']['total_requests']} requests!")

if __name__ == "__main__":
    asyncio.run(test_live_dual_mode_run())
