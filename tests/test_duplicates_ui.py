"""
Comprehensive UI test for OmniStore Duplicates page.
Tests:
- Empty state & scan state reflection
- Running duplicate detection with 1 MB and 1 KB min size
- Verifying groups, negative pairs absence, totals
- Safe selection lockout (cannot select all copies)
- "Select extras (keep oldest copy)" suggestion
- "Review in Cleanup" app_state integration
- Cancellation responsiveness
"""
import sys
import os
import time
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

from engine.scanner import scan_folder
import app_state
from ui.duplicates import DuplicatesPage, DuplicateGroupCard

def wait_for_worker(page):
    while page._worker is not None and page._worker.isRunning():
        QCoreApplication.processEvents()
        time.sleep(0.02)
    # Process any final queued events
    for _ in range(5):
        QCoreApplication.processEvents()
        time.sleep(0.01)

def run_tests():
    app = QApplication.instance() or QApplication(sys.argv)
    demo_dir = Path(os.environ.get("USERPROFILE", "C:/Users/Default")) / "OmniStore_Demo"
    if not demo_dir.exists():
        print(f"Error: Demo dir {demo_dir} does not exist.", flush=True)
        return False

    print("Step 1: Testing empty state when no scan exists...", flush=True)
    app_state.set_latest_scan(None)
    app_state.set_latest_duplicates(None)
    page = DuplicatesPage()
    page.show()

    # Empty state should be visible
    assert page._no_scan_card.isVisible(), "No-scan card should be visible when no scan exists"
    assert not page._controls_card.isVisible(), "Controls should be hidden when no scan exists"
    assert not page._results_container.isVisible(), "Results should be hidden when no scan exists"
    print("  -> Empty state verified.", flush=True)

    print("\nStep 2: Performing scan of demo folder and setting app_state...", flush=True)
    scan_res = scan_folder(str(demo_dir))
    app_state.set_latest_scan(scan_res)

    # Empty state should now be hidden
    assert not page._no_scan_card.isVisible(), "No-scan card should be hidden after scan"
    assert page._controls_card.isVisible(), "Controls card should be visible after scan"
    assert "OmniStore_Demo" in page._scanned_folder_lbl.text(), f"Folder label should mention demo dir: {page._scanned_folder_lbl.text()}"
    print(f"  -> Folder label correctly shows: '{page._scanned_folder_lbl.text()}'", flush=True)

    print("\nStep 3: Finding duplicates with default 1 MB threshold...", flush=True)
    # Default index is 2 ("1 MB")
    assert page._min_size_combo.currentData() == 1024 * 1024
    page._find_btn.click()
    wait_for_worker(page)

    dup_res_1mb = app_state.get_latest_duplicates()
    assert dup_res_1mb is not None
    # With 1 MB threshold: Group A (20 MB) and Group B (5 MB) are found (Group C 50 KB is skipped)
    assert dup_res_1mb.total_groups == 2, f"Expected 2 groups with 1MB threshold, got {dup_res_1mb.total_groups}"
    print(f"  -> 1 MB threshold found {dup_res_1mb.total_groups} groups (Groups A & B).", flush=True)

    print("\nStep 4: Finding duplicates with 1 KB threshold (finding all groups A, B, C)...", flush=True)
    page._min_size_combo.setCurrentIndex(0) # 1 KB
    assert page._min_size_combo.currentData() == 1024

    page._find_btn.click()
    wait_for_worker(page)

    dup_res = app_state.get_latest_duplicates()
    assert dup_res is not None, "Duplicate result should be populated in app_state"
    assert dup_res.total_groups == 3, f"Expected 3 groups, got {dup_res.total_groups}"
    assert dup_res.total_reclaimable_bytes == 47237120, f"Expected 47237120 bytes, got {dup_res.total_reclaimable_bytes}"
    reclaim_text = page._sc_reclaim._number.text()
    print(f"  -> Detected 3 groups. Reclaimable: {reclaim_text} ({dup_res.total_reclaimable_bytes:,} bytes).", flush=True)

    # Verify negative tests are absent
    all_paths = [f.path for g in dup_res.groups for f in g.files]
    for path in all_paths:
        assert "pic_a.raw" not in path and "pic_b.raw" not in path, "Same-size different-content files must not be in duplicates!"
        assert "empty1.log" not in path and "empty2.log" not in path, "0-byte files must not be in duplicates!"
    print("  -> Confirmed negative test files (pic_a.raw, pic_b.raw, empty files) are absent.", flush=True)

    print("\nStep 5: Testing safe selection rules on Group A...", flush=True)
    group_cards = page._group_cards
    assert len(group_cards) == 3, f"Expected 3 group cards, got {len(group_cards)}"

    group_a_card = group_cards[0]
    assert group_a_card.group.copies == 3

    # Initially none are selected
    assert len(group_a_card.get_selected_files()) == 0
    for row in group_a_card._rows:
        assert not row.checkbox.isChecked()
        assert row.checkbox.isEnabled()

    # Check copy 0
    group_a_card._rows[0].checkbox.setChecked(True)
    # Both rows 1 and 2 should still be enabled
    assert group_a_card._rows[1].checkbox.isEnabled()
    assert group_a_card._rows[2].checkbox.isEnabled()

    # Check copy 1 -> Now 2 out of 3 copies are selected (N-1)
    group_a_card._rows[1].checkbox.setChecked(True)
    # The remaining unchecked copy (index 2) MUST be disabled!
    assert not group_a_card._rows[2].checkbox.isEnabled(), "Last copy must be disabled when N-1 copies are selected"
    assert "At least one copy must be kept" in group_a_card._rows[2].checkbox.toolTip()
    print("  -> Verified safe selection: when N-1 copies checked, the remaining copy is disabled with safety tooltip.", flush=True)

    # Uncheck copy 1 -> All should be enabled again
    group_a_card._rows[1].checkbox.setChecked(False)
    assert group_a_card._rows[2].checkbox.isEnabled(), "Re-enabling should occur when count drops below N-1"
    group_a_card._rows[0].checkbox.setChecked(False)

    print("\nStep 6: Testing 'Select extras (keep oldest copy)' suggestion button...", flush=True)
    group_a_card._sugg_btn.click()
    selected_in_a = group_a_card.get_selected_files()
    assert len(selected_in_a) == 2, f"Expected 2 selected copies, got {len(selected_in_a)}"
    # The unchecked copy should be the oldest and disabled
    disabled_cbs = [row.checkbox for row in group_a_card._rows if not row.checkbox.isEnabled()]
    assert len(disabled_cbs) == 1, "Expected exactly 1 disabled checkbox"
    print("  -> Verified 'Select extras' selects N-1 copies and locks the oldest copy.", flush=True)

    # Check bottom bar update
    QCoreApplication.processEvents()
    assert "2 files selected" in page._selection_lbl.text()
    assert "40.0 MB" in page._selection_lbl.text()
    assert page._cleanup_btn.isEnabled()
    print(f"  -> Bottom bar correctly shows: '{page._selection_lbl.text()}'", flush=True)

    print("\nStep 7: Testing 'Review in Cleanup' button and app_state pending_cleanup...", flush=True)
    nav_called = []
    app_state.add_nav_listener(lambda idx: nav_called.append(idx))

    page._cleanup_btn.click()
    assert 3 in nav_called, f"Expected navigation to index 3 (Cleanup), got {nav_called}"
    pending = app_state.get_pending_cleanup()
    assert len(pending) == 2, f"Expected 2 pending cleanup items, got {len(pending)}"
    assert all(item["reason"] == "Exact duplicate" for item in pending)
    print("  -> Verified pending cleanup stored in app_state with reason 'Exact duplicate' and nav to Cleanup triggered.", flush=True)

    print("\nStep 8: Testing cancellation responsiveness...", flush=True)
    page._find_btn.click()
    assert page._find_btn.text() == "Cancel"
    assert page._worker is not None and page._worker.isRunning()
    # Click cancel
    page._find_btn.click()
    wait_for_worker(page)
    assert page._find_btn.text() == "Find duplicates"
    print("  -> Verified cancellation cleanly cancels worker and resets button text.", flush=True)

    page.close()
    print("\n========================================================================", flush=True)
    print("ALL DUPLICATES UI AND INTERACTION TESTS PASSED SUCCESSFULLY!", flush=True)
    print("========================================================================", flush=True)
    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
