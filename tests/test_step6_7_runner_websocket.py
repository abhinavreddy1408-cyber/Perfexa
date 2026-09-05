"""
Verification for Steps 6 and 7: k6 Subprocess Execution, Stream Logging & Live Metrics.
Executes a real 5-second test against target-app on :8001,
verifies that results.json is tailed in real-time,
and verifies that live metric snapshots are streamed to listeners.
"""

import asyncio
import os
import time
from pathlib import Path
import pytest

from backend.app.services.k6_runner import execute_k6_run
from backend.app.api.websocket import ws_manager

TEST_SCRIPT_CONTENT = """import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '4s',
};

export default function () {
  const res = http.get('http://127.0.0.1:8001/api/fast');
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(0.1);
}
"""


@pytest.mark.asyncio
async def test_k6_subprocess_and_live_tailing():
    run_id = "test_step6_7_verification"
    run_dir = Path(f"test_runs/{run_id}")
    run_dir.mkdir(parents=True, exist_ok=True)
    script_path = run_dir / "test_script.js"

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(TEST_SCRIPT_CONTENT)

    captured_snapshots = []

    async def on_metric_update(snapshot):
        captured_snapshots.append(snapshot)
        print(f"  [Live Metric Update] Elapsed: {snapshot['elapsed_sec']}s, VUs: {snapshot['vus']}, Req/s: {snapshot['rps']}, p95: {snapshot['p95_ms']}ms, Total: {snapshot['total_requests']}")

    print("\nLaunching real 4s k6 load test via subprocess...")
    start_time = time.time()
    
    final_summary = await execute_k6_run(
        run_id=run_id,
        script_path=str(script_path),
        success_criteria={"p95_ms": 100, "max_error_rate": 0.01},
        on_metric_update=on_metric_update
    )
    duration = time.time() - start_time

    print(f"\nk6 test completed in {duration:.2f}s!")
    print(f"Total Requests: {final_summary['total_requests']}")
    print(f"Failed Requests: {final_summary['failed_requests']} ({final_summary['error_percentage']}%)")
    print(f"p50: {final_summary['p50_ms']}ms, p95: {final_summary['p95_ms']}ms, p99: {final_summary['p99_ms']}ms")
    print(f"Passed Thresholds: {final_summary['passed']}")
    print(f"Captured Live Snapshots: {len(captured_snapshots)}")

    # Verification checks
    assert os.path.exists(run_dir / "results.json"), "results.json was not created!"
    assert final_summary["total_requests"] > 0, "No requests were executed!"
    assert len(captured_snapshots) >= 2, "Live metrics were not tailed/emitted during execution!"
    assert final_summary["k6_exit_code"] == 0, f"k6 exited with non-zero code: {final_summary['k6_exit_code']}"
    assert final_summary["failed_requests"] == 0, "Fast endpoint had unexpected failures!"

    print("\nPASS: Steps 6 and 7 verified! Subprocess execution and live metric tailing work end-to-end.")


if __name__ == "__main__":
    asyncio.run(test_k6_subprocess_and_live_tailing())
