"""
workers/duplicate_worker.py
===========================
Background QThread worker for finding exact duplicate files.
Runs engine.duplicates.find_duplicates off the main thread so the UI remains 100% responsive.
"""

from __future__ import annotations

import logging
import traceback
from typing import Optional

from PySide6.QtCore import QThread, Signal

import app_state
from engine.duplicates import DuplicateResult, find_duplicates
from engine.models import ScanResult

log = logging.getLogger(__name__)


class DuplicateWorker(QThread):
    """
    Background worker thread that runs find_duplicates.

    Signals
    -------
    progress(str, object, object, object)
        Emitted during analysis: (stage_name, items_done, items_total, bytes_hashed)
    finished(object)
        Emitted when duplicate analysis completes with DuplicateResult
    failed(str)
        Emitted if an unhandled exception occurs
    """

    progress: Signal = Signal(str, object, object, object)
    finished: Signal = Signal(object)
    failed: Signal = Signal(str)

    def __init__(
        self,
        scan_result: Optional[ScanResult] = None,
        min_size_bytes: int = 1024 * 1024,
        parent: Optional[QThread] = None,
    ) -> None:
        super().__init__(parent)
        self._scan_result = scan_result or app_state.get_latest_scan()
        self._min_size_bytes = min_size_bytes
        self._is_cancelled = False

    def cancel(self) -> None:
        """Request the worker to stop duplicate detection."""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def run(self) -> None:
        if not self._scan_result:
            self.failed.emit("No scan data available. Please scan a folder in the Analyzer first.")
            return

        try:
            result = find_duplicates(
                scan_result=self._scan_result,
                min_size_bytes=self._min_size_bytes,
                progress_cb=self._on_progress,
                cancel_check=self.is_cancelled,
            )
            self.finished.emit(result)
        except Exception:
            err_msg = traceback.format_exc()
            log.error("DuplicateWorker unhandled exception:\n%s", err_msg)
            self.failed.emit("An unexpected error occurred during duplicate analysis:\n" + err_msg)

    def _on_progress(self, stage: str, done: int, total: int, bytes_hashed: int) -> None:
        self.progress.emit(stage, done, total, bytes_hashed)
