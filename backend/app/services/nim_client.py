"""
NVIDIA NIM LLM Client wrapper using OpenAI SDK.
Includes:
1. Exponential backoff retry logic (handles 429 rate limits, 503 capacity, connection drops)
2. Raw call logging to logs/llm_raw_calls.jsonl
3. Resilient JSON parsing
4. Offline mock/replay fallback when NVIDIA_API_KEY is not yet populated
"""

import json
import logging
import os
import re
import time
import random
from typing import List, Dict, Any, Optional, Iterator
from openai import OpenAI, APIError, RateLimitError, APIConnectionError

from backend.app.config import (
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    RAW_LLM_LOG_PATH
)

logger = logging.getLogger("nim_client")
logging.basicConfig(level=logging.INFO)


def _log_raw_call(
    model: str,
    messages: List[Dict[str, str]],
    raw_output: str,
    duration_sec: float,
    status: str,
    metadata: Optional[Dict[str, Any]] = None
):
    """Appends full raw prompt and output to local JSONL log."""
    entry = {
        "timestamp": time.time(),
        "model": model,
        "duration_sec": round(duration_sec, 3),
        "status": status,
        "messages": messages,
        "raw_output": raw_output,
        "metadata": metadata or {}
    }
    try:
        with open(RAW_LLM_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning(f"Could not log raw LLM call: {e}")


def clean_json_string(text: str) -> str:
    """Removes markdown fences or extra surrounding text from LLM JSON response."""
    cleaned = text.strip()
    # Match ```json ... ``` or ``` ... ```
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    else:
        # Find first '{' or '[' and last '}' or ']'
        start_idx = -1
        end_idx = -1
        for i, ch in enumerate(cleaned):
            if ch in ('{', '['):
                start_idx = i
                break
        for i in range(len(cleaned) - 1, -1, -1):
            if cleaned[i] in ('}', ']'):
                end_idx = i + 1
                break
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx:end_idx]
    # Repair invalid escape sequences such as \' commonly emitted by LLMs
    cleaned = re.sub(r"(?<!\\)\\'", "'", cleaned)
    return cleaned


class NimClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or NVIDIA_API_KEY
        self.base_url = base_url or NVIDIA_BASE_URL
        self.has_real_key = bool(self.api_key and len(self.api_key.strip()) > 5 and not self.api_key.startswith("your_"))
        
        if self.has_real_key:
            self.client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key
            )
        else:
            self.client = None
            logger.info("NimClient initialized in local replay/mock mode (no valid NVIDIA_API_KEY found)")

    def call_with_retry(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1500,
        temperature: float = 0.2,
        max_retries: int = 4,
        base_delay: float = 1.5,
        fallback_model: str = "meta/llama-3.2-11b-vision-instruct"
    ) -> str:
        """
        Executes an LLM chat completion with exponential backoff and jitter.
        Handles NIM ~40 req/min rate limits and model fallback.
        """
        if not self.has_real_key:
            return self._offline_fallback(model, messages, stream=False)

        current_model = model
        last_err = None
        for attempt in range(max_retries + 1):
            start_time = time.time()
            try:
                response = self.client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=False
                )
                raw_text = response.choices[0].message.content or ""
                duration = time.time() - start_time
                _log_raw_call(current_model, messages, raw_text, duration, status="success")
                return raw_text

            except (RateLimitError, APIError, APIConnectionError) as e:
                err_msg = str(e)
                last_err = e
                duration = time.time() - start_time
                _log_raw_call(current_model, messages, err_msg, duration, status=f"error_attempt_{attempt}")

                if "ResourceExhausted" in err_msg or "404" in err_msg or "504" in err_msg:
                    if current_model != fallback_model:
                        logger.info(f"Switching from {current_model} to fallback {fallback_model}")
                        current_model = fallback_model
                        time.sleep(1.0)
                        continue

                if attempt == max_retries:
                    logger.error(f"NIM API failed after {max_retries} retries: {e}")
                    raise

                sleep_time = (base_delay * (2 ** attempt)) + random.uniform(0.2, 1.0)
                logger.warning(f"Rate limit or API error on attempt {attempt+1}/{max_retries}. Backing off for {sleep_time:.2f}s: {e}")
                time.sleep(sleep_time)
            except Exception as e:
                logger.error(f"Unexpected error in NIM client: {e}")
                raise

        raise last_err

    def stream_with_retry(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1500,
        temperature: float = 0.2,
        max_retries: int = 3,
        base_delay: float = 1.5,
        fallback_model: str = "meta/llama-3.2-11b-vision-instruct"
    ) -> Iterator[str]:
        """
        Streams tokens from NIM API with resilient retry and fallback.
        Yields text deltas as they arrive.
        """
        if not self.has_real_key:
            for chunk in ["import http from 'k6/http';\n", "export default function() { http.get('http://localhost:8001/api/fast'); }\n"]:
                yield chunk
            return

        current_model = model
        for attempt in range(max_retries + 1):
            start_time = time.time()
            collected_tokens = []
            try:
                stream = self.client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        collected_tokens.append(delta)
                        yield delta

                duration = time.time() - start_time
                _log_raw_call(current_model, messages, "".join(collected_tokens), duration, status="stream_success")
                return

            except (RateLimitError, APIError, APIConnectionError) as e:
                err_msg = str(e)
                logger.warning(f"Stream error on attempt {attempt+1}/{max_retries} with {current_model}: {err_msg}")
                _log_raw_call(current_model, messages, err_msg, time.time() - start_time, status=f"stream_err_{attempt}")

                if "ResourceExhausted" in err_msg or "404" in err_msg or "504" in err_msg:
                    if current_model != fallback_model:
                        logger.info(f"Switching from {current_model} to reliable fallback {fallback_model}")
                        current_model = fallback_model
                        time.sleep(1.0)
                        continue

                if attempt == max_retries:
                    raise

                sleep_time = (base_delay * (2 ** attempt)) + random.uniform(0.3, 1.0)
                time.sleep(sleep_time)

    def _offline_fallback(self, model: str, messages: List[Dict[str, str]], stream: bool = False) -> Any:
        """Deterministic fallback when running without NVIDIA_API_KEY."""
        user_prompt = ""
        for m in messages:
            if m.get("role") == "user":
                user_prompt = m.get("content", "")
        
        # Check if this is intent extraction
        if "test intent" in messages[0].get("content", "").lower() or "synthetic_payloads" in user_prompt.lower():
            p_lower = user_prompt.lower()
            test_type = "baseline"
            vus = 10
            duration = "30s"
            target_url = "http://localhost:8001"
            assumptions = ["Defaulted to localhost:8001"]

            if "stress" in p_lower or "break" in p_lower or "overload" in p_lower or "200" in p_lower:
                test_type = "stress"
                vus = 200
                duration = "1m"
                assumptions.append("Detected stress test request; set 200 VUs to search for breaking point")
            elif "soak" in p_lower or "endurance" in p_lower or "long" in p_lower:
                test_type = "soak"
                vus = 50
                duration = "3m"
                assumptions.append("Detected soak test request; set 50 steady VUs for endurance")
            else:
                assumptions.append("Prompt did not specify test type; defaulted to baseline with 10 VUs for 30s")

            # Extract numbers if present
            vu_match = re.search(r"(\d+)\s*(?:users?|vus?)", p_lower)
            if vu_match:
                vus = int(vu_match.group(1))
                assumptions.append(f"Extracted explicit VU target: {vus}")

            dur_match = re.search(r"(\d+)\s*(?:min(?:ute)?s?|m\b)", p_lower)
            if dur_match:
                duration = f"{dur_match.group(1)}m"
                assumptions.append(f"Extracted explicit duration: {duration}")
            sec_match = re.search(r"(\d+)\s*(?:sec(?:ond)?s?|s\b)", p_lower)
            if sec_match:
                duration = f"{sec_match.group(1)}s"
                assumptions.append(f"Extracted explicit duration: {duration}")

            # Endpoints
            endpoints = []
            if "login" in p_lower:
                endpoints.append({
                    "path": "/api/login",
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "payload_template": {"username": "testuser", "password": "password123"},
                    "weight": 100
                })
                assumptions.append("Targeting /api/login endpoint based on prompt text")
            elif "heavy" in p_lower or "checkout" in p_lower or "order" in p_lower or test_type == "stress":
                endpoints.append({
                    "path": "/api/heavy",
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "payload_template": {"user_id": "usr_99", "action": "checkout"},
                    "weight": 100
                })
                assumptions.append("Targeting /api/heavy endpoint for load/stress evaluation")
            else:
                endpoints.append({
                    "path": "/api/fast",
                    "method": "GET",
                    "headers": {"Content-Type": "application/json"},
                    "payload_template": None,
                    "weight": 100
                })
                assumptions.append("Targeting healthy /api/fast endpoint")

            # Ramp pattern
            if test_type == "stress":
                ramp = [
                    {"duration": "10s", "target_vus": min(50, vus // 4)},
                    {"duration": "20s", "target_vus": min(150, vus * 3 // 4)},
                    {"duration": "20s", "target_vus": vus},
                    {"duration": "10s", "target_vus": 0}
                ]
            elif test_type == "soak":
                ramp = [
                    {"duration": "15s", "target_vus": vus},
                    {"duration": duration, "target_vus": vus},
                    {"duration": "10s", "target_vus": 0}
                ]
            else:
                ramp = [
                    {"duration": "5s", "target_vus": vus},
                    {"duration": duration, "target_vus": vus},
                    {"duration": "5s", "target_vus": 0}
                ]

            mock_data = {
                "intent": {
                    "test_type": test_type,
                    "target_url": target_url,
                    "virtual_users": vus,
                    "duration": duration,
                    "ramp_pattern": ramp,
                    "endpoints_involved": endpoints,
                    "success_criteria": {
                        "p95_ms": 600 if test_type == "stress" else 300,
                        "max_error_rate": 0.05 if test_type == "stress" else 0.01,
                        "p99_ms": 1200 if test_type == "stress" else 600
                    },
                    "assumptions_made": assumptions,
                    "summary_description": f"{test_type.capitalize()} test against {endpoints[0]['path']} with {vus} VUs over {duration}"
                },
                "synthetic_payloads": {
                    endpoints[0]["path"]: [
                        {"username": f"user_{i}", "password": f"pass_{i}!", "index": i}
                        for i in range(10)
                    ]
                }
            }
            raw = json.dumps(mock_data, indent=2)
            _log_raw_call(model, messages, raw, 0.05, status="mock_success")
            return raw

        # Summary generation fallback — metrics-driven, no fabricated infrastructure claims
        if "summary" in messages[0].get("content", "").lower() or "report" in messages[0].get("content", "").lower():
            import re as _re
            # Extract actual metrics from the user prompt content
            def _extract(pattern, text, default="N/A"):
                m = _re.search(pattern, text)
                return m.group(1) if m else default

            total_reqs = _extract(r"Total Requests Executed:\s*(\d+)", user_prompt, "0")
            failed_reqs = _extract(r"Failed Requests:\s*(\d+)", user_prompt, "0")
            error_pct = _extract(r"Failed Requests:.*?\(([\d.]+)%", user_prompt, "0")
            p95 = _extract(r"Latency p95:\s*([\d.]+)", user_prompt, "0")
            p50 = _extract(r"Latency p50:\s*([\d.]+)", user_prompt, "0")
            p99 = _extract(r"Latency p99:\s*([\d.]+)", user_prompt, "0")
            avg_rps = _extract(r"Average Throughput:\s*([\d.]+)", user_prompt, "0")
            test_type = _extract(r"Test Type:\s*(\w+)", user_prompt, "BASELINE")
            endpoints = _extract(r"Endpoints Tested:\s*\[([^\]]+)\]", user_prompt, "/api/fast")
            pass_fail = _extract(r"Pass/Fail Status:\s*(\w+)", user_prompt, "PASSED")

            is_fail = pass_fail.upper() == "FAILED" or "503" in user_prompt or float(error_pct) > 1.0

            verdict_text = "FAILED (Threshold Breached)" if is_fail else "PASSED (All Thresholds Met)"

            root_cause = (
                "Errors appeared during the test run. The observed pattern is consistent with the target "
                "service rejecting requests under high concurrency — exact internal mechanism cannot be "
                "determined from load test metrics alone."
            ) if is_fail else (
                "The target service handled the applied load within acceptable latency and error rate bounds. "
                "No anomalies were detected in the metrics."
            )

            report = (
                f"### Verdict\n\n"
                f"**{verdict_text}**\n\n"
                f"### What Happened (Observed Performance)\n\n"
                f"- **Test Type**: {test_type}\n"
                f"- **Endpoints Tested**: {endpoints}\n"
                f"- **Total Requests**: {total_reqs} ({failed_reqs} failed, {error_pct}% error rate)\n"
                f"- **Throughput**: {avg_rps} req/sec\n"
                f"- **Latency**: p50={p50}ms, p95={p95}ms, p99={p99}ms\n\n"
                f"### Root Cause Analysis\n\n"
                f"{root_cause}\n\n"
                f"*Note: This is an offline-generated summary (no LLM API key configured). "
                f"For detailed root-cause analysis, configure a valid NVIDIA_API_KEY.*\n\n"
                f"### Recommendations\n\n"
                f"1. Configure a valid NVIDIA_API_KEY to enable grounded AI diagnostics.\n"
                f"2. Review the endpoint(s) under test ({endpoints}) for concurrency handling.\n"
                f"3. Compare these baseline numbers against subsequent runs to track regressions."
            )
            _log_raw_call(model, messages, report, 0.05, status="mock_success")
            return report

        # Default fallback
        fallback = "ok"
        _log_raw_call(model, messages, fallback, 0.05, status="mock_success")
        return fallback


# Global singleton instance
default_nim_client = NimClient()
