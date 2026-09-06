"""
Locked Test Intent and Payload Schema.
This schema is central to the platform and MUST remain stable across all steps.
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, field_validator


class RampStage(BaseModel):
    duration: str = Field(..., description="Duration for this stage, e.g., '10s', '1m', '30s'")
    target_vus: int = Field(..., ge=0, description="Target virtual users at the end of this stage")

    @field_validator("duration", mode="before")
    @classmethod
    def sanitize_duration(cls, v: Any) -> str:
        if isinstance(v, (int, float)):
            return f"{int(v)}s"
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if v_clean.isdigit():
                return f"{v_clean}s"
            return v_clean
        return "10s"


class EndpointConfig(BaseModel):
    path: str = Field(..., description="API endpoint path, e.g. '/api/login' or '/api/heavy'")
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = Field(
        default="GET",
        description="HTTP method"
    )
    headers: Dict[str, str] = Field(
        default_factory=lambda: {"Content-Type": "application/json"},
        description="HTTP request headers"
    )
    payload_template: Optional[Dict[str, Any]] = Field(
        default=None,
        description="JSON payload body with realistic dummy data or tokens"
    )
    weight: int = Field(
        default=100,
        ge=1,
        le=100,
        description="Traffic weight distribution if multiple endpoints are specified"
    )

    @field_validator("weight", mode="before")
    @classmethod
    def sanitize_weight(cls, v: Any) -> int:
        if v is None:
            return 100
        try:
            val = float(v)
            if val > 100 and val <= 1000:
                val = val / 10.0
            elif val > 1000:
                val = 100.0
            return max(1, min(100, int(round(val))))
        except Exception:
            return 100


class SuccessCriteria(BaseModel):
    p95_ms: int = Field(
        default=500,
        gt=0,
        description="Maximum acceptable 95th percentile response time in milliseconds"
    )
    max_error_rate: float = Field(
        default=0.01,
        ge=0.0,
        le=1.0,
        description="Maximum acceptable error rate as a decimal (e.g. 0.01 = 1%, 0.05 = 5%)"
    )
    p99_ms: Optional[int] = Field(
        default=1000,
        gt=0,
        description="Maximum acceptable 99th percentile response time in milliseconds"
    )

    @field_validator("max_error_rate", mode="before")
    @classmethod
    def sanitize_max_error_rate(cls, v: Any) -> float:
        if v is None:
            return 0.01
        try:
            val = float(v)
            if val > 1.0 and val <= 100.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        except Exception:
            return 0.01


class TestIntent(BaseModel):
    test_type: Literal["baseline", "soak", "stress"] = Field(
        ...,
        description="Type of test: 'baseline' (steady low load), 'soak' (moderate load over longer duration), or 'stress' (ramping load to find breaking point)"
    )
    target_url: str = Field(
        default="http://localhost:8001",
        description="Target application base URL"
    )
    virtual_users: int = Field(
        ...,
        gt=0,
        description="Peak or steady virtual users (concurrent threads)"
    )
    duration: str = Field(
        ...,
        description="Overall test duration or steady period, e.g. '30s', '2m', '5m'"
    )
    ramp_pattern: List[RampStage] = Field(
        default_factory=list,
        description="Stages for ramping VUs up, holding, and ramping down"
    )
    endpoints_involved: List[EndpointConfig] = Field(
        ...,
        min_length=1,
        description="List of endpoints targeted during the load test"
    )
    success_criteria: SuccessCriteria = Field(
        default_factory=SuccessCriteria,
        description="Pass/fail thresholds for latency and error rates"
    )
    assumptions_made: List[str] = Field(
        default_factory=list,
        description="Explicit assumptions made when interpreting vague or unspecified prompt details"
    )
    summary_description: str = Field(
        ...,
        description="Concise plain-English summary of the extracted intent"
    )


class MergedIntentPayloadResponse(BaseModel):
    """
    Unified response model for Step 4 merged LLM call.
    Contains both the structured intent and the generated synthetic payloads.
    """
    intent: TestIntent = Field(..., description="Structured test intent")
    synthetic_payloads: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Dictionary mapping endpoint path to a pool of realistic synthetic payloads"
    )
