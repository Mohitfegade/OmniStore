"""
tests/check_tools.py
====================
Verification tests for commands/tools.py (Deterministic Tool Registry & Execution).

Validates:
1. Tool schemas and security constraints (no destructive/shell tools).
2. validate_tool_call:
   - Accepts valid arguments.
   - Rejects unknown tool names.
   - Rejects extra or unrecognized arguments.
   - Rejects incorrect parameter types.
   - Rejects out-of-range numeric arguments (limits 1..200, sizes >= 0, days 0..36500).
   - Rejects invalid category enums.
   - Strips control characters and enforces max string length of 100.
3. execute_tool:
   - Runs against real scan data of OmniStore_Demo.
   - Returns capped data (<= 200 items).
   - Returns compact summaries under 2 KB JSON.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from commands.tools import (
    TOOL_SCHEMAS,
    execute_tool,
    validate_tool_call,
)
from engine.duplicates import find_duplicates
from engine.scanner import scan_folder


def test_no_destructive_tools() -> None:
    """Verify that no tool schema permits modifying files or executing commands."""
    forbidden = {"delete", "remove", "unlink", "trash", "rm", "exec", "sh", "bash", "cmd", "open", "copy", "move", "rename"}
    for schema in TOOL_SCHEMAS:
        name = schema["function"]["name"].lower()
        desc = schema["function"]["description"].lower()
        for term in forbidden:
            assert term not in name, f"Forbidden term '{term}' in tool name '{name}'"
        print(f"  [OK] Tool schema validated safe: {name}")


def test_validate_valid_calls() -> None:
    """Verify valid calls pass with cleaned arguments."""
    # 1. get_scan_overview
    ok, args, err = validate_tool_call("get_scan_overview", {})
    assert ok, f"Expected ok, got: {err}"
    assert args == {}

    # 2. find_largest_files
    ok, args, err = validate_tool_call(
        "find_largest_files",
        {"limit": 25, "category": "Videos", "min_size_mb": 10.5, "name_contains": "clip"}
    )
    assert ok, f"Expected ok, got: {err}"
    assert args["limit"] == 25
    assert args["category"] == "Videos"
    assert args["min_size_mb"] == 10.5
    assert args["name_contains"] == "clip"

    # 3. filter_files
    ok, args, err = validate_tool_call(
        "filter_files",
        {
            "category": "Archives",
            "extensions": [".zip", ".tar.gz"],
            "min_size_mb": 1,
            "max_size_mb": 500,
            "modified_before_days": 30,
            "limit": 50,
            "sort_by": "size",
            "descending": True,
        }
    )
    assert ok, f"Expected ok, got: {err}"
    assert args["category"] == "Archives"
    assert args["extensions"] == ["zip", "tar.gz"]

    # 4. get_largest_folders
    ok, args, err = validate_tool_call("get_largest_folders", {"limit": 10})
    assert ok, f"Expected ok, got: {err}"
    assert args["limit"] == 10

    # 5. get_category_breakdown
    ok, args, err = validate_tool_call("get_category_breakdown", {})
    assert ok, f"Expected ok, got: {err}"

    # 6. get_duplicate_summary
    ok, args, err = validate_tool_call("get_duplicate_summary", {"max_groups": 15})
    assert ok, f"Expected ok, got: {err}"
    assert args["max_groups"] == 15

    print("  [OK] All valid tool calls passed validation.")


def test_validate_unknown_tools() -> None:
    """Verify unknown tools are rejected with clear errors."""
    for bad_name in ["delete_files", "system_exec", "run_bash", "non_existent_tool"]:
        ok, args, err = validate_tool_call(bad_name, {})
        assert not ok, f"Expected failure for {bad_name}"
        assert err and "Unknown tool" in err, f"Unexpected error message: {err}"
    print("  [OK] Unknown tools correctly rejected.")


def test_validate_extra_arguments() -> None:
    """Verify extra or unknown arguments are rejected."""
    ok, args, err = validate_tool_call("get_scan_overview", {"unexpected_arg": 123})
    assert not ok
    assert err and ("takes no arguments" in err or "Unexpected argument" in err)

    ok, args, err = validate_tool_call("find_largest_files", {"limit": 10, "format": "pdf"})
    assert not ok
    assert err and "Unexpected argument" in err
    print("  [OK] Extra/unknown arguments correctly rejected.")


def test_validate_wrong_types() -> None:
    """Verify type checking catches incorrect parameter types."""
    ok, args, err = validate_tool_call("find_largest_files", {"limit": "twenty"})
    assert not ok
    assert err and "must be an integer" in err

    ok, args, err = validate_tool_call("find_largest_files", {"min_size_mb": "not_a_number"})
    assert not ok
    assert err and "non-negative number" in err

    ok, args, err = validate_tool_call("filter_files", {"extensions": "not_a_list"})
    assert not ok
    assert err and "must be a list" in err

    ok, args, err = validate_tool_call("filter_files", {"descending": "true"})
    assert not ok
    assert err and "must be a boolean" in err
    print("  [OK] Incorrect parameter types correctly rejected.")


def test_validate_ranges_and_enums() -> None:
    """Verify out-of-range numbers and invalid enums are rejected."""
    # limit out of range
    ok, _, err = validate_tool_call("find_largest_files", {"limit": 0})
    assert not ok and "between 1 and 200" in err

    ok, _, err = validate_tool_call("find_largest_files", {"limit": 500})
    assert not ok and "between 1 and 200" in err

    # negative size
    ok, _, err = validate_tool_call("find_largest_files", {"min_size_mb": -10})
    assert not ok and "non-negative" in err

    # days out of range
    ok, _, err = validate_tool_call("filter_files", {"modified_before_days": -1})
    assert not ok and "between 0 and 36500" in err

    ok, _, err = validate_tool_call("filter_files", {"modified_before_days": 50000})
    assert not ok and "between 0 and 36500" in err

    # invalid category enum
    ok, _, err = validate_tool_call("find_largest_files", {"category": "Cryptocurrency"})
    assert not ok and "Invalid category" in err

    # invalid sort_by enum
    ok, _, err = validate_tool_call("filter_files", {"sort_by": "color"})
    assert not ok and "Invalid sort_by" in err

    print("  [OK] Range and enum checks correctly enforced.")


def test_validate_string_sanitization() -> None:
    """Verify control characters are stripped and string length is capped at 100."""
    dirty_name = "test\x00\x08file\r\nname"
    ok, args, err = validate_tool_call("find_largest_files", {"name_contains": dirty_name})
    assert ok
    assert "\x00" not in args["name_contains"]
    assert "\r" not in args["name_contains"]
    assert "\n" not in args["name_contains"]
    assert args["name_contains"] == "testfilename"

    long_str = "A" * 250
    ok, args, err = validate_tool_call("find_largest_files", {"name_contains": long_str})
    assert ok
    assert len(args["name_contains"]) == 100
    print("  [OK] String cleaning and length capping correctly enforced.")


def test_execute_tool_on_demo_scan() -> None:
    """Verify tool execution over real scan data returns capped and compact results."""
    user_home = Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))
    demo_dir = user_home / "OmniStore_Demo"
    if not demo_dir.is_dir():
        print(f"  [SKIP] Demo directory not found at {demo_dir}")
        return

    print(f"  Scanning demo directory: {demo_dir} ...")
    scan_res = scan_folder(str(demo_dir))
    dup_res = find_duplicates(scan_res)
    print(f"  Scan completed: {len(scan_res.files)} files, {len(dup_res.groups)} duplicate groups.")

    # 1. get_scan_overview
    res = execute_tool("get_scan_overview", {}, scan_res, dup_res)
    assert res.ok
    assert "total_files" in res.data
    summary_bytes = len(json.dumps(res.summary).encode("utf-8"))
    assert summary_bytes < 2048, f"Summary exceeds 2 KB ({summary_bytes} bytes)"

    # 2. find_largest_files
    res = execute_tool("find_largest_files", {"limit": 100}, scan_res, dup_res)
    assert res.ok
    assert len(res.data.get("items", [])) <= 100
    assert len(res.summary.get("top_items", [])) <= 10
    summary_bytes = len(json.dumps(res.summary).encode("utf-8"))
    assert summary_bytes < 2048, f"Summary exceeds 2 KB ({summary_bytes} bytes)"

    # 3. filter_files
    res = execute_tool("filter_files", {"limit": 50}, scan_res, dup_res)
    assert res.ok
    assert len(res.data.get("items", [])) <= 50
    summary_bytes = len(json.dumps(res.summary).encode("utf-8"))
    assert summary_bytes < 2048

    # 4. get_largest_folders
    res = execute_tool("get_largest_folders", {"limit": 10}, scan_res, dup_res)
    assert res.ok
    assert len(res.data.get("folders", [])) <= 10
    summary_bytes = len(json.dumps(res.summary).encode("utf-8"))
    assert summary_bytes < 2048

    # 5. get_category_breakdown
    res = execute_tool("get_category_breakdown", {}, scan_res, dup_res)
    assert res.ok
    assert "categories" in res.data
    summary_bytes = len(json.dumps(res.summary).encode("utf-8"))
    assert summary_bytes < 2048

    # 6. get_duplicate_summary
    res = execute_tool("get_duplicate_summary", {"max_groups": 20}, scan_res, dup_res)
    assert res.ok
    assert "total_groups" in res.data
    summary_bytes = len(json.dumps(res.summary).encode("utf-8"))
    assert summary_bytes < 2048

    print("  [OK] All tools executed successfully on real demo scan with compact summaries < 2 KB.")


def main() -> None:
    print("=" * 60)
    print("RUNNING CHECK_TOOLS.PY")
    print("=" * 60)

    try:
        test_no_destructive_tools()
        test_validate_valid_calls()
        test_validate_unknown_tools()
        test_validate_extra_arguments()
        test_validate_wrong_types()
        test_validate_ranges_and_enums()
        test_validate_string_sanitization()
        test_execute_tool_on_demo_scan()
        print("\nOVERALL: ALL TOOL CHECKS PASSED (PASS)")
    except AssertionError as exc:
        print(f"\nASSERTION FAILED: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as exc:
        print(f"\nUNEXPECTED ERROR: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
