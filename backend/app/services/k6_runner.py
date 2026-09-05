"""
Step 6: k6 Subprocess Execution & Stream Logging.
Executes k6 load test scripts via subprocess with `--out json=results.json`,
asynchronously tails the output file as it is written, parses live metrics,
and feeds real-time updates to listeners.
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional, Dict, Any, Awaitable

from backend.app.config import TEST_RUNS_DIR, TOOLS_BIN_DIR
from backend.app.services.docker_utils import is_docker_running
from backend.app.services.metric_parser import LiveMetricAggregator

logger = logging.getLogger("k6_runner")


def get_k6_command(script_path: Path, results_path: Path) -> list:
    """
    Builds the execution command for k6.
    Matches the execution environment required by the script:
    - If the script targets 'target-app' and Docker is active, uses grafana/k6 container.
    - Otherwise uses local standalone k6.exe.
    """
    script_content = ""
    try:
        script_content = script_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        pass

    use_docker = ("target-app" in script_content) and is_docker_running()
    
    if use_docker:
        # Dockerized invocation
        run_dir = script_path.parent.resolve()
        return [
            "docker", "run", "--rm",
            "--network", "perf-net",
            "-v", f"{run_dir}:/scripts",
            "grafana/k6",
            "run",
            "--out", f"json=/scripts/{results_path.name}",
            f"/scripts/{script_path.name}"
        ]
    else:
        # Native standalone invocation
        local_k6 = TOOLS_BIN_DIR / "k6.exe"
        k6_bin = str(local_k6) if local_k6.exists() else "k6"
        return [
            k6_bin,
            "run",
            "--out", f"json={str(results_path)}",
            str(script_path)
        ]


async def tail_results_file(
    results_path: Path,
    aggregator: LiveMetricAggregator,
    on_metric_update: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
    is_running_check: Callable[[], bool],
    poll_interval: float = 0.2
):
    """
    Asynchronously tails results.json as it is being written by k6.
    Feeds parsed metrics into LiveMetricAggregator and invokes on_metric_update.
    """
    # Wait until file is created by k6
    timeout_start = time.time()
    while not results_path.exists() and is_running_check():
        if time.time() - timeout_start > 10.0:
            logger.warning(f"Timeout waiting for results file {results_path} to appear")
            break
        await asyncio.sleep(0.1)

    if not results_path.exists():
        return

    with open(results_path, "r", encoding="utf-8", errors="ignore") as f:
        last_emit_time = time.time()
        lines_since_yield = 0
        while is_running_check() or f.tell() < results_path.stat().st_size:
            line = f.readline()
            if line:
                aggregator.process_line(line)
                lines_since_yield += 1
                if lines_since_yield >= 50:
                    lines_since_yield = 0
                    await asyncio.sleep(0.002)
            else:
                lines_since_yield = 0
                await asyncio.sleep(poll_interval)

            # Check if we should broadcast periodic snapshot
            now = time.time()
            if now - last_emit_time >= 0.5:
                snapshot = aggregator.get_snapshot()
                if on_metric_update:
                    try:
                        await on_metric_update(snapshot)
                    except Exception as e:
                        logger.warning(f"Error calling on_metric_update: {e}")
                last_emit_time = now

        # Final pass over any remaining lines
        for remaining_line in f:
            aggregator.process_line(remaining_line)
        
        # Emit final snapshot
        if on_metric_update:
            try:
                await on_metric_update(aggregator.get_snapshot())
            except Exception as e:
                pass


async def execute_k6_run(
    run_id: str,
    script_path: str,
    success_criteria: Optional[Any] = None,
    on_metric_update: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
) -> Dict[str, Any]:
    """
    Runs k6 script via subprocess, tails results.json in real time, and returns final metrics.
    """
    script_file = Path(script_path)
    run_dir = script_file.parent
    results_file = run_dir / "results.json"

    # Clean old results file if re-running
    if results_file.exists():
        try:
            results_file.unlink()
        except Exception:
            pass

    cmd = get_k6_command(script_file, results_file)
    logger.info(f"Launching k6 process for run {run_id}: {' '.join(cmd)}")

    aggregator = LiveMetricAggregator()

    # Launch subprocess asynchronously
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    is_running = True

    def check_running() -> bool:
        return is_running and process.returncode is None

    # Start tailing task concurrently
    tail_task = asyncio.create_task(
        tail_results_file(results_file, aggregator, on_metric_update, check_running)
    )

    # Await process exit with timeout (5 minutes max for any k6 run)
    K6_TIMEOUT_SEC = 300
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=K6_TIMEOUT_SEC
        )
    except asyncio.TimeoutError:
        logger.error(f"k6 process for run {run_id} timed out after {K6_TIMEOUT_SEC}s — killing")
        process.kill()
        await process.wait()
        is_running = False
        await tail_task
        raise TimeoutError(f"k6 process exceeded {K6_TIMEOUT_SEC}s timeout and was killed")
    is_running = False
    
    stdout_text = stdout_bytes.decode(errors="ignore")
    stderr_text = stderr_bytes.decode(errors="ignore")

    # Wait for tailing to complete processing final lines
    await tail_task

    final_summary = aggregator.get_final_summary(success_criteria)
    final_summary["k6_exit_code"] = process.returncode
    final_summary["stdout"] = stdout_text[-1000:] if stdout_text else ""
    final_summary["stderr"] = stderr_text[-1000:] if stderr_text else ""
    final_summary["results_file"] = str(results_file)

    # Save summary json in run dir
    with open(run_dir / "final_summary.json", "w", encoding="utf-8") as f:
        json.dump(final_summary, f, indent=2)

    logger.info(f"k6 run {run_id} completed with exit code {process.returncode}. Total requests: {final_summary['total_requests']}")
    return final_summary
