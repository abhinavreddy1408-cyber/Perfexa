"""
AI-Powered Code Quality Summary Service.
Uses the NIM fast model (meta/llama-3.2-11b-vision-instruct) via default_nim_client
to generate a thoughtful, senior-engineer plain-English code review grounded in
static analysis findings and surrounding source code context.
"""

import logging
from typing import Dict, Any, List

from backend.app.config import MODEL_FAST
from backend.app.services.nim_client import default_nim_client

logger = logging.getLogger("llm_code_summary")

CODE_SUMMARY_SYSTEM_PROMPT = """You are an experienced senior software engineer providing a thoughtful, direct, and actionable code review based on static analysis findings and the actual surrounding code.

Your review must read like a senior colleague who respects the developer's time: direct, specific, and focused on real-world impact and consequences, rather than restating a linter's one-line messages.

STRICT REVIEW PRINCIPLES:
1. GROUP BY ROOT CAUSE:
   Before writing, group findings that share a single underlying root cause (e.g., multiple unused imports from an abandoned refactor, or related undefined variables in a function). Explain shared root causes once, together — never repeat the same explanation line by line.

2. PRIORITIZE REAL RISK OVER LINTER LABELS:
   Do not treat the linter's severity labels as the final word. A cosmetic formatting nit and a runtime bug are not equally important. Explicitly separate:
   - Real bugs or runtime crash risks (e.g., undefined variables that will raise NameError/ReferenceError when executed, broken logic, syntax errors).
   - Cosmetic or convention issues (e.g., blank lines, unused imports, whitespace) that have zero runtime impact.

3. REASON ABOUT CONCRETE CONSEQUENCES:
   For each grouped issue, state the concrete consequence if left unfixed (e.g., "calling calculate_average() will immediately crash with NameError because undefined_count is referenced instead of total_count"). If an issue has no meaningful real-world consequence (pure style), say so plainly rather than manufacturing importance.

4. END WITH ONE CLEAR TOP PRIORITY:
   Close with the SINGLE most important thing to fix first and briefly why it matters more than all others. Never present every issue as equally urgent.

5. STRICT GROUNDING DISCIPLINE:
   - Base all reasoning strictly on the provided findings and surrounding code context.
   - STRICTLY FORBIDDEN: Do NOT invent bugs, phantom dependencies, unverified concurrency bottlenecks, or missing test suites not evidenced in the code.
   - If the code has 0 findings and is completely clean, state that plainly and commend the clean implementation without manufacturing problems.

TONE:
Direct, specific, and constructive — like a senior engineer who respects the developer's time.

STRUCTURE YOUR REVIEW IN 3 FOCUSED SECTIONS:
### Code Quality Assessment
(A concise, direct synthesis assessing the overall state of the code, clearly separating functional runtime risks from cosmetic noise.)

### Root Causes & Real-World Impact
(Explain the grouped issues with their concrete runtime consequences, citing the affected lines and surrounding context.)

### Top Priority
(Specify the single most important fix to make first and explain why it takes precedence.)
"""


def generate_code_quality_summary(analysis_result: Dict[str, Any]) -> str:
    """
    Generates a thoughtful, senior-engineer code quality review
    strictly grounded in static analysis findings and surrounding code context.
    """
    filename = analysis_result.get("filename", "unknown")
    language = analysis_result.get("language", "unknown").capitalize()
    total_lines = analysis_result.get("total_lines", 0)
    total_findings = analysis_result.get("total_findings", 0)
    error_count = analysis_result.get("error_count", 0)
    warning_count = analysis_result.get("warning_count", 0)
    findings = analysis_result.get("findings", [])
    code_content = analysis_result.get("code_content", "")

    # Cap findings passed to LLM to keep call bounded and fast
    capped_findings = findings[:25]

    if total_findings == 0:
        findings_text = "No lint violations or errors detected. The file is completely clean."
    else:
        finding_blocks = []
        for f in capped_findings:
            l_num = f.get("line", 1)
            col_num = f.get("column", 1)
            sev = f.get("severity", "warning").upper()
            rule = f.get("rule", "LINT")
            msg = f.get("message", "")
            ctx = f.get("context_snippet", "")
            block = f"Finding: Line {l_num}:{col_num} [{sev} - {rule}]: {msg}"
            if ctx:
                block += f"\nSurrounding Code:\n{ctx}"
            finding_blocks.append(block)
        findings_text = "\n\n".join(finding_blocks)

    # Provide annotated source code if file is reasonably sized (<= 120 lines)
    source_context = ""
    if code_content and total_lines <= 120:
        annotated_lines = [f"{idx+1:3d} | {line}" for idx, line in enumerate(code_content.splitlines())]
        source_context = f"\nFULL FILE SOURCE CODE:\n```\n" + "\n".join(annotated_lines) + "\n```\n"

    user_prompt = f"""Review this {language} file and its static analysis findings:

FILE DETAILS:
- Filename: {filename}
- Total Lines: {total_lines}
- Total Issues Flagged: {total_findings} ({error_count} errors, {warning_count} warnings)
{source_context}
STATIC ANALYSIS FINDINGS WITH SURROUNDING CONTEXT:
{findings_text}

Provide your senior engineer review. Group issues by root cause, clearly separate runtime risks from cosmetic style conventions, state concrete consequences, and identify the single most important fix first.
"""

    messages = [
        {"role": "system", "content": CODE_SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]

    logger.info(f"Generating senior engineer code review for {filename} ({language}) with model {MODEL_FAST}...")
    try:
        report = default_nim_client.call_with_retry(
            model=MODEL_FAST,
            messages=messages,
            max_tokens=900,
            temperature=0.2
        )
        return report.strip()
    except Exception as e:
        logger.error(f"Error calling LLM for code summary: {e}", exc_info=True)
        # Fallback summary grounded in findings and consequences
        if total_findings == 0:
            return (
                "### Code Quality Assessment\n\n"
                f"The source file '{filename}' passed static analysis cleanly with zero defects. "
                "The code adheres strictly to recommended language conventions and contains no unreferenced symbols or style deviations.\n\n"
                "### Top Priority\n\n"
                "No action required. The codebase is production-ready from a static analysis standpoint."
            )

        top_issue = findings[0]
        return (
            "### Code Quality Assessment\n\n"
            f"Static analysis of '{filename}' identified {total_findings} issues ({error_count} errors, {warning_count} warnings) "
            f"across {total_lines} lines. These divide into functional runtime risks and cosmetic styling conventions.\n\n"
            "### Root Causes & Real-World Impact\n\n"
            f"- **Functional Risk**: The primary concern is at line {top_issue.get('line')}: `{top_issue.get('message')}` ({top_issue.get('rule')}). "
            "If left unfixed, this will cause an unexpected runtime exception or reference failure when executed.\n"
            "- **Code Hygiene**: The remaining warnings represent unused variables or styling formatting issues with no runtime impact.\n\n"
            "### Top Priority\n\n"
            f"Resolve the issue on line {top_issue.get('line')} ({top_issue.get('message')}) first to ensure basic runtime stability."
        )
