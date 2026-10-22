"""
workers/cleanup_worker.py
=========================
Background QThread worker that runs engine.cleanup.execute_plan off the
main thread so the UI stays 100% responsive during recycling.

Signals
-------
progress(done: int, total: int, current_path: str)
    Emitted at start of each item and once at completion.
finished(CleanupOutcome)
    Emitted when the run finishes (including cancellation).
failed(str)
    Emitted only on an unhandled exception in the worker.
"""

from __future__ import annotations

import logging
import traceback
from typing import Optional

from PySide6.QtCore import QThread, Signal

from engine.cleanup import CleanupOutcome, CleanupPlan, execute_plan

log = logging.getLogger(__name__)


class CleanupWorker(QThread):
    progress: Signal = Signal(object, object, str)    # done, total, current_path
    finished: Signal = Signal(object)           # CleanupOutcome
    failed:   Signal = Signal(str)

    def __init__(
        self,
        plan: CleanupPlan,
        parent: Optional[QThread] = None,
    ) -> None:
        super().__init__(parent)
        self._plan          = plan
        self._is_cancelled  = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def run(self) -> None:
        try:
            outcome = execute_plan(
                plan=self._plan,
                confirmed=True,
                progress_cb=self._on_progress,
                cancel_check=self.is_cancelled,
            )
            self.finished.emit(outcome)
        except ValueError as exc:
            # Should never happen — caller must ensure confirmed=True
            log.error("CleanupWorker: execute_plan rejected: %s", exc)
            self.failed.emit(str(exc))
        except Exception:
            err = traceback.format_exc()
            log.error("CleanupWorker unhandled exception:\n%s", err)
            self.failed.emit("An unexpected error occurred during recycling:\n" + err)

    def _on_progress(self, done: int, total: int, path: str) -> None:
        self.progress.emit(done, total, path)
