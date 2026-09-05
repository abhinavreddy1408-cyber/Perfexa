"""
Target Demo App for AI-Powered Autonomous Performance Testing Platform.
Features:
1. Fast/healthy endpoint (/api/fast, /api/health)
2. Artificial random latency endpoint (/api/delayed)
3. Deliberately breaking endpoint (/api/heavy, /api/orders, /api/checkout)
   that fails/slows down severely once concurrent load crosses ~150 requests.
4. Realistic API endpoints (/api/login, /api/users) for natural language tests.
"""

import asyncio
import random
import time
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel

app = FastAPI(
    title="Demo Target Application",
    description="Target API for realistic performance, soak, and stress testing.",
    version="1.0.0"
)

# Concurrency tracker
_concurrency_lock = asyncio.Lock()
_active_heavy_requests = 0
_peak_concurrency = 0
_total_requests = 0
BREAKING_POINT_CONCURRENCY = 50


class LoginPayload(BaseModel):
    username: Optional[str] = "testuser"
    password: Optional[str] = "secret123"


class OrderPayload(BaseModel):
    user_id: Optional[str] = "usr_123"
    item_id: Optional[str] = "item_456"
    quantity: Optional[int] = 1


@app.middleware("http")
async def track_total_requests(request: Request, call_next):
    global _total_requests
    _total_requests += 1
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    response.headers["X-Response-Time-Ms"] = f"{duration * 1000:.2f}"
    return response


@app.get("/api/health")
@app.get("/api/fast")
async def fast_endpoint():
    """Fast, healthy endpoint with near-zero latency (< 5ms)."""
    return {
        "status": "healthy",
        "service": "target-app",
        "timestamp": time.time(),
        "message": "Immediate 200 OK response."
    }


@app.get("/api/delayed")
async def delayed_endpoint(min_ms: int = 150, max_ms: int = 400):
    """Endpoint with artificial random latency between min_ms and max_ms."""
    delay = random.uniform(min_ms, max_ms) / 1000.0
    await asyncio.sleep(delay)
    return {
        "status": "ok",
        "simulated_latency_ms": round(delay * 1000, 2),
        "timestamp": time.time()
    }


@app.api_route("/api/login", methods=["GET", "POST"])
async def login_endpoint(payload: Optional[LoginPayload] = None):
    """Realistic login endpoint with moderate fixed latency (30-60ms)."""
    await asyncio.sleep(random.uniform(0.03, 0.06))
    return {
        "status": "authenticated",
        "token": "simulated-jwt-token-xyz789",
        "user": payload.username if payload else "guest"
    }


@app.api_route("/api/heavy", methods=["GET", "POST"])
@app.api_route("/api/checkout", methods=["GET", "POST"])
@app.api_route("/api/orders", methods=["GET", "POST"])
async def heavy_breaking_endpoint(request: Request):
    """
    Deliberately breaking endpoint.
    Tracks active concurrent requests. Once concurrent load crosses BREAKING_POINT_CONCURRENCY (~150),
    it simulates thread-pool starvation / DB connection exhaustion by:
    1. Sleeping for 2000ms+
    2. Returning HTTP 503 Service Unavailable (or 500 Internal Server Error).
    """
    global _active_heavy_requests, _peak_concurrency

    # Increment active concurrency
    async with _concurrency_lock:
        _active_heavy_requests += 1
        if _active_heavy_requests > _peak_concurrency:
            _peak_concurrency = _active_heavy_requests
        current_concurrency = _active_heavy_requests

    try:
        # Check if breaking point crossed
        if current_concurrency > BREAKING_POINT_CONCURRENCY:
            # Overloaded state: simulate resource exhaustion
            extra_overload = current_concurrency - BREAKING_POINT_CONCURRENCY
            # Severe artificial delay simulating queue backlog
            backlog_delay = min(2.5, 0.5 + (extra_overload * 0.02))
            await asyncio.sleep(backlog_delay)

            # 90% chance of failing with 503 Service Unavailable, 10% with 500
            error_code = status.HTTP_503_SERVICE_UNAVAILABLE if random.random() < 0.9 else status.HTTP_500_INTERNAL_SERVER_ERROR
            raise HTTPException(
                status_code=error_code,
                detail=f"Resource Pool Exhausted: Concurrency limit {BREAKING_POINT_CONCURRENCY} exceeded (current in-flight: {current_concurrency})"
            )

        # Normal load (< 50 concurrent requests): smooth response with slight realistic processing time
        await asyncio.sleep(random.uniform(0.08, 0.14))
        return {
            "status": "success",
            "message": "Order / heavy transaction processed successfully",
            "active_concurrency": current_concurrency,
            "timestamp": time.time()
        }

    finally:
        async with _concurrency_lock:
            _active_heavy_requests -= 1


@app.get("/api/metrics")
async def metrics_endpoint():
    """Returns runtime telemetry of the target demo application."""
    return {
        "active_heavy_requests": _active_heavy_requests,
        "peak_concurrency": _peak_concurrency,
        "breaking_point_threshold": BREAKING_POINT_CONCURRENCY,
        "total_requests": _total_requests
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
