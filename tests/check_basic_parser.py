"""
tests/check_basic_parser.py
===========================
Verification script for commands/basic_parser.py.
Evaluates >= 30 test cases across common phrasing, numbers, units, and categories,
plus negative cases that must safely return None without guessing.
Prints a PASS/FAIL line per case and a final PASS/FAIL.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from commands.basic_parser import ParsedCommand, parse_basic


# Positive test cases: (query, expected_tool, expected_arg_subset)
POSITIVE_CASES: List[Tuple[str, str, Dict[str, Any]]] = [
    # 1. Largest / biggest files
    ("largest files", "find_largest_files", {"limit": 10}),
    ("biggest files", "find_largest_files", {"limit": 10}),
    ("top 5 largest files", "find_largest_files", {"limit": 5}),
    ("top 20 biggest files", "find_largest_files", {"limit": 20}),
    ("10 biggest files", "find_largest_files", {"limit": 10}),
    ("show my 10 largest files", "find_largest_files", {"limit": 10}),

    # 2. What is taking up space / biggest folders
    ("what is taking up the most space", "get_largest_folders", {"limit": 5}),
    ("what is taking the most space?", "get_largest_folders", {"limit": 5}),
    ("what is taking up the most storage", "get_largest_folders", {"limit": 5}),
    ("biggest folders", "get_largest_folders", {"limit": 5}),
    ("largest folders", "get_largest_folders", {"limit": 5}),
    ("top 10 biggest folders", "get_largest_folders", {"limit": 10}),

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

    # 5. Duplicates
    ("find duplicates", "get_duplicate_summary", {"max_groups": 5}),
    ("duplicate files", "get_duplicate_summary", {"max_groups": 5}),
    ("find duplicate files", "get_duplicate_summary", {"max_groups": 5}),
    ("show duplicates", "get_duplicate_summary", {"max_groups": 5}),

    # 6. Old files (days, months, years)
    ("files older than 30 days", "filter_files", {"modified_before_days": 30}),
    ("files older than 6 months", "filter_files", {"modified_before_days": 180}),
    ("files older than 1 year", "filter_files", {"modified_before_days": 365}),
    ("files older than 2 years", "filter_files", {"modified_before_days": 730}),
    ("videos older than 1 year", "filter_files", {"category": "Videos", "modified_before_days": 365}),

    # 7. suggest_free_space ("I need N GB/MB free", "free up N GB")
    ("I need 5 GB free", "suggest_free_space", {"target_gb": 5.0}),
    ("free up 10 GB", "suggest_free_space", {"target_gb": 10.0}),
    ("I need 500 MB free", "suggest_free_space", {"target_gb": round(500.0 / 1024.0, 4)}),
    ("ways to free 2 GB", "suggest_free_space", {"target_gb": 2.0}),
    ("free up 1 GB", "suggest_free_space", {"target_gb": 1.0}),

    # 8. Drive usage / free space
    ("drive usage", "get_scan_overview", {}),
    ("free space on drive", "get_scan_overview", {}),
    ("scan overview", "get_scan_overview", {}),

    # 9. Category breakdown / file types
    ("file types", "get_category_breakdown", {}),
    ("category breakdown", "get_category_breakdown", {}),
    ("breakdown by category", "get_category_breakdown", {}),
]

# Negative cases: must return None
NEGATIVE_CASES: List[str] = [
    "delete my old files",
    "wipe everything",
    "clean up junk",
    "remove duplicates",
    "erase my drive",
    "move files to desktop",
    "unlink file.txt",
    "format c:",
    "destroy all temp files",
    "gibberish asdkjhwer123",
    "123456789",
    "hello there",
    "what is the weather today",
    "",
    "   ",
]


def run_checks() -> bool:
    print("=" * 65)
    print("RUNNING CHECK_BASIC_PARSER.PY")
    print(f"Total positive cases: {len(POSITIVE_CASES)}")
    print(f"Total negative cases: {len(NEGATIVE_CASES)}")
    print("=" * 65)

    all_passed = True

    # 1. Test positive cases
    print("\n--- POSITIVE TEST CASES ---")
    for idx, (query, exp_tool, exp_args) in enumerate(POSITIVE_CASES, 1):
        res: Optional[ParsedCommand] = parse_basic(query)
        case_passed = True
        err_msg = ""

        if res is None:
            case_passed = False
            err_msg = "Expected ParsedCommand, got None"
        elif not isinstance(res, ParsedCommand):
            case_passed = False
            err_msg = f"Expected instance of ParsedCommand, got {type(res).__name__}"
        elif res.tool != exp_tool:
            case_passed = False
            err_msg = f"Expected tool '{exp_tool}', got '{res.tool}'"
        else:
            for k, v in exp_args.items():
                if k not in res.args:
                    case_passed = False
                    err_msg = f"Missing argument '{k}' in result {res.args}"
                    break
                # Float tolerance for sizes
                if isinstance(v, float) and isinstance(res.args[k], float):
                    if abs(v - res.args[k]) > 0.01:
                        case_passed = False
                        err_msg = f"Arg '{k}' value {res.args[k]} != expected {v}"
                        break
                elif res.args[k] != v:
                    case_passed = False
                    err_msg = f"Arg '{k}' value {res.args[k]!r} != expected {v!r}"
                    break

        if case_passed:
            print(f"[{idx:02d}] PASS: \"{query}\" -> {res.tool}({res.args}) [rule: {res.rule}]")
        else:
            print(f"[{idx:02d}] FAIL: \"{query}\" -> {err_msg}")
            all_passed = False

    # 2. Test negative cases
    print("\n--- NEGATIVE TEST CASES (MUST RETURN NONE) ---")
    for idx, query in enumerate(NEGATIVE_CASES, 1):
        res = parse_basic(query)
        if res is None:
            print(f"[{idx:02d}] PASS (rejected): \"{query}\" -> None")
        else:
            print(f"[{idx:02d}] FAIL: \"{query}\" -> unexpectedly parsed as {res}")
            all_passed = False

    print("\n" + "=" * 65)
    if all_passed:
        print("OVERALL: ALL BASIC PARSER CHECKS PASSED (PASS)")
    else:
        print("OVERALL: SOME BASIC PARSER CHECKS FAILED (FAIL)")
    print("=" * 65)

    return all_passed


if __name__ == "__main__":
    success = run_checks()
    sys.exit(0 if success else 1)
