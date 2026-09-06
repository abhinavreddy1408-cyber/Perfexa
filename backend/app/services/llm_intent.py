"""
Step 4: Merged LLM Call for Test Intent Extraction + Synthetic Payload Generation.
Uses the fast model (meta/llama-3.2-11b-vision-instruct) to extract structured
intent and generate realistic payloads in a single round-trip.
"""

import json
import logging
import re
from typing import Dict, Any, Optional
from pydantic import ValidationError

from backend.app.config import MODEL_FAST, TARGET_APP_URL
from backend.app.services.docker_utils import get_effective_target_url
from backend.app.schemas.intent import (
    TestIntent,
    MergedIntentPayloadResponse
)
from backend.app.services.nim_client import default_nim_client, clean_json_string

logger = logging.getLogger("llm_intent")


SYSTEM_PROMPT = """You are an expert performance engineering AI.
Your job is to analyze a natural language performance testing request and produce:
1. "intent": A strictly valid structured load test configuration
2. "synthetic_payloads": Realistic mock data payloads for each endpoint involved

RULES:
- Respond with PURE JSON ONLY. No markdown fences, no explanatory text outside the JSON.
- Supported test_type values: "baseline" (steady low load), "soak" (steady moderate load over duration), "stress" (ramping load to identify breaking points).
- If the user prompt is completely uninterpretable gibberish, random keystrokes (e.g. "asdkjhaskjdh", "qwertyuiop", "12345"), or contains no intelligible intent or testing goal:
  Respond with JSON containing an "error" key:
  {{
    "error": "Could not understand performance test intent from the provided text. Please describe what endpoints and load you want to test (for example: stress test my heavy endpoint with 50 users)."
  }}
- If the user prompt is vague or omits details (e.g. "check if my API can handle load"):
  - Pick sensible defaults (e.g. baseline: 10 VUs for 30s, stress: 200 VUs ramping up).
  - Target URL defaults to "{default_url}".
  - Known demo endpoints:
    * "/api/fast" (GET, healthy baseline)
    * "/api/delayed" (GET, latency simulation)
    * "/api/heavy" or "/api/checkout" (POST, concurrency-sensitive, breaking point at ~150 concurrent requests)
    * "/api/login" (POST, authentication endpoint)
  - You MUST document every defaulted value or interpretation in the "assumptions_made" list!
- Under "success_criteria":
  * "p95_ms": Target 95th percentile latency in ms (e.g. 200 for baseline, 500 for soak/stress).
  * "max_error_rate": NEVER default max_error_rate to 0.0 unless the user explicitly demands zero tolerance or 0% errors. Use a sane tolerance: 0.01 (1%) for baseline tests or 0.05 (5%) for soak/stress tests.
- Under "synthetic_payloads", provide a dictionary mapping each endpoint path (e.g. "/api/login") to a list of 5-10 realistic JSON payload objects.

JSON SCHEMA STRUCTURE:
{{
  "intent": {{
    "test_type": "baseline" | "soak" | "stress",
    "target_url": "http://...",
    "virtual_users": <int>,
    "duration": "<e.g. 30s, 1m, 2m>",
    "ramp_pattern": [
      {{"duration": "10s", "target_vus": 50}},
      {{"duration": "20s", "target_vus": 100}},
      {{"duration": "10s", "target_vus": 0}}
    ],
    "endpoints_involved": [
      {{
        "path": "/api/login",
        "method": "POST",
        "headers": {{"Content-Type": "application/json"}},
        "payload_template": {{"username": "testuser", "password": "password123"}},
        "weight": 100
      }}
    ],
    "success_criteria": {{
      "p95_ms": <int>,
      "max_error_rate": <float between 0.0 and 1.0>,
      "p99_ms": <int>
    }},
    "assumptions_made": [
      "Assumption 1...",
      "Assumption 2..."
    ],
    "summary_description": "Short plain English summary of the test plan"
  }},
  "synthetic_payloads": {{
    "/api/login": [
      {{"username": "alice_smith", "password": "SafePassword!123"}},
      {{"username": "bob_jones", "password": "TestPass#2026"}}
    ]
  }}
}}
"""


def extract_intent_and_payloads(
    prompt: str,
    target_url: Optional[str] = None
) -> MergedIntentPayloadResponse:
    """
    Executes the merged LLM call to extract structured test intent and synthetic payloads.
    """
    active_target = get_effective_target_url(target_url)
    system_msg = SYSTEM_PROMPT.format(default_url=active_target)

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": f"Extract performance test intent and generate payloads for this request:\n\"{prompt}\""}
    ]

    logger.info(f"Extracting intent with model {MODEL_FAST} for prompt: {prompt[:80]}...")
    raw_response = default_nim_client.call_with_retry(
        model=MODEL_FAST,
        messages=messages,
        max_tokens=1800,
        temperature=0.1
    )

    cleaned_json = clean_json_string(raw_response)

    try:
        data = json.loads(cleaned_json)
    except json.JSONDecodeError as e:
        logger.warning(f"Direct JSON parse failed: {e}. Attempting JSON cleanup...")
        # Try stripping leading/trailing garbage
        match = re.search(r"\{[\s\S]*\}", cleaned_json)
        if match:
            data = json.loads(match.group(0))
        else:
            raise ValueError(f"Could not parse valid JSON from LLM response: {raw_response[:300]}")

    if isinstance(data, dict) and "error" in data:
        raise ValueError(str(data["error"]))

    # Pre-sanitize and scale endpoint weights if needed
    if isinstance(data, dict):
        intent_dict = data.get("intent")
        if isinstance(intent_dict, dict):
            eps = intent_dict.get("endpoints_involved")
            if isinstance(eps, list) and eps:
                raw_weights = []
                for ep in eps:
                    if isinstance(ep, dict):
                        try:
                            raw_weights.append(float(ep.get("weight", 100)))
                        except Exception:
                            raw_weights.append(100.0)
                max_w = max(raw_weights) if raw_weights else 100
                scale = (100.0 / max_w) if max_w > 100 else 1.0
                for ep in eps:
                    if isinstance(ep, dict) and "weight" in ep:
                        try:
                            w = float(ep.get("weight", 100))
                            ep["weight"] = max(1, min(100, int(round(w * scale))))
                        except Exception:
                            ep["weight"] = 100

    # Validate against Pydantic schema
    try:
        parsed = MergedIntentPayloadResponse.model_validate(data)
        # Ensure target_url is populated and normalized for environment
        parsed.intent.target_url = get_effective_target_url(parsed.intent.target_url or active_target)

        # Safeguard: Never allow max_error_rate to default to 0.0 unless user explicitly requested 0%/zero tolerance
        zero_tolerance_requested = bool(
            re.search(r"\b(0%|zero\s+(percent|tolerance|errors?))\b", prompt, re.IGNORECASE)
        )
        if parsed.intent.success_criteria.max_error_rate <= 0.0 and not zero_tolerance_requested:
            default_err = 0.05 if parsed.intent.test_type in ("stress", "soak") else 0.01
            parsed.intent.success_criteria.max_error_rate = default_err
            parsed.intent.assumptions_made.append(
                f"Defaulted max_error_rate tolerance to {default_err * 100:.1f}% (avoiding strict 0.0% false failures)."
            )

        return parsed
    except ValidationError as ve:
        logger.error(f"Pydantic schema validation error: {ve}")
        raise ve
