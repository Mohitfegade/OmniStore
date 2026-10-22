"""
tests/test_cleanup_ui.py
========================
Automated UI and Integration tests for OmniStore Cleanup Center.

Tests:
1. Empty state when no items are pending
2. Candidate tools (Large files, Old large files) - opt-in rows, nothing pre-checked
3. PlanTable display with duplicate items from app_state pending_cleanup
4. Per-row Remove button removes item and recalculates plan
5. Blocked items section in PlanTable (e.g. protected path)
6. ConfirmDialog safety: confirm button disabled until checkbox checked, cancel is default
7. Worker execution: progress handling, result card display
8. File system verification: files recycled, kept copy intact
9. app_state updates: ScanResult updated, DuplicateResult updated, pending_cleanup cleared
10. cleanup_log.jsonl written
"""

import os
import shutil
import sys
import time
from pathlib import Path

# Project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication, QDialog

import app_state
from engine.cleanup import (
    CleanupItem,
    REASON_DUPLICATE,
    REASON_LARGE,
    build_plan,
)
from engine.duplicates import find_duplicates
from engine.scanner import scan_folder
from ui.cleanup import CleanupPage, ConfirmDialog
from workers.cleanup_worker import CleanupWorker


def _wait_for_worker(page):
    while page._worker is not None and page._worker.isRunning():
        QCoreApplication.processEvents()
        time.sleep(0.02)
    for _ in range(10):
        QCoreApplication.processEvents()
        time.sleep(0.01)


def run_tests():
    app = QApplication.instance() or QApplication(sys.argv)
    demo_dir = Path(os.environ.get("USERPROFILE", "C:/Users/Default")) / "OmniStore_Demo"
    if not demo_dir.exists():
        print(f"Error: Demo dir {demo_dir} does not exist.", flush=True)
        return False

    user_home = Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))
    tmp_root = user_home / f"OmniStore_CleanupUITest_{int(time.time())}"
    print(f"Copying {demo_dir} -> {tmp_root} ...", flush=True)
    shutil.copytree(str(demo_dir), str(tmp_root))

    failures = []

    try:
        # ------------------------------------------------------------------
        # Step 1: Empty state
        # ------------------------------------------------------------------
        print("\nStep 1: Testing empty state when nothing is queued ...", flush=True)
        app_state.set_latest_scan(None)
        app_state.set_latest_duplicates(None)
        app_state.set_pending_cleanup([])

        page = CleanupPage()
        page.show()
        QCoreApplication.processEvents()

        assert page._empty_card.isVisible(), "Empty card should be visible"
        assert not page._plan_card.isVisible(), "Plan card should be hidden"
        assert not page._summary_card.isVisible(), "Summary card should be hidden"
        assert not page._result_card.isVisible(), "Result card should be hidden"
        print("  PASS -- Empty state verified.", flush=True)

        # ------------------------------------------------------------------
        # Step 2: Scan temp copy & inspect candidate tools
        # ------------------------------------------------------------------
        print("\nStep 2: Scanning temp copy and testing candidate tools ...", flush=True)
        scan_res = scan_folder(str(tmp_root))
        app_state.set_latest_scan(scan_res)
        page._load_large_files()
        page._load_old_files()
        QCoreApplication.processEvents()

        # Both candidate tables should exist
        assert page._lf_table is not None
        assert page._olf_table is not None

        # Verify nothing is pre-checked (opt-in only)
        assert len(page._lf_table.get_checked_records()) == 0, "No large files should be pre-checked"
        assert len(page._olf_table.get_checked_records()) == 0, "No old files should be pre-checked"
        print("  PASS -- Candidate tools verified: nothing pre-checked (opt-in only).", flush=True)

        # ------------------------------------------------------------------
        # Step 3: Find duplicates and queue 2 extras of Group A
        # ------------------------------------------------------------------
        print("\nStep 3: Finding duplicates and queuing 2 extras of Group A ...", flush=True)
        dup_res = find_duplicates(scan_res, min_size_bytes=1024)
        app_state.set_latest_duplicates(dup_res)

        group_a = next(g for g in dup_res.groups if g.copies == 3)
        files_a = list(group_a.files)
        oldest = min(files_a, key=lambda f: f.modified_ts)
        extras = [f for f in files_a if f is not oldest]
        assert len(extras) == 2

        pending_items = [
            {
                "file": f,
                "reason": REASON_DUPLICATE,
                "keep_path": oldest.path,
                "group_id": group_a.group_id,
            }
            for f in extras
        ]
        app_state.set_pending_cleanup(pending_items)
        QCoreApplication.processEvents()

        assert not page._empty_card.isVisible(), "Empty card should now be hidden"
        assert page._plan_card.isVisible(), "Plan card should now be visible"
        assert page._summary_card.isVisible(), "Summary card should be visible"
        assert page._plan_table.rowCount() == 2, f"Expected 2 rows in plan table, got {page._plan_table.rowCount()}"
        assert page._current_plan is not None
        assert page._current_plan.total_bytes == 41943040, f"Expected 40 MB total, got {page._current_plan.total_bytes}"
        assert "40.0 MB" in page._summary_lbl.text()
        print("  PASS -- Plan table loaded 2 duplicate items: 40 MB total.", flush=True)

        # ------------------------------------------------------------------
        # Step 4: Remove button removes item and updates plan
        # ------------------------------------------------------------------
        print("\nStep 4: Testing per-row Remove button ...", flush=True)
        page._remove_plan_item(0)
        QCoreApplication.processEvents()

        assert page._plan_table.rowCount() == 1, f"Expected 1 row after removal, got {page._plan_table.rowCount()}"
        assert page._current_plan.total_bytes == 20971520, f"Expected 20 MB after removal, got {page._current_plan.total_bytes}"
        assert "20.0 MB" in page._summary_lbl.text()
        print("  PASS -- Per-row Remove works and recalculates plan to 20 MB.", flush=True)

        # Restore both items for subsequent steps
        app_state.set_pending_cleanup(pending_items)
        QCoreApplication.processEvents()
        assert page._plan_table.rowCount() == 2

        # ------------------------------------------------------------------
        # Step 5: Blocked items section in PlanTable
        # ------------------------------------------------------------------
        print("\nStep 5: Testing protected path blocking in plan table ...", flush=True)
        fake_win_path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "notepad.exe")
        from engine.models import FileRecord
        fake_rec = FileRecord(
            path=fake_win_path,
            name="notepad.exe",
            extension="exe",
            size_bytes=200000,
            modified_ts=time.time(),
            accessed_ts=time.time(),
            parent_folder=os.path.dirname(fake_win_path),
        )
        items_with_blocked = pending_items + [{
            "file": fake_rec,
            "reason": REASON_LARGE,
            "keep_path": None,
            "group_id": None,
        }]
        app_state.set_pending_cleanup(items_with_blocked)
        QCoreApplication.processEvents()

        # Should have 2 active rows + 1 separator row + 1 blocked row = 4 rows
        assert len(page._current_plan.blocked) == 1, "Protected file should be in blocked list"
        assert page._plan_table.rowCount() == 4, f"Expected 4 rows (2 active + sep + 1 blocked), got {page._plan_table.rowCount()}"
        print("  PASS -- Blocked item appears in muted 'Not included' section.", flush=True)

        # Reset back to just the 2 duplicates
        app_state.set_pending_cleanup(pending_items)
        QCoreApplication.processEvents()

        # ------------------------------------------------------------------
        # Step 6: ConfirmDialog safety
        # ------------------------------------------------------------------
        print("\nStep 6: Testing ConfirmDialog safety requirements ...", flush=True)
        dlg = ConfirmDialog(page._current_plan, parent=page)
        dlg.show()
        QCoreApplication.processEvents()

        # Confirm button must be disabled initially
        assert not dlg._confirm_btn.isEnabled(), "Confirm button must be disabled initially"
        assert dlg._cancel_btn.isDefault(), "Cancel button must be default"

        # Check the box -> confirm enables
        dlg._checkbox.setChecked(True)
        QCoreApplication.processEvents()
        assert dlg._confirm_btn.isEnabled(), "Confirm button must be enabled when checkbox is checked"

        # Uncheck -> confirm disables
        dlg._checkbox.setChecked(False)
        QCoreApplication.processEvents()
        assert not dlg._confirm_btn.isEnabled(), "Confirm button must be disabled when checkbox is unchecked"

        dlg.close()
        print("  PASS -- ConfirmDialog safety verified.", flush=True)

        # ------------------------------------------------------------------
        # Step 7: Worker execution and file recycling
        # ------------------------------------------------------------------
        print("\nStep 7: Executing cleanup worker (recycling 2 files) ...", flush=True)
        paths_to_recycle = [f.path for f in extras]
        assert all(os.path.exists(p) for p in paths_to_recycle)

        # Start cleanup directly bypassing the modal dialog exec() for automated headless test
        page._prog_bar.setValue(0)
        page._prog_stage_lbl.setText("Moving files to Recycle Bin...")
        page._prog_count_lbl.setText(f"0 / {len(page._current_plan.items)}")
        page._prog_card.show()
        page._summary_card.hide()
        page._result_card.hide()
        page._cancel_btn.setEnabled(True)

        page._worker = CleanupWorker(page._current_plan, parent=page)
        page._worker.progress.connect(page._on_worker_progress)
        page._worker.finished.connect(page._on_worker_finished)
        page._worker.failed.connect(page._on_worker_failed)
        page._worker.start()

        _wait_for_worker(page)

        # Verify UI state
        assert not page._prog_card.isVisible(), "Progress card should be hidden after finish"
        assert page._result_card.isVisible(), "Result card should be visible"
        clean_hdr = page._result_hdr.text().encode("ascii", errors="replace").decode("ascii")
        print(f"  PASS -- UI result card shows: '{clean_hdr}'", flush=True)

        # ------------------------------------------------------------------
        # Step 8: File system verification
        # ------------------------------------------------------------------
        print("\nStep 8: Verifying file system state ...", flush=True)
        for p in paths_to_recycle:
            assert not os.path.exists(p), f"Recycled file still exists at {p}!"
        assert os.path.exists(oldest.path), f"Kept copy does not exist at {oldest.path}!"
        print(f"  PASS -- Recycled 2 files, kept copy still intact at: {os.path.basename(oldest.path)}", flush=True)

        # ------------------------------------------------------------------
        # Step 9: app_state updates
        # ------------------------------------------------------------------
        print("\nStep 9: Verifying app_state updates ...", flush=True)
        latest_scan = app_state.get_latest_scan()
        assert latest_scan is not None
        assert len(latest_scan.files) == 17 - 2, f"Expected 15 files in scan, got {len(latest_scan.files)}"

        latest_dup = app_state.get_latest_duplicates()
        assert latest_dup is not None
        # Group A should now be removed from duplicate groups since only 1 copy remains
        group_a_after = [g for g in latest_dup.groups if g.group_id == group_a.group_id]
        assert len(group_a_after) == 0, "Group A should have been removed since only 1 copy remains"

        pending_after = app_state.get_pending_cleanup()
        assert len(pending_after) == 0, f"pending_cleanup should be empty, got {len(pending_after)}"
        print("  PASS -- app_state updated: scan files reduced, group removed, pending cleared.", flush=True)

        # ------------------------------------------------------------------
        # Step 10: Log file verification
        # ------------------------------------------------------------------
        print("\nStep 10: Verifying cleanup_log.jsonl ...", flush=True)
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        log_path = Path(local_app_data) / "OmniStore" / "cleanup_log.jsonl"
        assert log_path.exists(), f"Log file {log_path} does not exist"
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) > 0, "Log file is empty"
        print(f"  PASS -- cleanup_log.jsonl exists and has {len(lines)} entry/entries.", flush=True)

        page.close()

    except Exception as exc:
        import traceback
        traceback.print_exc()
        failures.append(str(exc))
    finally:
        print(f"\nCleaning up temp copy {tmp_root} ...", flush=True)
        try:
            from send2trash import send2trash
            send2trash(str(tmp_root))
        except Exception:
            pass

    print("\n" + "=" * 72, flush=True)
    if failures:
        print(f"FAILURES ({len(failures)}):", flush=True)
        for f in failures:
            print(f"  - {f}", flush=True)
        print("\nTEST RESULT: FAIL", flush=True)
        return False
    else:
        print("ALL CLEANUP UI AND INTEGRATION TESTS PASSED SUCCESSFULLY!", flush=True)
        print("TEST RESULT: PASS", flush=True)
        print("=" * 72, flush=True)
        return True


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
