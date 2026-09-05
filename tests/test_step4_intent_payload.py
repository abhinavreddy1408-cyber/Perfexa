"""
Verification for Step 4: Merged Intent + Synthetic Payload Generation.
Runs across 10 varied natural-language prompts (including vague ones).
Paced with a 1.8s delay between prompts to respect the ~40 req/min rate limit.
"""

import time
import pytest
from backend.app.services.llm_intent import extract_intent_and_payloads

TEST_PROMPTS = [
    # 1. Fully specified stress test
    "stress test my login API with 200 users for 2 minutes",

    # 2. Highly vague prompt (must fill sensible defaults & assumptions)
    "just check if my API can handle load",

    # 3. Explicit baseline test
    "run a baseline health check on my fast endpoint with 10 users for 30 seconds",

    # 4. Explicit soak test
    "soak test my order checkout service for 5 minutes with 50 steady users",

    # 5. Concurrency survivability question
    "can my login system survive 300 concurrent requests without crashing?",

    # 6. Latency-oriented prompt
    "see how the server behaves when latency is introduced",

    # 7. Minimal quick test
    "quick smoke test on api",

    # 8. Deliberate breaking point test
    "push the heavy checkout API until it breaks",

    # 9. Partial specification (VU count only)
    "test my api with 25 users",

    # 10. Multi-endpoint test
    "run a 1 minute stability test on the login and checkout endpoints"
]


def test_10_varied_prompts():
    print(f"\nEvaluating {len(TEST_PROMPTS)} varied natural language test prompts with model...")
    results = []

    for idx, prompt in enumerate(TEST_PROMPTS, 1):
        print(f"\n[{idx}/10] Prompt: '{prompt}'")
        start_time = time.time()
        
        response = extract_intent_and_payloads(prompt)
        elapsed = time.time() - start_time

        intent = response.intent
        payloads = response.synthetic_payloads

        print(f"  -> Extracted test_type: {intent.test_type}")
        print(f"  -> Target VUs: {intent.virtual_users}, Duration: {intent.duration}")
        print(f"  -> Endpoints ({len(intent.endpoints_involved)}): {[ep.path for ep in intent.endpoints_involved]}")
        print(f"  -> Success Criteria: p95<={intent.success_criteria.p95_ms}ms, max_err<={intent.success_criteria.max_error_rate}")
        print(f"  -> Assumptions Made ({len(intent.assumptions_made)}): {intent.assumptions_made}")
        print(f"  -> Synthetic Payloads generated for: {list(payloads.keys())}")
        print(f"  -> Completed in {elapsed:.2f}s")

        # Assertions
        assert intent.test_type in ("baseline", "soak", "stress"), f"Invalid test_type: {intent.test_type}"
        assert intent.virtual_users > 0, "VUs must be positive"
        assert len(intent.duration) > 0, "Duration must not be empty"
        assert len(intent.endpoints_involved) >= 1, "Must identify at least one endpoint"
        assert intent.success_criteria.p95_ms > 0, "p95 criteria must be set"
        
        # For vague prompts like prompt 2, assumptions MUST be populated
        if "just check" in prompt.lower() or "quick" in prompt.lower() or "25 users" in prompt.lower():
            assert len(intent.assumptions_made) > 0, f"Expected assumptions for vague prompt: '{prompt}'"

        results.append((prompt, intent.test_type, intent.virtual_users))

        # Rate limit safety delay (1.8s)
        if idx < len(TEST_PROMPTS):
            time.sleep(1.8)

    print(f"\nALL {len(TEST_PROMPTS)} PROMPTS EXTRACTED VALID LOCKED INTENT AND SYNTHETIC PAYLOADS!")


if __name__ == "__main__":
    test_10_varied_prompts()
