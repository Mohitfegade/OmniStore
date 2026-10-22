"""
ui/command_widgets.py
=====================
Modular UI components for OmniStore Command Center:
- ChipRow: suggestion pill buttons
- UserBubble: user query chat bubble
- ResultCard: real tool results display with "Review in Cleanup" button
- ExplanationCard: streaming explanation with Gemma/Basic mode badge
- NoticeCard: informational and safety notices
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui import theme


# ---------------------------------------------------------------------------
# ChipRow
# ---------------------------------------------------------------------------

class ChipRow(QWidget):
    """Horizontal scrollable or wrapping row of suggestion chips."""
    chipClicked = Signal(str)

    def __init__(self, chips: Optional[List[str]] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._buttons: List[QPushButton] = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 4, 0, 4)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        if chips:
            self.set_chips(chips)

    def set_chips(self, chips: List[str]) -> None:
        # Clear existing
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._buttons.clear()

        for text in chips:
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #FFFFFF;
                    color: #111113;
                    border: 1px solid #E6E6E8;
                    border-radius: 16px;
                    padding: 6px 14px;
                    font-family: Inter;
                    font-size: 13px;
                    font-weight: 500;
                    min-height: 32px;
                }
                QPushButton:hover {
                    background-color: #F3F3F2;
                    border-color: #C0C0C4;
                }
                QPushButton:pressed {
                    background-color: #EAEAEC;
                }
                QPushButton:disabled {
                    background-color: #FAFAFA;
                    color: #A0A0A5;
                    border-color: #EDEDEF;
                }
            """)
            btn.clicked.connect(lambda checked=False, t=text: self.chipClicked.emit(t))
            self._layout.addWidget(btn)
            self._buttons.append(btn)

    def set_enabled_state(self, enabled: bool) -> None:
        for btn in self._buttons:
            btn.setEnabled(enabled)


# ---------------------------------------------------------------------------
# UserBubble
# ---------------------------------------------------------------------------

class UserBubble(QWidget):
    """Chat bubble representing the user's submitted query."""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 6)
        root.setSpacing(0)
        root.addStretch()

        bubble = QFrame()
        bubble.setStyleSheet("""
            QFrame {
                background-color: #1A1A1A;
                border-radius: 18px;
                padding: 10px 18px;
            }
        """)
        bubble_layout = QHBoxLayout(bubble)
        bubble_layout.setContentsMargins(14, 8, 14, 8)

        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-family: Inter;
                font-size: 14px;
                font-weight: 500;
                background: transparent;
            }
        """)
        bubble_layout.addWidget(lbl)
        root.addWidget(bubble)


# ---------------------------------------------------------------------------
# ResultCard
# ---------------------------------------------------------------------------

class ResultCard(QWidget):
    """
    Card displaying real, deterministic tool results with *_human sizes.
    Shows 'Review in Cleanup' button only when candidate items are available.
    """
    reviewInCleanup = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._candidate_items: List[Dict[str, Any]] = []

        self.card = QFrame(self)
        self.card.setStyleSheet("""
            QFrame#resultCardFrame {
                background-color: #FFFFFF;
                border: 1px solid #E6E6E8;
                border-radius: 20px;
            }
        """)
        self.card.setObjectName("resultCardFrame")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 6)
        outer.addWidget(self.card)

        self._card_layout = QVBoxLayout(self.card)
        self._card_layout.setContentsMargins(20, 20, 20, 20)
        self._card_layout.setSpacing(14)

    def set_result(self, tool_name: str, data: Dict[str, Any]) -> None:
        # Clear previous content
        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            l = item.layout()
            if l:
                while l.count():
                    sub = l.takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        self._candidate_items = []

        # Header with badge
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        tool_title_map = {
            "get_scan_overview": "Scan Overview",
            "find_largest_files": "Largest Files",
            "filter_files": "Filtered Files",
            "get_largest_folders": "Largest Folders",
            "get_category_breakdown": "Storage by Category",
            "get_duplicate_summary": "Duplicate Detection",
            "suggest_free_space": "Space Saving Suggestions",
        }
        title_text = tool_title_map.get(tool_name, tool_name.replace("_", " ").title())

        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet("font-family: 'Inter Tight', sans-serif; font-size: 16px; font-weight: 600; color: #111113; background: transparent;")
        hdr.addWidget(title_lbl)
        hdr.addStretch()

        badge = QLabel("Real Scan Data")
        badge.setStyleSheet("font-family: Inter; font-size: 11px; font-weight: 600; color: #22A447; background-color: #EDFDF0; border: 1px solid #B6F2C2; border-radius: 10px; padding: 2px 8px;")
        hdr.addWidget(badge)
        self._card_layout.addLayout(hdr)

        # Body according to tool
        if tool_name in ("find_largest_files", "filter_files"):
            self._render_files(data)
        elif tool_name == "get_largest_folders":
            self._render_folders(data)
        elif tool_name == "get_category_breakdown":
            self._render_categories(data)
        elif tool_name == "get_duplicate_summary":
            self._render_duplicates(data)
        elif tool_name == "suggest_free_space":
            self._render_suggestions(data)
        elif tool_name == "get_scan_overview":
            self._render_overview(data)
        else:
            lbl = QLabel(str(data))
            lbl.setWordWrap(True)
            self._card_layout.addWidget(lbl)

        # "Review in Cleanup" button if candidate items exist
        if self._candidate_items:
            action_row = QHBoxLayout()
            action_row.setContentsMargins(0, 10, 0, 0)
            action_row.addStretch()

            btn = QPushButton("Review in Cleanup")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2347E6;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 18px;
                    padding: 8px 20px;
                    font-family: Inter;
                    font-size: 13px;
                    font-weight: 600;
                    min-height: 36px;
                }
                QPushButton:hover {
                    background-color: #1A37C4;
                }
            """)
            btn.clicked.connect(lambda: self.reviewInCleanup.emit(list(self._candidate_items)))
            action_row.addWidget(btn)
            self._card_layout.addLayout(action_row)

    def _render_files(self, data: Dict[str, Any]) -> None:
        files = data.get("files") or data.get("items") or []
        if not files:
            lbl = QLabel("No files found matching criteria.")
            lbl.setStyleSheet("color: #6B6B72; font-size: 13px; background: transparent;")
            self._card_layout.addWidget(lbl)
            return

        table = QTableWidget(min(len(files), 15), 4)
        table.setHorizontalHeaderLabels(["Name", "Folder", "Size", "Modified"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setStyleSheet("border: 1px solid #E6E6E8; border-radius: 12px; background: #FFFFFF;")

        for row, f in enumerate(files[:15]):
            name = f.get("name") or os.path.basename(f.get("path", ""))
            parent_name = f.get("parent_name") or f.get("folder", "")
            sz = f.get("size_human") or f.get("size_bytes_human") or ""
            dt = f.get("modified_date") or ""

            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(row, 1, QTableWidgetItem(parent_name))
            table.setItem(row, 2, QTableWidgetItem(sz))
            table.setItem(row, 3, QTableWidgetItem(dt))

            # Add to candidate items for cleanup review
            if "path" in f:
                self._candidate_items.append({
                    "path": f["path"],
                    "name": name,
                    "size_bytes": f.get("size_bytes", 0),
                    "reason": "Large file you chose to review",
                    "keep_path": None,
                })

        table.setFixedHeight(min(320, 42 + len(files[:15]) * 36))
        self._card_layout.addWidget(table)

    def _render_folders(self, data: Dict[str, Any]) -> None:
        folders = data.get("folders", [])
        if not folders:
            lbl = QLabel("No folders found.")
            lbl.setStyleSheet("color: #6B6B72; font-size: 13px; background: transparent;")
            self._card_layout.addWidget(lbl)
            return

        table = QTableWidget(min(len(folders), 10), 3)
        table.setHorizontalHeaderLabels(["Folder", "Parent", "Size"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setStyleSheet("border: 1px solid #E6E6E8; border-radius: 12px; background: #FFFFFF;")

        for row, f in enumerate(folders[:10]):
            name = f.get("name") or os.path.basename(f.get("path", ""))
            parent_name = f.get("parent_name") or ""
            sz = f.get("size_human") or f.get("total_bytes_human") or ""

            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(row, 1, QTableWidgetItem(parent_name))
            table.setItem(row, 2, QTableWidgetItem(sz))

        table.setFixedHeight(min(280, 42 + len(folders[:10]) * 36))
        self._card_layout.addWidget(table)

    def _render_categories(self, data: Dict[str, Any]) -> None:
        categories = data.get("categories", [])
        total_sz = data.get("total_size_human") or data.get("total_bytes_human") or ""

        info_lbl = QLabel(f"Total Scanned Size: {total_sz}")
        info_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #111113; background: transparent;")
        self._card_layout.addWidget(info_lbl)

        table = QTableWidget(len(categories), 3)
        table.setHorizontalHeaderLabels(["Category", "Files", "Total Size"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setStyleSheet("border: 1px solid #E6E6E8; border-radius: 12px; background: #FFFFFF;")

        for row, c in enumerate(categories):
            cat = c.get("category", "")
            cnt = str(c.get("file_count", 0))
            sz = c.get("size_human") or c.get("total_bytes_human") or ""
            table.setItem(row, 0, QTableWidgetItem(cat))
            table.setItem(row, 1, QTableWidgetItem(cnt))
            table.setItem(row, 2, QTableWidgetItem(sz))

        table.setFixedHeight(min(260, 42 + len(categories) * 36))
        self._card_layout.addWidget(table)

    def _render_duplicates(self, data: Dict[str, Any]) -> None:
        groups = data.get("total_groups", 0)
        rec_sz = data.get("reclaimable_human") or data.get("total_reclaimable_bytes_human") or "0 B"
        dup_files = data.get("total_duplicate_files", 0)

        info_lbl = QLabel(f"Found {groups} duplicate groups ({dup_files} files) · Up to {rec_sz} reclaimable")
        info_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #111113; background: transparent;")
        self._card_layout.addWidget(info_lbl)

        top_groups = data.get("top_groups", [])
        for g in top_groups[:5]:
            files = g.get("files", [])
            if len(files) >= 2:
                keep_path = files[0].get("path", "")
                for extra in files[1:]:
                    p = extra.get("path", "")
                    self._candidate_items.append({
                        "path": p,
                        "name": extra.get("name") or os.path.basename(p),
                        "size_bytes": extra.get("size_bytes", 0),
                        "reason": "Exact duplicate",
                        "keep_path": keep_path,
                    })

    def _render_suggestions(self, data: Dict[str, Any]) -> None:
        target_h = data.get("target_human", "")
        total_up_to = data.get("total_up_to_human", "")
        reachable = data.get("reachable", False)
        status_txt = "Target can be reached" if reachable else "Partially reached"

        hdr_lbl = QLabel(f"Target: {target_h} · Potential: up to {total_up_to} ({status_txt})")
        hdr_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #111113; background: transparent;")
        self._card_layout.addWidget(hdr_lbl)

        suggestions = data.get("suggestions", [])
        for s in suggestions:
            box = QFrame()
            box.setStyleSheet("background-color: #F8F8F9; border: 1px solid #E6E6E8; border-radius: 12px; padding: 10px;")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(10, 8, 10, 8)
            box_layout.setSpacing(4)

            lbl_title = QLabel(f"• {s.get('label')}: {s.get('count')} files (up to {s.get('size_human')})")
            lbl_title.setStyleSheet("font-weight: 600; font-size: 13px; color: #111113; background: transparent;")
            lbl_desc = QLabel(s.get("reason", ""))
            lbl_desc.setStyleSheet("color: #6B6B72; font-size: 12px; background: transparent;")

            box_layout.addWidget(lbl_title)
            box_layout.addWidget(lbl_desc)
            self._card_layout.addWidget(box)

            # Add paths to cleanup candidates
            for p in s.get("paths", []):
                self._candidate_items.append({
                    "path": p,
                    "name": os.path.basename(p),
                    "size_bytes": s.get("size_bytes", 0) // max(1, s.get("count", 1)),
                    "reason": s.get("label", "Review candidate"),
                    "keep_path": None,
                })

        note_lbl = QLabel(data.get("note", ""))
        note_lbl.setWordWrap(True)
        note_lbl.setStyleSheet("font-size: 12px; color: #6B6B72; font-style: italic; background: transparent;")
        self._card_layout.addWidget(note_lbl)

    def _render_overview(self, data: Dict[str, Any]) -> None:
        total_files = data.get("total_files", 0)
        total_sz = data.get("total_size_human") or data.get("total_bytes_human") or ""
        root_path = data.get("root_path", "")

        stat_row = QHBoxLayout()
        stat_row.setSpacing(16)

        c1 = QFrame()
        c1.setStyleSheet("background: #F8F8F9; border: 1px solid #E6E6E8; border-radius: 12px; padding: 12px;")
        l1 = QVBoxLayout(c1)
        l1.addWidget(QLabel("TOTAL FILES"))
        v1 = QLabel(str(total_files))
        v1.setStyleSheet("font-size: 18px; font-weight: 700; color: #111113;")
        l1.addWidget(v1)

        c2 = QFrame()
        c2.setStyleSheet("background: #F8F8F9; border: 1px solid #E6E6E8; border-radius: 12px; padding: 12px;")
        l2 = QVBoxLayout(c2)
        l2.addWidget(QLabel("TOTAL SIZE"))
        v2 = QLabel(total_sz)
        v2.setStyleSheet("font-size: 18px; font-weight: 700; color: #2347E6;")
        l2.addWidget(v2)

        stat_row.addWidget(c1)
        stat_row.addWidget(c2)
        self._card_layout.addLayout(stat_row)


# ---------------------------------------------------------------------------
# ExplanationCard
# ---------------------------------------------------------------------------

class ExplanationCard(QWidget):
    """Card displaying streamed or deterministic explanation with source badge."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.card = QFrame(self)
        self.card.setStyleSheet("""
            QFrame#explCardFrame {
                background-color: #FFFFFF;
                border: 1px solid #E6E6E8;
                border-radius: 20px;
            }
        """)
        self.card.setObjectName("explCardFrame")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 6)
        outer.addWidget(self.card)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(10)

        # Header with badge
        self._hdr = QHBoxLayout()
        self._badge = QLabel("⚡ Thinking...")
        self._badge.setStyleSheet("font-family: Inter; font-size: 11px; font-weight: 600; color: #7C3AED; background-color: #F5F3FF; border: 1px solid #DDD6FE; border-radius: 10px; padding: 2px 8px;")
        self._hdr.addWidget(self._badge)
        self._hdr.addStretch()
        layout.addLayout(self._hdr)

        self._text_lbl = QLabel("")
        self._text_lbl.setWordWrap(True)
        self._text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._text_lbl.setStyleSheet("""
            QLabel {
                font-family: Inter;
                font-size: 14px;
                color: #111113;
                background: transparent;
                line-height: 1.5;
            }
        """)
        layout.addWidget(self._text_lbl)
        self._content = ""

    def set_pending(self) -> None:
        self._content = ""
        self._text_lbl.setText("Analyzing results...")
        self._badge.setText("⚡ Thinking...")
        self._badge.setStyleSheet("font-family: Inter; font-size: 11px; font-weight: 600; color: #7C3AED; background-color: #F5F3FF; border: 1px solid #DDD6FE; border-radius: 10px; padding: 2px 8px;")

    def append(self, text: str) -> None:
        if self._text_lbl.text() == "Analyzing results...":
            self._content = ""
        self._content += text
        self._text_lbl.setText(self._content)

    def finish(self, source: str) -> None:
        if source == "gemma":
            self._badge.setText("⚡ Explained by Gemma 4 (local)")
            self._badge.setStyleSheet("font-family: Inter; font-size: 11px; font-weight: 600; color: #7C3AED; background-color: #F5F3FF; border: 1px solid #DDD6FE; border-radius: 10px; padding: 2px 8px;")
        else:
            self._badge.setText("⚡ Basic mode")
            self._badge.setStyleSheet("font-family: Inter; font-size: 11px; font-weight: 600; color: #6B6B72; background-color: #F3F3F2; border: 1px solid #E6E6E8; border-radius: 10px; padding: 2px 8px;")


# ---------------------------------------------------------------------------
# NoticeCard
# ---------------------------------------------------------------------------

class NoticeCard(QWidget):
    """Informational or safety notice card."""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 6)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #F8F8F9;
                border: 1px solid #E6E6E8;
                border-radius: 16px;
            }
        """)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        icon_lbl = QLabel("ℹ")
        icon_lbl.setStyleSheet("font-size: 16px; color: #2347E6; font-weight: bold; background: transparent;")
        layout.addWidget(icon_lbl)

        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-family: Inter; font-size: 13px; color: #111113; background: transparent; line-height: 1.4;")
        layout.addWidget(lbl, 1)

        outer.addWidget(card)
