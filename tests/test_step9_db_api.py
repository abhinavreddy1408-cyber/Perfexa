"""
Verification for Step 9: SQLite Models and Persistence for Run History.
Tests database table creation, run insertion, querying, and updating.
"""

import asyncio
import json
import time
import pytest
import httpx
from sqlalchemy import select

from backend.app.database import init_db, async_session
from backend.app.models import TestRun
from backend.app.main import app

@pytest.mark.asyncio
async def test_database_init_and_crud():
    print("\n--- Testing SQLite Database Initialization and CRUD ---")
    await init_db()

    run_id = f"test_run_{int(time.time())}"
    sample_intent = {
        "test_type": "baseline",
        "target_url": "http://127.0.0.1:8001",
        "virtual_users": 10,
        "duration": "20s"
    }

    # 1. Insert
    async with async_session() as session:
        new_run = TestRun(
            id=run_id,
            prompt="Test baseline health check",
            test_type="baseline",
            status="PENDING",
            target_url="http://127.0.0.1:8001",
            virtual_users=10,
            duration="20s",
            intent_json=json.dumps(sample_intent),
            created_at=time.time()
        )
        session.add(new_run)
        await session.commit()
    print(f"PASS: Successfully inserted TestRun record with ID: {run_id}")

    # 2. Query via API client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/runs")
        assert res.status_code == 200
        runs = res.json()
        assert any(r["id"] == run_id for r in runs), f"Run {run_id} not found in /api/runs output!"
        print(f"PASS: GET /api/runs returned {len(runs)} runs, containing inserted run.")

        detail_res = await client.get(f"/api/runs/{run_id}")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["prompt"] == "Test baseline health check"
        assert detail["status"] == "PENDING"
        assert detail["intent"]["virtual_users"] == 10
        print(f"PASS: GET /api/runs/{run_id} returned accurate run details.")

    # 3. Update status and metrics
    async with async_session() as session:
        result = await session.execute(select(TestRun).where(TestRun.id == run_id))
        run = result.scalars().first()
        run.status = "COMPLETED"
        run.metrics_summary_json = json.dumps({"p95_ms": 4.5, "passed": True})
        run.ai_report = "### Verdict\nPASSED"
        run.completed_at = time.time()
        await session.commit()
    print("PASS: Successfully updated TestRun status, metrics, and report in SQLite.")

    # 4. Verify updated record
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        updated_res = await client.get(f"/api/runs/{run_id}")
        assert updated_res.status_code == 200
        updated = updated_res.json()
        assert updated["status"] == "COMPLETED"
        assert updated["metrics"]["p95_ms"] == 4.5
        assert "PASSED" in updated["ai_report"]
        print("PASS: Verified updated state through REST endpoint.")

if __name__ == "__main__":
    asyncio.run(test_database_init_and_crud())
