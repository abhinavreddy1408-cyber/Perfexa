import pytest
from backend.app.services.code_analyzer import (
    analyze_code_content,
    detect_language,
    UnsupportedLanguageError,
    InvalidFileError
)

def test_python_messy_analysis():
    py_code = """import os
import sys

def calculate_sum(a,b):
    unused_var = 100
    return a + undefined_variable

print(calculate_sum(1,2))
"""
    result = analyze_code_content("messy.py", py_code)
    assert result["language"] == "python"
    assert result["total_findings"] > 0
    assert result["error_count"] > 0
    assert all(f["filename"] == "messy.py" for f in result["findings"])
    assert all(f["location"].startswith("messy.py:") for f in result["findings"])
    assert any(">" in f["context_snippet"] for f in result["findings"])
    rules = [f["rule"] for f in result["findings"]]
    # Should catch unused imports (F401) or undefined variable (F821)
    assert any(r.startswith("F") or r.startswith("E") for r in rules)
    print("\n[PYTHON TEST PASSED] Found:", [f["rule"] + ": " + f["message"] for f in result["findings"]])

def test_javascript_messy_analysis():
    js_code = """function compute(a, b) {
    const unusedLocal = 42;
    return a + undeclaredGlobalVariable;
}
"""
    result = analyze_code_content("messy.js", js_code)
    assert result["language"] == "javascript"
    assert result["total_findings"] > 0
    assert result["error_count"] > 0
    assert all(f["filename"] == "messy.js" for f in result["findings"])
    assert all(f["location"].startswith("messy.js:") for f in result["findings"])
    assert any(">" in f["context_snippet"] for f in result["findings"])
    rules = [f["rule"] for f in result["findings"]]
    # Should catch no-unused-vars or no-undef
    assert any(r in ("no-unused-vars", "no-undef") for r in rules)
    print("\n[JS TEST PASSED] Found:", [f["rule"] + ": " + f["message"] for f in result["findings"]])

def test_unsupported_language():
    try:
        analyze_code_content("script.rb", "puts 'hello'")
        assert False, "Should have raised UnsupportedLanguageError"
    except UnsupportedLanguageError as e:
        assert "Language not yet supported — currently supports Python and JavaScript" in str(e)
        print("\n[UNSUPPORTED EXTENSION PASSED]:", str(e))

def test_empty_file():
    try:
        analyze_code_content("empty.py", "   \n\t  ")
        assert False, "Should have raised InvalidFileError"
    except InvalidFileError as e:
        assert "empty" in str(e).lower()
        print("\n[EMPTY FILE PASSED]:", str(e))

def test_binary_file():
    try:
        analyze_code_content("fake.py", "abc\x00def")
        assert False, "Should have raised InvalidFileError"
    except InvalidFileError as e:
        assert "binary" in str(e).lower()
        print("\n[BINARY FILE PASSED]:", str(e))

if __name__ == "__main__":
    test_python_messy_analysis()
    test_javascript_messy_analysis()
    test_unsupported_language()
    test_empty_file()
    test_binary_file()
