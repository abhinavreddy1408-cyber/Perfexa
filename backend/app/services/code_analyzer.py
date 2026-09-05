"""
Static analysis engine for Codebase Corrector.
Runs Flake8 for Python and ESLint for JavaScript against uploaded source code.
Returns normalized structured findings: line, column, severity, rule, message, and line snippet.
"""

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Dict, Any, List, Optional

from backend.app.config import BASE_DIR

logger = logging.getLogger("code_analyzer")

# Supported language extensions
SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
}

TEMP_CODE_DIR = BASE_DIR / ".temp_code"
TEMP_CODE_DIR.mkdir(parents=True, exist_ok=True)


class UnsupportedLanguageError(ValueError):
    """Raised when file extension is not supported."""
    pass


class InvalidFileError(ValueError):
    """Raised when file is binary, empty, or unparseable."""
    pass


def detect_language(filename: str) -> str:
    """
    Detects language strictly from file extension.
    Raises UnsupportedLanguageError if not .py or .js.
    """
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedLanguageError(
            "Language not yet supported — currently supports Python and JavaScript"
        )
    return SUPPORTED_EXTENSIONS[ext]


def _get_line_snippet(lines: List[str], line_no: int) -> str:
    """Safely retrieves line text (1-indexed) from code lines."""
    if 1 <= line_no <= len(lines):
        return lines[line_no - 1].strip()
    return ""


def _get_context_window(lines: List[str], line_no: int, window: int = 3) -> str:
    """Returns surrounding code lines around line_no (1-indexed) with line numbers and a pointer."""
    start = max(1, line_no - window)
    end = min(len(lines), line_no + window)
    snippet_lines = []
    for i in range(start, end + 1):
        prefix = ">" if i == line_no else " "
        line_text = lines[i - 1] if 0 <= i - 1 < len(lines) else ""
        snippet_lines.append(f"{prefix} {i:3d} | {line_text}")
    return "\n".join(snippet_lines)


def _finding_location(filename: str, line_no: int, column: int) -> str:
    """Builds a user-facing source location for an uploaded file."""
    safe_filename = Path(filename).name or "uploaded file"
    return f"{safe_filename}:{line_no}:{column}"


def _build_finding(
    *,
    filename: str,
    lines: List[str],
    row: int,
    col: int,
    severity: str,
    rule: str,
    message: str,
) -> Dict[str, Any]:
    """Normalizes analyzer findings with explicit file location and source context."""
    return {
        "filename": Path(filename).name,
        "line": row,
        "column": col,
        "location": _finding_location(filename, row, col),
        "severity": severity,
        "rule": rule,
        "message": message,
        "line_content": _get_line_snippet(lines, row),
        "context_snippet": _get_context_window(lines, row, window=3),
    }


def run_python_analysis(code_content: str, filename: str) -> Dict[str, Any]:
    """
    Executes Flake8 against python source code via temporary file.
    Parses custom delimited format '%(row)d:::%(col)d:::%(code)s:::%(text)s'.
    """
    lines = code_content.splitlines()
    total_lines = len(lines)
    findings: List[Dict[str, Any]] = []

    # Write code to temp file inside project .temp_code
    with tempfile.NamedTemporaryFile(
        dir=TEMP_CODE_DIR,
        mode="w",
        suffix=".py",
        delete=False,
        encoding="utf-8"
    ) as tmp:
        tmp.write(code_content)
        tmp_path = tmp.name

    try:
        # Run flake8 using current python environment
        cmd = [
            sys.executable,
            "-m",
            "flake8",
            "--format=%(row)d:::%(col)d:::%(code)s:::%(text)s",
            "--max-line-length=100",
            tmp_path
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
            timeout=15
        )

        raw_output = res.stdout
        for line in raw_output.splitlines():
            line = line.strip()
            if not line or ":::" not in line:
                continue
            parts = line.split(":::", 3)
            if len(parts) != 4:
                continue

            try:
                row = int(parts[0])
                col = int(parts[1])
                code = parts[2].strip()
                msg = parts[3].strip()

                # Determine severity
                if code.startswith(("E9", "F")) or "syntaxerror" in msg.lower():
                    severity = "error"
                elif code.startswith("W"):
                    severity = "warning"
                elif code.startswith("E"):
                    severity = "warning"
                else:
                    severity = "info"

                findings.append(_build_finding(
                    filename=filename,
                    lines=lines,
                    row=row,
                    col=col,
                    severity=severity,
                    rule=code,
                    message=msg,
                ))
            except Exception as parse_err:
                logger.warning(f"Error parsing flake8 output line '{line}': {parse_err}")

    except subprocess.TimeoutExpired:
        logger.error("Flake8 execution timed out")
        findings.append(_build_finding(
            filename=filename,
            lines=lines,
            row=1,
            col=1,
            severity="error",
            rule="TIMEOUT",
            message="Static analysis execution timed out",
        ))
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception as e:
            logger.warning(f"Could not delete temp file {tmp_path}: {e}")

    # Sort findings by line number then column
    findings.sort(key=lambda x: (x["line"], x["column"]))

    error_count = sum(1 for f in findings if f["severity"] == "error")
    warning_count = sum(1 for f in findings if f["severity"] == "warning")
    info_count = sum(1 for f in findings if f["severity"] not in ("error", "warning"))

    return {
        "filename": filename,
        "language": "python",
        "total_lines": total_lines,
        "total_findings": len(findings),
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "findings": findings,
        "code_content": code_content
    }


def run_javascript_analysis(code_content: str, filename: str) -> Dict[str, Any]:
    """
    Executes ESLint against javascript source code via temporary file.
    Parses ESLint JSON output format.
    """
    lines = code_content.splitlines()
    total_lines = len(lines)
    findings: List[Dict[str, Any]] = []

    # Write code to temp file inside project .temp_code
    with tempfile.NamedTemporaryFile(
        dir=TEMP_CODE_DIR,
        mode="w",
        suffix=".js",
        delete=False,
        encoding="utf-8"
    ) as tmp:
        tmp.write(code_content)
        tmp_path = tmp.name

    try:
        eslint_bin = BASE_DIR / "node_modules" / "eslint" / "bin" / "eslint.js"
        config_path = BASE_DIR / "eslint.config.mjs"

        if eslint_bin.exists():
            cmd = [
                "node",
                str(eslint_bin),
                "--config",
                str(config_path),
                "--format",
                "json",
                tmp_path
            ]
        else:
            cmd = [
                "npx",
                "eslint",
                "--config",
                str(config_path),
                "--format",
                "json",
                tmp_path
            ]

        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
            timeout=15,
            shell=True if sys.platform == "win32" and not eslint_bin.exists() else False
        )

        stdout_text = res.stdout.strip()
        if stdout_text:
            try:
                parsed = json.loads(stdout_text)
                if isinstance(parsed, list) and len(parsed) > 0:
                    file_result = parsed[0]
                    for msg in file_result.get("messages", []):
                        row = msg.get("line", 1)
                        col = msg.get("column", 1)
                        rule = msg.get("ruleId") or ("SyntaxError" if msg.get("fatal") else "lint-error")
                        text = msg.get("message", "Lint rule violation")
                        is_fatal = bool(msg.get("fatal"))
                        raw_sev = msg.get("severity", 1)

                        severity = "error" if (is_fatal or raw_sev == 2) else "warning"

                        findings.append(_build_finding(
                            filename=filename,
                            lines=lines,
                            row=row,
                            col=col,
                            severity=severity,
                            rule=rule,
                            message=text,
                        ))
            except json.JSONDecodeError as jerr:
                logger.error(f"Failed to parse ESLint JSON output: {jerr}\nRaw stdout: {stdout_text}")
                err_text = res.stderr.strip() or stdout_text
                findings.append(_build_finding(
                    filename=filename,
                    lines=lines,
                    row=1,
                    col=1,
                    severity="error",
                    rule="ESLINT_ERROR",
                    message=err_text[:200],
                ))

    except subprocess.TimeoutExpired:
        logger.error("ESLint execution timed out")
        findings.append(_build_finding(
            filename=filename,
            lines=lines,
            row=1,
            col=1,
            severity="error",
            rule="TIMEOUT",
            message="Static analysis execution timed out",
        ))
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception as e:
            logger.warning(f"Could not delete temp file {tmp_path}: {e}")

    # Sort findings by line number then column
    findings.sort(key=lambda x: (x["line"], x["column"]))

    error_count = sum(1 for f in findings if f["severity"] == "error")
    warning_count = sum(1 for f in findings if f["severity"] == "warning")
    info_count = sum(1 for f in findings if f["severity"] not in ("error", "warning"))

    return {
        "filename": filename,
        "language": "javascript",
        "total_lines": total_lines,
        "total_findings": len(findings),
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "findings": findings,
        "code_content": code_content
    }


def analyze_code_content(filename: str, code_content: str) -> Dict[str, Any]:
    """
    Validates input and runs the corresponding linter.
    Raises UnsupportedLanguageError or InvalidFileError.
    """
    language = detect_language(filename)

    if not code_content or not code_content.strip():
        raise InvalidFileError("Uploaded file is empty.")

    # Guard against binary files
    if "\x00" in code_content:
        raise InvalidFileError("Uploaded file contains binary data or invalid text encoding.")

    if language == "python":
        return run_python_analysis(code_content, filename)
    elif language == "javascript":
        return run_javascript_analysis(code_content, filename)
    else:
        raise UnsupportedLanguageError(
            "Language not yet supported — currently supports Python and JavaScript"
        )
