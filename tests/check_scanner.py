"""
tests/check_scanner.py
======================
CLI test script to verify folder scanning and query functions.
Usage:
    python tests/check_scanner.py [folder_path]
"""

from __future__ import annotations

import io
import os
from pathlib import Path
import sys
import time

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force UTF-8 output for Windows console
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from engine.categories import category_for
from engine.drives import format_bytes
from engine.query import largest_files, largest_folders
from engine.scanner import scan_folder


def get_default_downloads_folder() -> str:
    """Return the user's Downloads directory."""
    home = Path.home()
    downloads = home / "Downloads"
    if downloads.exists():
        return str(downloads)
    return str(home)


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else get_default_downloads_folder()
    print("=" * 72)
    print("OmniStore — Scanner Test")
    print("=" * 72)
    print(f"Target folder : {target}")

    if not os.path.exists(target):
        print(f"Error: Target path does not exist: {target}")
        sys.exit(1)

    print("Scanning...")
    t0 = time.perf_counter()

    def on_progress(files: int, bytes_count: int, curr_dir: str) -> None:
        # Simple progress indication
        print(f"\r  Scanned: {files} files | {format_bytes(bytes_count)}", end="", flush=True)

    result = scan_folder(target, progress_cb=on_progress)
    elapsed = time.perf_counter() - t0
    print()  # newline after progress

    print("-" * 72)
    print(f"Status        : {'Cancelled' if result.cancelled else 'Complete'}")
    print(f"Scan time     : {result.duration_seconds:.3f} s")
    print(f"Total files   : {result.total_files:,}")
    print(f"Total size    : {format_bytes(result.total_bytes)} ({result.total_bytes:,} bytes)")
    print(f"Unique folders: {len(result.folder_sizes):,}")
    print(f"Errors        : {len(result.errors)}")
    print(f"Skipped       : {result.skipped_count}")
    print("-" * 72)

    top10 = largest_files(result, limit=10)
    print("Top 10 Largest Files:")
    if not top10:
        print("  (No files found)")
    else:
        print(f"  {'#':<3} {'Size':>10}  {'Category':<12} {'Name'}")
        print("  " + "-" * 68)
        for i, f in enumerate(top10, start=1):
            cat = category_for(f.extension)
            size_str = format_bytes(f.size_bytes)
            name_disp = f.name if len(f.name) <= 45 else f.name[:42] + "..."
            print(f"  {i:<3} {size_str:>10}  {cat:<12} {name_disp}")

    print("-" * 72)
    top_dirs = largest_folders(result, limit=5)
    print("Top 5 Largest Folders (including subfolders):")
    if not top_dirs:
        print("  (No subfolders found)")
    else:
        for i, d in enumerate(top_dirs, start=1):
            size_str = format_bytes(d["total_bytes"])
            print(f"  {i}. {size_str:>10} ({d['percent_of_scan']:>5.1f}%)  {d['path']}")
    print("=" * 72)


if __name__ == "__main__":
    main()
