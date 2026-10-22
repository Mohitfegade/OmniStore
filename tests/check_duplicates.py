"""
tests/check_duplicates.py
=========================
CLI verification script for exact duplicate detection in OmniStore.
Scans the demo directory, runs find_duplicates, asserts expected results,
and outputs PASS or FAIL.

Usage:
    python tests/check_duplicates.py [demo_folder_path]
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import time

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force UTF-8 output for Windows console
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from engine.drives import format_bytes
from engine.duplicates import build_duplicate_summary, find_duplicates
from engine.scanner import scan_folder


def get_default_demo_dir() -> str:
    return str(Path.home() / "OmniStore_Demo")


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else get_default_demo_dir()
    print("=" * 72)
    print("OmniStore — Duplicate Detection Verification")
    print("=" * 72)
    print(f"Target folder : {target}")

    if not os.path.isdir(target):
        print(f"\n[ERROR] Directory not found: {target}")
        print("Please run `python tests/make_demo_data.py` first.")
        print("\nTEST RESULT: FAIL")
        sys.exit(1)

    print("\nScanning demo directory...")
    scan_result = scan_folder(target)
    print(f"Discovered {scan_result.total_files} files ({format_bytes(scan_result.total_bytes)}) in {scan_result.duration_seconds:.3f} s")

    print("\nRunning find_duplicates (min_size_bytes=1024)...")
    t0 = time.perf_counter()

    def on_progress(stage: str, done: int, total: int, b_hashed: int) -> None:
        pct = (done / total * 100) if total > 0 else 0
        print(f"\r  [{stage:<30}] {done}/{total} files ({pct:5.1f}%) | Hashed: {format_bytes(b_hashed):>10}", end="", flush=True)

    dup_result = find_duplicates(scan_result, min_size_bytes=1024, progress_cb=on_progress)
    elapsed = time.perf_counter() - t0
    print()  # newline

    print("-" * 72)
    print("Duplicate Detection Results:")
    print(f"  Duration              : {dup_result.duration_seconds:.3f} s")
    print(f"  Duplicate Groups      : {dup_result.total_groups}")
    print(f"  Total Redundant Files : {dup_result.total_duplicate_files - dup_result.total_groups}")
    print(f"  Total Files in Groups : {dup_result.total_duplicate_files}")
    print(f"  Total Reclaimable     : {format_bytes(dup_result.total_reclaimable_bytes)} ({dup_result.total_reclaimable_bytes:,} bytes)")
    print(f"  Bytes Hashed          : {format_bytes(dup_result.bytes_hashed)} ({dup_result.bytes_hashed:,} bytes)")
    print(f"  Errors                : {len(dup_result.errors)}")
    print("-" * 72)

    for i, g in enumerate(dup_result.groups, start=1):
        print(f"Group #{i}: {format_bytes(g.size_bytes)} each | {g.copies} copies | Reclaimable: up to {format_bytes(g.reclaimable_bytes)}")
        for f in g.files:
            rel = os.path.relpath(f.path, target)
            print(f"    - {rel}")

    # Summary JSON validation
    summary = build_duplicate_summary(dup_result)
    summary_json = json.dumps(summary)
    print("-" * 72)
    print(f"Gemma Summary JSON size: {len(summary_json.encode('utf-8')):,} bytes (under ~2 KB target: {len(summary_json.encode('utf-8')) <= 2048})")

    # -----------------------------------------------------------------------
    # Assertions for demo folder
    # -----------------------------------------------------------------------
    print("\nRunning Verification Assertions...")
    failed_assertions = []

    # 1. Exactly 3 duplicate groups
    if dup_result.total_groups != 3:
        failed_assertions.append(f"Expected 3 duplicate groups, got {dup_result.total_groups}")

    # 2. Group A has 3 copies of 20 MB file
    group_20mb = [g for g in dup_result.groups if g.size_bytes == 20 * 1024 * 1024]
    if not group_20mb or group_20mb[0].copies != 3:
        copies = group_20mb[0].copies if group_20mb else 0
        failed_assertions.append(f"Expected Group A to have 3 copies of 20 MB, found {copies}")

    # 3. Group B has 2 copies of 5 MB file
    group_5mb = [g for g in dup_result.groups if g.size_bytes == 5 * 1024 * 1024]
    if not group_5mb or group_5mb[0].copies != 2:
        copies = group_5mb[0].copies if group_5mb else 0
        failed_assertions.append(f"Expected Group B to have 2 copies of 5 MB, found {copies}")

    # 4. Group C has 2 copies of 50 KB file
    group_50kb = [g for g in dup_result.groups if g.size_bytes == 50 * 1024]
    if not group_50kb or group_50kb[0].copies != 2:
        copies = group_50kb[0].copies if group_50kb else 0
        failed_assertions.append(f"Expected Group C to have 2 copies of 50 KB, found {copies}")

    # 5. Negative test: Same size (8 MB) different content MUST NOT be reported
    all_dup_paths = {f.path.lower() for g in dup_result.groups for f in g.files}
    for p in all_dup_paths:
        if "pic_a.raw" in p or "pic_b.raw" in p:
            failed_assertions.append("Negative test failed: 8 MB different-content files were reported as duplicates!")

    # 6. Negative test: Empty 0-byte files MUST NOT be reported
    for p in all_dup_paths:
        if "empty1.log" in p or "empty2.log" in p:
            failed_assertions.append("Negative test failed: 0-byte empty files were reported as duplicates!")

    # 7. Total reclaimable bytes exact match: 2*20MB + 1*5MB + 1*50KB = 47,237,120 bytes (45.05 MB)
    expected_reclaimable = 2 * (20 * 1024 * 1024) + (5 * 1024 * 1024) + (50 * 1024)
    if dup_result.total_reclaimable_bytes != expected_reclaimable:
        failed_assertions.append(
            f"Expected {expected_reclaimable} reclaimable bytes, got {dup_result.total_reclaimable_bytes}"
        )

    print("=" * 72)
    if not failed_assertions:
        print("ALL ASSERTIONS PASSED")
        print("TEST RESULT: PASS")
        print("=" * 72)
    else:
        print("ASSERTIONS FAILED:")
        for err in failed_assertions:
            print(f"  [X] {err}")
        print("TEST RESULT: FAIL")
        print("=" * 72)
        sys.exit(1)


if __name__ == "__main__":
    main()
