"""
Live metric aggregator and parser for k6 streamed JSON lines.
Parses `--out json=results.json` metric lines and calculates:
- Active VUs
- Throughput (Requests/sec)
- Cumulative Error Rate
- Latency Percentiles (p50, p95, p99) and Mean
- Time series history for live dashboard graphs
"""

import json
import math
import time
from typing import Dict, Any, List, Optional
from collections import deque


class LiveMetricAggregator:
    def __init__(self, window_size_sec: float = 1.0):
        self.window_size_sec = window_size_sec
        self.start_time = time.time()
        
        # Current state
        self.current_vus = 0
        self.total_requests = 0
        self.failed_requests = 0
        
        # Durations for percentile calculation
        self.durations_all: List[float] = []
        self.recent_durations: deque = deque(maxlen=200)
        
        # Throughput tracking
        self.recent_requests: deque = deque() # (timestamp, count)
        
        # History for charts: list of snapshots
        self.history: List[Dict[str, Any]] = []
        self.last_snapshot_time = 0.0

    def process_line(self, line: str):
        line = line.strip()
        if not line:
            return
        try:
            record = json.loads(line)
        except Exception:
            return

        rec_type = record.get("type")
        metric = record.get("metric")
        data = record.get("data", {})
        val = data.get("value", 0)
        now = time.time()

        if rec_type == "Point":
            if metric == "vus":
                self.current_vus = int(val)
            elif metric == "http_reqs":
                self.total_requests += 1
                self.recent_requests.append(now)
            elif metric == "http_req_failed":
                if val == 1:
                    self.failed_requests += 1
            elif metric == "http_req_duration":
                val_f = float(val)
                self.durations_all.append(val_f)
                self.recent_durations.append(val_f)

    def _calc_percentile(self, values: List[float], percentile: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        k = (len(sorted_vals) - 1) * (percentile / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return round(sorted_vals[int(k)], 2)
        d0 = sorted_vals[int(f)] * (c - k)
        d1 = sorted_vals[int(c)] * (k - f)
        return round(d0 + d1, 2)

    def get_snapshot(self) -> Dict[str, Any]:
        """Returns instantaneous snapshot for WebSocket live broadcast."""
        now = time.time()
        elapsed = round(now - self.start_time, 1)

        # Calculate current RPS based on last 2 seconds
        window_cutoff = now - 2.0
        while self.recent_requests and self.recent_requests[0] < window_cutoff:
            self.recent_requests.popleft()
        rps = round(len(self.recent_requests) / 2.0, 1)

        # Cumulative error rate
        err_rate = round(self.failed_requests / max(1, self.total_requests), 4)

        # Percentiles
        sample_durations = list(self.recent_durations) if self.recent_durations else self.durations_all
        p50 = self._calc_percentile(sample_durations, 50)
        p95 = self._calc_percentile(sample_durations, 95)
        p99 = self._calc_percentile(sample_durations, 99)
        avg_lat = round(sum(sample_durations) / max(1, len(sample_durations)), 2)

        snapshot = {
            "elapsed_sec": elapsed,
            "vus": self.current_vus,
            "rps": rps,
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "error_rate": err_rate,
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "avg_latency_ms": avg_lat,
            "timestamp": now
        }

        # Keep history for charts (at most once every 0.8s)
        if now - self.last_snapshot_time >= 0.8:
            self.history.append({
                "time": f"{elapsed}s",
                "vus": self.current_vus,
                "rps": rps,
                "error_rate": err_rate,
                "p95_ms": p95,
                "p50_ms": p50
            })
            self.last_snapshot_time = now

        return snapshot

    def get_final_summary(self, success_criteria: Optional[Any] = None) -> Dict[str, Any]:
        """Calculates final aggregate summary metrics for the post-run report and DB."""
        err_rate = round(self.failed_requests / max(1, self.total_requests), 4)
        p50 = self._calc_percentile(self.durations_all, 50)
        p95 = self._calc_percentile(self.durations_all, 95)
        p99 = self._calc_percentile(self.durations_all, 99)
        avg_lat = round(sum(self.durations_all) / max(1, len(self.durations_all)), 2)
        total_time = round(time.time() - self.start_time, 2)
        avg_rps = round(self.total_requests / max(0.1, total_time), 2)

        # Threshold checks
        passed = True
        threshold_failures = []

        # Guard: zero requests means no data was collected — never report as passed
        if self.total_requests == 0:
            passed = False
            threshold_failures.append("No requests were completed — k6 may have crashed or the target was unreachable")
        elif success_criteria:
            crit = getattr(success_criteria, "__dict__", success_criteria)
            p95_limit = crit.get("p95_ms", 500)
            err_limit = crit.get("max_error_rate", 0.05)

            if p95 > p95_limit:
                passed = False
                threshold_failures.append(f"p95 latency ({p95}ms) exceeded limit ({p95_limit}ms)")

            # Error rate threshold check:
            # 1. Exact-equal-to-zero safeguard: if 0 requests failed (failed_requests == 0 or err_rate == 0.0),
            #    the error rate check MUST pass, even if max_error_rate is 0.0.
            # 2. Otherwise, fail if actual error rate strictly exceeds the allowable limit (err_rate > err_limit).
            if self.failed_requests == 0 or err_rate == 0.0:
                pass  # 0 errors always passes any error rate threshold
            elif err_rate > err_limit:
                passed = False
                threshold_failures.append(f"Error rate ({err_rate*100:.1f}%) exceeded limit ({err_limit*100:.1f}%)")

        return {
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "error_rate": err_rate,
            "error_percentage": round(err_rate * 100, 2),
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "avg_latency_ms": avg_lat,
            "avg_rps": avg_rps,
            "total_duration_sec": total_time,
            "passed": passed,
            "no_data": self.total_requests == 0,
            "threshold_failures": threshold_failures,
            "chart_history": self.history
        }
