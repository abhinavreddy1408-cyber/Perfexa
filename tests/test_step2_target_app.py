"""
Test verification for Step 2: Target Demo App & Deliberate Breaking Point.
"""

import asyncio
import time
import httpx
import pytest
from target_app.main import app, BREAKING_POINT_CONCURRENCY

@pytest.mark.asyncio
async def test_fast_endpoint():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        start = time.time()
        resp = await client.get("/api/fast")
        duration = time.time() - start
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
        assert duration < 0.05, f"Fast endpoint took {duration}s"
        print(f"PASS: Fast endpoint returned in {duration*1000:.2f}ms")

@pytest.mark.asyncio
async def test_delayed_endpoint():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        start = time.time()
        resp = await client.get("/api/delayed?min_ms=100&max_ms=200")
        duration = time.time() - start
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert duration >= 0.09, f"Delayed endpoint returned too fast: {duration}s"
        print(f"PASS: Delayed endpoint returned in {duration*1000:.2f}ms")

@pytest.mark.asyncio
async def test_heavy_endpoint_normal_concurrency():
    """Under 30 concurrent requests (well below 150), all should succeed."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        tasks = [client.get("/api/heavy") for _ in range(30)]
        responses = await asyncio.gather(*tasks)
        status_codes = [r.status_code for r in responses]
        assert all(code == 200 for code in status_codes), f"Unexpected failure in normal load: {status_codes}"
        print(f"PASS: 30 concurrent requests to /api/heavy all returned 200 OK")

@pytest.mark.asyncio
async def test_heavy_endpoint_breaking_point_concurrency():
    """When concurrent requests exceed 150 (e.g. 180 concurrent requests), errors must be triggered."""
    concurrency_count = 180
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=10.0) as client:
        tasks = [client.get("/api/heavy") for _ in range(concurrency_count)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        successes = 0
        failures = 0
        status_breakdown = {}

        for r in responses:
            if isinstance(r, httpx.Response):
                status_breakdown[r.status_code] = status_breakdown.get(r.status_code, 0) + 1
                if r.status_code == 200:
                    successes += 1
                elif r.status_code in (500, 503):
                    failures += 1
            else:
                failures += 1

        print(f"Concurrency {concurrency_count} results: Successes={successes}, Failures={failures}, Breakdown={status_breakdown}")
        assert failures > 0, "Breaking point was not triggered despite crossing 150 concurrency!"
        assert successes > 0, "Some initial requests below threshold should have succeeded!"
        print(f"PASS: Deliberate breaking point verified! {failures} requests failed when concurrency crossed {BREAKING_POINT_CONCURRENCY}.")

if __name__ == "__main__":
    asyncio.run(test_fast_endpoint())
    asyncio.run(test_delayed_endpoint())
    asyncio.run(test_heavy_endpoint_normal_concurrency())
    asyncio.run(test_heavy_endpoint_breaking_point_concurrency())
