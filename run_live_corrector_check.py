import httpx
import json

BASE_URL = "http://127.0.0.1:8000"

def test_file(fixture_path, mime_type):
    print(f"\n=======================================================")
    print(f"LIVE RUN: {fixture_path}")
    print(f"=======================================================")
    with open(fixture_path, "rb") as f:
        files = {"file": (fixture_path.split("/")[-1], f, mime_type)}
        data = {"run_ai_summary": "true"}
        response = httpx.post(f"{BASE_URL}/api/code-review", files=files, data=data, timeout=60.0)
    
    print(f"HTTP Status: {response.status_code}")
    result = response.json()
    print(f"Language: {result.get('language')}")
    print(f"Total Findings: {result.get('total_findings')} (Errors: {result.get('error_count')}, Warnings: {result.get('warning_count')})")
    print("\nFINDINGS:")
    for f in result.get("findings", []):
        print(f"  - Line {f['line']}:{f['column']} [{f['severity'].upper()} - {f['rule']}]: {f['message']}")
    
    print("\nACTUAL AI SUMMARY TEXT:")
    print("-" * 50)
    print(result.get("ai_summary"))
    print("-" * 50)

if __name__ == "__main__":
    test_file("tests/fixtures/messy.py", "text/x-python")
    test_file("tests/fixtures/messy.js", "text/javascript")
