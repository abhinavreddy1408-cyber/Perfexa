"""
Step 5: k6 Load-Test Script Generation with Strict Few-Shot Templates and Self-Healing.
Uses the verified coding model (nvidia/nemotron-3-nano-omni-30b-a3b-reasoning)
to generate valid JavaScript k6 load-testing scripts with streaming directly to disk.
Validates each script with a 2-second smoke run: `k6 run --duration 2s --vus 1 <script>`
and automatically retries once if syntax/runtime validation fails.
"""

import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from backend.app.config import (
    MODEL_CODE,
    TOOLS_BIN_DIR,
    TEST_RUNS_DIR,
    TARGET_APP_URL
)
from backend.app.schemas.intent import TestIntent, MergedIntentPayloadResponse
from backend.app.services.docker_utils import is_docker_running, get_effective_target_url, normalize_script_target_urls
from backend.app.services.nim_client import default_nim_client, _log_raw_call

logger = logging.getLogger("k6_generator")

# Locate k6 executable (local tools/bin/k6.exe or system PATH)
def get_k6_executable() -> str:
    local_k6 = TOOLS_BIN_DIR / "k6.exe"
    if local_k6.exists():
        return str(local_k6)
    return "k6"


# ---------------------------------------------------------------------------
# STRICT FEW-SHOT TEMPLATES (CONCRETE WORKING EXAMPLES)
# ---------------------------------------------------------------------------

BASELINE_TEMPLATE = """import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 10,
  duration: '15s',
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<300'],
  },
};

const BASE_URL = 'http://127.0.0.1:8001';

export default function () {
  const res = http.get(`${BASE_URL}/api/fast`, {
    headers: { 'Content-Type': 'application/json' },
  });
  check(res, {
    'status is 200': (r) => r.status === 200,
  });
  sleep(1);
}
"""

SOAK_TEMPLATE = """import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '5s', target: 20 },
    { duration: '20s', target: 20 },
    { duration: '5s', target: 0 }
  ],
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<500'],
  },
};

const BASE_URL = 'http://127.0.0.1:8001';

export default function () {
  const res = http.get(`${BASE_URL}/api/delayed`, {
    headers: { 'Content-Type': 'application/json' },
  });
  check(res, {
    'status is 200': (r) => r.status === 200,
  });
  sleep(0.5);
}
"""

STRESS_TEMPLATE = """import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '5s', target: 50 },
    { duration: '10s', target: 150 },
    { duration: '10s', target: 200 },
    { duration: '5s', target: 0 }
  ],
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<800'],
  },
};

const BASE_URL = 'http://127.0.0.1:8001';
const PAYLOADS = [
  { username: 'user_0', password: 'password123' },
  { username: 'user_1', password: 'password123' }
];

export default function () {
  const payload = PAYLOADS[Math.floor(Math.random() * PAYLOADS.length)];
  const res = http.post(`${BASE_URL}/api/heavy`, JSON.stringify(payload), {
    headers: { 'Content-Type': 'application/json' },
  });
  check(res, {
    'status is 200': (r) => r.status === 200,
    'not 503 overloaded': (r) => r.status !== 503,
  });
  sleep(0.2);
}
"""


def clean_js_code(raw_text: str) -> str:
    """Strips markdown code blocks, preamble, and postamble from generated JS."""
    cleaned = raw_text.strip()
    match = re.search(r"```(?:javascript|js)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    
    # Ensure it starts with import
    import_idx = cleaned.find("import ")
    if import_idx != -1:
        cleaned = cleaned[import_idx:]

    cleaned = normalize_script_target_urls(cleaned)

    # Ensure required imports are present
    if "from 'k6/http'" not in cleaned and 'from "k6/http"' not in cleaned:
        cleaned = "import http from 'k6/http';\n" + cleaned
    if "from 'k6'" not in cleaned and 'from "k6"' not in cleaned:
        cleaned = "import { check, sleep } from 'k6';\n" + cleaned
    else:
        # If check or sleep is missing from { ... } in import from 'k6'
        k6_imp_match = re.search(r"import\s*\{([^}]*)\}\s*from\s*['\"]k6['\"];?", cleaned)
        if k6_imp_match:
            symbols = [s.strip() for s in k6_imp_match.group(1).split(",") if s.strip()]
            if "check" not in symbols:
                symbols.append("check")
            if "sleep" not in symbols:
                symbols.append("sleep")
            new_imp = f"import {{ {', '.join(symbols)} }} from 'k6';"
            cleaned = cleaned[:k6_imp_match.start()] + new_imp + cleaned[k6_imp_match.end():]

    return cleaned


def run_smoke_test(script_path: str) -> Tuple[bool, str]:
    """
    Executes precise 2-second smoke test:
    `k6 run --duration 2s --vus 1 --no-thresholds <script>`
    If Docker is running, executes via grafana/k6 container in the perf-net network.
    Otherwise executes using local standalone k6.exe.
    Returns (success, output/error_message).
    """
    p = Path(script_path).resolve()
    if is_docker_running():
        run_dir = p.parent
        cmd = [
            "docker", "run", "--rm",
            "--network", "perf-net",
            "-v", f"{run_dir}:/scripts",
            "grafana/k6",
            "run", "--duration", "2s", "--vus", "1", "--no-thresholds",
            f"/scripts/{p.name}"
        ]
    else:
        k6_exe = get_k6_executable()
        cmd = [k6_exe, "run", "--duration", "2s", "--vus", "1", "--no-thresholds", str(p)]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15
        )
        output = proc.stdout + "\n" + proc.stderr
        if "ReferenceError" in output or "SyntaxError" in output or "TypeError" in output:
            return False, output
        if proc.returncode == 0:
            return True, output
        else:
            return False, output
    except Exception as e:
        return False, str(e)


def generate_k6_script_stream(
    intent_data: MergedIntentPayloadResponse,
    output_path: Path,
    error_feedback: Optional[str] = None
) -> str:
    """
    Calls coding model with few-shot template and streams tokens directly to output_path.
    """
    intent = intent_data.intent
    test_type = intent.test_type.lower()
    
    # Select matching template
    if test_type == "soak":
        reference_template = SOAK_TEMPLATE
    elif test_type == "stress":
        reference_template = STRESS_TEMPLATE
    else:
        reference_template = BASELINE_TEMPLATE

    # Extract primary endpoint details
    ep = intent.endpoints_involved[0]
    payloads = intent_data.synthetic_payloads.get(ep.path, [ep.payload_template or {"test": 1}])

    # Normalize target URL for local environment if Docker is absent
    target_url = get_effective_target_url(intent.target_url)

    err_limit_val = intent.success_criteria.max_error_rate
    if err_limit_val <= 0.0:
        err_limit_val = 0.01

    prompt = f"""You are generating an autonomous k6 load testing script in JavaScript.
Test Intent:
- Test Type: {intent.test_type}
- Target URL: {target_url}
- Virtual Users: {intent.virtual_users}
- Duration: {intent.duration}
- Primary Endpoint: {ep.path} (Method: {ep.method})
- Thresholds: p95 < {intent.success_criteria.p95_ms}ms, error_rate <= {err_limit_val}
- Stages: {[stage.model_dump() for stage in intent.ramp_pattern]}
- Sample Payloads: {payloads[:5]}

REFERENCE FEW-SHOT TEMPLATE FOR THIS TEST TYPE:
{reference_template}

INSTRUCTIONS:
1. Output ONLY executable JavaScript code compatible with k6.
2. Do NOT include markdown code fences, comments outside code, or prose.
3. Define the options export with either 'vus & duration' or 'stages', and 'thresholds'.
   For the http_req_failed threshold, use 'rate<={err_limit_val}' or 'rate<{err_limit_val}'. NEVER use 'rate<0' or 'rate<0.0'.
4. In default function, make HTTP requests to `${{BASE_URL}}{ep.path}` and use k6 checks.
5. Embed concrete values directly. NEVER write placeholders like __SAMPLE_PAYLOAD__ or __PAYLOADS_JSON__.
6. If the endpoint method is GET, do NOT send a request body. If POST, send JSON.stringify(payload).
"""

    if error_feedback:
        prompt += f"\n\nPREVIOUS GENERATION ERROR TO FIX:\nThe previous script failed smoke testing with error:\n{error_feedback}\nFix the script to resolve this error completely!"

    messages = [
        {"role": "system", "content": "You are an expert performance test engineer writing pure JavaScript k6 test scripts. Output only valid JS code, no explanations."},
        {"role": "user", "content": prompt}
    ]

    logger.info(f"Generating k6 script with coding model {MODEL_CODE} for run at {output_path}...")
    start_time = time.time()
    
    # Stream tokens directly to file
    full_text = []
    with open(output_path, "w", encoding="utf-8") as f:
        for delta in default_nim_client.stream_with_retry(
            model=MODEL_CODE,
            messages=messages,
            max_tokens=1500,
            temperature=0.1
        ):
            f.write(delta)
            f.flush()
            full_text.append(delta)

    raw_script = "".join(full_text)
    duration = time.time() - start_time
    _log_raw_call(MODEL_CODE, messages, raw_script, duration, status="stream_success")

    # Post-process file to strip markdown code blocks if the model wrapped it
    cleaned = clean_js_code(raw_script)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(cleaned)

    return cleaned


def build_and_validate_k6_script(
    intent_data: MergedIntentPayloadResponse,
    run_id: str
) -> Tuple[str, str]:
    """
    Generates k6 script, validates it with a 2-second smoke run.
    If validation fails, retries ONCE with error feedback.
    Returns (script_code, script_path).
    """
    run_dir = TEST_RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    script_path = run_dir / "test_script.js"

    # Attempt 1: Initial generation
    script_code = generate_k6_script_stream(intent_data, script_path)
    
    # Smoke run validation: k6 run --duration 2s --vus 1 <script>
    logger.info(f"Running 2s smoke run validation on {script_path}...")
    success, smoke_output = run_smoke_test(str(script_path))

    if success:
        logger.info("Smoke test passed on first attempt!")
        return script_code, str(script_path)

    # Attempt 2: Self-healing retry with error feedback
    logger.warning(f"Smoke test failed. Retrying once with error feedback...\n{smoke_output[:300]}")
    time.sleep(1.5) # Rate limit safety
    script_code = generate_k6_script_stream(intent_data, script_path, error_feedback=smoke_output)
    
    retry_success, retry_output = run_smoke_test(str(script_path))
    if retry_success:
        logger.info("Smoke test passed on self-healing retry attempt!")
        return script_code, str(script_path)

    logger.error(f"k6 script validation failed on retry:\n{retry_output}")
    raise RuntimeError(f"k6 script failed validation after retry:\n{retry_output}")
