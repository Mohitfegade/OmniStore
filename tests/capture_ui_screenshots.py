"""
tests/capture_ui_screenshots.py
================================
Drives the OmniStore UI to capture screenshots:
1. Command Center with Gemma on ("What is taking the most space?", "I need 1 GB free")
2. Command Center in Basic mode ("What is taking the most space?", "I need 1 GB free")
3. Dashboard page
4. Cleanup page
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Add project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import app_state
from engine.duplicates import find_duplicates
from engine.scanner import scan_folder
from ui.main_window import MainWindow
from ui.theme import apply_theme

ARTIFACT_DIR = Path(r"C:\Users\Mohit\.gemini\antigravity-ide\brain\b50c061e-8a9d-40e0-8172-7da12db1f5c6")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def wait_until_worker_done(cc_page, timeout_s: float = 25.0) -> None:
    app = QApplication.instance()
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout_s:
        app.processEvents()
        if cc_page._active_worker is None or not cc_page._active_worker.isRunning():
            # Extra wait for UI update
            for _ in range(10):
                time.sleep(0.05)
                app.processEvents()
            return
        time.sleep(0.05)
    print("Warning: worker did not finish within timeout")


def run() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)

    print("Scanning demo directory...")
    user_home = Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))
    demo_dir = user_home / "OmniStore_Demo"
    scan_res = scan_folder(str(demo_dir))
    dup_res = find_duplicates(scan_res)

    app_state.set_latest_scan(scan_res)
    app_state.set_latest_duplicates(dup_res)

    window = MainWindow()
    window.resize(1280, 820)
    window.show()

    app.processEvents()
    time.sleep(0.5)
    app.processEvents()

    cc = window._command_center
    assert cc is not None, "CommandCenterPage not found"

    # 1. Switch to Command Center
    print("Navigating to Command Center...")
    window._switch_page(4)
    app.processEvents()
    time.sleep(0.3)

    # Question 1 with Gemma
    print("Querying: 'What is taking the most space?' (Gemma)...")
    cc._input.setText("What is taking the most space?")
    cc._on_send()
    wait_until_worker_done(cc)

    # Question 2 with Gemma
    print("Querying: 'I need 1 GB free' (Gemma)...")
    cc._input.setText("I need 1 GB free")
    cc._on_send()
    wait_until_worker_done(cc)

    # Capture Screenshot 1: Command Center with Gemma on
    p1 = ARTIFACT_DIR / "screenshot_command_center_gemma.png"
    window.grab().save(str(p1))
    print(f"Saved: {p1}")

    # 2. Turn Gemma OFF -> Basic Mode
    print("\nSwitching to Basic Mode (Gemma offline)...")
    cc.set_gemma_available(False)
    app.processEvents()

    # Clear previous conversation or let it append to show Basic badge
    print("Querying: 'What is taking the most space?' (Basic)...")
    cc._input.setText("What is taking the most space?")
    cc._on_send()
    wait_until_worker_done(cc, timeout_s=5.0)

    print("Querying: 'I need 1 GB free' (Basic)...")
    cc._input.setText("I need 1 GB free")
    cc._on_send()
    wait_until_worker_done(cc, timeout_s=5.0)

    # Capture Screenshot 2: Command Center in Basic mode
    p2 = ARTIFACT_DIR / "screenshot_command_center_basic.png"
    window.grab().save(str(p2))
    print(f"Saved: {p2}")

    # 3. Dashboard Page
    print("\nNavigating to Dashboard...")
    window._switch_page(0)
    for _ in range(10):
        time.sleep(0.05)
        app.processEvents()
    p3 = ARTIFACT_DIR / "screenshot_dashboard.png"
    window.grab().save(str(p3))
    print(f"Saved: {p3}")

    # 4. Cleanup Page
    print("\nNavigating to Cleanup...")
    window._switch_page(3)
    for _ in range(10):
        time.sleep(0.05)
        app.processEvents()
    p4 = ARTIFACT_DIR / "screenshot_cleanup.png"
    window.grab().save(str(p4))
    print(f"Saved: {p4}")

    print("\nAll 4 screenshots captured successfully.")
    window.close()


if __name__ == "__main__":
    run()
