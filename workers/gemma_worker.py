"""
workers/gemma_worker.py
=======================
Background QThread workers for Gemma health checks, warmup, and staged command execution.
Keeps the UI completely non-blocking during LLM interactions.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from PySide6.QtCore import QObject, QThread, Signal

from commands.agent import AgentResponse, handle_user_request
from commands.events import FlowEvent
from commands.flow import CommandContext, run_command
from engine.duplicates import DuplicateResult
from engine.models import ScanResult
from gemma.config import GemmaSettings, load_settings
from gemma.ollama_provider import OllamaProvider
from gemma.provider import ProviderStatus

log = logging.getLogger(__name__)


class CommandWorker(QThread):
    """
    Executes a user request through the staged flow in the background.
    Emits FlowEvent instances via eventReady signal as they occur.
    """
    eventReady = Signal(object)

    def __init__(
        self,
        text: str,
        ctx: CommandContext,
        provider: Any,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._ctx = ctx
        self._provider = provider
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            for event in run_command(self._text, self._ctx, self._provider, self._cancel):
                self.eventReady.emit(event)
                if self._cancel.is_set():
                    break
        except Exception as exc:
            log.error("CommandWorker error: %s", exc, exc_info=True)
            self.eventReady.emit(FlowEvent(kind="error", text=f"Command error: {exc}"))


class WarmupWorker(QThread):
    """Warms up local Gemma model weights into VRAM once in the background."""
    done = Signal(bool)

    def __init__(self, provider: Any = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._provider = provider or OllamaProvider()

    def run(self) -> None:
        try:
            ok = self._provider.warm_up()
            self.done.emit(ok)
        except Exception as exc:
            log.warning("WarmupWorker error: %s", exc)
            self.done.emit(False)


class GemmaHealthWorker(QThread):
    """Checks local Gemma/Ollama provider health and model availability."""
    status_ready = Signal(object)  # ProviderStatus
    failed = Signal(str)

    def __init__(self, settings: Optional[GemmaSettings] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._settings = settings or load_settings()

    def run(self) -> None:
        try:
            provider = OllamaProvider(self._settings)
            status = provider.health()
            self.status_ready.emit(status)
        except Exception as exc:
            log.warning("GemmaHealthWorker error: %s", exc)
            self.failed.emit(str(exc))


class GemmaRequestWorker(QThread):
    """Legacy request worker for backwards compatibility."""
    response_ready = Signal(object)
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

    def run(self) -> None:
        try:
            response = handle_user_request(
                text=self._text,
                scan_result=self._scan_result,
                duplicate_result=self._duplicate_result,
                settings=self._settings,
            )
            self.response_ready.emit(response)
        except Exception as exc:
            log.error("GemmaRequestWorker error: %s", exc, exc_info=True)
            self.failed.emit(str(exc))


class GemmaWarmupWorker(QThread):
    """Legacy warmup worker alias."""
    finished = Signal(bool)
    failed = Signal(str)

    def __init__(self, settings: Optional[GemmaSettings] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._settings = settings or load_settings()

    def run(self) -> None:
        try:
            provider = OllamaProvider(self._settings)
            ok = provider.warm_up()
            self.finished.emit(ok)
        except Exception as exc:
            log.warning("GemmaWarmupWorker error: %s", exc)
            self.failed.emit(str(exc))
