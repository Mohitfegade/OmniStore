"""
tests/check_query.py
====================
CLI test script to verify query summaries and compact JSON output for Gemma tool calling.
Usage:
    python tests/check_query.py [folder_path]
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force UTF-8 output for Windows console
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from engine.drives import format_bytes
from engine.query import (
    build_scan_summary,
    largest_folders,
    summarize_by_category,
)
from engine.scanner import scan_folder


def get_default_folder() -> str:
    home = Path.home()
    downloads = home / "Downloads"
    if downloads.exists():
        return str(downloads)
    return str(home)


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else get_default_folder()
    print("=" * 72)
    print("OmniStore — Query & Summary Test")
    print("=" * 72)
    print(f"Target folder : {target}")

    if not os.path.exists(target):
        print(f"Error: Target path does not exist: {target}")
        sys.exit(1)

    print("Scanning...")
    result = scan_folder(target)
    print(f"Scan complete in {result.duration_seconds:.3f} s ({result.total_files:,} files, {format_bytes(result.total_bytes)})")
    print("-" * 72)

    # 1. Category breakdown
    print("Category Breakdown (summarize_by_category):")
    cats = summarize_by_category(result)
    if not cats:
        print("  (No files found)")
    else:
        print(f"  {'Category':<14} {'Files':>8} {'Total Size':>12} {'Percent':>9}")
        print("  " + "-" * 47)
        for c in cats:
            size_str = format_bytes(c["total_bytes"])
            print(f"  {c['category']:<14} {c['file_count']:>8,} {size_str:>12} {c['percent_of_total']:>8.1f}%")

    print("-" * 72)

    # 2. Largest folders
    print("Largest Folders (largest_folders, excluding root):")
    folders = largest_folders(result, limit=10)
    if not folders:
        print("  (No subfolders found)")
    else:
        print(f"  {'#':<3} {'Size':>10} {'Share':>8}  {'Path'}")
        print("  " + "-" * 60)
        for i, f in enumerate(folders, start=1):
            size_str = format_bytes(f["total_bytes"])
            print(f"  {i:<3} {size_str:>10} {f['percent_of_scan']:>7.1f}%  {f['path']}")

    print("-" * 72)

    # 3. Compact Scan Summary for Gemma
    print("Gemma Scan Summary (build_scan_summary JSON):")
    summary = build_scan_summary(result)
    compact_json = json.dumps(summary, ensure_ascii=False)
    compact_bytes = len(compact_json.encode("utf-8"))
    pretty_json = json.dumps(summary, indent=2, ensure_ascii=False)
    print(pretty_json)
    print("-" * 72)
    print(f"JSON Payload Size : {compact_bytes:,} bytes (under ~2 KB target: {compact_bytes <= 2048})")
    print("=" * 72)


if __name__ == "__main__":
    main()
