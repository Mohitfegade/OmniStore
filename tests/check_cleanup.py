"""
tests/check_cleanup.py
======================
Verification test for engine/cleanup.py.

Run against a THROWAWAY COPY of the demo data (never the original).
The demo folder C:\\Users\\<me>\\OmniStore_Demo must exist first
(run tests/make_demo_data.py if needed).

Usage:
    python tests/check_cleanup.py          # auto-creates temp copy
    python tests/check_cleanup.py --help
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cleanup import (
    CleanupItem,
    CleanupPlan,
    REASON_DUPLICATE,
    REASON_LARGE,
    build_plan,
    build_cleanup_summary,
    execute_plan,
    verify_duplicate_before_delete,
)
from engine.duplicates import find_duplicates
from engine.scanner import scan_folder

SEPARATOR = "=" * 72


def _make_temp_copy(demo_dir: Path) -> Path:
    """Copy demo dir to a unique temp location (outside AppData) and return the path."""
    # Use user home / OmniStore_Tests so it is NOT inside AppData/LocalAppData
    user_home = Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))
    tmp_root = user_home / f"OmniStore_CleanupTest_{int(time.time())}"
    print(f"  Copying {demo_dir} -> {tmp_root} ...", flush=True)
    shutil.copytree(str(demo_dir), str(tmp_root))
    print(f"  Done. Temp copy has {sum(1 for _ in tmp_root.rglob('*') if _.is_file())} files.", flush=True)
    return tmp_root


def _cleanup_temp(tmp_root: Path) -> None:
    try:
        shutil.rmtree(str(tmp_root), ignore_errors=True)
    except Exception:
        pass


def _find_group_a(scan_res, dup_res):
    """Return the DuplicateGroup that has 3 copies (~20 MB each)."""
    for g in dup_res.groups:
        if g.copies == 3:
            return g
    return None


def run_tests(demo_dir: Path) -> bool:
    print(SEPARATOR, flush=True)
    print("OmniStore -- Cleanup Engine Verification", flush=True)
    print(SEPARATOR, flush=True)

    if not demo_dir.exists():
        print(f"ERROR: Demo folder {demo_dir} not found.", flush=True)
        print("Run:  python tests/make_demo_data.py", flush=True)
        return False

    tmp_root = _make_temp_copy(demo_dir)
    failures: list[str] = []

    try:
        print("\nScanning temp copy...", flush=True)
        scan_res = scan_folder(str(tmp_root))
        print(f"  {scan_res.total_files} files, {scan_res.total_bytes:,} bytes", flush=True)

        print("\nFinding duplicates (min 1 KB)...", flush=True)
        dup_res = find_duplicates(scan_res, min_size_bytes=1024)
        print(f"  {dup_res.total_groups} groups, {dup_res.total_reclaimable_bytes:,} reclaimable bytes", flush=True)

        group_a = _find_group_a(scan_res, dup_res)
        assert group_a is not None, "Group A (3 x 20 MB) not found"
        assert group_a.copies == 3
        assert group_a.size_bytes == 20 * 1024 * 1024

        files_a = list(group_a.files)  # 3 FileRecords
        # Pick the oldest as keep_path
        oldest = min(files_a, key=lambda f: f.modified_ts)
        extras = [f for f in files_a if f is not oldest]

        # ------------------------------------------------------------------
        # TEST 1: Plan with 2 extra copies of Group A -> total_bytes == 40 MB
        # ------------------------------------------------------------------
        print("\n[TEST 1] Plan 2 extras of Group A -> expect 40 MB ...", flush=True)
        items_2 = [
            CleanupItem(
                path=f.path,
                name=f.name,
                size_bytes=f.size_bytes,
                modified_ts=f.modified_ts,
                reason=REASON_DUPLICATE,
                group_id=group_a.group_id,
                keep_path=oldest.path,
            )
            for f in extras
        ]
        plan_2 = build_plan(items_2, duplicate_result=dup_res)
        expected = 2 * 20 * 1024 * 1024  # 40 MB in binary
        if plan_2.total_bytes == expected and len(plan_2.blocked) == 0:
            print(f"  PASS -- total_bytes={plan_2.total_bytes:,} ({plan_2.total_bytes // (1024*1024)} MB)", flush=True)
        else:
            msg = (
                f"FAIL -- total_bytes={plan_2.total_bytes:,}, "
                f"expected={expected:,}, blocked={plan_2.blocked}"
            )
            print(f"  {msg}", flush=True)
            failures.append(msg)

        # ------------------------------------------------------------------
        # TEST 2: Plan with all 3 copies -> must have >=1 blocked
        # ------------------------------------------------------------------
        print("\n[TEST 2] Plan all 3 copies of Group A -> at least 1 blocked ...", flush=True)
        items_all3 = [
            CleanupItem(
                path=f.path,
                name=f.name,
                size_bytes=f.size_bytes,
                modified_ts=f.modified_ts,
                reason=REASON_DUPLICATE,
                group_id=group_a.group_id,
                keep_path=None,  # no keep_path -> will be blocked
            )
            for f in files_a
        ]
        plan_all3 = build_plan(items_all3, duplicate_result=dup_res)
        if len(plan_all3.blocked) >= 1:
            print(f"  PASS -- {len(plan_all3.blocked)} item(s) blocked: "
                  f"{[b['reason'][:60] for b in plan_all3.blocked]}", flush=True)
        else:
            msg = f"FAIL -- expected >=1 blocked, got {len(plan_all3.blocked)}"
            print(f"  {msg}", flush=True)
            failures.append(msg)

        # ------------------------------------------------------------------
        # TEST 3: Protected path is blocked
        # ------------------------------------------------------------------
        print("\n[TEST 3] File in C:\\Windows is blocked ...", flush=True)
        fake_win_file = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "notepad.exe")
        item_protected = CleanupItem(
            path=fake_win_file,
            name="notepad.exe",
            size_bytes=100,
            modified_ts=0.0,
            reason=REASON_LARGE,
        )
        plan_protected = build_plan([item_protected])
        if len(plan_protected.blocked) == 1 and "protected" in plan_protected.blocked[0]["reason"].lower():
            print(f"  PASS -- blocked with: {plan_protected.blocked[0]['reason'][:80]}", flush=True)
        else:
            msg = f"FAIL -- protected path not blocked: {plan_protected.blocked}"
            print(f"  {msg}", flush=True)
            failures.append(msg)

        # ------------------------------------------------------------------
        # TEST 4: execute_plan raises when confirmed=False
        # ------------------------------------------------------------------
        print("\n[TEST 4] execute_plan(confirmed=False) raises ValueError ...", flush=True)
        try:
            execute_plan(plan_2, confirmed=False)
            msg = "FAIL -- ValueError was NOT raised"
            print(f"  {msg}", flush=True)
            failures.append(msg)
        except ValueError as exc:
            print(f"  PASS -- raised ValueError: {exc}", flush=True)

        # ------------------------------------------------------------------
        # TEST 5: Execute plan with confirmed=True -> files recycled
        # ------------------------------------------------------------------
        print("\n[TEST 5] execute_plan(confirmed=True) -- recycling 2 extras of Group A ...", flush=True)

        # Rebuild plan against temp copy paths (they exist)
        plan_exec = build_plan(items_2, duplicate_result=dup_res)
        assert len(plan_exec.items) == 2, f"Expected 2 items, got {len(plan_exec.items)}"

        paths_to_remove = [it.path for it in plan_exec.items]
        keep_path = oldest.path

        outcome = execute_plan(plan_exec, confirmed=True)

        ok = True
        # 2 files should have been recycled
        if len(outcome.succeeded) != 2:
            msg = f"FAIL -- expected 2 succeeded, got {len(outcome.succeeded)}. failed={outcome.failed} skipped={outcome.skipped}"
            print(f"  {msg}", flush=True)
            failures.append(msg)
            ok = False

        # Original paths no longer exist
        for p in paths_to_remove:
            if os.path.exists(p):
                msg = f"FAIL -- file still exists after recycling: {p}"
                print(f"  {msg}", flush=True)
                failures.append(msg)
                ok = False

        # Kept copy still exists
        if not os.path.exists(keep_path):
            msg = f"FAIL -- kept copy no longer exists: {keep_path}"
            print(f"  {msg}", flush=True)
            failures.append(msg)
            ok = False

        if ok:
            print(
                f"  PASS -- {len(outcome.succeeded)} files recycled, "
                f"kept copy exists at {os.path.basename(keep_path)}, "
                f"originals gone.",
                flush=True,
            )
            print(f"         bytes_recovered_estimate={outcome.bytes_recovered_estimate:,}", flush=True)

        # ------------------------------------------------------------------
        # TEST 6: build_cleanup_summary produces compact output
        # ------------------------------------------------------------------
        print("\n[TEST 6] build_cleanup_summary is compact ...", flush=True)
        import json
        plan_summary = build_cleanup_summary(plan_exec)
        outcome_summary = build_cleanup_summary(outcome)
        plan_json = json.dumps(plan_summary)
        outcome_json = json.dumps(outcome_summary)
        plan_ok = len(plan_json.encode()) < 2048
        outcome_ok = len(outcome_json.encode()) < 2048
        if plan_ok and outcome_ok:
            print(f"  PASS -- plan: {len(plan_json)} bytes, outcome: {len(outcome_json)} bytes", flush=True)
        else:
            msg = f"FAIL -- summaries too large: plan={len(plan_json)}, outcome={len(outcome_json)}"
            print(f"  {msg}", flush=True)
            failures.append(msg)

        # ------------------------------------------------------------------
        # TEST 7: Codebase guard -- no os.remove or shutil.rmtree in app code
        # ------------------------------------------------------------------
        print("\n[TEST 7] Guard: No permanent deletion (os.remove, os.unlink, shutil.rmtree) in app code ...", flush=True)
        import re
        project_root = Path(__file__).resolve().parent.parent
        forbidden_patterns = [
            (re.compile(r"\bos\.remove\s*\("), "os.remove"),
            (re.compile(r"\bos\.unlink\s*\("), "os.unlink"),
            (re.compile(r"\bshutil\.rmtree\s*\("), "shutil.rmtree"),
        ]
        scanned_dirs = ["engine", "ui", "workers", "commands"]
        violations = []

        for d_name in scanned_dirs:
            d_path = project_root / d_name
            if not d_path.exists():
                continue
            for py_file in d_path.rglob("*.py"):
                text = py_file.read_text(encoding="utf-8")
                for pat, name in forbidden_patterns:
                    if pat.search(text):
                        rel = py_file.relative_to(project_root)
                        violations.append(f"{rel}: found {name}() call")

        for f_name in ["main.py", "app_state.py"]:
            f_path = project_root / f_name
            if f_path.exists():
                text = f_path.read_text(encoding="utf-8")
                for pat, name in forbidden_patterns:
                    if pat.search(text):
                        violations.append(f"{f_name}: found {name}() call")

        if not violations:
            print("  PASS -- Zero permanent deletion calls found across engine, ui, workers, commands, main.py, app_state.py.", flush=True)
        else:
            msg = f"FAIL -- Permanent deletion calls detected: {violations}"
            print(f"  {msg}", flush=True)
            failures.append(msg)

    finally:
        print(f"\nCleaning up temp folder {tmp_root} ...", flush=True)
        _cleanup_temp(tmp_root)

    print(f"\n{SEPARATOR}", flush=True)
    if failures:
        print(f"FAILURES ({len(failures)}):", flush=True)
        for f in failures:
            print(f"  - {f}", flush=True)
        print(f"\nTEST RESULT: FAIL", flush=True)
    else:
        print("ALL ASSERTIONS PASSED", flush=True)
        print("TEST RESULT: PASS", flush=True)
    print(SEPARATOR, flush=True)
    return len(failures) == 0


if __name__ == "__main__":
    demo = Path(os.environ.get("USERPROFILE", "C:/Users/Default")) / "OmniStore_Demo"
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        demo = Path(sys.argv[1])
    success = run_tests(demo)
    sys.exit(0 if success else 1)
