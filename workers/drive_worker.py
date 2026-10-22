"""
workers/drive_worker.py
=======================
Background QThread worker that calls engine.drives.list_drives() off the
main thread so the UI never freezes (network drives can hang for several
seconds).

Usage
-----
    worker = DriveWorker()
    worker.drives_ready.connect(my_slot)
    worker.error_occurred.connect(my_error_slot)
    worker.start()          # starts the thread; emits drives_ready when done

Or use the convenience helper:
    worker = DriveWorker.run_once(on_ready=my_slot, on_error=my_error_slot)
"""

from __future__ import annotations

import logging
import traceback
from typing import Callable, Optional

from PySide6.QtCore import QThread, Signal

from engine.drives import DriveInfo, list_drives

log = logging.getLogger(__name__)


class DriveWorker(QThread):
    """
    QThread subclass — calls list_drives() in the worker thread.

    Signals
    -------
    drives_ready(list[DriveInfo])
        Emitted on success with the full list (may be empty).
    error_occurred(str)
        Emitted if an unexpected exception escapes list_drives().
        list_drives() is itself written to never raise, so this is a
        last-resort safety net.
    """

    drives_ready:   Signal = Signal(object)
    error_occurred: Signal = Signal(str)

    def run(self) -> None:
        try:
            drives = list_drives()
            self.drives_ready.emit(drives)
        except Exception:  # noqa: BLE001
            msg = traceback.format_exc()
            log.error("DriveWorker.run() raised unexpectedly:\n%s", msg)
            self.error_occurred.emit(
                "An unexpected error occurred while reading your drives.\n"
                "See the console for details."
            )

    # ------------------------------------------------------------------
    # Convenience factory

    @classmethod
    def run_once(
        cls,
        on_ready: Callable[[list[DriveInfo]], None],
        on_error: Optional[Callable[[str], None]] = None,
    ) -> "DriveWorker":
        """
        Create, wire, and start a one-shot worker.

        The returned worker must be kept alive (store it in an instance
        variable on the caller) until `finished` is emitted.
        """
        worker = cls()
        worker.drives_ready.connect(on_ready)
        if on_error is not None:
            worker.error_occurred.connect(on_error)
        worker.start()
        return worker
