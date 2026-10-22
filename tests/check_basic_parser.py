"""
tests/check_basic_parser.py
===========================
Verification script for the deterministic rule-based query parser (commands/basic_parser.py).
Evaluates >= 25 test cases across common phrasing, numbers, units, and categories,
plus negative cases that must safely return None without guessing.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from commands.basic_parser import parse_basic
from commands.tools import validate_tool_call


TEST_CASES: List[Tuple[str, str, Dict[str, Any]]] = [
    # 1. Largest / biggest files
    ("largest files", "find_largest_files", {"limit": 10}),
    ("biggest files", "find_largest_files", {"limit": 10}),
    ("top 5 largest files", "find_largest_files", {"limit": 5}),
    ("top 20 biggest files", "find_largest_files", {"limit": 20}),
    ("10 biggest files", "find_largest_files", {"limit": 10}),

    # 2. What is taking up space
    ("what is taking up the most space", "get_largest_folders", {"limit": 5}),
    ("what is taking up the most storage", "get_largest_folders", {"limit": 5}),
    ("what is taking up all my space?", "get_largest_folders", {"limit": 5}),

    # 3. Category + size filters
    ("videos larger than 500 MB", "filter_files", {"category": "Videos", "min_size_mb": 500.0}),
    ("videos larger than 1 gb", "filter_files", {"category": "Videos", "min_size_mb": 1024.0}),
    ("images larger than 10 mb", "filter_files", {"category": "Images", "min_size_mb": 10.0}),
    ("documents bigger than 50 MB", "filter_files", {"category": "Documents", "min_size_mb": 50.0}),
    ("archives larger than 2 gb", "filter_files", {"category": "Archives", "min_size_mb": 2048.0}),
    ("installers larger than 100mb", "filter_files", {"category": "Installers", "min_size_mb": 100.0}),
    ("pdfs larger than 5 mb", "filter_files", {"category": "Documents", "extensions": ["pdf"], "min_size_mb": 5.0}),

    # 4. Generic size filters
    ("files larger than 100 MB", "filter_files", {"min_size_mb": 100.0}),
    ("files bigger than 2 GB", "filter_files", {"min_size_mb": 2048.0}),
    ("files larger than 500kb", "filter_files", {"min_size_mb": round(500.0 / 1024.0, 4)}),

    # 5. Duplicates
    ("find duplicates", "get_duplicate_summary", {"max_groups": 5}),
    ("duplicate files", "get_duplicate_summary", {"max_groups": 5}),
    ("find duplicate files", "get_duplicate_summary", {"max_groups": 5}),
    ("show duplicates", "get_duplicate_summary", {"max_groups": 5}),

    # 6. Access date filters
    ("files not opened in 30 days", "filter_files", {"not_accessed_for_days": 30}),
    ("files not opened in 6 months", "filter_files", {"not_accessed_for_days": 180}),
    ("files not opened in 1 year", "filter_files", {"not_accessed_for_days": 365}),
    ("files I haven't opened recently", "filter_files", {"not_accessed_for_days": 180}),
    ("haven't opened recently", "filter_files", {"not_accessed_for_days": 180}),

    # 7. Modification date filters
    ("PDFs modified last month", "filter_files", {"category": "Documents", "extensions": ["pdf"], "modified_after_days": 30}),
    ("PDFs modified last week", "filter_files", {"category": "Documents", "extensions": ["pdf"], "modified_after_days": 7}),
    ("PDFs modified in the last 14 days", "filter_files", {"category": "Documents", "extensions": ["pdf"], "modified_after_days": 14}),

    # 8. Free space suggestions
    ("ways to free 5 GB", "suggest_free_space", {"target_gb": 5.0}),
    ("free up 10 GB", "suggest_free_space", {"target_gb": 10.0}),
    ("Show ways to free 5 GB", "suggest_free_space", {"target_gb": 5.0}),

    # 9. Biggest folders
    ("biggest folders", "get_largest_folders", {"limit": 5}),
    ("largest folders", "get_largest_folders", {"limit": 5}),

    # 10. Overview / summary
    ("overview", "get_scan_overview", {}),
    ("summary", "get_scan_overview", {}),
    ("scan summary", "get_scan_overview", {}),
]

NEGATIVE_CASES: List[str] = [
    "delete all my duplicate files",
    "permanently remove old files",
    "move files to D:\\Backup",
    "rename document.pdf to new.pdf",
    "how do I make pizza?",
    "what is the capital of France?",
    "run antivirus scan",
    "send email with report",
    "open chrome browser",
]


def main() -> int:
    print(f"\n{'='*78}")
    print("OmniStore: Deterministic Basic Parser Test Suite")
    print(f"{'='*78}\n")

    passed = 0
    failed = 0

    print(f"{'QUERY':<42} | {'EXPECTED TOOL':<22} | {'RESULT'}")
    print(f"{'-'*42}-+-{'-'*22}-+-{'-'*8}")

    for query, exp_tool, exp_args in TEST_CASES:
        calls = parse_basic(query)
        if not calls:
            print(f"{query[:40]:<42} | {exp_tool:<22} | FAIL (got None)")
            failed += 1
            continue

        call = calls[0]
        # Validate that the generated tool call conforms to schema
        val_ok, cleaned, err = validate_tool_call(call.name, call.arguments)
        if not val_ok:
            print(f"{query[:40]:<42} | {exp_tool:<22} | FAIL (validation error: {err})")
            failed += 1
            continue

        match_tool = (call.name == exp_tool)
        match_args = True
        for k, v in exp_args.items():
            if isinstance(v, float):
                if abs(cleaned.get(k, 0) - v) > 0.01:
                    match_args = False
                    break
            elif cleaned.get(k) != v:
                match_args = False
                break

        if match_tool and match_args:
            print(f"{query[:40]:<42} | {exp_tool:<22} | PASS")
            passed += 1
        else:
            print(f"{query[:40]:<42} | {exp_tool:<22} | FAIL (got {call.name} {cleaned})")
            failed += 1

    print(f"\n--- Negative Cases (Expected None) ---")
    for neg in NEGATIVE_CASES:
        calls = parse_basic(neg)
        if calls is None:
            print(f"{neg[:40]:<42} | {'None':<22} | PASS")
            passed += 1
        else:
            print(f"{neg[:40]:<42} | {'None':<22} | FAIL (got {calls})")
            failed += 1

    print(f"\n{'='*78}")
    print(f"Results: {passed} PASSED, {failed} FAILED (Total: {passed + failed})")
    print(f"{'='*78}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
