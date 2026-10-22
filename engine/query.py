"""
engine/query.py
===============
Pure query functions over a ScanResult.
These functions serve as the analysis engine and will become tools for Gemma tool-calling.
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

from collections import defaultdict
import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.categories import category_for
from engine.models import FileRecord, ScanResult


def filter_files(
    result: ScanResult,
    category: Optional[str] = None,
    extensions: Optional[List[str]] = None,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
    modified_before: Optional[float] = None,
    modified_after: Optional[float] = None,
    not_accessed_since: Optional[float] = None,
    name_contains: Optional[str] = None,
    limit: Optional[int] = None,
    sort_by: str = "size",
    descending: bool = True,
) -> List[FileRecord]:
    """
    Filter and sort files from a ScanResult.

    Parameters
    ----------
    result : ScanResult
    category : str, optional
        Filter by high-level category e.g. "Videos", "Documents"
    extensions : list of str, optional
        Filter by specific extensions e.g. ["iso", "zip"]
    min_size : int, optional
        Minimum size in bytes
    max_size : int, optional
        Maximum size in bytes
    modified_before : float, optional
        POSIX timestamp
    modified_after : float, optional
        POSIX timestamp
    not_accessed_since : float, optional
        POSIX timestamp (files not accessed since this timestamp)
    name_contains : str, optional
        Substring to search in file name (case-insensitive)
    limit : int, optional
        Max number of records to return
    sort_by : str, default "size"
        One of "size", "name", "modified", "accessed", "category"
    descending : bool, default True

    Returns
    -------
    list of FileRecord
    """
    clean_exts = set(e.lstrip(".").lower() for e in extensions) if extensions else None
    search_term = name_contains.strip().lower() if name_contains else None
    cat_filter = category.strip() if category and category.lower() != "all" else None

    filtered: list[FileRecord] = []

    for f in result.files:
        if cat_filter is not None and category_for(f.extension) != cat_filter:
            continue

        if clean_exts is not None and f.extension not in clean_exts:
            continue

        if min_size is not None and f.size_bytes < min_size:
            continue

        if max_size is not None and f.size_bytes > max_size:
            continue

        if modified_before is not None and f.modified_ts > modified_before:
            continue

        if modified_after is not None and f.modified_ts < modified_after:
            continue

        if not_accessed_since is not None and f.accessed_ts > not_accessed_since:
            continue

        if search_term is not None and search_term not in f.name.lower():
            continue

        filtered.append(f)

    # Sort
    sort_key: Any
    if sort_by == "size":
        filtered.sort(key=lambda r: r.size_bytes, reverse=descending)
    elif sort_by == "name":
        filtered.sort(key=lambda r: r.name.lower(), reverse=descending)
    elif sort_by == "modified":
        filtered.sort(key=lambda r: r.modified_ts, reverse=descending)
    elif sort_by == "accessed":
        filtered.sort(key=lambda r: r.accessed_ts, reverse=descending)
    elif sort_by == "category":
        filtered.sort(key=lambda r: category_for(r.extension), reverse=descending)
    else:
        filtered.sort(key=lambda r: r.size_bytes, reverse=descending)

    if limit is not None and limit > 0:
        return filtered[:limit]

    return filtered


def largest_files(
    result: ScanResult,
    limit: int = 50,
    **filters: Any,
) -> List[FileRecord]:
    """Return the largest files in result, optionally applying further filters."""
    return filter_files(result, limit=limit, sort_by="size", descending=True, **filters)


def summarize_by_category(result: ScanResult) -> List[Dict[str, Any]]:
    """
    Group files by category and return statistics for each category that has at least one file.

    Returns
    -------
    list of dicts:
        [{"category": str, "file_count": int, "total_bytes": int, "percent_of_total": float}, ...]
        sorted by total_bytes descending.
    """
    counts: dict[str, int] = defaultdict(int)
    sizes: dict[str, int] = defaultdict(int)

    for f in result.files:
        cat = category_for(f.extension)
        counts[cat] += 1
        sizes[cat] += f.size_bytes

    summary: list[dict[str, Any]] = []
    total_bytes = result.total_bytes

    for cat, count in counts.items():
        cat_size = sizes[cat]
        pct = round((cat_size / total_bytes) * 100, 1) if total_bytes > 0 else 0.0
        summary.append({
            "category": cat,
            "file_count": count,
            "total_bytes": cat_size,
            "percent_of_total": pct,
        })

    summary.sort(key=lambda d: d["total_bytes"], reverse=True)
    return summary


def largest_folders(
    result: ScanResult,
    limit: int = 10,
    min_depth: int = 0,
) -> List[Dict[str, Any]]:
    """
    Return the largest folders by total bytes (including subfolders).
    Excludes the scan root itself from the ranking.
    When the root has no subfolders, returns an empty list.

    Parameters
    ----------
    result : ScanResult
    limit : int, default 10
    min_depth : int, default 0
        Minimum directory depth relative to root_path.

    Returns
    -------
    list of {"path": str, "total_bytes": int, "percent_of_scan": float}
    """
    norm_root = os.path.normcase(os.path.abspath(result.root_path))
    total_scan_bytes = result.total_bytes

    items: list[dict[str, Any]] = []

    for path, size in result.folder_sizes.items():
        norm_path = os.path.normcase(os.path.abspath(path))
        # Exclude the scan root itself
        if norm_path == norm_root:
            continue

        if min_depth > 0:
            rel = os.path.relpath(path, result.root_path)
            depth = len(Path(rel).parts)
            if depth < min_depth:
                continue

        pct = round((size / total_scan_bytes) * 100, 1) if total_scan_bytes > 0 else 0.0
        items.append({
            "path": path,
            "total_bytes": size,
            "percent_of_scan": pct,
        })

    items.sort(key=lambda d: d["total_bytes"], reverse=True)
    return items[:limit]


def build_scan_summary(result: ScanResult) -> Dict[str, Any]:
    """
    Build a compact summary (under ~2 KB JSON) for Gemma or LLM tool consumption.
    Contains only computed aggregates and metadata from the real scan, never file contents.
    """
    top_files = [
        {
            "name": f.name if len(f.name) <= 30 else f.name[:27] + "...",
            "size_bytes": f.size_bytes,
            "category": category_for(f.extension),
            "modified_date": datetime.datetime.fromtimestamp(f.modified_ts).strftime("%Y-%m-%d"),
        }
        for f in largest_files(result, limit=10)
    ]

    return {
        "root_path": result.root_path,
        "total_files": result.total_files,
        "total_bytes": result.total_bytes,
        "duration_seconds": round(result.duration_seconds, 3),
        "categories": summarize_by_category(result)[:8],
        "top_folders": largest_folders(result, limit=5),
        "top_files": top_files,
        "errors_count": len(result.errors),
        "skipped_count": result.skipped_count,
    }
