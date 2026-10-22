"""
ui/cleanup.py
=============
Cleanup Center for OmniStore — the only place that can remove files.

Files are ALWAYS sent to the Windows Recycle Bin (never permanently deleted).

Layout
------
1. PageHeader
2. Empty state card   – shown when nothing is queued
3. Review candidates card (two tools: Large files / Old large files) – opt-in rows
4. Review list card   – current plan table (plan items + blocked items in muted section)
5. Summary + action bar – "Move N files to Recycle Bin" button
6. Progress card      – shown while worker runs
7. Result card        – shown after completion

No PySide6 restrictions apply here (this is the UI layer).
"""

from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import app_state
from engine.cleanup import (
    REASON_DUPLICATE,
    REASON_LARGE,
    REASON_OLD,
    CleanupItem,
    CleanupPlan,
    build_plan,
)
from engine.drives import format_bytes
from engine.models import FileRecord
from engine.query import filter_files
from ui.components import Card, PageHeader, PillButton, StatCard
from workers.cleanup_worker import CleanupWorker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WARNING_ICON = "⚠"
_OK_ICON      = "🗑"


def _ts_to_str(ts: float) -> str:
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return "—"


def _rel_path(path: str) -> str:
    """Show a shortened path for display."""
    try:
        return str(Path(path).parent)
    except Exception:
        return os.path.dirname(path)


# ---------------------------------------------------------------------------
# Dialogs & Results
# ---------------------------------------------------------------------------

from ui.cleanup_dialogs import CleanupResultCard, ConfirmDialog



# ---------------------------------------------------------------------------
# Candidate Rows (Large / Old large files) — opt-in only
# ---------------------------------------------------------------------------

class CandidateTable(QTableWidget):
    """
    Read-only table showing candidate files. Rows have an 'Add to review'
    checkbox in column 0. Nothing is pre-checked.
    """

    COLS = ["", "Name", "Size", "Modified", "Folder"]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(0, len(self.COLS), parent)
        self.setHorizontalHeaderLabels(self.COLS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setMinimumHeight(150)
        self._records: List[FileRecord] = []

    def load_records(self, records: List[FileRecord]) -> None:
        self.setRowCount(0)
        self._records = records
        for row_idx, rec in enumerate(records):
            self.insertRow(row_idx)
            cb = QTableWidgetItem()
            cb.setCheckState(Qt.CheckState.Unchecked)
            cb.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            self.setItem(row_idx, 0, cb)
            self.setItem(row_idx, 1, QTableWidgetItem(rec.name))
            self.setItem(row_idx, 2, QTableWidgetItem(format_bytes(rec.size_bytes)))
            self.setItem(row_idx, 3, QTableWidgetItem(_ts_to_str(rec.modified_ts)))
            self.setItem(row_idx, 4, QTableWidgetItem(rec.parent_folder))

    def get_checked_records(self) -> List[FileRecord]:
        checked = []
        for row in range(self.rowCount()):
            cb_item = self.item(row, 0)
            if cb_item and cb_item.checkState() == Qt.CheckState.Checked:
                checked.append(self._records[row])
        return checked


# ---------------------------------------------------------------------------
# Plan Table — items in the current plan
# ---------------------------------------------------------------------------

class PlanTable(QTableWidget):
    """Table showing plan items (active + blocked). Has a Remove button per active row."""

    COLS = ["Reason", "Name", "Size", "Folder", "Keeping", ""]

    def __init__(self, on_remove: callable, parent: Optional[QWidget] = None) -> None:
        super().__init__(0, len(self.COLS), parent)
        self._on_remove = on_remove
        self.setHorizontalHeaderLabels(self.COLS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self._item_paths: List[str] = []

    def load_plan(self, plan: CleanupPlan, warnings: List[Dict[str, str]]) -> None:
        warn_paths = {w["path"]: w["message"] for w in warnings}
        self.setRowCount(0)
        self._item_paths = []

        for item in plan.items:
            row = self.rowCount()
            self.insertRow(row)
            self._item_paths.append(item.path)

            reason_lbl = item.reason
            warn_msg = warn_paths.get(item.path)
            if warn_msg:
                reason_lbl = f"{_WARNING_ICON} {item.reason}"

            reason_item = QTableWidgetItem(reason_lbl)
            if warn_msg:
                reason_item.setForeground(QColor("#B45309"))
                reason_item.setToolTip(warn_msg)
            self.setItem(row, 0, reason_item)

            self.setItem(row, 1, QTableWidgetItem(item.name))
            self.setItem(row, 2, QTableWidgetItem(format_bytes(item.size_bytes)))
            self.setItem(row, 3, QTableWidgetItem(item.keep_path and str(Path(item.keep_path).parent) or item.path and str(Path(item.path).parent) or ""))

            keep_text = os.path.basename(item.keep_path) if item.keep_path else "—"
            keep_item = QTableWidgetItem(keep_text)
            if item.keep_path:
                keep_item.setToolTip(item.keep_path)
            self.setItem(row, 4, keep_item)

            # Remove button
            remove_btn = QPushButton("Remove")
            remove_btn.setObjectName("quickPickPill")
            remove_btn.setFixedHeight(26)
            idx = row
            remove_btn.clicked.connect(lambda _, i=idx: self._on_remove(i))
            self.setCellWidget(row, 5, remove_btn)

        # Blocked items (muted section)
        if plan.blocked:
            # Separator row
            sep_row = self.rowCount()
            self.insertRow(sep_row)
            sep_item = QTableWidgetItem(f"  Not included ({len(plan.blocked)} item(s))")
            sep_item.setFlags(Qt.ItemFlag.NoItemFlags)
            sep_item.setForeground(QColor("#9CA3AF"))
            sep_item.setBackground(QColor("#F3F4F6"))
            self.setSpan(sep_row, 0, 1, len(self.COLS))
            self.setItem(sep_row, 0, sep_item)
            self._item_paths.append("")  # placeholder

            for blocked in plan.blocked:
                row = self.rowCount()
                self.insertRow(row)
                self._item_paths.append("")

                reason_item = QTableWidgetItem(blocked.get("reason", "Blocked"))
                reason_item.setForeground(QColor("#9CA3AF"))
                self.setItem(row, 0, reason_item)

                name = os.path.basename(blocked.get("path", ""))
                name_item = QTableWidgetItem(name)
                name_item.setForeground(QColor("#9CA3AF"))
                name_item.setToolTip(blocked.get("path", ""))
                self.setItem(row, 1, name_item)

                for col in range(2, len(self.COLS)):
                    empty = QTableWidgetItem("—")
                    empty.setForeground(QColor("#9CA3AF"))
                    self.setItem(row, col, empty)

    def remove_row_at(self, row_idx: int) -> Optional[str]:
        if row_idx < 0 or row_idx >= len(self._item_paths):
            return None
        path = self._item_paths[row_idx]
        self.removeRow(row_idx)
        self._item_paths.pop(row_idx)
        return path


# ---------------------------------------------------------------------------
# Cleanup Page
# ---------------------------------------------------------------------------

class CleanupPage(QWidget):
    """Main widget for the Cleanup screen."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("cleanupPage")

        self._plan_items:  List[CleanupItem] = []   # current working plan
        self._current_plan: Optional[CleanupPlan] = None
        self._worker: Optional[CleanupWorker] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 32)
        root.setSpacing(20)

        # 1. Header
        root.addWidget(PageHeader(
            "Cleanup Center",
            "Review and remove files by sending them to the Recycle Bin. "
            "Nothing is permanently deleted.",
        ))

        # 2. Empty state
        self._empty_card = Card()
        empty_vbox = QVBoxLayout()
        empty_vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_vbox.setContentsMargins(40, 50, 40, 50)
        empty_vbox.setSpacing(12)

        ei = QLabel("🗑")
        ei.setStyleSheet("font-size:40px; background:transparent;")
        ei.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_vbox.addWidget(ei)

        et = QLabel("Nothing to review yet.")
        et.setObjectName("comingNextTitle")
        et.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_vbox.addWidget(et)

        eb = QLabel(
            "Find duplicates in the Duplicates tab and click 'Review in Cleanup', "
            "or use the tools below to add large or old files for review."
        )
        eb.setObjectName("comingNextBody")
        eb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        eb.setWordWrap(True)
        empty_vbox.addWidget(eb)

        go_dup_btn = PillButton("Go to Duplicates", primary=True)
        go_dup_btn.clicked.connect(lambda: app_state.navigate_to(2))
        btn_c = QHBoxLayout()
        btn_c.addStretch()
        btn_c.addWidget(go_dup_btn)
        btn_c.addStretch()
        empty_vbox.addLayout(btn_c)

        self._empty_card.body_layout.addLayout(empty_vbox)
        root.addWidget(self._empty_card)

        # 3. Candidate tools card
        self._candidates_card = Card()
        cand_vbox = QVBoxLayout()
        cand_vbox.setSpacing(16)

        cand_title = QLabel("Review other candidates")
        cand_title.setObjectName("sectionHeading")
        cand_vbox.addWidget(cand_title)

        disclaimer = QLabel(
            "These are only files you may want to look at. "
            "Large or old does not mean unneeded. Nothing is pre-checked."
        )
        disclaimer.setStyleSheet("color:#6B6B72; font-size:13px; background:transparent;")
        disclaimer.setWordWrap(True)
        cand_vbox.addWidget(disclaimer)

        # --- Large files tool ---
        lf_hdr = QLabel("Large files")
        lf_hdr.setStyleSheet("font-weight:600; font-size:14px; background:transparent;")
        cand_vbox.addWidget(lf_hdr)

        lf_ctrl_row = QHBoxLayout()
        lf_ctrl_row.setSpacing(10)
        lf_min_lbl = QLabel("Minimum size:")
        lf_min_lbl.setStyleSheet("color:#6B6B72; font-size:13px; background:transparent;")
        lf_ctrl_row.addWidget(lf_min_lbl)

        self._lf_combo = QComboBox()
        self._lf_combo.addItem("100 MB",   100 * 1024 * 1024)
        self._lf_combo.addItem("500 MB",   500 * 1024 * 1024)
        self._lf_combo.addItem("1 GB",     1024 * 1024 * 1024)
        lf_ctrl_row.addWidget(self._lf_combo)
        lf_ctrl_row.addStretch()

        lf_btn = PillButton("Show large files", primary=False)
        lf_btn.clicked.connect(self._load_large_files)
        lf_ctrl_row.addWidget(lf_btn)
        cand_vbox.addLayout(lf_ctrl_row)

        self._lf_table = CandidateTable()
        self._lf_table.hide()
        cand_vbox.addWidget(self._lf_table)

        lf_add_btn = PillButton("Add selected to review list", primary=False)
        lf_add_btn.clicked.connect(lambda: self._add_candidates(self._lf_table, REASON_LARGE))
        self._lf_add_btn = lf_add_btn
        self._lf_add_btn.hide()
        cand_vbox.addWidget(lf_add_btn)

        # Divider
        div1 = QFrame()
        div1.setFrameShape(QFrame.Shape.HLine)
        div1.setStyleSheet("color:#E6E6E8; background-color:#E6E6E8; max-height:1px;")
        cand_vbox.addWidget(div1)

        # --- Old large files tool ---
        olf_hdr = QLabel("Old large files")
        olf_hdr.setStyleSheet("font-weight:600; font-size:14px; background:transparent;")
        cand_vbox.addWidget(olf_hdr)

        olf_ctrl_row = QHBoxLayout()
        olf_ctrl_row.setSpacing(10)
        olf_sz_lbl = QLabel("Min size:")
        olf_sz_lbl.setStyleSheet("color:#6B6B72; font-size:13px; background:transparent;")
        olf_ctrl_row.addWidget(olf_sz_lbl)

        self._olf_size_combo = QComboBox()
        self._olf_size_combo.addItem("100 MB",  100 * 1024 * 1024)
        self._olf_size_combo.addItem("500 MB",  500 * 1024 * 1024)
        self._olf_size_combo.addItem("1 GB",    1024 * 1024 * 1024)
        olf_ctrl_row.addWidget(self._olf_size_combo)

        olf_age_lbl = QLabel("Not accessed in:")
        olf_age_lbl.setStyleSheet("color:#6B6B72; font-size:13px; background:transparent;")
        olf_ctrl_row.addWidget(olf_age_lbl)

        self._olf_age_combo = QComboBox()
        self._olf_age_combo.addItem("6 months",  6)
        self._olf_age_combo.addItem("12 months", 12)
        self._olf_age_combo.addItem("24 months", 24)
        self._olf_age_combo.setToolTip(
            "Access time is based on the file's 'Last Accessed' timestamp. "
            "Note: Windows may not always update access times accurately "
            "(depends on system settings and NTFS configuration)."
        )
        olf_ctrl_row.addWidget(self._olf_age_combo)
        olf_ctrl_row.addStretch()

        olf_btn = PillButton("Show old large files", primary=False)
        olf_btn.clicked.connect(self._load_old_files)
        olf_ctrl_row.addWidget(olf_btn)
        cand_vbox.addLayout(olf_ctrl_row)

        self._olf_table = CandidateTable()
        self._olf_table.hide()
        cand_vbox.addWidget(self._olf_table)

        olf_add_btn = PillButton("Add selected to review list", primary=False)
        olf_add_btn.clicked.connect(lambda: self._add_candidates(self._olf_table, REASON_OLD))
        self._olf_add_btn = olf_add_btn
        self._olf_add_btn.hide()
        cand_vbox.addWidget(olf_add_btn)

        self._candidates_card.body_layout.addLayout(cand_vbox)
        root.addWidget(self._candidates_card)

        # 4. Plan review card
        self._plan_card = Card()
        plan_vbox = QVBoxLayout()
        plan_vbox.setSpacing(12)

        plan_title = QLabel("Review list")
        plan_title.setObjectName("sectionHeading")
        plan_vbox.addWidget(plan_title)

        self._plan_table = PlanTable(on_remove=self._remove_plan_item)
        plan_vbox.addWidget(self._plan_table)

        self._plan_card.body_layout.addLayout(plan_vbox)
        root.addWidget(self._plan_card)

        # 5. Summary + action bar
        self._summary_card = Card()
        summary_vbox = QVBoxLayout()
        summary_vbox.setSpacing(10)

        summary_row = QHBoxLayout()
        self._summary_lbl = QLabel("0 files, 0 B")
        self._summary_lbl.setStyleSheet("font-size:15px; font-weight:600; background:transparent;")
        summary_row.addWidget(self._summary_lbl)
        summary_row.addStretch()

        self._recycle_btn = PillButton("Move 0 files to Recycle Bin", primary=True)
        self._recycle_btn.setEnabled(False)
        self._recycle_btn.clicked.connect(self._start_cleanup)
        summary_row.addWidget(self._recycle_btn)

        summary_vbox.addLayout(summary_row)

        bin_note = QLabel("Files go to the Recycle Bin, so you can restore them from there.")
        bin_note.setStyleSheet("color:#6B6B72; font-size:13px; background:transparent;")
        summary_vbox.addWidget(bin_note)

        self._summary_card.body_layout.addLayout(summary_vbox)
        root.addWidget(self._summary_card)

        # 6. Progress card
        self._prog_card = Card()
        prog_vbox = QVBoxLayout()
        prog_vbox.setSpacing(8)
        prog_hdr = QHBoxLayout()
        self._prog_stage_lbl = QLabel("Moving files to Recycle Bin…")
        self._prog_stage_lbl.setStyleSheet("font-weight:600; font-size:14px; background:transparent;")
        self._prog_count_lbl = QLabel("0 / 0")
        self._prog_count_lbl.setStyleSheet("color:#6B6B72; font-size:13px; background:transparent;")
        prog_hdr.addWidget(self._prog_stage_lbl)
        prog_hdr.addStretch()
        prog_hdr.addWidget(self._prog_count_lbl)
        prog_vbox.addLayout(prog_hdr)
        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, 100)
        prog_vbox.addWidget(self._prog_bar)
        cancel_btn = PillButton("Cancel", primary=False)
        cancel_btn.clicked.connect(self._cancel_cleanup)
        self._cancel_btn = cancel_btn
        prog_row = QHBoxLayout()
        prog_row.addStretch()
        prog_row.addWidget(cancel_btn)
        prog_vbox.addLayout(prog_row)
        self._prog_card.body_layout.addLayout(prog_vbox)
        self._prog_card.hide()
        root.addWidget(self._prog_card)

        # 7. Result card
        self._result_card = CleanupResultCard()
        self._result_card.hide()
        root.addWidget(self._result_card)

        root.addStretch()

        # Listen for incoming cleanup items from Duplicates page
        app_state.add_cleanup_listener(self._on_pending_cleanup)

        # Load initial state
        self._on_pending_cleanup(app_state.get_pending_cleanup())

    # -----------------------------------------------------------------------
    # State
    # -----------------------------------------------------------------------

    def _on_pending_cleanup(self, raw_items: List[Dict[str, Any]]) -> None:
        """Called when Duplicates page sends items here via app_state."""
        new_items = self._raw_to_cleanup_items(raw_items)
        # Merge: don't add duplicates already in list
        existing_paths = {it.path for it in self._plan_items}
        for it in new_items:
            if it.path not in existing_paths:
                self._plan_items.append(it)
        self._rebuild_plan()

    def _raw_to_cleanup_items(self, raw: List[Dict[str, Any]]) -> List[CleanupItem]:
        """Convert the raw dicts from app_state into CleanupItem objects."""
        result = []
        for d in raw:
            file_rec: Optional[FileRecord] = d.get("file")
            reason: str = d.get("reason", REASON_LARGE)
            if file_rec is None:
                continue
            keep_path = d.get("keep_path")
            # If keep_path not given but this is a duplicate, derive from DuplicateResult
            if reason == REASON_DUPLICATE and not keep_path:
                keep_path = self._find_keep_path(file_rec)
            result.append(CleanupItem(
                path=file_rec.path,
                name=file_rec.name,
                size_bytes=file_rec.size_bytes,
                modified_ts=file_rec.modified_ts,
                reason=reason,
                group_id=d.get("group_id"),
                keep_path=keep_path,
            ))
        return result

    def _find_keep_path(self, file_rec: FileRecord) -> Optional[str]:
        """Find the oldest copy in the same duplicate group to use as keep_path."""
        dup_res = app_state.get_latest_duplicates()
        if not dup_res:
            return None
        norm = os.path.normcase(os.path.abspath(file_rec.path))
        for group in dup_res.groups:
            for f in group.files:
                if os.path.normcase(os.path.abspath(f.path)) == norm:
                    oldest = min(group.files, key=lambda r: r.modified_ts)
                    return oldest.path
        return None

    def _rebuild_plan(self) -> None:
        dup_res = app_state.get_latest_duplicates()
        self._current_plan = build_plan(self._plan_items, duplicate_result=dup_res)
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        plan = self._current_plan
        has_items = bool(self._plan_items)

        self._empty_card.setVisible(not has_items)
        self._plan_card.setVisible(has_items)
        self._summary_card.setVisible(has_items)

        if not plan:
            return

        # Rebuild plan table
        self._plan_table.load_plan(plan, plan.warnings)

        # Summary bar
        n = len(plan.items)
        self._summary_lbl.setText(
            f"{n} file(s), up to {format_bytes(plan.total_bytes)}"
        )
        self._recycle_btn.setText(f"Move {n} file(s) to Recycle Bin")
        self._recycle_btn.setEnabled(n > 0)

    # -----------------------------------------------------------------------
    # Candidate tools
    # -----------------------------------------------------------------------

    def _load_large_files(self) -> None:
        scan = app_state.get_latest_scan()
        if not scan:
            self._lf_table.load_records([])
            self._lf_table.show()
            self._lf_add_btn.show()
            return
        min_sz = self._lf_combo.currentData()
        records = filter_files(scan, min_size=min_sz, sort_by="size", descending=True, limit=200)
        self._lf_table.load_records(records)
        self._lf_table.show()
        self._lf_add_btn.show()

    def _load_old_files(self) -> None:
        scan = app_state.get_latest_scan()
        if not scan:
            self._olf_table.load_records([])
            self._olf_table.show()
            self._olf_add_btn.show()
            return
        min_sz = self._olf_size_combo.currentData()
        months = self._olf_age_combo.currentData()
        cutoff = datetime.datetime.now() - datetime.timedelta(days=months * 30)
        cutoff_ts = cutoff.timestamp()
        records = filter_files(
            scan,
            min_size=min_sz,
            not_accessed_since=cutoff_ts,
            sort_by="size",
            descending=True,
            limit=200,
        )
        self._olf_table.load_records(records)
        self._olf_table.show()
        self._olf_add_btn.show()

    def _add_candidates(self, table: CandidateTable, reason: str) -> None:
        checked = table.get_checked_records()
        if not checked:
            return
        existing = {it.path for it in self._plan_items}
        for rec in checked:
            if rec.path not in existing:
                self._plan_items.append(CleanupItem(
                    path=rec.path,
                    name=rec.name,
                    size_bytes=rec.size_bytes,
                    modified_ts=rec.modified_ts,
                    reason=reason,
                ))
        self._rebuild_plan()

    # -----------------------------------------------------------------------
    # Plan management
    # -----------------------------------------------------------------------

    def _remove_plan_item(self, row_idx: int) -> None:
        """Remove item at plan table row index from the working list."""
        removed_path = self._plan_table.remove_row_at(row_idx)
        if removed_path:
            self._plan_items = [it for it in self._plan_items if it.path != removed_path]
            self._rebuild_plan()

    # -----------------------------------------------------------------------
    # Cleanup execution
    # -----------------------------------------------------------------------

    def _start_cleanup(self) -> None:
        if not self._current_plan or not self._current_plan.items:
            return

        dlg = ConfirmDialog(self._current_plan, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Show progress
        self._prog_bar.setValue(0)
        self._prog_stage_lbl.setText("Moving files to Recycle Bin…")
        self._prog_count_lbl.setText(f"0 / {len(self._current_plan.items)}")
        self._prog_card.show()
        self._summary_card.hide()
        self._result_card.hide()
        self._cancel_btn.setEnabled(True)

        self._worker = CleanupWorker(self._current_plan, parent=self)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.start()

    def _cancel_cleanup(self) -> None:
        if self._worker and self._worker.isRunning():
            self._prog_stage_lbl.setText("Cancelling…")
            self._cancel_btn.setEnabled(False)
            self._worker.cancel()

    def _on_worker_progress(self, done: int, total: int, path: str) -> None:
        pct = int((done / total) * 100) if total > 0 else 0
        self._prog_bar.setValue(pct)
        self._prog_count_lbl.setText(f"{done} / {total}")
        if path:
            self._prog_stage_lbl.setText(f"Recycling: {os.path.basename(path)}")

    def _on_worker_finished(self, outcome) -> None:
        self._worker = None
        self._prog_card.hide()
        self._result_card.display_outcome(outcome)
        self._summary_card.show()

        # Update app_state (removes recycled files, updates duplicate groups, clears pending)
        app_state.apply_cleanup_outcome(outcome)

        # Remove succeeded files from working plan items
        succeeded_paths = {s["path"] for s in outcome.succeeded}
        self._plan_items = [it for it in self._plan_items if it.path not in succeeded_paths]
        self._rebuild_plan()

    def _on_worker_failed(self, error_msg: str) -> None:
        self._worker = None
        self._prog_card.hide()
        self._result_card.display_error(error_msg)
        self._summary_card.show()

    @property
    def _result_hdr(self) -> QLabel:
        return self._result_card._result_hdr

    @property
    def _result_detail(self) -> QLabel:
        return self._result_card._result_detail


# ---------------------------------------------------------------------------
# Factory for main_window.py
# ---------------------------------------------------------------------------

def build_cleanup_scroll() -> QScrollArea:
    """Wrap CleanupPage in a QScrollArea for the nav stack."""
    page = CleanupPage()
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(page)
    return sa
