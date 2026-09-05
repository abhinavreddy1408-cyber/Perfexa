"""
Live verification script for confirmed NVIDIA NIM models:
1. mistralai/mistral-7b-instruct-v0.3
2. mistralai/codestral-22b-instruct-v0.1
"""

import os
import sys
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(".env", override=True)
api_key = os.getenv("NVIDIA_API_KEY", "").strip()

if not api_key or api_key == "your_nvidia_api_key_here":
    print("STATUS: MISSING_KEY")
    print("NVIDIA_API_KEY is not set in .env or environment.")
    sys.exit(2)

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key
)

models_to_test = [
    ("Fast Model", "mistralai/mistral-7b-instruct-v0.3"),
    ("Coding Model", "mistralai/codestral-22b-instruct-v0.1"),
]

results = {}

for label, model_id in models_to_test:
    print(f"\nTesting {label} ({model_id})...")
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "Say hello in 2 words."}],
            max_tokens=10,
            temperature=0.1
        )
        content = resp.choices[0].message.content.strip()
        print(f"SUCCESS (200 OK): Received response: '{content}'")
        results[model_id] = {"status": 200, "content": content}
    except Exception as e:
        print(f"FAILED: {e}")
        results[model_id] = {"status": "error", "error": str(e)}

all_passed = all(r.get("status") == 200 for r in results.values())
if all_passed:
    print("\nALL CONFIRMED MODELS RETURNED HTTP 200 SUCCESS!")
    sys.exit(0)
else:
    print("\nONE OR MORE MODELS FAILED.")
    sys.exit(1)
