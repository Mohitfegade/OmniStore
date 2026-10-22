"""
tests/check_gemma.py
====================
End-to-end verification test for Gemma 4 via local Ollama.

Checks:
1. Provider health check (skips gracefully with clear instructions if Ollama is offline).
2. Runs 3 real requests against the demo scan:
   - "What is taking up the most space?"
   - "Find duplicate files"
   - "Show videos larger than 10 MB"
3. Prints tool call(s) chosen, results summary, explanation, latency, and payload bytes.
4. Fact-checking assertions:
   - Verifies that file names mentioned in the explanation are present in the tool results.
   - Verifies that numbers/sizes mentioned in the explanation originate from tool results or query.
5. Asserts the local AI audit log was written to %LOCALAPPDATA%\\OmniStore\\ai_audit_log.jsonl.
6. Prints PASS or FAIL.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from commands.agent import handle_user_request
from engine.duplicates import find_duplicates
from engine.scanner import scan_folder
from gemma.config import load_settings
from gemma.ollama_provider import OllamaProvider
from gemma.privacy import AuditLog


def extract_facts_from_tool_runs(tool_runs) -> tuple[set[str], set[str]]:
    """
    Extract all recognized file names and numbers/sizes from tool data and summaries.
    """
    known_filenames: set[str] = set()
    known_numbers: set[str] = set()

    def visit(val):
        if isinstance(val, dict):
            for k, v in val.items():
                if k in ("name", "filename") and isinstance(v, str):
                    known_filenames.add(v.lower().strip())
                if isinstance(v, str):
                    for s_num in re.findall(r"\b\d+(?:[\.,]\d+)?\b", v):
                        known_numbers.add(s_num)
                if isinstance(v, (int, float)):
                    known_numbers.add(str(v))
                    if isinstance(v, int):
                        # Add with comma separators too (e.g. 20,971,520)
                        known_numbers.add(f"{v:,}")
                visit(v)
        elif isinstance(val, list):
            for item in val:
                visit(item)
        elif isinstance(val, (int, float)):
            known_numbers.add(str(val))
            if isinstance(val, int):
                known_numbers.add(f"{val:,}")
        elif isinstance(val, str):
            for s_num in re.findall(r"\b\d+(?:[\.,]\d+)?\b", val):
                known_numbers.add(s_num)

    for tr in tool_runs:
        visit(tr.data)
        visit(tr.summary)

    return known_filenames, known_numbers


def verify_explanation_facts(query: str, explanation: str, tool_runs) -> None:
    """
    Assert that file names and numbers in the explanation are backed by the tool results.
    """
    known_filenames, known_numbers = extract_facts_from_tool_runs(tool_runs)

    # Allow numbers from the user query itself (e.g. "10" from "10 MB")
    query_numbers = set(re.findall(r"\b\d+(?:[\.,]\d+)?\b", query))
    known_numbers.update(query_numbers)
    # Common small linguistic integers (e.g. 1st, 2nd, group 1, 2)
    known_numbers.update({"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "1", "2", "3"})

    # Check 1: File names in explanation (tokens with common file extensions)
    file_pattern = re.compile(r"\b[a-zA-Z0-9_\-\.\(\)\s]+\.(?:mp4|mkv|pdf|txt|zip|tar|gz|docx|csv)\b", re.IGNORECASE)
    # Also strip markdown backticks and formatting
    cleaned_text = explanation.replace("`", " ").replace("*", " ").replace("\\_", "_")
    found_filenames = file_pattern.findall(cleaned_text)

    for fn in found_filenames:
        fn_clean = fn.strip().lower()
        # Find if fn_clean is in any known filename or vice-versa
        matched = any(fn_clean in kf or kf in fn_clean for kf in known_filenames)
        assert matched, f"Hallucinated file name detected in explanation: '{fn}' not in tool results: {known_filenames}"

    # Check 2: Numbers/sizes mentioned in explanation
    # Match numbers (like 157,286,400 or 50.1 or 3)
    found_numbers = re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", cleaned_text)
    for num_str in found_numbers:
        # Strip commas for comparison
        raw_num = num_str.replace(",", "")
        # Skip years like 2025, 2026 or small ranks
        if raw_num in ("2025", "2026", "2024", "1", "2", "3", "4", "5", "0"):
            continue
        # Verify number exists in known numbers
        matched = (
            num_str in known_numbers
            or raw_num in known_numbers
            or any(raw_num in kn.replace(",", "") for kn in known_numbers)
        )
        # Note: allow if close float or percentage
        if not matched:
            try:
                flt = float(raw_num)
                matched = any(abs(float(kn.replace(",", "")) - flt) < 0.2 for kn in known_numbers if kn.replace(",", "").replace(".", "").isdigit())
            except ValueError:
                pass

        assert matched, f"Unverified number detected in explanation: '{num_str}' not found in tool results or query."


def main() -> None:
    print("=" * 65)
    print("OMNISTORE — GEMMA 4 VERIFICATION TEST")
    print("=" * 65)

    settings = load_settings()
    provider = OllamaProvider(settings)

    print(f"\n[1/4] Checking Ollama health ({settings.host}, model: {settings.model})...")
    status = provider.health()
    if not status.ok:
        print(f"\n[SKIP] Ollama is not running or model not found: {status.message}")
        print("To run this test:")
        print("  1. Start Ollama (https://ollama.com)")
        print(f"  2. Pull the model: ollama pull {settings.model}")
        print("\nTEST RESULT: SKIP (Ollama not running)")
        sys.exit(0)

    print(f"  [OK] Ollama connected (latency: {status.latency_ms:.1f} ms, models: {status.models_available})")

    # Locate demo scan directory
    user_home = Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))
    demo_dir = user_home / "OmniStore_Demo"
    if not demo_dir.is_dir():
        print(f"\n[ERROR] Demo directory not found at {demo_dir}.")
        print("Please run `python tests/make_demo_data.py` first.")
        print("\nTEST RESULT: FAIL")
        sys.exit(1)

    print(f"\n[2/4] Scanning demo directory: {demo_dir} ...")
    scan_res = scan_folder(str(demo_dir))
    dup_res = find_duplicates(scan_res)
    print(f"  [OK] Scan completed: {len(scan_res.files)} files, {len(dup_res.groups)} duplicate groups.")

    queries = [
        "What is taking up the most space?",
        "Find duplicate files",
        "Show videos larger than 10 MB",
    ]

    print("\n[3/4] Running 3 real requests through Gemma 4...")

    for i, query in enumerate(queries, 1):
        print("\n" + "-" * 60)
        print(f"TEST QUERY {i}: \"{query}\"")
        print("-" * 60)

        response = handle_user_request(
            text=query,
            scan_result=scan_res,
            duplicate_result=dup_res,
            provider=provider,
            settings=settings,
        )

        assert response.ok, f"Agent response failed: {response.error}"
        assert response.mode == "gemma", f"Expected mode 'gemma', got '{response.mode}'"
        assert len(response.tool_runs) >= 1, "Expected at least 1 tool run"

        print(f"Mode          : {response.mode}")
        print(f"Duration      : {response.duration_ms:.1f} ms")
        print(f"Bytes Sent    : {response.payload_bytes_sent} B")
        print(f"Tools Chosen  : {[t.name for t in response.tool_runs]}")

        for tr in response.tool_runs:
            print(f"  - Tool: {tr.name}")
            summary_json = json.dumps(tr.summary, ensure_ascii=False)
            print(f"    Summary: {summary_json[:120]}…")

        print(f"\nExplanation:\n{response.explanation}\n")

        # Fact checking assertion
        verify_explanation_facts(query, response.explanation, response.tool_runs)
        print("  [OK] Fact-check passed: All file names and numbers verified against tool results.")

    print("\n[4/4] Verifying AI Audit Log...")
    recent_logs = AuditLog.read_recent(10)
    assert len(recent_logs) >= 3, f"Expected at least 3 audit entries, found {len(recent_logs)}"
    latest = recent_logs[0]
    assert "model" in latest and "tool_names" in latest and "sanitized_payload" in latest
    print(f"  [OK] Audit log verified ({len(recent_logs)} recent entries found).")
    print(f"       Latest entry: model={latest['model']}, tools={latest['tool_names']}, bytes={latest['payload_bytes']}")

    print("\n" + "=" * 65)
    print("ALL GEMMA 4 VERIFICATIONS PASSED: PASS")
    print("=" * 65)


if __name__ == "__main__":
    main()
