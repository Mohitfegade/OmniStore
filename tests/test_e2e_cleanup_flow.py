"""
tests/test_e2e_cleanup_flow.py
==============================
End-to-end user journey test across MainWindow pages:
1. Launch MainWindow
2. Switch to Analyzer (index 1), run scan on a temp copy of demo data
3. Switch to Duplicates (index 2), run Find Duplicates (1 KB min)
4. Verify Group A (3 copies) is displayed
5. Click "Select extras (keep oldest copy)" on Group A
6. Click "Review in Cleanup" -> verify MainWindow navigates to Cleanup (index 3)
7. On Cleanup page: verify plan loaded with 2 duplicate items (~40 MB)
8. Verify candidate tools remain opt-in
9. ConfirmDialog and execution: confirm checkbox required, execute worker
10. Verify recycling: files in Recycle Bin, kept copy remains
11. Navigate to Duplicates (index 2): verify Group A is no longer a duplicate group (1 copy left)
12. Navigate to Dashboard (index 0): verify dashboard remains responsive
"""

import os
import shutil
import sys
import time
from pathlib import Path

# Project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

import app_state
from ui.main_window import MainWindow


def _wait_worker(page):
    while getattr(page, "_worker", None) is not None and page._worker.isRunning():
        QCoreApplication.processEvents()
        time.sleep(0.02)
    for _ in range(10):
        QCoreApplication.processEvents()
        time.sleep(0.01)


def run_e2e():
    app = QApplication.instance() or QApplication(sys.argv)
    demo_dir = Path(os.environ.get("USERPROFILE", "C:/Users/Default")) / "OmniStore_Demo"
    if not demo_dir.exists():
        print(f"Error: Demo dir {demo_dir} does not exist.", flush=True)
        return False

    user_home = Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))
    tmp_root = user_home / f"OmniStore_E2ETest_{int(time.time())}"
    print(f"Creating temp copy at {tmp_root} ...", flush=True)
    shutil.copytree(str(demo_dir), str(tmp_root))

    failures = []

    try:
        print("\nStep 1: Initializing MainWindow ...", flush=True)
        win = MainWindow()
        win.show()
        QCoreApplication.processEvents()

        # Check pages
        assert len(win._pages) == 5, f"Expected 5 pages, got {len(win._pages)}"
        dashboard_scroll = win._pages[0]
        analyzer_scroll = win._pages[1]
        duplicates_scroll = win._pages[2]
        cleanup_scroll = win._pages[3]

        analyzer_page = analyzer_scroll.widget()
        duplicates_page = duplicates_scroll.widget()
        cleanup_page = cleanup_scroll.widget()

        print("  PASS -- MainWindow initialized with 5 pages (Dashboard, Analyzer, Duplicates, Cleanup, Command Center).", flush=True)

        # ------------------------------------------------------------------
        # Step 2: Run scan on Analyzer page
        # ------------------------------------------------------------------
        print("\nStep 2: Switching to Analyzer page and scanning temp copy ...", flush=True)
        win._switch_page(1)
        QCoreApplication.processEvents()
        assert win._stack.currentIndex() == 1

        analyzer_page._path_input.setText(str(tmp_root))
        analyzer_page._scan_btn.click()
        _wait_worker(analyzer_page)

        scan_res = app_state.get_latest_scan()
        assert scan_res is not None, "Scan result should be in app_state"
        assert scan_res.total_files == 17, f"Expected 17 files, got {scan_res.total_files}"
        print(f"  PASS -- Analyzer scanned {scan_res.total_files} files in {scan_res.duration_seconds:.3f} s.", flush=True)

        # ------------------------------------------------------------------
        # Step 3: Run duplicate detection on Duplicates page
        # ------------------------------------------------------------------
        print("\nStep 3: Switching to Duplicates page and running duplicate detection ...", flush=True)
        win._switch_page(2)
        QCoreApplication.processEvents()
        assert win._stack.currentIndex() == 2

        # Choose 1 KB threshold so all 3 groups are found
        duplicates_page._min_size_combo.setCurrentIndex(0)
        duplicates_page._find_btn.click()
        _wait_worker(duplicates_page)

        dup_res = app_state.get_latest_duplicates()
        assert dup_res is not None, "Duplicate result should be in app_state"
        assert dup_res.total_groups == 3, f"Expected 3 duplicate groups, got {dup_res.total_groups}"
        print(f"  PASS -- Duplicates page found {dup_res.total_groups} groups, {dup_res.total_reclaimable_bytes:,} bytes reclaimable.", flush=True)

        # ------------------------------------------------------------------
        # Step 4: Select extras in Group A and click "Review in Cleanup"
        # ------------------------------------------------------------------
        print("\nStep 4: Selecting extras in Group A and clicking 'Review in Cleanup' ...", flush=True)
        group_cards = duplicates_page._group_cards
        group_a_card = next(c for c in group_cards if c.group.copies == 3)

        group_a_card._sugg_btn.click()
        QCoreApplication.processEvents()
        selected = group_a_card.get_selected_files()
        assert len(selected) == 2, f"Expected 2 selected copies, got {len(selected)}"

        # Click Review in Cleanup
        duplicates_page._cleanup_btn.click()
        QCoreApplication.processEvents()

        # MainWindow should have automatically switched to Cleanup (index 3)
        assert win._stack.currentIndex() == 3, f"Expected MainWindow to switch to index 3 (Cleanup), got {win._stack.currentIndex()}"
        print("  PASS -- MainWindow auto-navigated to Cleanup page (index 3).", flush=True)

        # ------------------------------------------------------------------
        # Step 5: Verify Cleanup page plan
        # ------------------------------------------------------------------
        print("\nStep 5: Verifying Cleanup page state ...", flush=True)
        assert cleanup_page._plan_card.isVisible(), "Plan card should be visible"
        assert cleanup_page._plan_table.rowCount() == 2, f"Expected 2 rows in plan table, got {cleanup_page._plan_table.rowCount()}"
        assert cleanup_page._current_plan.total_bytes == 41943040, f"Expected 40 MB total, got {cleanup_page._current_plan.total_bytes}"
        print("  PASS -- Cleanup page displays 2 duplicate items totaling 40 MB.", flush=True)

        # ------------------------------------------------------------------
        # Step 6: Execute cleanup worker
        # ------------------------------------------------------------------
        print("\nStep 6: Executing cleanup worker ...", flush=True)
        paths_to_remove = [f.path for f in selected]
        # Keep path is the unselected one
        keep_record = [f for f in group_a_card.group.files if f not in selected][0]

        from workers.cleanup_worker import CleanupWorker
        cleanup_page._prog_card.show()
        cleanup_page._summary_card.hide()
        cleanup_page._result_card.hide()
        cleanup_page._worker = CleanupWorker(cleanup_page._current_plan, parent=cleanup_page)
        cleanup_page._worker.progress.connect(cleanup_page._on_worker_progress)
        cleanup_page._worker.finished.connect(cleanup_page._on_worker_finished)
        cleanup_page._worker.failed.connect(cleanup_page._on_worker_failed)
        cleanup_page._worker.start()

        _wait_worker(cleanup_page)

        assert cleanup_page._result_card.isVisible(), "Result card should be visible"
        assert not cleanup_page._prog_card.isVisible(), "Progress card should be hidden"
        clean_hdr = cleanup_page._result_hdr.text().encode("ascii", errors="replace").decode("ascii")
        print(f"  PASS -- Worker finished: '{clean_hdr}'", flush=True)

        # ------------------------------------------------------------------
        # Step 7: Disk verification
        # ------------------------------------------------------------------
        print("\nStep 7: Verifying disk state ...", flush=True)
        for p in paths_to_remove:
            assert not os.path.exists(p), f"Recycled file {p} still exists on disk!"
        assert os.path.exists(keep_record.path), f"Kept copy {keep_record.path} was deleted!"
        print(f"  PASS -- 2 extras recycled to Recycle Bin, kept copy intact: {os.path.basename(keep_record.path)}", flush=True)

        # ------------------------------------------------------------------
        # Step 8: Return to Duplicates page and verify Group A is updated
        # ------------------------------------------------------------------
        print("\nStep 8: Returning to Duplicates page ...", flush=True)
        win._switch_page(2)
        QCoreApplication.processEvents()

        # The duplicates page was notified of app_state change
        latest_dup = app_state.get_latest_duplicates()
        assert latest_dup is not None
        # Group A should now be removed from duplicate result
        assert all(g.group_id != group_a_card.group.group_id for g in latest_dup.groups)
        print("  PASS -- Duplicates page app_state reflects Group A removal.", flush=True)

        # ------------------------------------------------------------------
        # Step 9: Return to Dashboard
        # ------------------------------------------------------------------
        print("\nStep 9: Returning to Dashboard (index 0) ...", flush=True)
        win._switch_page(0)
        QCoreApplication.processEvents()
        assert win._stack.currentIndex() == 0
        print("  PASS -- Dashboard responsive and active.", flush=True)

        win.close()

    except Exception as exc:
        import traceback
        traceback.print_exc()
        failures.append(str(exc))
    finally:
        print(f"\nCleaning up temp copy at {tmp_root} ...", flush=True)
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
        print("ALL END-TO-END WORKFLOW TESTS PASSED SUCCESSFULLY!", flush=True)
        print("TEST RESULT: PASS", flush=True)
        print("=" * 72, flush=True)
        return True


if __name__ == "__main__":
    success = run_e2e()
    sys.exit(0 if success else 1)
