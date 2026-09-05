import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000"

def test_empty_file():
    with open("tests/fixtures/empty.py", "rb") as f:
        res = httpx.post(f"{BASE_URL}/api/code-review", files={"file": ("empty.py", f, "text/x-python")})
    assert res.status_code == 400
    assert "empty" in res.json().get("detail", "").lower()
    print("\n[STEP 4 TEST PASSED] Empty file rejected with 400:", res.json())

def test_binary_file():
    with open("tests/fixtures/fake_image.py", "rb") as f:
        res = httpx.post(f"{BASE_URL}/api/code-review", files={"file": ("fake_image.py", f, "application/octet-stream")})
    assert res.status_code == 400
    assert "binary" in res.json().get("detail", "").lower()
    print("\n[STEP 4 TEST PASSED] Binary file rejected with 400:", res.json())

def test_unsupported_extension():
    with open("tests/fixtures/sample.rb", "rb") as f:
        res = httpx.post(f"{BASE_URL}/api/code-review", files={"file": ("sample.rb", f, "text/x-ruby")})
    assert res.status_code == 400
    assert "Language not yet supported — currently supports Python and JavaScript" in res.json().get("detail", "")
    print("\n[STEP 4 TEST PASSED] Unsupported language rejected with 400:", res.json())

def test_broken_python_syntax():
    with open("tests/fixtures/broken_syntax.py", "rb") as f:
        res = httpx.post(f"{BASE_URL}/api/code-review", files={"file": ("broken_syntax.py", f, "text/x-python")}, timeout=30.0)
    assert res.status_code == 200
    data = res.json()
    assert data["total_findings"] > 0
    assert data["error_count"] > 0
    assert any("syntax" in f["message"].lower() or "syntax" in f["rule"].lower() for f in data["findings"])
    print("\n[STEP 4 TEST PASSED] Broken Python syntax gracefully parsed:", [f["rule"] + ": " + f["message"] for f in data["findings"]])
    print("AI Summary for Broken Python:\n", data["ai_summary"])

def test_broken_javascript_syntax():
    with open("tests/fixtures/broken_syntax.js", "rb") as f:
        res = httpx.post(f"{BASE_URL}/api/code-review", files={"file": ("broken_syntax.js", f, "text/javascript")}, timeout=30.0)
    assert res.status_code == 200
    data = res.json()
    assert data["total_findings"] > 0
    assert data["error_count"] > 0
    assert any("parsing error" in f["message"].lower() or "syntax" in f["rule"].lower() for f in data["findings"])
    print("\n[STEP 4 TEST PASSED] Broken JS syntax gracefully parsed:", [f["rule"] + ": " + f["message"] for f in data["findings"]])
    print("AI Summary for Broken JS:\n", data["ai_summary"])

if __name__ == "__main__":
    test_empty_file()
    test_binary_file()
    test_unsupported_extension()
    test_broken_python_syntax()
    test_broken_javascript_syntax()
    print("\nALL STEP 4 ERROR-HANDLING TESTS PASSED!")
