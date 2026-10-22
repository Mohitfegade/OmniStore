"""
commands/tools.py
=================
Read-only tool schemas, validation, and deterministic execution for OmniStore.

These tools are exposed to Gemma as function-calling schemas. Gemma chooses which
tool to call with what parameters. All tools are executed deterministically over
the active ScanResult and DuplicateResult.

SAFETY:
-------
There are NO tools for deleting, moving, renaming, copying, opening files, or running
shell commands. All tools are strictly read-only analysis functions.
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

import datetime
import json
import re
import time
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from engine.categories import CATEGORIES, category_for
from engine.drives import format_bytes
from engine.duplicates import DuplicateResult, build_duplicate_summary, find_duplicates
from engine.models import FileRecord, ScanResult
from engine.query import (
    build_scan_summary,
    filter_files,
    largest_files,
    largest_folders,
    summarize_by_category,
)

# ---------------------------------------------------------------------------
# Tool Schemas for Gemma / Ollama Function Calling
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_scan_overview",
            "description": "Get high-level storage statistics for the currently scanned folder (total files, total size, categories, top folders).",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_largest_files",
            "description": "Find the largest files in the scanned folder, optionally filtered by category or minimum size.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of files to return (1 to 200, default 10).",
                        "minimum": 1,
                        "maximum": 200,
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional file category filter.",
                        "enum": list(CATEGORIES),
                    },
                    "min_size_mb": {
                        "type": "number",
                        "description": "Minimum file size in megabytes (MB).",
                        "minimum": 0,
                    },
                    "name_contains": {
                        "type": "string",
                        "description": "Search keyword in the file name.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_files",
            "description": "Filter files with precise criteria (category, extension, size range, age, access time, sorting).",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Category name filter.",
                        "enum": list(CATEGORIES),
                    },
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific file extensions to match (e.g. ['mp4', 'zip']).",
                    },
                    "min_size_mb": {
                        "type": "number",
                        "description": "Minimum size in megabytes (MB).",
                        "minimum": 0,
                    },
                    "max_size_mb": {
                        "type": "number",
                        "description": "Maximum size in megabytes (MB).",
                        "minimum": 0,
                    },
                    "modified_before_days": {
                        "type": "integer",
                        "description": "Files modified more than N days ago.",
                        "minimum": 0,
                        "maximum": 36500,
                    },
                    "modified_after_days": {
                        "type": "integer",
                        "description": "Files modified within the last N days.",
                        "minimum": 0,
                        "maximum": 36500,
                    },
                    "not_accessed_for_days": {
                        "type": "integer",
                        "description": "Files not accessed in the last N days.",
                        "minimum": 0,
                        "maximum": 36500,
                    },
                    "name_contains": {
                        "type": "string",
                        "description": "Substring to search in file name.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return (1 to 200, default 20).",
                        "minimum": 1,
                        "maximum": 200,
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Field to sort by.",
                        "enum": ["size", "name", "modified", "accessed", "category"],
                    },
                    "descending": {
                        "type": "boolean",
                        "description": "Sort order (default true for descending).",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_largest_folders",
            "description": "Get subfolders that consume the most disk space inside the scanned folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of folders to return (1 to 200, default 5).",
                        "minimum": 1,
                        "maximum": 200,
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_category_breakdown",
            "description": "Get storage breakdown by category (file counts, total bytes, and percentages).",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_duplicate_summary",
            "description": "Get duplicate file groups and estimated reclaimable disk space from duplicate detection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_groups": {
                        "type": "integer",
                        "description": "Maximum duplicate groups to summarize (1 to 50, default 5).",
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_free_space",
            "description": "Find potential candidates to free up a target amount of disk space (combining duplicate extra copies and old unaccessed files for user review).",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_gb": {
                        "type": "number",
                        "description": "Target amount of space to free up in gigabytes (GB, between 0.1 and 1000).",
                        "minimum": 0.1,
                        "maximum": 1000.0,
                    },
                },
                "required": ["target_gb"],
                "additionalProperties": False,
            },
        },
    },
]

_TOOL_NAMES = {s["function"]["name"] for s in TOOL_SCHEMAS}


# ---------------------------------------------------------------------------
# Tool Result Dataclass
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    """The outcome of running a validated tool on real scan data."""
    name: str
    ok: bool
    data: Dict[str, Any]
    summary: Dict[str, Any]
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Input Validation & Sanitization
# ---------------------------------------------------------------------------

def _strip_control_chars(s: str) -> str:
    """Strip ASCII control characters (keep printable text)."""
    return "".join(ch for ch in s if ch >= " " and ch != "\x7f")


def validate_tool_call(name: str, arguments: Dict[str, Any]) -> tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Strictly validate a tool call proposed by Gemma.

    Rules:
    - Tool name must exist in TOOL_SCHEMAS.
    - No unrecognized arguments allowed.
    - Argument types, enums, and ranges are strictly enforced.
    - Strings are stripped of control chars and capped at 100 characters.

    Returns
    -------
    (ok: bool, cleaned_arguments: dict, error_message: str | None)
    """
    if not isinstance(name, str) or name not in _TOOL_NAMES:
        return False, {}, (
            f"Unknown tool '{name}'. Allowed tools are: {', '.join(sorted(_TOOL_NAMES))}. "
            f"OmniStore tools are strictly read-only analysis tools."
        )

    if not isinstance(arguments, dict):
        return False, {}, f"Tool arguments must be a dictionary, got {type(arguments).__name__}."

    cleaned: Dict[str, Any] = {}

    if name in ("get_scan_overview", "get_category_breakdown"):
        if arguments:
            return False, {}, f"Tool '{name}' takes no arguments, but received: {list(arguments.keys())}."
        return True, {}, None

    elif name == "find_largest_files":
        allowed = {"limit", "category", "min_size_mb", "name_contains"}
        extra = set(arguments) - allowed
        if extra:
            return False, {}, f"Unexpected arguments for '{name}': {list(extra)}."

        if "limit" in arguments:
            val = arguments["limit"]
            if not isinstance(val, int) or isinstance(val, bool) or not (1 <= val <= 200):
                return False, {}, f"'limit' must be an integer between 1 and 200, got {val!r}."
            cleaned["limit"] = val
        else:
            cleaned["limit"] = 10

        if "category" in arguments and arguments["category"] is not None:
            cat = str(arguments["category"]).strip()
            if cat not in CATEGORIES:
                return False, {}, f"Invalid category '{cat}'. Allowed: {sorted(CATEGORIES)}."
            cleaned["category"] = cat

        if "min_size_mb" in arguments and arguments["min_size_mb"] is not None:
            val = arguments["min_size_mb"]
            if not isinstance(val, (int, float)) or isinstance(val, bool) or val < 0:
                return False, {}, f"'min_size_mb' must be a non-negative number, got {val!r}."
            cleaned["min_size_mb"] = float(val)

        if "name_contains" in arguments and arguments["name_contains"] is not None:
            s = _strip_control_chars(str(arguments["name_contains"]))[:100].strip()
            if s:
                cleaned["name_contains"] = s

        return True, cleaned, None

    elif name == "filter_files":
        allowed = {
            "category", "extensions", "min_size_mb", "max_size_mb",
            "modified_before_days", "modified_after_days", "not_accessed_for_days",
            "name_contains", "limit", "sort_by", "descending",
        }
        extra = set(arguments) - allowed
        if extra:
            return False, {}, f"Unexpected arguments for '{name}': {list(extra)}."

        if "category" in arguments and arguments["category"] is not None:
            cat = str(arguments["category"]).strip()
            if cat not in CATEGORIES:
                return False, {}, f"Invalid category '{cat}'. Allowed: {sorted(CATEGORIES)}."
            cleaned["category"] = cat

        if "extensions" in arguments and arguments["extensions"] is not None:
            exts = arguments["extensions"]
            if not isinstance(exts, list):
                return False, {}, f"'extensions' must be a list of strings, got {type(exts).__name__}."
            clean_exts = []
            for e in exts:
                clean_e = _strip_control_chars(str(e)).lstrip(".").lower()[:20].strip()
                if clean_e:
                    clean_exts.append(clean_e)
            cleaned["extensions"] = clean_exts

        for size_key in ("min_size_mb", "max_size_mb"):
            if size_key in arguments and arguments[size_key] is not None:
                val = arguments[size_key]
                if not isinstance(val, (int, float)) or isinstance(val, bool) or val < 0:
                    return False, {}, f"'{size_key}' must be a non-negative number, got {val!r}."
                cleaned[size_key] = float(val)

        for days_key in ("modified_before_days", "modified_after_days", "not_accessed_for_days"):
            if days_key in arguments and arguments[days_key] is not None:
                val = arguments[days_key]
                if not isinstance(val, int) or isinstance(val, bool) or not (0 <= val <= 36500):
                    return False, {}, f"'{days_key}' must be an integer between 0 and 36500, got {val!r}."
                cleaned[days_key] = val

        if "name_contains" in arguments and arguments["name_contains"] is not None:
            s = _strip_control_chars(str(arguments["name_contains"]))[:100].strip()
            if s:
                cleaned["name_contains"] = s

        if "limit" in arguments:
            val = arguments["limit"]
            if not isinstance(val, int) or isinstance(val, bool) or not (1 <= val <= 200):
                return False, {}, f"'limit' must be an integer between 1 and 200, got {val!r}."
            cleaned["limit"] = val
        else:
            cleaned["limit"] = 20

        if "sort_by" in arguments and arguments["sort_by"] is not None:
            sb = str(arguments["sort_by"]).strip().lower()
            valid_sorts = {"size", "name", "modified", "accessed", "category"}
            if sb not in valid_sorts:
                return False, {}, f"Invalid sort_by '{sb}'. Allowed: {sorted(valid_sorts)}."
            cleaned["sort_by"] = sb
        else:
            cleaned["sort_by"] = "size"

        if "descending" in arguments and arguments["descending"] is not None:
            val = arguments["descending"]
            if not isinstance(val, bool):
                return False, {}, f"'descending' must be a boolean, got {type(val).__name__}."
            cleaned["descending"] = val
        else:
            cleaned["descending"] = True

        return True, cleaned, None

    elif name == "get_largest_folders":
        allowed = {"limit"}
        extra = set(arguments) - allowed
        if extra:
            return False, {}, f"Unexpected arguments for '{name}': {list(extra)}."

        if "limit" in arguments:
            val = arguments["limit"]
            if not isinstance(val, int) or isinstance(val, bool) or not (1 <= val <= 200):
                return False, {}, f"'limit' must be an integer between 1 and 200, got {val!r}."
            cleaned["limit"] = val
        else:
            cleaned["limit"] = 5

        return True, cleaned, None

    elif name == "get_duplicate_summary":
        allowed = {"max_groups"}
        extra = set(arguments) - allowed
        if extra:
            return False, {}, f"Unexpected arguments for '{name}': {list(extra)}."

        if "max_groups" in arguments:
            val = arguments["max_groups"]
            if not isinstance(val, int) or isinstance(val, bool) or not (1 <= val <= 50):
                return False, {}, f"'max_groups' must be an integer between 1 and 50, got {val!r}."
            cleaned["max_groups"] = val
        else:
            cleaned["max_groups"] = 5

        return True, cleaned, None

    elif name == "suggest_free_space":
        allowed = {"target_gb"}
        extra = set(arguments) - allowed
        if extra:
            return False, {}, f"Unexpected arguments for '{name}': {list(extra)}."

        if "target_gb" not in arguments:
            return False, {}, "Missing required argument 'target_gb' for 'suggest_free_space'."

        val = arguments["target_gb"]
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            return False, {}, f"'target_gb' must be a number between 0.1 and 1000, got {type(val).__name__}."

        fval = float(val)
        if not (0.1 <= fval <= 1000.0):
            return False, {}, f"'target_gb' must be between 0.1 and 1000, got {fval}."

        cleaned["target_gb"] = fval
        return True, cleaned, None

    return False, {}, f"Unhandled tool '{name}'."


# ---------------------------------------------------------------------------
# Tool Execution
# ---------------------------------------------------------------------------

def _file_record_to_dict(f: FileRecord) -> Dict[str, Any]:
    return {
        "name": f.name if len(f.name) <= 60 else f.name[:57] + "...",
        "path": f.path,
        "size_bytes": f.size_bytes,
        "size_human": format_bytes(f.size_bytes),
        "category": category_for(f.extension),
        "extension": f.extension,
        "modified_date": datetime.datetime.fromtimestamp(f.modified_ts).strftime("%Y-%m-%d"),
        "folder": f.parent_folder[-40:] if len(f.parent_folder) > 40 else f.parent_folder,
    }


def _compact_summary_item(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": r.get("name", "")[:50],
        "size_bytes": r.get("size_bytes", 0),
        "size_human": r.get("size_human", ""),
        "category": r.get("category", ""),
        "modified_date": r.get("modified_date", ""),
    }


def execute_tool(
    name: str,
    cleaned_args: Dict[str, Any],
    scan_result: Optional[ScanResult],
    duplicate_result: Optional[DuplicateResult] = None,
) -> ToolResult:
    """
    Execute a validated tool call over real scan data.

    Constraints:
    - Never executes if scan_result is None.
    - Capped at 200 records in data.
    - Produces a summary object under 2 KB JSON.
    """
    if scan_result is None:
        return ToolResult(
            name=name,
            ok=False,
            data={},
            summary={},
            error="No active folder scan. Please scan a folder in the Analyzer first.",
        )

    try:
        now_ts = time.time()

        if name == "get_scan_overview":
            summary = build_scan_summary(scan_result)
            summary["total_size_human"] = format_bytes(summary["total_bytes"])
            for cat in summary.get("categories", []):
                cat["size_human"] = format_bytes(cat.get("total_bytes", 0))
            for fld in summary.get("top_folders", []):
                p = fld.get("path", "")
                fld["name"] = Path(p).name or p
                fld["size_human"] = format_bytes(fld.get("total_bytes", 0))

            top_cats = [
                {
                    "category": c["category"],
                    "total_bytes": c["total_bytes"],
                    "size_human": format_bytes(c["total_bytes"]),
                    "percent": c["percent_of_total"],
                }
                for c in summary.get("categories", [])[:5]
            ]
            top_flds = [
                {
                    "name": Path(f.get("path", "")).name or f.get("path", ""),
                    "path": f.get("path", ""),
                    "total_bytes": f.get("total_bytes", 0),
                    "size_human": format_bytes(f.get("total_bytes", 0)),
                    "percent_of_scan": f.get("percent_of_scan", 0.0),
                }
                for f in summary.get("top_folders", [])[:3]
            ]

            return ToolResult(
                name=name,
                ok=True,
                data=summary,
                summary={
                    "root_path": summary["root_path"],
                    "total_files": summary["total_files"],
                    "total_bytes": summary["total_bytes"],
                    "total_size_human": format_bytes(summary["total_bytes"]),
                    "top_categories": top_cats,
                    "top_folders": top_flds,
                },
            )

        elif name == "find_largest_files":
            limit = min(cleaned_args.get("limit", 10), 200)
            category = cleaned_args.get("category")
            min_size = int(cleaned_args["min_size_mb"] * 1024 * 1024) if "min_size_mb" in cleaned_args else None
            name_contains = cleaned_args.get("name_contains")

            files = largest_files(
                scan_result,
                limit=limit,
                category=category,
                min_size=min_size,
                name_contains=name_contains,
            )
            records = [_file_record_to_dict(f) for f in files]
            total_bytes = sum(f.size_bytes for f in files)

            return ToolResult(
                name=name,
                ok=True,
                data={
                    "files": records,
                    "count": len(records),
                    "total_bytes": total_bytes,
                    "total_size_human": format_bytes(total_bytes),
                },
                summary={
                    "count": len(records),
                    "total_bytes": total_bytes,
                    "total_size_human": format_bytes(total_bytes),
                    "top_10": [_compact_summary_item(r) for r in records[:10]],
                },
            )

        elif name == "filter_files":
            limit = min(cleaned_args.get("limit", 20), 200)
            category = cleaned_args.get("category")
            extensions = cleaned_args.get("extensions")
            min_size = int(cleaned_args["min_size_mb"] * 1024 * 1024) if "min_size_mb" in cleaned_args else None
            max_size = int(cleaned_args["max_size_mb"] * 1024 * 1024) if "max_size_mb" in cleaned_args else None

            mod_before = (now_ts - cleaned_args["modified_before_days"] * 86400) if "modified_before_days" in cleaned_args else None
            mod_after = (now_ts - cleaned_args["modified_after_days"] * 86400) if "modified_after_days" in cleaned_args else None
            not_acc = (now_ts - cleaned_args["not_accessed_for_days"] * 86400) if "not_accessed_for_days" in cleaned_args else None

            name_contains = cleaned_args.get("name_contains")
            sort_by = cleaned_args.get("sort_by", "size")
            descending = cleaned_args.get("descending", True)

            files = filter_files(
                scan_result,
                category=category,
                extensions=extensions,
                min_size=min_size,
                max_size=max_size,
                modified_before=mod_before,
                modified_after=mod_after,
                not_accessed_since=not_acc,
                name_contains=name_contains,
                limit=limit,
                sort_by=sort_by,
                descending=descending,
            )
            records = [_file_record_to_dict(f) for f in files]
            total_bytes = sum(f.size_bytes for f in files)

            return ToolResult(
                name=name,
                ok=True,
                data={
                    "files": records,
                    "count": len(records),
                    "total_bytes": total_bytes,
                    "total_size_human": format_bytes(total_bytes),
                },
                summary={
                    "count": len(records),
                    "total_bytes": total_bytes,
                    "total_size_human": format_bytes(total_bytes),
                    "top_10": [_compact_summary_item(r) for r in records[:10]],
                },
            )

        elif name == "get_largest_folders":
            limit = min(cleaned_args.get("limit", 5), 200)
            folders = largest_folders(scan_result, limit=limit)
            enriched_folders = []
            for f in folders:
                p = f.get("path", "")
                enriched_folders.append({
                    "name": Path(p).name or p,
                    "path": p,
                    "total_bytes": f.get("total_bytes", 0),
                    "size_human": format_bytes(f.get("total_bytes", 0)),
                    "percent_of_scan": f.get("percent_of_scan", 0.0),
                })
            return ToolResult(
                name=name,
                ok=True,
                data={"folders": enriched_folders, "count": len(enriched_folders)},
                summary={"count": len(enriched_folders), "folders": enriched_folders[:10]},
            )

        elif name == "get_category_breakdown":
            cats = summarize_by_category(scan_result)
            total_bytes = sum(c["total_bytes"] for c in cats)
            enriched_cats = []
            for c in cats:
                enriched_cats.append({
                    "category": c["category"],
                    "total_bytes": c["total_bytes"],
                    "size_human": format_bytes(c["total_bytes"]),
                    "file_count": c.get("file_count", 0),
                    "percent_of_total": c.get("percent_of_total", 0.0),
                })
            return ToolResult(
                name=name,
                ok=True,
                data={
                    "categories": enriched_cats,
                    "total_bytes": total_bytes,
                    "total_size_human": format_bytes(total_bytes),
                },
                summary={
                    "categories": enriched_cats[:8],
                    "total_bytes": total_bytes,
                    "total_size_human": format_bytes(total_bytes),
                },
            )

        elif name == "get_duplicate_summary":
            if duplicate_result is None:
                return ToolResult(
                    name=name,
                    ok=False,
                    data={},
                    summary={},
                    error="Duplicate detection has not been run yet for this scan. Go to the Duplicates tab to scan for duplicates.",
                )
            max_groups = min(cleaned_args.get("max_groups", 5), 50)
            summary = build_duplicate_summary(duplicate_result, max_groups=max_groups)
            summary["reclaimable_human"] = format_bytes(summary["total_reclaimable_bytes"])

            for g in summary.get("top_groups", []):
                g["size_human"] = format_bytes(g.get("size_bytes", 0))
                g["reclaimable_human"] = format_bytes(g.get("reclaimable_bytes", 0))

            return ToolResult(
                name=name,
                ok=True,
                data=summary,
                summary={
                    "total_groups": summary["total_groups"],
                    "total_duplicate_files": summary["total_duplicate_files"],
                    "total_reclaimable_bytes": summary["total_reclaimable_bytes"],
                    "reclaimable_human": format_bytes(summary["total_reclaimable_bytes"]),
                    "top_groups": summary.get("top_groups", [])[:5],
                },
            )

        elif name == "suggest_free_space":
            target_gb = cleaned_args.get("target_gb", 1.0)
            target_bytes = int(target_gb * 1024 * 1024 * 1024)
            candidates: List[Dict[str, Any]] = []
            seen_paths: set[str] = set()

            # 1. Duplicates: extra copies, keep oldest copy
            dup_res = duplicate_result
            if dup_res is None and scan_result:
                try:
                    dup_res = find_duplicates(scan_result)
                except Exception:
                    dup_res = None

            if dup_res and dup_res.groups:
                for g in dup_res.groups:
                    sorted_files = sorted(g.files, key=lambda f: f.modified_ts)
                    oldest = sorted_files[0]
                    keep_path = oldest.path
                    seen_paths.add(os.path.normcase(os.path.abspath(keep_path)))

                    for dup_file in sorted_files[1:]:
                        norm_p = os.path.normcase(os.path.abspath(dup_file.path))
                        if norm_p not in seen_paths:
                            seen_paths.add(norm_p)
                            candidates.append({
                                "path": dup_file.path,
                                "name": dup_file.name[:60],
                                "size_bytes": dup_file.size_bytes,
                                "size_human": format_bytes(dup_file.size_bytes),
                                "modified_date": datetime.datetime.fromtimestamp(dup_file.modified_ts).strftime("%Y-%m-%d"),
                                "reason": "Exact duplicate",
                                "keep_path": keep_path,
                                "potential": "potential reclaimable",
                                "folder": dup_file.parent_folder[-40:] if len(dup_file.parent_folder) > 40 else dup_file.parent_folder,
                            })

            # 2. Large unaccessed files: 180+ days old
            cutoff_ts = now_ts - (180 * 86400)
            for f in scan_result.files:
                norm_p = os.path.normcase(os.path.abspath(f.path))
                if norm_p in seen_paths:
                    continue
                acc_ts = f.accessed_ts or f.modified_ts
                if acc_ts < cutoff_ts and f.size_bytes >= 5 * 1024 * 1024:
                    seen_paths.add(norm_p)
                    candidates.append({
                        "path": f.path,
                        "name": f.name[:60],
                        "size_bytes": f.size_bytes,
                        "size_human": format_bytes(f.size_bytes),
                        "modified_date": datetime.datetime.fromtimestamp(f.modified_ts).strftime("%Y-%m-%d"),
                        "reason": "Large file not opened recently",
                        "keep_path": None,
                        "potential": "review only",
                        "folder": f.parent_folder[-40:] if len(f.parent_folder) > 40 else f.parent_folder,
                    })

            # Sort descending by size
            candidates.sort(key=lambda x: x["size_bytes"], reverse=True)

            # Cap rows at 200
            selected = candidates[:200]
            cumulative_bytes = sum(c["size_bytes"] for c in selected)
            target_reached = cumulative_bytes >= target_bytes
            target_human = format_bytes(target_bytes)
            cumulative_human = format_bytes(cumulative_bytes)

            return ToolResult(
                name=name,
                ok=True,
                data={
                    "target_gb": target_gb,
                    "target_bytes": target_bytes,
                    "target_human": target_human,
                    "cumulative_bytes": cumulative_bytes,
                    "cumulative_human": cumulative_human,
                    "target_reached": target_reached,
                    "count": len(selected),
                    "candidates": selected,
                },
                summary={
                    "target_gb": target_gb,
                    "target_human": target_human,
                    "cumulative_human": cumulative_human,
                    "target_reached": target_reached,
                    "count": len(selected),
                    "top_candidates": [
                        {
                            "name": c.get("name", "")[:50],
                            "size_human": c.get("size_human", ""),
                            "reason": c.get("reason", ""),
                            "potential": c.get("potential", ""),
                        }
                        for c in selected[:10]
                    ],
                },
            )

        return ToolResult(name=name, ok=False, data={}, summary={}, error=f"Unknown tool '{name}'.")

    except Exception as exc:
        return ToolResult(name=name, ok=False, data={}, summary={}, error=f"Tool execution error: {exc}")
