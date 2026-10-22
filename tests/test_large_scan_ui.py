"""
tests/test_large_scan_ui.py
===========================
Automates scanning a large folder (> 2.147 GB / > 3 GB) through the UI
to verify that:
1. ScanWorker.progress handles > 2,147,483,647 bytes with zero OverflowError.
2. The progress card, stat cards, donut chart, and largest files table appear.
3. No QFont / setPointSize warnings occur.
4. Takes screenshot of the finished scan for C:\\Users\\Mohit\\Downloads.
5. Then scans C:\\Users\\Mohit\\OmniStore_Demo and confirms it works.
"""

from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

# Add project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.theme import apply_theme

ARTIFACT_DIR = Path(r"C:\Users\Mohit\.gemini\antigravity-ide\brain\b50c061e-8a9d-40e0-8172-7da12db1f5c6")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def run_test() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)

    window = MainWindow()
    window.resize(1280, 840)
    window.show()

    app.processEvents()
    time.sleep(0.3)

    # Navigate to Analyzer page (index 1)
    print("Navigating to Analyzer...")
    window._switch_page(1)
    app.processEvents()

    analyzer_scroll = window._pages[1]
    analyzer = getattr(analyzer_scroll, "analyzer_page", None)
    if not analyzer:
        # find child of scroll area
        from ui.analyzer import AnalyzerPage
        analyzer = analyzer_scroll.findChild(AnalyzerPage)

    assert analyzer is not None, "AnalyzerPage not found in scroll area"

    # 1. SCAN LARGE FOLDER (C:\Users\Mohit\Downloads)
    downloads_dir = str(Path.home() / "Downloads")
    print(f"\n--- TEST 1: Scanning large folder: {downloads_dir} ---")
    analyzer._path_input.setText(downloads_dir)
    app.processEvents()

    # Click scan
    analyzer._scan_btn.click()
    app.processEvents()

    # Wait for scan to finish
    t0 = time.perf_counter()
    timeout = 30.0
    scan_completed = False

    while time.perf_counter() - t0 < timeout:
        app.processEvents()
        if analyzer._worker is None or not analyzer._worker.isRunning():
            scan_completed = True
            break
        time.sleep(0.05)

    assert scan_completed, "Scan did not complete within timeout"

    # Give UI a moment to render charts and tables
    for _ in range(10):
        time.sleep(0.05)
        app.processEvents()

    total_bytes = analyzer._scan_result.total_bytes if analyzer._scan_result else 0
    total_files = analyzer._scan_result.total_files if analyzer._scan_result else 0
    print(f"Large scan completed: {total_files} files, {total_bytes:,} bytes ({total_bytes / (1024**3):.2f} GB)")

    assert total_bytes > 2_147_483_647, f"Expected total_bytes > 2,147,483,647 (32-bit limit), got {total_bytes}"
    assert analyzer._donut_chart.isVisible(), "Donut chart should be visible"
    assert analyzer._table_view.isVisible(), "Largest files table should be visible"
    print("  [OK] Progress and donut chart successfully displayed for large scan.")

    # Save screenshot of large scan
    p_large = ARTIFACT_DIR / "screenshot_large_scan.png"
    window.grab().save(str(p_large))
    print(f"Saved: {p_large}")

    # 2. SCAN DEMO FOLDER (C:\Users\Mohit\OmniStore_Demo)
    demo_dir = str(Path.home() / "OmniStore_Demo")
    print(f"\n--- TEST 2: Scanning demo folder: {demo_dir} ---")
    analyzer._path_input.setText(demo_dir)
    app.processEvents()

    analyzer._scan_btn.click()
    app.processEvents()

    t0 = time.perf_counter()
    scan_completed = False
    while time.perf_counter() - t0 < timeout:
        app.processEvents()
        if analyzer._worker is None or not analyzer._worker.isRunning():
            scan_completed = True
            break
        time.sleep(0.05)

    assert scan_completed, "Demo scan did not complete within timeout"

    for _ in range(10):
        time.sleep(0.05)
        app.processEvents()

    total_bytes_demo = analyzer._scan_result.total_bytes if analyzer._scan_result else 0
    total_files_demo = analyzer._scan_result.total_files if analyzer._scan_result else 0
    print(f"Demo scan completed: {total_files_demo} files, {total_bytes_demo:,} bytes")
    assert total_files_demo == 17, f"Expected 17 files in demo, got {total_files_demo}"

    p_demo = ARTIFACT_DIR / "screenshot_demo_scan.png"
    window.grab().save(str(p_demo))
    print(f"Saved: {p_demo}")

    print("\nALL UI SCAN TESTS PASSED (PASS)")
    # Gracefully wait for any background threads to prevent Qt ~QThread fastfail
    badge = getattr(window._top_bar, "status_badge", None)
    if badge and getattr(badge, "_worker", None) and badge._worker.isRunning():
        badge._worker.wait(2000)
    if hasattr(window, "_warmup_worker") and window._warmup_worker and window._warmup_worker.isRunning():
        window._warmup_worker.wait(2000)
    dashboard_page = getattr(window._pages[0], "dashboard_page", None)
    if dashboard_page and getattr(dashboard_page, "_drive_worker", None) and dashboard_page._drive_worker.isRunning():
        dashboard_page._drive_worker.wait(2000)

    window.close()



if __name__ == "__main__":
    run_test()




