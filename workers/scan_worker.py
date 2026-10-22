"""
workers/scan_worker.py
======================
Background QThread worker for folder scanning.
Runs engine.scanner.scan_folder off the main thread so the UI remains 100% responsive.
"""

from __future__ import annotations

import logging
import traceback
from typing import Optional

from PySide6.QtCore import QThread, Signal

from engine.models import ScanResult
from engine.scanner import scan_folder

log = logging.getLogger(__name__)


class ScanWorker(QThread):
    """
    Background worker thread that runs scan_folder.

    Signals
    -------
    progress(int, int, str)
        Emitted during scan: (files_scanned, bytes_scanned, current_folder)
    scan_finished(object)
        Emitted when scan finishes (normally or cancelled) with ScanResult
    failed(str)
        Emitted if an unhandled exception occurs
    """

    progress: Signal = Signal(int, int, str)
    scan_finished: Signal = Signal(object)
    failed: Signal = Signal(str)

    def __init__(self, root_path: str, parent: Optional[QThread] = None) -> None:
        super().__init__(parent)
        self._root_path = root_path
        self._is_cancelled = False

    def cancel(self) -> None:
        """Request the worker to stop scanning as soon as possible."""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def run(self) -> None:
        try:
            result = scan_folder(
                root=self._root_path,
                progress_cb=self._on_progress,
                cancel_check=self.is_cancelled,
            )
            self.scan_finished.emit(result)
        except Exception:
            err_msg = traceback.format_exc()
            log.error("ScanWorker unhandled exception:\n%s", err_msg)
            self.failed.emit("An unexpected error occurred during scan:\n" + err_msg)

    def _on_progress(self, files: int, bytes_count: int, curr_folder: str) -> None:
        self.progress.emit(files, bytes_count, curr_folder)
