"""
ui/command_center.py
====================
The Command Center screen where users type plain English questions and get
real results from the engine first, with Gemma 4 (local, via Ollama) interpreting
the request and explaining results.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import app_state
from commands.events import FlowEvent
from commands.flow import CommandContext
from gemma.config import load_settings
from gemma.ollama_provider import OllamaProvider
from ui import theme
from ui.command_widgets import (
    ChipRow,
    ExplanationCard,
    NoticeCard,
    ResultCard,
    UserBubble,
)
from ui.components import PageHeader, PillButton
from workers.gemma_worker import CommandWorker

log = logging.getLogger(__name__)

SUGGESTION_CHIPS = [
    "What is taking the most space?",
    "Show my 10 largest files",
    "Find duplicate files",
    "Files older than 1 year",
    "I need 5 GB free",
]


class CommandCenterPage(QWidget):
    """
    Command Center screen widget.
    Follows contract:
    - signal reviewInCleanupRequested(list)
    - set_context(ctx: CommandContext)
    - set_gemma_available(bool)
    """
    reviewInCleanupRequested = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("commandCenterPage")

        self._ctx = CommandContext()
        self._provider: Optional[OllamaProvider] = None
        self._gemma_available: bool = True
        self._active_worker: Optional[CommandWorker] = None

        # Try initializing OllamaProvider
        try:
            self._provider = OllamaProvider(load_settings())
        except Exception:
            self._provider = None

        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 32)
        root.setSpacing(20)

        # 1. Header
        header = PageHeader(
            "Command Center",
            "Ask questions about your disk usage in plain English. Fast real results with local AI explanation.",
        )
        root.addWidget(header)

        # 2. Offline / Status banner (hidden by default)
        self._banner = QFrame()
        self._banner.setStyleSheet("""
            QFrame {
                background-color: #FEF3F2;
                border: 1px solid #FECDCA;
                border-radius: 12px;
                padding: 10px 16px;
            }
        """)
        banner_layout = QHBoxLayout(self._banner)
        banner_layout.setContentsMargins(12, 6, 12, 6)
        banner_layout.setSpacing(8)

        self._banner_lbl = QLabel("Gemma is offline. OmniStore is running in fast Basic mode.")
        self._banner_lbl.setStyleSheet("color: #B42318; font-size: 13px; font-weight: 500; background: transparent;")
        banner_layout.addWidget(self._banner_lbl)
        banner_layout.addStretch()
        self._banner.setVisible(False)
        root.addWidget(self._banner)

        # 3. Conversation scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("background: transparent;")

        self._convo_container = QWidget()
        self._convo_container.setStyleSheet("background: transparent;")
        self._convo_layout = QVBoxLayout(self._convo_container)
        self._convo_layout.setContentsMargins(0, 0, 0, 16)
        self._convo_layout.setSpacing(16)
        self._convo_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._scroll.setWidget(self._convo_container)
        root.addWidget(self._scroll, 1)

        # 4. Empty state container with chips
        self._empty_container = QWidget()
        self._empty_layout = QVBoxLayout(self._empty_container)
        self._empty_layout.setContentsMargins(16, 24, 16, 24)
        self._empty_layout.setSpacing(14)
        self._empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_icon = QLabel("✦")
        empty_icon.setStyleSheet("font-size: 28px; color: #2347E6; background: transparent;")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_layout.addWidget(empty_icon)

        empty_prompt = QLabel("Explore your storage with plain English questions:")
        empty_prompt.setStyleSheet("font-family: 'Inter Tight'; font-size: 16px; font-weight: 600; color: #111113; background: transparent;")
        empty_prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_layout.addWidget(empty_prompt)

        # Chips
        self._chip_row = ChipRow(SUGGESTION_CHIPS)
        self._chip_row.chipClicked.connect(self._on_chip_clicked)
        self._empty_layout.addWidget(self._chip_row, 0, Qt.AlignmentFlag.AlignCenter)

        # Scan prompt for empty state when no scan exists
        self._no_scan_banner = QFrame()
        self._no_scan_banner.setStyleSheet("background: #FFF9F5; border: 1px solid #FFE4D6; border-radius: 12px; padding: 12px 18px;")
        ns_layout = QHBoxLayout(self._no_scan_banner)
        ns_layout.setContentsMargins(12, 6, 12, 6)
        ns_layout.setSpacing(12)

        ns_lbl = QLabel("No scan loaded yet. Scan a folder first to ask questions about your files.")
        ns_lbl.setStyleSheet("color: #C4320A; font-size: 13px; font-weight: 500; background: transparent;")
        ns_layout.addWidget(ns_lbl)

        scan_btn = QPushButton("Scan a folder first")
        scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        scan_btn.setStyleSheet("""
            QPushButton {
                background-color: #2347E6;
                color: #FFFFFF;
                border-radius: 14px;
                padding: 4px 14px;
                font-size: 12px;
                font-weight: 600;
                min-height: 28px;
            }
            QPushButton:hover { background-color: #1A37C4; }
        """)
        scan_btn.clicked.connect(lambda: app_state.navigate_to(1))
        ns_layout.addWidget(scan_btn)

        self._empty_layout.addWidget(self._no_scan_banner, 0, Qt.AlignmentFlag.AlignCenter)
        self._convo_layout.addWidget(self._empty_container)

        # 5. Bottom Input Pill
        input_card = QFrame()
        input_card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E6E6E8;
                border-radius: 24px;
                padding: 4px 8px;
            }
        """)
        input_layout = QHBoxLayout(input_card)
        input_layout.setContentsMargins(16, 4, 6, 4)
        input_layout.setSpacing(12)

        sparkle_lbl = QLabel("✦")
        sparkle_lbl.setStyleSheet("color: #7C3AED; font-size: 16px; font-weight: bold; background: transparent;")
        input_layout.addWidget(sparkle_lbl)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask a question about your files or click a suggestion...")
        self._input.setStyleSheet("""
            QLineEdit {
                border: none;
                background: transparent;
                font-family: Inter;
                font-size: 14px;
                color: #111113;
                min-height: 38px;
            }
        """)
        self._input.returnPressed.connect(self._on_send)
        input_layout.addWidget(self._input, 1)

        self._btn_send = QPushButton("Send")
        self._btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_send.setStyleSheet("""
            QPushButton {
                background-color: #2347E6;
                color: #FFFFFF;
                border: none;
                border-radius: 18px;
                padding: 8px 22px;
                font-family: Inter;
                font-size: 13px;
                font-weight: 600;
                min-height: 36px;
            }
            QPushButton:hover { background-color: #1A37C4; }
            QPushButton:disabled { background-color: #E6E6E8; color: #A0A0A5; }
        """)
        self._btn_send.clicked.connect(self._on_send)
        input_layout.addWidget(self._btn_send)

        self._btn_stop = QPushButton("Stop")
        self._btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #FFF1F0;
                color: #D92D20;
                border: 1px solid #FDA29B;
                border-radius: 18px;
                padding: 8px 18px;
                font-family: Inter;
                font-size: 13px;
                font-weight: 600;
                min-height: 36px;
            }
            QPushButton:hover { background-color: #FEE4E2; }
        """)
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.setVisible(False)
        input_layout.addWidget(self._btn_stop)

        root.addWidget(input_card)

        # Update initial scan state
        self._update_scan_state()

    def set_context(self, ctx: CommandContext) -> None:
        """Update active command context (scan, duplicates, drives)."""
        self._ctx = ctx
        self._update_scan_state()

    def set_gemma_available(self, available: bool) -> None:
        """Update Gemma connection status."""
        self._gemma_available = available
        self._banner.setVisible(not available)

    def _update_scan_state(self) -> None:
        has_scan = self._ctx.scan is not None
        self._chip_row.set_enabled_state(has_scan)
        self._no_scan_banner.setVisible(not has_scan)

    def _on_chip_clicked(self, chip_text: str) -> None:
        self._input.setText(chip_text)
        self._on_send()

    def _on_stop(self) -> None:
        if self._active_worker:
            self._active_worker.cancel()
        self._reset_input_state()

    def _reset_input_state(self) -> None:
        self._btn_send.setEnabled(True)
        self._btn_send.setVisible(True)
        self._btn_stop.setVisible(False)
        self._input.setEnabled(True)
        self._input.setFocus()

    def _on_send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return

        self._input.clear()
        self._btn_send.setEnabled(False)
        self._btn_send.setVisible(False)
        self._btn_stop.setVisible(True)
        self._input.setEnabled(False)

        # Hide empty container on first query
        self._empty_container.setVisible(False)

        # Add user bubble
        bubble = UserBubble(text)
        self._convo_layout.addWidget(bubble)

        # Active answer widgets
        turn_container = QWidget()
        turn_container.setStyleSheet("background: transparent;")
        turn_layout = QVBoxLayout(turn_container)
        turn_layout.setContentsMargins(0, 4, 0, 8)
        turn_layout.setSpacing(12)

        result_card = ResultCard()
        result_card.reviewInCleanup.connect(self._on_review_in_cleanup)
        result_card.setVisible(False)
        turn_layout.addWidget(result_card)

        explanation_card = ExplanationCard()
        explanation_card.set_pending()
        turn_layout.addWidget(explanation_card)

        latency_lbl = QLabel("")
        latency_lbl.setStyleSheet("font-family: Inter; font-size: 11px; color: #6B6B72; margin-left: 6px; background: transparent;")
        turn_layout.addWidget(latency_lbl)

        self._convo_layout.addWidget(turn_container)
        self._scroll_to_bottom()

        # Start worker
        t_start = time.perf_counter()
        t_tool: list[float] = [0.0]
        active_tool_name: list[str] = [""]

        worker = CommandWorker(text, self._ctx, self._provider if self._gemma_available else None, parent=self)
        self._active_worker = worker

        def _handle_event(event: FlowEvent) -> None:
            if event.kind == "routed":
                if event.data and "tool" in event.data:
                    active_tool_name[0] = event.data["tool"]

            elif event.kind == "tool_result":
                t_tool[0] = (time.perf_counter() - t_start)
                tool_name = active_tool_name[0] or (event.data.get("name") if event.data else "") or "Results"
                result_card.set_result(tool_name, event.data or {})
                result_card.setVisible(True)
                self._scroll_to_bottom()

            elif event.kind == "explain_chunk":
                explanation_card.append(event.text)
                self._scroll_to_bottom()

            elif event.kind == "explain_done":
                explanation_card.finish(event.source)
                total_s = (time.perf_counter() - t_start)
                tool_s = t_tool[0] if t_tool[0] > 0 else total_s
                latency_lbl.setText(f"results in {tool_s:.1f} s, explained in {total_s:.1f} s")
                self._reset_input_state()
                self._scroll_to_bottom()

            elif event.kind == "notice":
                notice = NoticeCard(event.text)
                turn_layout.addWidget(notice)
                explanation_card.setVisible(False)
                self._reset_input_state()
                self._scroll_to_bottom()

            elif event.kind == "error":
                notice = NoticeCard(f"Notice: {event.text}")
                turn_layout.addWidget(notice)
                explanation_card.setVisible(False)
                self._reset_input_state()
                self._scroll_to_bottom()

        worker.eventReady.connect(_handle_event)
        worker.finished.connect(lambda: self._reset_input_state())
        worker.start()

    def _on_review_in_cleanup(self, candidate_items: list) -> None:
        """Route candidate items to Cleanup page without deleting."""
        app_state.set_pending_cleanup(candidate_items)
        self.reviewInCleanupRequested.emit(candidate_items)
        app_state.navigate_to(3)

    def _scroll_to_bottom(self) -> None:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))


def build_command_center_scroll() -> QScrollArea:
    """Convenience factory to embed CommandCenterPage in MainWindow."""
    page = CommandCenterPage()
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(page)
    # Store reference so MainWindow can access the CommandCenterPage instance
    sa.command_center_page = page  # type: ignore[attr-defined]
    return sa
