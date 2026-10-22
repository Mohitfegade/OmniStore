"""
workers/command_worker.py
=========================
Background QThread worker executing handle_user_request_staged.
Relays staged progression events as Qt signals.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, QThread, Signal

from commands.agent import AgentResponse, handle_user_request_staged
from engine.duplicates import DuplicateResult
from engine.models import ScanResult
from gemma.config import GemmaSettings, load_settings

log = logging.getLogger(__name__)


class CommandWorker(QThread):
    interpreting = Signal()
    tools_ready = Signal(object)       # dict: {"tool_runs": list[ToolResult], "mode": str}
    explanation_chunk = Signal(str)    # text chunk
    finished = Signal(object)          # AgentResponse
    failed = Signal(str)

    def __init__(
        self,
        text: str,
        scan_result: Optional[ScanResult],
        duplicate_result: Optional[DuplicateResult] = None,
        settings: Optional[GemmaSettings] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._scan_result = scan_result
        self._duplicate_result = duplicate_result
        self._settings = settings or load_settings()
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel execution and explanation streaming."""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def _on_stage(self, stage: str, payload: Dict[str, Any]) -> None:
        if self._cancelled:
            return
        if stage == "interpreting":
            self.interpreting.emit()
        elif stage == "tools_ready":
            self.tools_ready.emit(payload)
        elif stage == "explanation_chunk":
            self.explanation_chunk.emit(payload.get("text", ""))
        elif stage == "done":
            pass

    def run(self) -> None:
        try:
            resp = handle_user_request_staged(
                text=self._text,
                scan_result=self._scan_result,
                duplicate_result=self._duplicate_result,
                provider=None,
                settings=self._settings,
                on_stage=self._on_stage,
                cancel_token=self.is_cancelled,
            )
            if not self._cancelled:
                self.finished.emit(resp)
        except Exception as exc:
            log.error("CommandWorker error: %s", exc, exc_info=True)
            if not self._cancelled:
                self.failed.emit(str(exc))
