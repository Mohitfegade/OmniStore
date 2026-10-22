"""
tests/check_signals.py
======================
Verification test for PySide6 signal safety and 64-bit integer / object passing:
1. Scans AST of workers/ and ui/ to ensure no Signal declaration uses plain `int`
   for arguments carrying byte counts, file sizes, totals, or large numbers.
2. Uses QCoreApplication to emit large integer values (5,000,000,000) through
   ScanWorker, DuplicateWorker, and CleanupWorker signals, verifying zero 32-bit
   overflow errors.
3. Verifies font size safety guards.
4. Outputs PASS/FAIL per check and overall PASS/FAIL.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

# Add project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication, QObject, Signal
from workers.scan_worker import ScanWorker
from workers.duplicate_worker import DuplicateWorker
from workers.cleanup_worker import CleanupWorker
from ui.theme import safe_font_size, create_safe_font, safe_set_point_size


def check_ast_signals() -> bool:
    """Scan AST of workers/ and ui/ for vulnerable int-typed signals."""
    print("[1/3] Scanning AST of workers/ and ui/ for vulnerable signals...")
    vulnerable_keywords = {"byte", "bytes", "size", "total", "count", "hashed"}
    violations = []

    checked_dirs = [ROOT / "workers", ROOT / "ui"]
    total_signals_checked = 0

    for directory in checked_dirs:
        for py_path in directory.rglob("*.py"):
            try:
                tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
            except Exception as e:
                print(f"  Error parsing {py_path}: {e}")
                continue

            for node in ast.walk(tree):
                # Look for Signal(...) calls
                if isinstance(node, ast.Call):
                    func = node.func
                    is_signal = False
                    if isinstance(func, ast.Name) and func.id in ("Signal", "pyqtSignal"):
                        is_signal = True
                    elif isinstance(func, ast.Attribute) and func.attr in ("Signal", "pyqtSignal"):
                        is_signal = True

                    if is_signal:
                        total_signals_checked += 1
                        # Check argument types
                        for arg_idx, arg in enumerate(node.args):
                            if isinstance(arg, ast.Name) and arg.id == "int":
                                # Check if this arg represents bytes or large counts
                                # Check comments/docstrings or variable names
                                rel_path = py_path.relative_to(ROOT)
                                violations.append(
                                    f"{rel_path}:{node.lineno} Signal argument #{arg_idx} is plain 'int' in {ast.unparse(node)}"
                                )

    # If any Signal uses int for byte/size counts:
    # Specifically, check that scan_worker, duplicate_worker, cleanup_worker do not use int for large fields
    if violations:
        print(f"  FAILED: Found {len(violations)} plain 'int' Signal argument(s):")
        for v in violations:
            print(f"    - {v}")
        return False

    print(f"  PASS: All {total_signals_checked} signals in workers/ and ui/ use safe types (object, str, bool, list).")
    return True


def check_large_value_emission() -> bool:
    """Emit 5,000,000,000 (> 32-bit signed int) through worker signals without overflow."""
    print("\n[2/3] Testing large integer emission (> 2^31 - 1 = 2,147,483,647)...")
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)

    LARGE_VALUE = 5_000_000_000  # 5 GB (overflows 32-bit int)
    all_passed = True

    # 1. ScanWorker.progress
    received_scan = {}
    class ScanReceiver(QObject):
        def on_progress(self, files, bytes_scanned, folder):
            received_scan["files"] = files
            received_scan["bytes"] = bytes_scanned
            received_scan["folder"] = folder

    worker_scan = ScanWorker("C:\\test")
    rec_scan = ScanReceiver()
    worker_scan.progress.connect(rec_scan.on_progress)

    try:
        worker_scan.progress.emit(1000, LARGE_VALUE, "C:\\test\\subfolder")
        app.processEvents()
        assert received_scan.get("bytes") == LARGE_VALUE, f"Expected {LARGE_VALUE}, got {received_scan.get('bytes')}"
        print(f"  PASS: ScanWorker.progress successfully received {received_scan['bytes']:,} bytes.")
    except OverflowError as exc:
        print(f"  FAIL: ScanWorker.progress raised OverflowError: {exc}")
        all_passed = False
    except Exception as exc:
        print(f"  FAIL: ScanWorker.progress failed with: {exc}")
        all_passed = False

    # 2. DuplicateWorker.progress
    received_dup = {}
    class DupReceiver(QObject):
        def on_progress(self, stage, done, total, bytes_hashed):
            received_dup["stage"] = stage
            received_dup["done"] = done
            received_dup["total"] = total
            received_dup["bytes"] = bytes_hashed

    worker_dup = DuplicateWorker()
    rec_dup = DupReceiver()
    worker_dup.progress.connect(rec_dup.on_progress)

    try:
        worker_dup.progress.emit("Hashing", 500, 1000, LARGE_VALUE)
        app.processEvents()
        assert received_dup.get("bytes") == LARGE_VALUE, f"Expected {LARGE_VALUE}, got {received_dup.get('bytes')}"
        print(f"  PASS: DuplicateWorker.progress successfully received {received_dup['bytes']:,} bytes hashed.")
    except OverflowError as exc:
        print(f"  FAIL: DuplicateWorker.progress raised OverflowError: {exc}")
        all_passed = False
    except Exception as exc:
        print(f"  FAIL: DuplicateWorker.progress failed with: {exc}")
        all_passed = False

    # 3. CleanupWorker.progress
    received_cleanup = {}
    class CleanupReceiver(QObject):
        def on_progress(self, done, total, path):
            received_cleanup["done"] = done
            received_cleanup["total"] = total
            received_cleanup["path"] = path

    from engine.cleanup import CleanupPlan
    dummy_plan = CleanupPlan(items=[], total_bytes=0, blocked=[], warnings=[])
    worker_cleanup = CleanupWorker(dummy_plan)
    rec_cleanup = CleanupReceiver()
    worker_cleanup.progress.connect(rec_cleanup.on_progress)

    try:
        worker_cleanup.progress.emit(LARGE_VALUE, LARGE_VALUE * 2, "C:\\file.tmp")
        app.processEvents()
        assert received_cleanup.get("done") == LARGE_VALUE
        print(f"  PASS: CleanupWorker.progress successfully received count {received_cleanup['done']:,}.")
    except OverflowError as exc:
        print(f"  FAIL: CleanupWorker.progress raised OverflowError: {exc}")
        all_passed = False
    except Exception as exc:
        print(f"  FAIL: CleanupWorker.progress failed with: {exc}")
        all_passed = False

    return all_passed


def check_font_guards() -> bool:
    """Verify font size guards against 0 or negative point sizes."""
    print("\n[3/3] Testing font size safety guards...")
    all_passed = True

    cases = [
        (-1, 10),
        (0, 10),
        (-100, 10),
        (None, 10),
        ("invalid", 10),
        (14, 14),
        (16, 16),
    ]

    for val, expected in cases:
        out = safe_font_size(val, default=10)
        if out != expected:
            print(f"  FAIL: safe_font_size({val}) returned {out}, expected {expected}")
            all_passed = False

    # Test create_safe_font
    font_neg = create_safe_font("Segoe UI", -1)
    if font_neg.pointSize() != 10:
        print(f"  FAIL: create_safe_font('Segoe UI', -1) pointSize is {font_neg.pointSize()}, expected 10")
        all_passed = False

    font_zero = create_safe_font("Segoe UI", 0)
    if font_zero.pointSize() != 10:
        print(f"  FAIL: create_safe_font('Segoe UI', 0) pointSize is {font_zero.pointSize()}, expected 10")
        all_passed = False

    font_valid = create_safe_font("Segoe UI", 16)
    if font_valid.pointSize() != 16:
        print(f"  FAIL: create_safe_font('Segoe UI', 16) pointSize is {font_valid.pointSize()}, expected 16")
        all_passed = False

    if all_passed:
        print("  PASS: All font size guards validated (invalid/<=0 inputs fall back to 10).")

    return all_passed


def main() -> None:
    print("=" * 65)
    print("OMNISTORE — SIGNAL SAFETY & 32-BIT OVERFLOW VERIFICATION")
    print("=" * 65)

    ast_ok = check_ast_signals()
    emission_ok = check_large_value_emission()
    font_ok = check_font_guards()

    print("\n" + "=" * 65)
    if ast_ok and emission_ok and font_ok:
        print("OVERALL: ALL SIGNAL AND FONT CHECKS PASSED (PASS)")
        print("=" * 65)
        sys.exit(0)
    else:
        print("OVERALL: SIGNAL CHECKS FAILED (FAIL)")
        print("=" * 65)
        sys.exit(1)


if __name__ == "__main__":
    main()
