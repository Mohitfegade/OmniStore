"""
ui/duplicates.py
================
Duplicates page for OmniStore.
Finds exact byte-identical duplicate files from the latest scan using engine.duplicates.
Features:
- Friendly empty state when no scan exists yet, with button to jump to Analyzer
- Configurable minimum size threshold (1 KB, 100 KB, 1 MB, 10 MB, default 1 MB)
- Progress card showing stages in plain English and hashed byte counts
- Stat cards: Duplicate groups, Redundant files, and "Up to X reclaimable"
- Expandable card per duplicate group with per-copy details, dates, paths, and context menus
- Safety selection rules: user can NEVER select all copies in a group
- "Select extras (keep oldest copy)" per-group suggestion helper
- Bottom summary bar with "Review in Cleanup" button
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
import subprocess
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import app_state
from engine.drives import format_bytes
from engine.duplicates import DuplicateGroup, DuplicateResult
from engine.models import FileRecord, ScanResult
from ui import theme
from ui.components import Card, PageHeader, PillButton, StatCard
from workers.duplicate_worker import DuplicateWorker


# ---------------------------------------------------------------------------
# Duplicate Copy Row Widget
# ---------------------------------------------------------------------------

class DuplicateCopyRow(QWidget):
    """
    A single file copy row inside an expanded DuplicateGroupCard.
    Contains checkbox, middle-elided path, modified date, and context menu.
    """

    def __init__(self, file_record: FileRecord, on_toggle: callable, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.file_record = file_record
        self._on_toggle = on_toggle

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        self.checkbox = QCheckBox()
        self.checkbox.stateChanged.connect(lambda: self._on_toggle())
        layout.addWidget(self.checkbox)

        # File name and folder path (middle elided)
        self._path_lbl = QLabel(file_record.path)
        self._path_lbl.setToolTip(file_record.path)
        self._path_lbl.setStyleSheet("font-size: 13px; color: #111113; background: transparent;")
        layout.addWidget(self._path_lbl, 1)

        # Modified date
        try:
            dt = datetime.datetime.fromtimestamp(file_record.modified_ts)
            dt_str = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, OSError):
            dt_str = "—"

        self._date_lbl = QLabel(dt_str)
        self._date_lbl.setStyleSheet("font-size: 12px; color: #6B6B72; background: transparent;")
        layout.addWidget(self._date_lbl)

        # Context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if os.path.exists(self.file_record.path):
            try:
                os.startfile(self.file_record.path)
            except Exception as e:
                print(f"[OmniStore] Failed to open file: {e}")

    def _show_context_menu(self, pos) -> None:  # noqa: ANN001
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #E6E6E8;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                font-size: 13px;
                color: #111113;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #EDF1FD;
            }
        """)

        act_open = menu.addAction("Open file")
        act_open_folder = menu.addAction("Open containing folder")
        menu.addSeparator()
        act_copy = menu.addAction("Copy path")

        action = menu.exec(QCursor.pos())
        if action == act_open:
            if os.path.exists(self.file_record.path):
                os.startfile(self.file_record.path)
        elif action == act_open_folder:
            if os.path.exists(self.file_record.path):
                norm_p = os.path.normpath(self.file_record.path)
                subprocess.run(["explorer", f"/select,{norm_p}"], check=False)
            elif os.path.exists(self.file_record.parent_folder):
                os.startfile(self.file_record.parent_folder)
        elif action == act_copy:
            QGuiApplication.clipboard().setText(self.file_record.path)


# ---------------------------------------------------------------------------
# Expandable Duplicate Group Card
# ---------------------------------------------------------------------------

class DuplicateGroupCard(Card):
    """
    Expandable card representing one cluster of duplicate files.
    Enforces the safety rule: at least one copy in the group must remain kept.
    """

    def __init__(
        self,
        group: DuplicateGroup,
        on_selection_changed: callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent=parent)
        self.group = group
        self._on_selection_changed = on_selection_changed
        self._is_expanded = True
        self._rows: list[DuplicateCopyRow] = []

        # ── Group Header Row ─────────────────────────────────────────
        header_widget = QWidget()
        header_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        first_file = group.files[0] if group.files else None
        first_name = first_file.name if first_file else "Unknown"

        # Icon + First file name
        icon_lbl = QLabel("📄")
        icon_lbl.setStyleSheet("font-size: 16px; background: transparent;")
        header_layout.addWidget(icon_lbl)

        name_lbl = QLabel(first_name)
        name_lbl.setStyleSheet("font-size: 14px; font-weight: 600; color: #111113; background: transparent;")
        header_layout.addWidget(name_lbl)

        # Copies badge
        badge = QLabel(f"{group.copies} identical copies")
        badge.setObjectName("driveTypeBadge")
        header_layout.addWidget(badge)

        # Size each
        size_lbl = QLabel(f"·  {format_bytes(group.size_bytes)} each")
        size_lbl.setStyleSheet("font-size: 13px; color: #6B6B72; background: transparent;")
        header_layout.addWidget(size_lbl)

        header_layout.addStretch()

        # Reclaimable upper bound
        reclaim_lbl = QLabel(f"up to {format_bytes(group.reclaimable_bytes)} reclaimable")
        reclaim_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #2347E6; background: transparent;")
        header_layout.addWidget(reclaim_lbl)

        # Toggle arrow
        self._arrow_lbl = QLabel("▲")
        self._arrow_lbl.setStyleSheet("font-size: 11px; color: #6B6B72; background: transparent; padding-left: 8px;")
        header_layout.addWidget(self._arrow_lbl)

        # Toggle on header click
        header_widget.mousePressEvent = lambda e: self.toggle_expanded()
        self.body_layout.addWidget(header_widget)

        # ── Expanded Container ───────────────────────────────────────
        self._expanded_container = QWidget()
        expanded_vbox = QVBoxLayout(self._expanded_container)
        expanded_vbox.setContentsMargins(0, 8, 0, 0)
        expanded_vbox.setSpacing(6)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #E6E6E8; background-color: #E6E6E8; max-height: 1px;")
        expanded_vbox.addWidget(div)

        # Suggestion action row
        sugg_row = QHBoxLayout()
        sugg_row.setContentsMargins(4, 4, 4, 4)
        sugg_row.setSpacing(12)

        self._sugg_btn = QPushButton("Select extras (keep oldest copy)")
        self._sugg_btn.setObjectName("quickPickPill")
        self._sugg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sugg_btn.clicked.connect(self._select_extras_keep_oldest)
        sugg_row.addWidget(self._sugg_btn)

        sugg_note = QLabel("Suggestion: preserves the earliest modified file; unchecks & keeps at least one copy.")
        sugg_note.setStyleSheet("font-size: 12px; color: #6B6B72; background: transparent;")
        sugg_row.addWidget(sugg_note)
        sugg_row.addStretch()
        expanded_vbox.addLayout(sugg_row)

        # Rows list
        for f in group.files:
            row = DuplicateCopyRow(f, on_toggle=self._handle_row_toggle, parent=self)
            self._rows.append(row)
            expanded_vbox.addWidget(row)

        self.body_layout.addWidget(self._expanded_container)

    def toggle_expanded(self) -> None:
        self._is_expanded = not self._is_expanded
        self._expanded_container.setVisible(self._is_expanded)
        self._arrow_lbl.setText("▲" if self._is_expanded else "▼")

    def _select_extras_keep_oldest(self) -> None:
        """
        Safety helper: selects all copies except the oldest one.
        """
        if not self._rows:
            return

        # Find copy with smallest modified timestamp (oldest)
        oldest_row = min(self._rows, key=lambda r: r.file_record.modified_ts)

        for row in self._rows:
            if row is oldest_row:
                row.checkbox.setChecked(False)
            else:
                row.checkbox.setChecked(True)

        self._enforce_safety_rules()
        self._on_selection_changed()

    def _handle_row_toggle(self) -> None:
        self._enforce_safety_rules()
        self._on_selection_changed()

    def _enforce_safety_rules(self) -> None:
        """
        CRITICAL SAFETY RULE:
        The user can NEVER select all copies in a group.
        When N - 1 copies are selected, the remaining unchecked copy is DISABLED
        with a tooltip explaining that at least one copy must be kept.
        """
        checked_rows = [r for r in self._rows if r.checkbox.isChecked()]
        unchecked_rows = [r for r in self._rows if not r.checkbox.isChecked()]

        if len(checked_rows) >= len(self._rows) - 1 and len(unchecked_rows) == 1:
            # Lock the last remaining copy
            last_copy = unchecked_rows[0]
            last_copy.checkbox.setEnabled(False)
            last_copy.checkbox.setToolTip("At least one copy must be kept.")
            last_copy.setToolTip("At least one copy must be kept.")
        else:
            # Re-enable all checkboxes
            for r in self._rows:
                r.checkbox.setEnabled(True)
                r.checkbox.setToolTip("")
                r.setToolTip("")

    def get_selected_files(self) -> list[FileRecord]:
        return [r.file_record for r in self._rows if r.checkbox.isChecked()]

    def get_reclaimable_selected_bytes(self) -> int:
        return len(self.get_selected_files()) * self.group.size_bytes


# ---------------------------------------------------------------------------
# Duplicates Page
# ---------------------------------------------------------------------------

class DuplicatesPage(QWidget):
    """
    Main widget for the Duplicates screen.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("duplicatesPage")

        self._scan_result: Optional[ScanResult] = None
        self._dup_result: Optional[DuplicateResult] = None
        self._worker: Optional[DuplicateWorker] = None
        self._group_cards: list[DuplicateGroupCard] = []

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(32, 28, 32, 32)
        root_layout.setSpacing(20)

        # 1. Page Header
        header = PageHeader(
            "Duplicates",
            "Find and remove identical files scattered across your drives.",
        )
        root_layout.addWidget(header)

        # 2. No Scan Empty State (Shown if no scan exists yet)
        self._no_scan_card = Card()
        no_scan_layout = QVBoxLayout()
        no_scan_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        no_scan_layout.setContentsMargins(40, 50, 40, 50)
        no_scan_layout.setSpacing(12)

        ns_icon = QLabel("🔍")
        ns_icon.setStyleSheet("font-size: 40px; background: transparent;")
        ns_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        no_scan_layout.addWidget(ns_icon)

        ns_title = QLabel("No folder scanned yet")
        ns_title.setObjectName("comingNextTitle")
        ns_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        no_scan_layout.addWidget(ns_title)

        ns_desc = QLabel(
            "OmniStore finds exact duplicates within a scanned folder. "
            "Run a scan in the Analyzer first to detect redundant files."
        )
        ns_desc.setObjectName("comingNextBody")
        ns_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ns_desc.setWordWrap(True)
        no_scan_layout.addWidget(ns_desc)

        go_btn = PillButton("Go to Analyzer", primary=True)
        go_btn.clicked.connect(lambda: app_state.navigate_to(1))
        btn_center = QHBoxLayout()
        btn_center.addStretch()
        btn_center.addWidget(go_btn)
        btn_center.addStretch()
        no_scan_layout.addLayout(btn_center)

        self._no_scan_card.body_layout.addLayout(no_scan_layout)
        root_layout.addWidget(self._no_scan_card)

        # 3. Controls Card (Shown when scan data is available)
        self._controls_card = Card()
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(12)

        self._scanned_folder_lbl = QLabel("Based on your scan of: —")
        self._scanned_folder_lbl.setStyleSheet("font-size: 13px; font-weight: 500; color: #111113; background: transparent;")
        controls_layout.addWidget(self._scanned_folder_lbl)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(12)

        min_size_lbl = QLabel("Minimum size:")
        min_size_lbl.setStyleSheet("font-size: 13px; color: #6B6B72; background: transparent;")
        ctrl_row.addWidget(min_size_lbl)

        self._min_size_combo = QComboBox()
        self._min_size_combo.addItem("1 KB", 1024)
        self._min_size_combo.addItem("100 KB", 100 * 1024)
        self._min_size_combo.addItem("1 MB", 1024 * 1024)
        self._min_size_combo.addItem("10 MB", 10 * 1024 * 1024)
        # Default 1 MB
        self._min_size_combo.setCurrentIndex(2)
        ctrl_row.addWidget(self._min_size_combo)

        ctrl_row.addStretch()

        self._find_btn = PillButton("Find duplicates", primary=True)
        self._find_btn.clicked.connect(self._toggle_find_duplicates)
        ctrl_row.addWidget(self._find_btn)

        controls_layout.addLayout(ctrl_row)
        self._controls_card.body_layout.addLayout(controls_layout)
        root_layout.addWidget(self._controls_card)

        # 4. Progress Card (Hidden by default)
        self._progress_card = Card()
        prog_layout = QVBoxLayout()
        prog_layout.setSpacing(8)

        prog_top = QHBoxLayout()
        self._prog_stage_lbl = QLabel("Comparing file sizes...")
        self._prog_stage_lbl.setStyleSheet("font-weight: 600; font-size: 14px; background: transparent;")
        self._prog_counts_lbl = QLabel("0 / 0 files · 0 B hashed")
        self._prog_counts_lbl.setStyleSheet("color: #6B6B72; font-size: 13px; background: transparent;")
        prog_top.addWidget(self._prog_stage_lbl)
        prog_top.addStretch()
        prog_top.addWidget(self._prog_counts_lbl)
        prog_layout.addLayout(prog_top)

        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setValue(0)
        prog_layout.addWidget(self._prog_bar)

        self._progress_card.body_layout.addLayout(prog_layout)
        self._progress_card.hide()
        root_layout.addWidget(self._progress_card)

        # 5. Results Container
        self._results_container = QWidget()
        results_layout = QVBoxLayout(self._results_container)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(16)

        # Stat cards row
        stat_row = QHBoxLayout()
        stat_row.setSpacing(16)

        self._sc_groups = StatCard("Duplicate Groups", "—")
        self._sc_files = StatCard("Redundant Files", "—")
        self._sc_reclaim = StatCard("Potential Savings", "—")
        self._sc_reclaim.setToolTip(
            "Assumes you keep one copy of each file. Actual space freed depends on the drive."
        )

        stat_row.addWidget(self._sc_groups)
        stat_row.addWidget(self._sc_files)
        stat_row.addWidget(self._sc_reclaim)
        results_layout.addLayout(stat_row)

        # Subtitle summary line
        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet("color: #6B6B72; font-size: 12px; background: transparent;")
        results_layout.addWidget(self._summary_lbl)

        # Empty results card (No duplicates found)
        self._empty_results_card = Card()
        empty_res_layout = QVBoxLayout()
        empty_res_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_res_layout.setContentsMargins(30, 40, 30, 40)
        empty_res_layout.setSpacing(8)

        er_icon = QLabel("✨")
        er_icon.setStyleSheet("font-size: 32px; background: transparent;")
        er_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_res_layout.addWidget(er_icon)

        self._er_title = QLabel("No exact duplicates found in this scan.")
        self._er_title.setObjectName("comingNextTitle")
        self._er_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_res_layout.addWidget(self._er_title)

        self._er_sub = QLabel("No duplicate files larger than the selected minimum size were detected.")
        self._er_sub.setObjectName("comingNextBody")
        self._er_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_res_layout.addWidget(self._er_sub)

        self._empty_results_card.body_layout.addLayout(empty_res_layout)
        self._empty_results_card.hide()
        results_layout.addWidget(self._empty_results_card)

        # Duplicate groups list container
        self._groups_vbox = QVBoxLayout()
        self._groups_vbox.setSpacing(14)
        results_layout.addLayout(self._groups_vbox)

        self._results_container.hide()
        root_layout.addWidget(self._results_container)

        # 6. Bottom Sticky Summary Bar
        self._bottom_bar = QFrame()
        self._bottom_bar.setObjectName("card")
        self._bottom_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bottom_layout = QHBoxLayout(self._bottom_bar)
        bottom_layout.setContentsMargins(24, 14, 24, 14)
        bottom_layout.setSpacing(16)

        self._selection_lbl = QLabel("0 files selected, up to 0 B")
        self._selection_lbl.setStyleSheet("font-size: 14px; font-weight: 500; color: #111113; background: transparent;")
        bottom_layout.addWidget(self._selection_lbl)

        bottom_layout.addStretch()

        self._cleanup_btn = PillButton("Review in Cleanup", primary=True)
        self._cleanup_btn.setEnabled(False)
        self._cleanup_btn.clicked.connect(self._review_in_cleanup)
        bottom_layout.addWidget(self._cleanup_btn)

        self._bottom_bar.hide()
        root_layout.addWidget(self._bottom_bar)

        root_layout.addStretch()

        # Connect global app state listeners
        app_state.add_scan_listener(self._on_app_state_scan_updated)
        app_state.add_duplicates_listener(self._on_app_state_duplicates_updated)

        # Check initial state
        self._on_app_state_scan_updated(app_state.get_latest_scan())

    # -----------------------------------------------------------------------
    # State & Event Handlers
    # -----------------------------------------------------------------------

    def _on_app_state_scan_updated(self, scan_result: ScanResult) -> None:
        self._scan_result = scan_result
        if scan_result and scan_result.total_files > 0:
            self._no_scan_card.hide()
            self._controls_card.show()
            self._scanned_folder_lbl.setText(f"Based on your scan of: {scan_result.root_path} ({scan_result.total_files:,} files)")
        else:
            self._no_scan_card.show()
            self._controls_card.hide()
            self._results_container.hide()
            self._bottom_bar.hide()

    def _on_app_state_duplicates_updated(self, dup_result: DuplicateResult) -> None:
        if dup_result is not self._dup_result:
            self._display_duplicate_results(dup_result)

    def _toggle_find_duplicates(self) -> None:
        if self._worker and self._worker.isRunning():
            self._cancel_duplicates()
        else:
            self._start_find_duplicates()

    def _start_find_duplicates(self) -> None:
        if not self._scan_result:
            return

        min_bytes = self._min_size_combo.currentData()

        # Switch button to Cancel
        self._find_btn.setText("Cancel")
        self._find_btn.setObjectName("pillCancel")
        self._find_btn.style().unpolish(self._find_btn)
        self._find_btn.style().polish(self._find_btn)

        self._results_container.hide()
        self._bottom_bar.hide()
        self._empty_results_card.hide()

        # Show progress card
        self._prog_stage_lbl.setText("Comparing file sizes...")
        self._prog_counts_lbl.setText(f"0 / {self._scan_result.total_files:,} files · 0 B hashed")
        self._prog_bar.setValue(0)
        self._progress_card.show()

        # Launch worker
        self._worker = DuplicateWorker(
            scan_result=self._scan_result,
            min_size_bytes=min_bytes,
            parent=self,
        )
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.start()

    def _cancel_duplicates(self) -> None:
        if self._worker:
            self._prog_stage_lbl.setText("Stopping comparison...")
            self._find_btn.setEnabled(False)
            self._worker.cancel()

    def _on_worker_progress(self, stage: str, done: int, total: int, bytes_hashed: int) -> None:
        self._prog_stage_lbl.setText(stage)
        pct = int((done / total) * 100) if total > 0 else 0
        self._prog_bar.setValue(min(100, max(0, pct)))
        self._prog_counts_lbl.setText(f"{done:,} / {total:,} files · {format_bytes(bytes_hashed)} hashed")

    def _on_worker_finished(self, result: DuplicateResult) -> None:
        self._worker = None
        app_state.set_latest_duplicates(result)
        if self._dup_result is not result:
            self._display_duplicate_results(result)

    def _on_worker_failed(self, error_msg: str) -> None:
        self._worker = None
        self._reset_find_button()
        self._progress_card.hide()
        self._summary_lbl.setText(f"Analysis failed: {error_msg}")
        self._results_container.show()

    def _reset_find_button(self) -> None:
        self._find_btn.setText("Find duplicates")
        self._find_btn.setObjectName("pillPrimary")
        self._find_btn.setEnabled(True)
        self._find_btn.style().unpolish(self._find_btn)
        self._find_btn.style().polish(self._find_btn)

    def _display_duplicate_results(self, result: DuplicateResult) -> None:
        self._dup_result = result
        self._reset_find_button()
        self._progress_card.hide()

        # Clear previous group cards
        while self._groups_vbox.count():
            item = self._groups_vbox.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._group_cards.clear()

        # Update StatCards
        redundant_count = max(0, result.total_duplicate_files - result.total_groups)
        self._sc_groups.set_number(f"{result.total_groups:,}")
        self._sc_files.set_number(f"{redundant_count:,}")
        self._sc_reclaim.set_number(f"Up to {format_bytes(result.total_reclaimable_bytes)}")

        min_txt = self._min_size_combo.currentText()
        status_txt = " (Cancelled)" if result.cancelled else ""
        dur_txt = f" in {result.duration_seconds:.2f}s" if result.duration_seconds > 0 else ""
        self._summary_lbl.setText(
            f"Comparison completed{status_txt}{dur_txt}. "
            f"Filtered by minimum size {min_txt}. "
            f"{format_bytes(result.bytes_hashed)} hashed."
        )

        if result.total_groups == 0:
            self._er_sub.setText(f"No duplicate files larger than {min_txt} were detected.")
            self._empty_results_card.show()
            self._bottom_bar.hide()
        else:
            self._empty_results_card.hide()
            for group in result.groups:
                card = DuplicateGroupCard(
                    group=group,
                    on_selection_changed=self._update_selection_summary,
                    parent=self,
                )
                self._group_cards.append(card)
                self._groups_vbox.addWidget(card)

            self._bottom_bar.show()
            self._update_selection_summary()

        self._results_container.show()

    def _update_selection_summary(self) -> None:
        """Calculate total selected files across all duplicate groups."""
        total_selected = 0
        total_bytes = 0

        for card in self._group_cards:
            files = card.get_selected_files()
            total_selected += len(files)
            total_bytes += len(files) * card.group.size_bytes

        self._selection_lbl.setText(f"{total_selected} files selected, up to {format_bytes(total_bytes)}")
        self._cleanup_btn.setEnabled(total_selected > 0)

    def _review_in_cleanup(self) -> None:
        """
        Send all selected FileRecords to app_state for review in Cleanup.
        Does NOT delete any files.
        """
        items: list[dict] = []
        for card in self._group_cards:
            selected_files = card.get_selected_files()
            if not selected_files:
                continue
            unselected = [f for f in card.group.files if f not in selected_files]
            keep_path = unselected[0].path if unselected else None
            for f in selected_files:
                items.append({
                    "file": f,
                    "reason": "Exact duplicate",
                    "keep_path": keep_path,
                    "group_id": card.group.group_id,
                })

        if not items:
            return

        app_state.set_pending_cleanup(items)
        print(f"[OmniStore] Sent {len(items)} files to pending cleanup.")

        # Switch to Cleanup tab (index 3)
        app_state.navigate_to(3)


def build_duplicates_scroll() -> QScrollArea:
    """Convenience factory to wrap DuplicatesPage in a QScrollArea."""
    page = DuplicatesPage()
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(page)
    return sa
