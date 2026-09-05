import os
from backend.app.services.code_analyzer import analyze_code_content
from backend.app.services.llm_code_summary import generate_code_quality_summary

def run_evaluation():
    # 1. Messy Python
    with open("tests/fixtures/messy.py", "r", encoding="utf-8") as f:
        py_code = f.read()
    py_analysis = analyze_code_content("messy.py", py_code)
    py_summary = generate_code_quality_summary(py_analysis)
    
    print("=" * 70)
    print("ENHANCED PYTHON REVIEW (messy.py):")
    print("=" * 70)
    print(py_summary)
    print("\n")

    # 2. Messy JS
    with open("tests/fixtures/messy.js", "r", encoding="utf-8") as f:
        js_code = f.read()
    js_analysis = analyze_code_content("messy.js", js_code)
    js_summary = generate_code_quality_summary(js_analysis)

    print("=" * 70)
    print("ENHANCED JAVASCRIPT REVIEW (messy.js):")
    print("=" * 70)
    print(js_summary)
    print("=" * 70)

if __name__ == "__main__":
    run_evaluation()
