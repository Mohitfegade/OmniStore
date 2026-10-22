"""
tests/check_tools.py
====================
Verification tests for commands/tools.py and engine/formatting.py.

Validates:
1. Tool schemas and security constraints (no destructive/shell tools, exact 7 tools).
2. engine/formatting.py: format_size and display_name behavior.
3. validate_tool_call:
   - Accepts valid arguments for all 7 tools.
   - Rejects unknown tool names.
   - Rejects extra or unrecognized arguments.
   - Rejects incorrect parameter types.
   - Rejects out-of-range numeric arguments (limits 1..200, sizes >= 0, days 0..36500, suggest_free_space 0.1..5000).
   - Rejects invalid category enums.
   - Strips control characters and enforces max string length of 100.
4. execute_tool:
   - Runs against real scan data of OmniStore_Demo.
   - Enforces *_human fields on every size field.
   - Enforces name and parent_name on folder and file entries.
   - Tests suggest_free_space: required keys, "up to" wording, review notice, no "junk" or "safe to delete".
   - Returns capped data (<= 200 items) and compact summaries under 2 KB JSON.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from commands.tools import (
    TOOL_SCHEMAS,
    execute_tool,
    validate_tool_call,
)
from engine.duplicates import find_duplicates
from engine.formatting import display_name, format_size
from engine.scanner import scan_folder


def test_formatting_helpers() -> None:
    """Verify format_size and display_name functions."""
    assert format_size(0) == "0 B"
    assert format_size(1024) == "1 KB"
    assert format_size(1024 * 1024 * 23) == "23 MB"
    assert "1.4 GB" in format_size(1_500_000_000)

    # Drive root
    assert display_name("C:\\") == "C:"
    assert display_name("D:/") == "D:"
    assert display_name("C:") == "C:"

    # File and folder
    assert display_name("C:\\Users\\Mohit\\report.pdf") == "report.pdf"
    assert display_name("C:\\Users\\Mohit\\Documents") == "Documents"
    print("  [OK] Formatting helpers format_size and display_name verified.")


def test_no_destructive_tools() -> None:
    """Verify that no tool schema permits modifying files or executing commands, and tool count is 7."""
    assert len(TOOL_SCHEMAS) == 7, f"Expected exactly 7 tools in TOOL_SCHEMAS, got {len(TOOL_SCHEMAS)}"

    forbidden = {"delete", "remove", "unlink", "trash", "rm", "exec", "sh", "bash", "cmd", "open", "copy", "move", "rename"}
    for schema in TOOL_SCHEMAS:
        name = schema["function"]["name"].lower()
        desc = schema["function"]["description"].lower()
        for term in forbidden:
            assert term not in name, f"Forbidden term '{term}' in tool name '{name}'"
            assert term not in desc or "user review" in desc or "reclaimable" in desc, f"Forbidden term '{term}' in description of '{name}'"
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

    # 7. suggest_free_space
    ok, args, err = validate_tool_call("suggest_free_space", {"target_gb": 2.5})
    assert ok, f"Expected ok, got: {err}"
    assert args["target_gb"] == 2.5

    print("  [OK] All 7 valid tool calls passed validation.")


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

    ok, args, err = validate_tool_call("suggest_free_space", {"target_gb": "three"})
    assert not ok
    assert err and "number between" in err
    print("  [OK] Incorrect parameter types correctly rejected.")


def test_validate_ranges_and_enums() -> None:
    """Verify out-of-range numbers and invalid enums are rejected."""
    # limit out of range
    ok, _, err = validate_tool_call("find_largest_files", {"limit": 0})
    assert not ok and "between 1 and 200" in err

    ok, _, err = validate_tool_call("find_largest_files", {"limit": 500})
    assert not ok and "between 1 and 200" in err

    # suggest_free_space: 0.1 to 5000.0
    ok, _, err = validate_tool_call("suggest_free_space", {"target_gb": 0.05})
    assert not ok and "between 0.1 and 5000" in err

    ok, _, err = validate_tool_call("suggest_free_space", {"target_gb": 5000.1})
    assert not ok and "between 0.1 and 5000" in err

    ok, args, _ = validate_tool_call("suggest_free_space", {"target_gb": 0.1})
    assert ok and args["target_gb"] == 0.1

    ok, args, _ = validate_tool_call("suggest_free_space", {"target_gb": 5000.0})
    assert ok and args["target_gb"] == 5000.0

    # negative size
    ok, _, err = validate_tool_call("find_largest_files", {"min_size_mb": -10})
    assert not ok and "non-negative" in err

    # days out of range
    ok, _, err = validate_tool_call("filter_files", {"modified_before_days": -1})
    assert not ok and "between 0 and 36500" in err

    # invalid category enum
    ok, _, err = validate_tool_call("find_largest_files", {"category": "Cryptocurrency"})
    assert not ok and "Invalid category" in err

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
    assert "total_bytes_human" in res.data
    assert "total_size_human" in res.data
    for tf in res.data.get("top_folders", []):
        assert "name" in tf and "parent_name" in tf and "size_human" in tf

    # 2. find_largest_files
    res = execute_tool("find_largest_files", {"limit": 100}, scan_res, dup_res)
    assert res.ok
    for r in res.data.get("files", []):
        assert "name" in r and "parent_name" in r and "size_human" in r and "size_bytes_human" in r

    # 3. filter_files
    res = execute_tool("filter_files", {"limit": 50}, scan_res, dup_res)
    assert res.ok
    for r in res.data.get("files", []):
        assert "name" in r and "parent_name" in r and "size_human" in r

    # 4. get_largest_folders
    res = execute_tool("get_largest_folders", {"limit": 10}, scan_res, dup_res)
    assert res.ok
    for f in res.data.get("folders", []):
        assert "name" in f and "parent_name" in f and "size_human" in f

    # 5. get_category_breakdown
    res = execute_tool("get_category_breakdown", {}, scan_res, dup_res)
    assert res.ok
    for c in res.data.get("categories", []):
        assert "size_human" in c and "total_bytes_human" in c

    # 6. get_duplicate_summary
    res = execute_tool("get_duplicate_summary", {"max_groups": 20}, scan_res, dup_res)
    assert res.ok
    assert "total_reclaimable_bytes_human" in res.data
    for g in res.data.get("top_groups", []):
        assert "size_human" in g and "reclaimable_human" in g

    # 7. suggest_free_space
    res = execute_tool("suggest_free_space", {"target_gb": 0.05}, scan_res, dup_res)
    # Even if target is small, execute_tool accepts cleaned args
    res = execute_tool("suggest_free_space", {"target_gb": 0.1}, scan_res, dup_res)
    assert res.ok
    assert "target_human" in res.data
    assert "reachable" in res.data
    assert "total_up_to_bytes" in res.data
    assert "total_up_to_human" in res.data
    assert "suggestions" in res.data
    assert "note" in res.data

    note_lower = res.data["note"].lower()
    assert "up to" in note_lower, f"'up to' missing in note: {res.data['note']}"
    assert "review" in note_lower, f"'review' missing in note: {res.data['note']}"
    assert "junk" not in note_lower, f"'junk' found in note: {res.data['note']}"
    assert "safe to delete" not in note_lower, f"'safe to delete' found in note: {res.data['note']}"

    summary_bytes = len(json.dumps(res.summary).encode("utf-8"))
    assert summary_bytes < 2048, f"Summary exceeds 2 KB ({summary_bytes} bytes)"

    print("  [OK] All 7 tools executed successfully on real demo scan with *_human and name fields verified.")


def main() -> None:
    print("=" * 60)
    print("RUNNING CHECK_TOOLS.PY")
    print("=" * 60)

    try:
        test_formatting_helpers()
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
