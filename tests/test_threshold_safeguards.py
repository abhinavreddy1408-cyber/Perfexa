"""
Unit tests for threshold checking safeguards in LiveMetricAggregator / metric_parser.
Verifies:
1. Zero error rate (0%) against 0% limit: PASSES.
2. Non-zero error rate (1%) against 0% limit: FAILS.
3. Non-zero error rate (3%) against non-zero limit (5%): PASSES.
4. Error rate exactly equal to limit (5% == 5%): PASSES (does not exceed).
5. Non-zero error rate (6%) against non-zero limit (5%): FAILS.
"""

from backend.app.services.metric_parser import LiveMetricAggregator


def test_zero_error_rate_with_zero_limit():
    """0 errors against a 0.0 limit MUST PASS."""
    agg = LiveMetricAggregator()
    agg.total_requests = 100
    agg.failed_requests = 0
    agg.durations_all = [3.0] * 100

    summary = agg.get_final_summary({"p95_ms": 200, "max_error_rate": 0.0})
    assert summary["passed"] is True
    assert len(summary["threshold_failures"]) == 0


def test_positive_error_rate_with_zero_limit():
    """1 error (1%) against a 0.0 limit MUST FAIL."""
    agg = LiveMetricAggregator()
    agg.total_requests = 100
    agg.failed_requests = 1
    agg.durations_all = [3.0] * 100

    summary = agg.get_final_summary({"p95_ms": 200, "max_error_rate": 0.0})
    assert summary["passed"] is False
    assert any("exceeded limit (0.0%)" in f for f in summary["threshold_failures"])


def test_nonzero_error_rate_below_nonzero_limit():
    """3% errors against a 5% limit MUST PASS."""
    agg = LiveMetricAggregator()
    agg.total_requests = 100
    agg.failed_requests = 3  # 3%
    agg.durations_all = [50.0] * 100

    summary = agg.get_final_summary({"p95_ms": 200, "max_error_rate": 0.05})
    assert summary["passed"] is True
    assert len(summary["threshold_failures"]) == 0
    assert summary["error_rate"] == 0.03
    assert summary["error_percentage"] == 3.0


def test_error_rate_equal_to_nonzero_limit():
    """5% errors against a 5% limit MUST PASS (did not exceed limit)."""
    agg = LiveMetricAggregator()
    agg.total_requests = 100
    agg.failed_requests = 5  # 5%
    agg.durations_all = [50.0] * 100

    summary = agg.get_final_summary({"p95_ms": 200, "max_error_rate": 0.05})
    assert summary["passed"] is True
    assert len(summary["threshold_failures"]) == 0
    assert summary["error_rate"] == 0.05


def test_nonzero_error_rate_exceeding_nonzero_limit():
    """6% errors against a 5% limit MUST FAIL."""
    agg = LiveMetricAggregator()
    agg.total_requests = 100
    agg.failed_requests = 6  # 6%
    agg.durations_all = [50.0] * 100

    summary = agg.get_final_summary({"p95_ms": 200, "max_error_rate": 0.05})
    assert summary["passed"] is False
    assert len(summary["threshold_failures"]) == 1
    assert "Error rate (6.0%) exceeded limit (5.0%)" in summary["threshold_failures"][0]
