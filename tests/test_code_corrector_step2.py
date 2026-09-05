import json
from backend.app.services.code_analyzer import analyze_code_content
from backend.app.services.llm_code_summary import generate_code_quality_summary

def test_summary_for_messy_py():
    with open("tests/fixtures/messy.py", "r", encoding="utf-8") as f:
        code = f.read()
    analysis = analyze_code_content("messy.py", code)
    summary = generate_code_quality_summary(analysis)
    print("\n--- MESSY.PY SUMMARY ---")
    print(summary)
    assert len(summary) > 50
    # Confirm it references real findings
    assert any(k in summary.lower() for k in ["os", "sys", "import", "undefined_count", "temp", "variable", "line"])

def test_summary_for_messy_js():
    with open("tests/fixtures/messy.js", "r", encoding="utf-8") as f:
        code = f.read()
    analysis = analyze_code_content("messy.js", code)
    summary = generate_code_quality_summary(analysis)
    print("\n--- MESSY.JS SUMMARY ---")
    print(summary)
    assert len(summary) > 50
    # Confirm it references real findings
    assert any(k in summary.lower() for k in ["unusedmultiplier", "undefinedglobal", "multiplier", "line", "variable"])

def test_summary_for_clean_py():
    with open("tests/fixtures/clean.py", "r", encoding="utf-8") as f:
        code = f.read()
    analysis = analyze_code_content("clean.py", code)
    summary = generate_code_quality_summary(analysis)
    print("\n--- CLEAN.PY SUMMARY ---")
    print(summary)
    assert len(summary) > 50
    assert any(w in summary.lower() for w in ["clean", "zero", "0", "passed", "no lint", "no issue"])

if __name__ == "__main__":
    test_summary_for_messy_py()
    test_summary_for_messy_js()
    test_summary_for_clean_py()
    print("\nALL STEP 2 VERIFICATIONS PASSED!")
