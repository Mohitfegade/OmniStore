"""
ui/command_center.py
====================
The Command Center screen where users type plain English questions and get
real results from the engine first, with Gemma 4 (local, via Ollama) interpreting
the request and explaining results.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QPoint, Qt, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import app_state
from commands.agent import AgentResponse
from commands.tools import ToolResult
from engine.drives import format_bytes
from engine.models import FileRecord
from gemma.config import load_settings
from gemma.ollama_provider import OllamaProvider
from ui import theme
from ui.components import Card, HatchedProgressBar, PageHeader, PillButton
from ui.gemma_status import AuditLogDialog
from workers.command_worker import CommandWorker

log = logging.getLogger(__name__)

SUGGESTION_CHIPS = [
    "What is taking up the most space?",
    "Find duplicate files",
    "Videos larger than 1 GB",
    "Files I haven't opened in 6 months",
    "PDFs modified last month",
    "Show ways to free 5 GB",
]


class CommandInput(QLineEdit):
    """Custom QLineEdit with Enter to submit and Esc to clear."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("What would you like to explore next?")
        self.setStyleSheet(
            f"QLineEdit {{ border: none; font-size: 14px; color: {theme.INK}; background: transparent; padding: 4px; }}"
        )

    def keyPressEvent(self, event) -> None:  # noqa: ANN001
        if event.key() == Qt.Key.Key_Escape:
            self.clear()
            event.accept()
            return
        super().keyPressEvent(event)


class ResponseCard(Card):
    """Card representing a single command interaction in the response feed."""

    def __init__(self, query: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)
        self.query = query
        self._tool_runs: List[ToolResult] = []
        self._mode = "gemma"
        self._explanation_text = ""
        self._cleanup_candidates: List[Dict[str, Any]] = []

        layout = self.body_layout
        layout.setSpacing(14)
        layout.setContentsMargins(20, 18, 20, 20)

        # 1. User Query Header
        query_row = QHBoxLayout()
        query_row.setSpacing(8)

        q_icon = QLabel("💬")
        q_icon.setStyleSheet("font-size: 15px; background: transparent;")
        query_row.addWidget(q_icon)

        self._query_lbl = QLabel(query)
        self._query_lbl.setFont(QFont(theme.FONT_HEADING, 13, QFont.Weight.Bold))
        self._query_lbl.setStyleSheet(f"color: {theme.INK}; background: transparent;")
        self._query_lbl.setWordWrap(True)
        query_row.addWidget(self._query_lbl, 1)

        layout.addLayout(query_row)

        # 2. Progress / Tool Chips Line
        self._status_row = QHBoxLayout()
        self._status_row.setSpacing(6)

        self._status_chip = QLabel("Understanding your request…")
        self._status_chip.setStyleSheet(
            "QLabel { background: #F1F1F3; color: #55555C; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 500; }"
        )
        self._status_row.addWidget(self._status_chip)
        self._status_row.addStretch()
        layout.addLayout(self._status_row)

        # 3. Results Container
        self._results_container = QWidget()
        self._results_layout = QVBoxLayout(self._results_container)
        self._results_layout.setContentsMargins(0, 4, 0, 4)
        self._results_layout.setSpacing(10)
        self._results_container.hide()
        layout.addWidget(self._results_container)

        # 4. Review in Cleanup Action Banner (Hidden until duplicates/suggest_free_space results)
        self._cleanup_banner = QFrame()
        self._cleanup_banner.setStyleSheet(
            "QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 8px 12px; }"
        )
        cl_layout = QHBoxLayout(self._cleanup_banner)
        cl_layout.setContentsMargins(6, 4, 6, 4)
        cl_layout.setSpacing(12)

        self._cleanup_info = QLabel("Review candidate files to reclaim storage:")
        self._cleanup_info.setStyleSheet("font-size: 12px; color: #334155; font-weight: 500; background: transparent;")
        cl_layout.addWidget(self._cleanup_info, 1)

        self._cleanup_btn = PillButton("Review in Cleanup", primary=True)
        self._cleanup_btn.clicked.connect(self._on_review_cleanup_clicked)
        cl_layout.addWidget(self._cleanup_btn)

        self._disclaimer = QLabel("Nothing is changed until you confirm in Cleanup.")
        self._disclaimer.setStyleSheet("font-size: 11px; color: #64748B; font-style: italic; background: transparent;")
        cl_layout.addWidget(self._disclaimer)

        self._cleanup_banner.hide()
        layout.addWidget(self._cleanup_banner)

        # 5. Explanation Section
        self._explanation_box = QFrame()
        self._explanation_box.setStyleSheet(
            "QFrame { background: #FAFAFB; border: 1px solid #EEEEF0; border-radius: 10px; padding: 12px 14px; }"
        )
        expl_layout = QVBoxLayout(self._explanation_box)
        expl_layout.setContentsMargins(0, 0, 0, 0)
        expl_layout.setSpacing(8)

        expl_top = QHBoxLayout()
        self._mode_badge = QLabel("Gemma 4 (local)")
        self._mode_badge.setStyleSheet(
            "QLabel { background: #E8F8EE; color: #166534; border: 1px solid #86EFAC; border-radius: 8px; "
            "padding: 2px 8px; font-size: 11px; font-weight: 600; }"
        )
        expl_top.addWidget(self._mode_badge)
        expl_top.addStretch()
        expl_layout.addLayout(expl_top)

        self._explanation_lbl = QLabel("Interpreting…")
        self._explanation_lbl.setFont(QFont(theme.FONT_BODY, 10))
        self._explanation_lbl.setStyleSheet(f"color: {theme.INK}; background: transparent; line-height: 1.4;")
        self._explanation_lbl.setWordWrap(True)
        expl_layout.addWidget(self._explanation_lbl)

        self._explanation_box.hide()
        layout.addWidget(self._explanation_box)

        # 6. Footer Line (Audit Log link)
        self._footer_row = QHBoxLayout()
        self._footer_row.setSpacing(6)

        self._audit_lbl = QLabel("")
        self._audit_lbl.setStyleSheet("color: #8C8C94; font-size: 11px; background: transparent;")
        self._footer_row.addWidget(self._audit_lbl)

        self._audit_link = QPushButton("View details")
        self._audit_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._audit_link.setStyleSheet(
            "QPushButton { border: none; color: #4361EE; font-size: 11px; font-weight: 600; text-decoration: underline; background: transparent; padding: 0; } "
            "QPushButton:hover { color: #2B45CD; }"
        )
        self._audit_link.clicked.connect(self._open_audit_log)
        self._audit_link.hide()
        self._footer_row.addWidget(self._audit_link)

        self._footer_row.addStretch()
        layout.addLayout(self._footer_row)

    def set_status(self, text: str) -> None:
        self._status_chip.setText(text)

    def render_tools_ready(self, tool_runs: List[ToolResult], mode: str) -> None:
        self._tool_runs = tool_runs
        self._mode = mode

        # Update mode badge
        if mode == "basic":
            self._mode_badge.setText("Basic mode")
            self._mode_badge.setStyleSheet(
                "QLabel { background: #F1F1F3; color: #55555C; border: 1px solid #D4D4D8; border-radius: 8px; "
                "padding: 2px 8px; font-size: 11px; font-weight: 600; }"
            )
        else:
            self._mode_badge.setText("Gemma 4 (local)")
            self._mode_badge.setStyleSheet(
                "QLabel { background: #E8F8EE; color: #166534; border: 1px solid #86EFAC; border-radius: 8px; "
                "padding: 2px 8px; font-size: 11px; font-weight: 600; }"
            )

        # Clear existing tool chips and add executed ones
        while self._status_row.count():
            item = self._status_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for r in tool_runs:
            friendly_name = r.name.replace("_", " ")
            chip = QLabel(f"✓ {friendly_name}")
            chip.setStyleSheet(
                "QLabel { background: #EDF1FD; color: #2B45CD; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600; }"
            )
            self._status_row.addWidget(chip)
        self._status_row.addStretch()

        # Render real results
        self._render_results_data()
        self._results_container.show()
        self._explanation_box.show()

    def append_explanation_chunk(self, chunk: str) -> None:
        self._explanation_text += chunk
        self._explanation_lbl.setText(self._explanation_text)

    def set_finished(self, response: AgentResponse) -> None:
        if response.explanation and not self._explanation_text:
            self._explanation_text = response.explanation
            self._explanation_lbl.setText(self._explanation_text)

        bytes_sent = response.payload_bytes_sent
        self._audit_lbl.setText(f"Shared with the model: {bytes_sent} bytes.")
        self._audit_link.show()

    def set_failed(self, error: str) -> None:
        self.set_status(f"Error: {error}")
        self._explanation_lbl.setText(f"Could not complete request: {error}")
        self._explanation_box.show()

    def _render_results_data(self) -> None:
        # Clear results layout
        while self._results_layout.count():
            item = self._results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for r in self._tool_runs:
            if not r.ok:
                err_lbl = QLabel(f"Tool {r.name} error: {r.error}")
                err_lbl.setStyleSheet("color: #DC2626; font-size: 12px; background: transparent;")
                self._results_layout.addWidget(err_lbl)
                continue

            data = r.data or {}

            # Case A: Folders breakdown
            if r.name == "get_largest_folders":
                folders = data.get("folders", [])
                if folders:
                    self._render_folder_bars(folders)

            # Case B: Category breakdown
            elif r.name == "get_category_breakdown":
                categories = data.get("categories", [])
                if categories:
                    self._render_category_bars(categories)

            # Case C: Scan overview
            elif r.name == "get_scan_overview":
                self._render_overview_card(data)

            # Case D: Duplicate summary
            elif r.name == "get_duplicate_summary":
                self._render_duplicate_results(data)

            # Case E: Suggest free space
            elif r.name == "suggest_free_space":
                self._render_free_space_results(data)

            # Case F: File items list (find_largest_files, filter_files)
            elif "items" in data:
                items = data.get("items", [])
                self._render_items_table(items)

    def _render_overview_card(self, data: Dict[str, Any]) -> None:
        card = QFrame()
        card.setStyleSheet("QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px; }")
        l = QHBoxLayout(card)
        l.setSpacing(20)

        f_lbl = QLabel(f"Total Files: {data.get('total_files', 0):,}")
        f_lbl.setStyleSheet("font-weight: 600; font-size: 13px; color: #1E293B; background: transparent;")
        l.addWidget(f_lbl)

        s_lbl = QLabel(f"Total Size: {data.get('total_size_human', format_bytes(data.get('total_bytes', 0)))}")
        s_lbl.setStyleSheet("font-weight: 600; font-size: 13px; color: #1E293B; background: transparent;")
        l.addWidget(s_lbl)

        l.addStretch()
        self._results_layout.addWidget(card)

    def _render_folder_bars(self, folders: List[Dict[str, Any]]) -> None:
        cont = QFrame()
        cont.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #E6E6E8; border-radius: 8px; padding: 10px; }")
        l = QVBoxLayout(cont)
        l.setSpacing(8)

        total_b = sum(f.get("total_bytes", 0) for f in folders) or 1
        for f in folders[:5]:
            row = QVBoxLayout()
            row.setSpacing(3)
            info = QHBoxLayout()

            name = f.get("name") or f.get("folder", "")
            lbl = QLabel(name)
            lbl.setFont(QFont(theme.FONT_BODY, 9, QFont.Weight.Medium))
            lbl.setStyleSheet("color: #111113; background: transparent;")
            info.addWidget(lbl, 1)

            sz_human = f.get("size_human") or format_bytes(f.get("total_bytes", 0))
            sz_lbl = QLabel(sz_human)
            sz_lbl.setStyleSheet("color: #6B6B72; font-size: 11px; background: transparent;")
            info.addWidget(sz_lbl)
            row.addLayout(info)

            pct = int((f.get("total_bytes", 0) / total_b) * 100)
            pct = max(1, min(100, pct))
            bar = HatchedProgressBar(value=pct, accent_color=theme.PURPLE)
            bar.setFixedHeight(6)
            row.addWidget(bar)
            l.addLayout(row)

        self._results_layout.addWidget(cont)

    def _render_category_bars(self, categories: List[Dict[str, Any]]) -> None:
        cont = QFrame()
        cont.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #E6E6E8; border-radius: 8px; padding: 10px; }")
        l = QVBoxLayout(cont)
        l.setSpacing(8)

        total_b = sum(c.get("total_bytes", 0) for c in categories) or 1
        for c in categories[:6]:
            row = QVBoxLayout()
            row.setSpacing(3)
            info = QHBoxLayout()

            cat_name = c.get("category", "")
            lbl = QLabel(cat_name)
            lbl.setFont(QFont(theme.FONT_BODY, 9, QFont.Weight.Medium))
            lbl.setStyleSheet("color: #111113; background: transparent;")
            info.addWidget(lbl, 1)

            sz_human = c.get("size_human") or format_bytes(c.get("total_bytes", 0))
            sz_lbl = QLabel(sz_human)
            sz_lbl.setStyleSheet("color: #6B6B72; font-size: 11px; background: transparent;")
            info.addWidget(sz_lbl)
            row.addLayout(info)

            pct = int((c.get("total_bytes", 0) / total_b) * 100)
            pct = max(1, min(100, pct))
            bar = HatchedProgressBar(value=pct, accent_color=theme.BLUE)
            bar.setFixedHeight(6)
            row.addWidget(bar)
            l.addLayout(row)

        self._results_layout.addWidget(cont)

    def _render_duplicate_results(self, data: Dict[str, Any]) -> None:
        groups = data.get("groups", [])
        flat_items: List[Dict[str, Any]] = []
        cleanup_items: List[Dict[str, Any]] = []

        for g in groups:
            files = g.get("files", [])
            keep_path = g.get("keep_path")
            for f in files:
                flat_items.append({
                    "name": f.get("name", ""),
                    "size_human": f.get("size_human", ""),
                    "category": "Duplicate",
                    "modified": f.get("modified_date", ""),
                    "path": f.get("path", ""),
                })
                # Only extra copies become cleanup candidates
                if f.get("path") != keep_path:
                    cleanup_items.append({
                        "path": f.get("path"),
                        "name": f.get("name"),
                        "size_bytes": f.get("size_bytes", 0),
                        "reason": "Exact duplicate",
                        "keep_path": keep_path,
                        "group_id": g.get("group_id"),
                    })

        self._render_items_table(flat_items)

        if cleanup_items:
            self._cleanup_candidates = cleanup_items
            self._cleanup_info.setText(
                f"Found {len(cleanup_items)} duplicate extra copies ready to review:"
            )
            self._cleanup_banner.show()

    def _render_free_space_results(self, data: Dict[str, Any]) -> None:
        candidates = data.get("candidates", [])
        flat_items: List[Dict[str, Any]] = []
        cleanup_items: List[Dict[str, Any]] = []

        for c in candidates:
            flat_items.append({
                "name": c.get("name", ""),
                "size_human": c.get("size_human", ""),
                "category": c.get("reason", "Review item"),
                "modified": "",
                "path": c.get("path", ""),
            })
            cleanup_items.append({
                "path": c.get("path"),
                "name": c.get("name"),
                "size_bytes": c.get("size_bytes", 0),
                "reason": "Exact duplicate" if c.get("reason") == "Exact duplicate" else "Large file you chose to review",
                "keep_path": c.get("keep_path"),
            })

        self._render_items_table(flat_items)

        if cleanup_items:
            self._cleanup_candidates = cleanup_items
            cum_h = data.get("cumulative_human", "")
            self._cleanup_info.setText(
                f"Suggested {len(cleanup_items)} review candidates (up to {cum_h}):"
            )
            self._cleanup_banner.show()

    def _render_items_table(self, items: List[Dict[str, Any]]) -> None:
        if not items:
            empty_lbl = QLabel("No files matching this query.")
            empty_lbl.setStyleSheet("color: #6B6B72; font-size: 12px; padding: 10px; background: transparent;")
            self._results_layout.addWidget(empty_lbl)
            return

        table = QTableWidget(len(items), 5)
        table.setHorizontalHeaderLabels(["Name", "Size", "Category", "Modified", "Path"])
        table.verticalHeader().hide()
        table.setShowGrid(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos, t=table: self._show_table_menu(pos, t))

        # Styling
        table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E6E6E8;
                border-radius: 8px;
                font-size: 12px;
                color: #111113;
            }
            QTableWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #F3F3F4;
            }
            QTableWidget::item:selected {
                background-color: #EDF1FD;
                color: #111113;
            }
            QHeaderView::section {
                background-color: #FAFAFA;
                border: none;
                border-bottom: 1px solid #E6E6E8;
                padding: 6px 8px;
                font-weight: 600;
                font-size: 11px;
                color: #6B6B72;
            }
        """)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        table.setColumnWidth(0, 220)
        table.setColumnWidth(1, 90)
        table.setColumnWidth(2, 110)
        table.setColumnWidth(3, 110)

        max_rows = min(len(items), 50)
        table.setRowCount(max_rows)

        for row, it in enumerate(items[:max_rows]):
            name = it.get("name", "")
            sz = it.get("size_human", "") or format_bytes(it.get("size_bytes", 0))
            cat = it.get("category", "")
            mod = it.get("modified_date", "") or it.get("modified", "")
            path = it.get("path", "")

            it_name = QTableWidgetItem(name)
            it_name.setData(Qt.ItemDataRole.UserRole, path)
            it_size = QTableWidgetItem(sz)
            it_cat = QTableWidgetItem(cat)
            it_mod = QTableWidgetItem(mod)
            it_path = QTableWidgetItem(path)

            table.setItem(row, 0, it_name)
            table.setItem(row, 1, it_size)
            table.setItem(row, 2, it_cat)
            table.setItem(row, 3, it_mod)
            table.setItem(row, 4, it_path)

        table_height = min(260, 36 + (max_rows * 28))
        table.setFixedHeight(table_height)
        self._results_layout.addWidget(table)

    def _show_table_menu(self, pos: QPoint, table: QTableWidget) -> None:
        row = table.rowAt(pos.y())
        if row < 0:
            return
        item = table.item(row, 0)
        if not item:
            return
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path:
            file_path = table.item(row, 4).text() if table.item(row, 4) else ""
        if not file_path:
            return

        menu = QMenu(table)
        menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #E6E6E8;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px;
                font-size: 12px;
                color: #111113;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #EDF1FD;
                color: #2B45CD;
            }
        """)

        act_open = menu.addAction("Open file")
        act_containing = menu.addAction("Open containing folder")
        act_copy = menu.addAction("Copy path")

        action = menu.exec(QCursor.pos())
        if action == act_open:
            if os.path.exists(file_path):
                try:
                    os.startfile(file_path)
                except Exception as exc:
                    log.warning("Could not open file: %s", exc)
        elif action == act_containing:
            if os.path.exists(file_path):
                try:
                    subprocess.Popen(["explorer", f"/select,{os.path.abspath(file_path)}"])
                except Exception as exc:
                    log.warning("Could not open folder: %s", exc)
        elif action == act_copy:
            QApplication.clipboard().setText(file_path)

    def _on_review_cleanup_clicked(self) -> None:
        if not self._cleanup_candidates:
            return

        scan = app_state.get_latest_scan()
        file_map: Dict[str, Any] = {}
        if scan:
            file_map = {os.path.normcase(os.path.abspath(f.path)): f for f in scan.files}

        pending: List[Dict[str, Any]] = []
        for it in self._cleanup_candidates:
            path = it.get("path")
            if not path:
                continue
            norm = os.path.normcase(os.path.abspath(path))
            rec = file_map.get(norm)
            if rec is None:
                rec = FileRecord(
                    path=path,
                    name=it.get("name") or os.path.basename(path),
                    size_bytes=it.get("size_bytes", 0),
                    modified_ts=time.time(),
                    category="Other",
                    extension=os.path.splitext(path)[1].lower().lstrip("."),
                )
            reason = it.get("reason", "Large file you chose to review")
            pending.append({
                "file": rec,
                "reason": reason,
                "keep_path": it.get("keep_path"),
                "group_id": it.get("group_id"),
            })

        if pending:
            app_state.set_pending_cleanup(pending)
            app_state.navigate_to(3)

    def _open_audit_log(self) -> None:
        dlg = AuditLogDialog(self)
        dlg.exec()


class CommandCenterPage(QWidget):
    """The complete Command Center screen."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("commandCenterPage")
        self._current_worker: Optional[CommandWorker] = None
        self._active_response_card: Optional[ResponseCard] = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 28, 32, 32)
        main_layout.setSpacing(20)

        # 1. Page Header
        header = PageHeader(
            "Command Center",
            "Ask plain English questions about your storage with local Gemma AI.",
        )
        main_layout.addWidget(header)

        # 2. Offline Banner (shown if Gemma offline)
        self._offline_banner = QFrame()
        self._offline_banner.setStyleSheet(
            "QFrame { background: #FEF3C7; border: 1px solid #FDE68A; border-radius: 10px; padding: 10px 14px; }"
        )
        off_layout = QHBoxLayout(self._offline_banner)
        off_layout.setContentsMargins(0, 0, 0, 0)
        off_layout.setSpacing(8)

        off_icon = QLabel("⚠️")
        off_icon.setStyleSheet("font-size: 14px; background: transparent;")
        off_layout.addWidget(off_icon)

        off_text = QLabel("Gemma is offline, using basic commands")
        off_text.setStyleSheet("color: #92400E; font-size: 12px; font-weight: 600; background: transparent;")
        off_layout.addWidget(off_text, 1)

        self._offline_banner.hide()
        main_layout.addWidget(self._offline_banner)

        # 3. Input Card
        input_card = Card()
        input_vbox = QVBoxLayout()
        input_vbox.setSpacing(12)

        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        sparkle = QLabel("✨")
        sparkle.setStyleSheet("font-size: 18px; background: transparent;")
        input_row.addWidget(sparkle)

        self._query_input = CommandInput()
        self._query_input.returnPressed.connect(self._on_ask_clicked)
        input_row.addWidget(self._query_input, 1)

        self._ask_btn = PillButton("Ask", primary=True)
        self._ask_btn.clicked.connect(self._on_ask_clicked)
        input_row.addWidget(self._ask_btn)

        input_vbox.addLayout(input_row)

        # Suggestion Chips Row
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(8)

        chips_lbl = QLabel("Try:")
        chips_lbl.setStyleSheet("color: #6B6B72; font-size: 12px; font-weight: 500; background: transparent;")
        chips_layout.addWidget(chips_lbl)

        for text in SUGGESTION_CHIPS:
            chip = QPushButton(text)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                f"QPushButton {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER}; border-radius: 12px; "
                f"padding: 4px 10px; font-size: 11px; font-weight: 500; color: {theme.INK}; }} "
                f"QPushButton:hover {{ background: #F3F3F4; border-color: #D4D4D8; }}"
            )
            chip.clicked.connect(lambda checked=False, q=text: self._on_chip_clicked(q))
            chips_layout.addWidget(chip)

        chips_layout.addStretch()
        input_vbox.addLayout(chips_layout)

        input_card.body_layout.addLayout(input_vbox)
        main_layout.addWidget(input_card)

        # 4. Empty State Card (When no scan is loaded)
        self._empty_card = Card()
        empty_vbox = QVBoxLayout()
        empty_vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_vbox.setContentsMargins(40, 48, 40, 48)
        empty_vbox.setSpacing(12)

        empty_icon = QLabel("📁")
        empty_icon.setStyleSheet("font-size: 38px; background: transparent;")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_vbox.addWidget(empty_icon)

        empty_title = QLabel("No scan loaded")
        empty_title.setFont(QFont(theme.FONT_HEADING, 14, QFont.Weight.Bold))
        empty_title.setStyleSheet(f"color: {theme.INK}; background: transparent;")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_vbox.addWidget(empty_title)

        empty_sub = QLabel("Select and scan a folder in the Analyzer tab to begin exploring your storage.")
        empty_sub.setFont(QFont(theme.FONT_BODY, 11))
        empty_sub.setStyleSheet("color: #6B6B72; background: transparent;")
        empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_vbox.addWidget(empty_sub)

        scan_btn = PillButton("Open Analyzer", primary=True)
        scan_btn.clicked.connect(lambda: app_state.navigate_to(1))
        empty_vbox.addWidget(scan_btn, 0, Qt.AlignmentFlag.AlignCenter)

        self._empty_card.body_layout.addLayout(empty_vbox)
        main_layout.addWidget(self._empty_card)

        # 5. Response Feed Container
        self._feed_container = QWidget()
        self._feed_layout = QVBoxLayout(self._feed_container)
        self._feed_layout.setContentsMargins(0, 0, 0, 0)
        self._feed_layout.setSpacing(16)
        main_layout.addWidget(self._feed_container)

        main_layout.addStretch()

        # Listen to scan changes
        app_state.add_scan_listener(self._on_scan_updated)
        self._check_initial_state()

    def _check_initial_state(self) -> None:
        scan = app_state.get_latest_scan()
        if scan is None:
            self._empty_card.show()
        else:
            self._empty_card.hide()

        # Check Gemma health for offline banner
        try:
            settings = load_settings()
            provider = OllamaProvider(settings)
            status = provider.health()
            if not status.ok or not settings.enabled:
                self._offline_banner.show()
            else:
                self._offline_banner.hide()
        except Exception:
            self._offline_banner.show()

    def _on_scan_updated(self, scan: Any) -> None:
        if scan:
            self._empty_card.hide()

    def _on_chip_clicked(self, query: str) -> None:
        self._query_input.setText(query)
        self._on_ask_clicked()

    def _on_ask_clicked(self) -> None:
        # If currently running, cancel!
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.cancel()
            self._ask_btn.setText("Ask")
            self._ask_btn.set_primary(True)
            if self._active_response_card:
                self._active_response_card.set_status("Cancelled")
            return

        query = self._query_input.text().strip()
        if not query:
            return

        scan = app_state.get_latest_scan()
        if scan is None:
            self._empty_card.show()
            return

        duplicates = app_state.get_latest_duplicates()

        # Create Response Card and prepend to feed
        card = ResponseCard(query, self)
        self._feed_layout.insertWidget(0, card)
        self._active_response_card = card

        # Update button state to "Stop"
        self._ask_btn.setText("Stop")
        self._ask_btn.set_primary(False)

        # Start CommandWorker
        self._current_worker = CommandWorker(
            text=query,
            scan_result=scan,
            duplicate_result=duplicates,
            parent=self,
        )
        self._current_worker.interpreting.connect(
            lambda c=card: c.set_status("Understanding your request…")
        )
        self._current_worker.tools_ready.connect(
            lambda payload, c=card: c.render_tools_ready(payload.get("tool_runs", []), payload.get("mode", "gemma"))
        )
        self._current_worker.explanation_chunk.connect(
            lambda chunk, c=card: c.append_explanation_chunk(chunk)
        )
        self._current_worker.finished.connect(
            lambda resp, c=card: self._on_worker_finished(resp, c)
        )
        self._current_worker.failed.connect(
            lambda err, c=card: self._on_worker_failed(err, c)
        )
        self._current_worker.start()

    def _on_worker_finished(self, response: AgentResponse, card: ResponseCard) -> None:
        self._ask_btn.setText("Ask")
        self._ask_btn.set_primary(True)
        card.set_finished(response)

    def _on_worker_failed(self, error: str, card: ResponseCard) -> None:
        self._ask_btn.setText("Ask")
        self._ask_btn.set_primary(True)
        card.set_failed(error)


def build_command_center_scroll() -> QScrollArea:
    """Convenience factory to wrap CommandCenterPage in a QScrollArea."""
    page = CommandCenterPage()
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(page)
    return sa
