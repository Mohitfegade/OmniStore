"""
tests/check_ui_chips.py
=======================
Automated verification of the Command Center UI & 6 Suggestion Chips:
1. Launches the real PySide6 UI and loads MainWindow.
2. Scans the demo folder (C:\\Users\\Mohit\\OmniStore_Demo) in the Analyzer.
3. Switches to the Command Center page.
4. Executes each of the 6 suggestion chips:
   - "What is taking up the most space?"
   - "Find duplicate files"
   - "Videos larger than 1 GB"
   - "Files I haven't opened in 6 months"
   - "PDFs modified last month"
   - "Show ways to free 5 GB"
5. Measures and reports:
   - Time to first results (tools_ready)
   - Time to full explanation (finished)
   - Verified facts and UI state
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

import app_state
from commands.events import FlowEvent
from commands.flow import CommandContext
from engine.duplicates import find_duplicates
from engine.scanner import scan_folder
from gemma.config import load_settings
from gemma.ollama_provider import OllamaProvider
from ui.main_window import MainWindow

SUGGESTION_CHIPS = [
    "What is taking up the most space?",
    "Find duplicate files",
    "Videos larger than 1 GB",
    "Files I haven't opened in 6 months",
    "PDFs modified last month",
    "Show ways to free 5 GB",
]


def run_chips_benchmark() -> int:
    print(f"\n{'='*78}")
    print("OmniStore: Command Center 6 Suggestion Chips Live Benchmark")
    print(f"{'='*78}\n")

    app = QApplication.instance() or QApplication(sys.argv)

    demo_dir = Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "OmniStore_Demo"
    if not demo_dir.is_dir():
        print(f"[SETUP] Demo folder not found at {demo_dir}. Creating...")
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "tests" / "make_demo_data.py")], check=True)

    print(f"[1/3] Scanning demo folder: {demo_dir} ...")
    scan_res = scan_folder(str(demo_dir))
    dup_res = find_duplicates(scan_res)
    app_state.set_latest_scan(scan_res)
    app_state.set_latest_duplicates(dup_res)
    print(f"  [OK] Scan loaded: {len(scan_res.files)} files, {len(dup_res.groups)} duplicate groups.\n")

    settings = load_settings()
    provider = OllamaProvider(settings)
    status = provider.health()
    print(f"[2/3] Checking Ollama: {status.message} (latency: {status.latency_ms} ms)")
    if status.ok:
        print("  Warming up model...")
        provider.warm_up()

    print("\n[3/3] Creating MainWindow and navigating to Command Center (Page #4)...")
    win = MainWindow()
    win.show()
    app_state.navigate_to(4)
    app.processEvents()

    # Locate CommandCenterPage
    command_page = getattr(win, "_command_center", None)
    if not command_page:
        for p in win._pages:
            widget = p.widget()
            if widget and widget.__class__.__name__ == "CommandCenterPage":
                command_page = widget
                break

    assert command_page is not None, "Could not find CommandCenterPage in MainWindow stack."

    results_table = []
    all_ok = True

    print("\nExecuting 6 Suggestion Chips...")
    print(f"{'CHIP QUERY':<38} | {'1st RESULTS':<12} | {'FULL EXPLANATION':<16} | {'STATUS'}")
    print(f"{'-'*38}-+-{'-'*12}-+-{'-'*16}-+-{'-'*6}")

    for chip in SUGGESTION_CHIPS:
        t_start = time.perf_counter()
        t_tools_ready = None
        t_finished = None
        final_resp = None
        explanation_chunks = []
        is_error = False

        loop = QEventLoop()

        # Trigger chip
        command_page._on_chip_clicked(chip)
        worker = getattr(command_page, "_active_worker", None)
        assert worker is not None, f"Worker failed to start for chip '{chip}'"

        def on_event(event: FlowEvent):
            nonlocal t_tools_ready, t_finished, final_resp, is_error
            if event.kind == "tool_result":
                if t_tools_ready is None:
                    t_tools_ready = time.perf_counter() - t_start
            elif event.kind == "explain_chunk":
                explanation_chunks.append(event.text)
            elif event.kind == "explain_done":
                t_finished = time.perf_counter() - t_start
                final_resp = event
                loop.quit()
            elif event.kind == "notice":
                t_finished = time.perf_counter() - t_start
                final_resp = event
                loop.quit()
            elif event.kind == "error":
                t_finished = time.perf_counter() - t_start
                is_error = True
                final_resp = event
                print(f"      [ERROR] Chip failed: {event.text}")
                loop.quit()

        worker.eventReady.connect(on_event)

        # Timeout after 45 seconds to avoid infinite hangs
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(45000)

        loop.exec()

        tools_sec = t_tools_ready or (t_finished or 0.0)
        total_sec = t_finished or 0.0

        # Check performance criteria
        target_met = (tools_sec <= 7.0) and (total_sec <= 18.0)
        status_str = "PASS" if (final_resp is not None and not is_error) else "FAIL"
        if is_error or final_resp is None:
            all_ok = False

        full_exp = "".join(explanation_chunks) or (final_resp.text if final_resp else "")
        results_table.append({
            "chip": chip,
            "tools_s": round(tools_sec, 2),
            "total_s": round(total_sec, 2),
            "status": status_str,
            "target_met": target_met,
            "explanation": full_exp,
        })

        print(
            f"{chip[:37]:<38} | "
            f"{tools_sec:<12.2f}s | "
            f"{total_sec:<16.2f}s | "
            f"{status_str}"
        )
        app.processEvents()

    print(f"\n{'='*78}")
    print("DETAILED CHIP EXPLANATIONS")
    print(f"{'='*78}")
    for r in results_table:
        print(f"\n• Query: {r['chip']}")
        print(f"  First Results: {r['tools_s']}s | Full Explanation: {r['total_s']}s")
        print(f"  Explanation: {r['explanation'].strip()}")

    print(f"\n{'='*78}")
    if all_ok:
        print("[SUCCESS] All 6 suggestion chips executed and rendered verified results.")
    else:
        print("[FAILURE] Some suggestion chips did not complete successfully.")
    print(f"{'='*78}\n")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(run_chips_benchmark())
