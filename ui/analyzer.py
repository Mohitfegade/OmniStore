"""
ui/analyzer.py
==============
Analyzer page — drill into any folder, see files and folder sizes,
file-type breakdown with DonutChart, largest folders,
and filter by category/size/name.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
import subprocess
from typing import List, Optional

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import app_state
from engine.categories import CATEGORIES, category_for
from engine.drives import format_bytes
from engine.models import FileRecord, ScanResult
from engine.query import filter_files, largest_folders, summarize_by_category
from ui import theme
from ui.charts import CATEGORY_COLORS, DonutChart
from ui.components import Card, HatchedProgressBar, PageHeader, PillButton, StatCard
from workers.scan_worker import ScanWorker


# ---------------------------------------------------------------------------
# File Table Model
# ---------------------------------------------------------------------------

class FileTableModel(QAbstractTableModel):
    """Sortable table model backed by a list of FileRecord objects."""

    COLUMNS = ["Name", "Size", "Type", "Modified", "Folder"]

    def __init__(self, files: Optional[List[FileRecord]] = None) -> None:
        super().__init__()
        self._files: list[FileRecord] = list(files) if files else []
        self._sort_col: int = 1       # default: Size
        self._sort_order: Qt.SortOrder = Qt.SortOrder.DescendingOrder

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(self._files)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: ANN201
        if not index.isValid() or not (0 <= index.row() < len(self._files)):
            return None

        file = self._files[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return file.name
            elif col == 1:
                return format_bytes(file.size_bytes)
            elif col == 2:
                return category_for(file.extension)
            elif col == 3:
                try:
                    dt = datetime.datetime.fromtimestamp(file.modified_ts)
                    return dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, OSError):
                    return "-"
            elif col == 4:
                return file.parent_folder

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col == 1:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        elif role == Qt.ItemDataRole.ToolTipRole:
            return file.path

        return None

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLUMNS[section]
        return None

    def get_file(self, row: int) -> Optional[FileRecord]:
        if 0 <= row < len(self._files):
            return self._files[row]
        return None

    def set_files(self, files: List[FileRecord]) -> None:
        self.beginResetModel()
        self._files = list(files)
        self.endResetModel()

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        self._sort_col = column
        self._sort_order = order
        reverse = (order == Qt.SortOrder.DescendingOrder)

        self.beginResetModel()
        if column == 0:
            self._files.sort(key=lambda f: f.name.lower(), reverse=reverse)
        elif column == 1:
            self._files.sort(key=lambda f: f.size_bytes, reverse=reverse)
        elif column == 2:
            self._files.sort(key=lambda f: category_for(f.extension), reverse=reverse)
        elif column == 3:
            self._files.sort(key=lambda f: f.modified_ts, reverse=reverse)
        elif column == 4:
            self._files.sort(key=lambda f: f.parent_folder.lower(), reverse=reverse)
        self.endResetModel()


# ---------------------------------------------------------------------------
# Color Dot Widget
# ---------------------------------------------------------------------------

class ColorDot(QWidget):
    """Small circular color dot for chart legends."""

    def __init__(self, color_hex: str, size: int = 10, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._color = QColor(color_hex)
        self.setFixedSize(size, size)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(0, 0, self.width(), self.height())
        painter.end()


# ---------------------------------------------------------------------------
# Folder Row Widget for Largest Folders List
# ---------------------------------------------------------------------------

class FolderRowWidget(QFrame):
    """Row widget for displaying a single folder in the Biggest folders card."""

    def __init__(
        self,
        folder_path: str,
        total_bytes: int,
        percent: float,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.folder_path = folder_path
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setToolTip(f"{folder_path}\n{format_bytes(total_bytes)} ({percent:.1f}% of scan)")

        self.setStyleSheet("""
            FolderRowWidget {
                background: transparent;
                border-radius: 8px;
                padding: 4px;
            }
            FolderRowWidget:hover {
                background-color: #F8F8FA;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(4)

        # Top line: Name + Size
        top_line = QHBoxLayout()
        top_line.setSpacing(8)

        base_name = os.path.basename(folder_path) or folder_path
        name_lbl = QLabel(base_name)
        name_lbl.setStyleSheet("font-size: 13px; font-weight: 500; color: #111113; background: transparent;")
        top_line.addWidget(name_lbl, 1)

        size_lbl = QLabel(f"{format_bytes(total_bytes)} ({percent:.1f}%)")
        size_lbl.setStyleSheet("font-size: 12px; font-weight: 500; color: #6B6B72; background: transparent;")
        top_line.addWidget(size_lbl)
        layout.addLayout(top_line)

        # Bottom line: Hatched Progress Bar
        bar = HatchedProgressBar(value=int(percent), accent_color=theme.BLUE)
        bar.setFixedHeight(8)
        layout.addWidget(bar)

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

        act_open = menu.addAction("Open folder")
        act_copy = menu.addAction("Copy path")

        action = menu.exec(QCursor.pos())
        if action == act_open:
            if os.path.exists(self.folder_path):
                os.startfile(self.folder_path)
        elif action == act_copy:
            QGuiApplication.clipboard().setText(self.folder_path)


# ---------------------------------------------------------------------------
# Responsive Two Card Row
# ---------------------------------------------------------------------------

class ResponsiveCardsRow(QWidget):
    """Layout container that shows two cards side-by-side or stacks vertically when narrow."""

    def __init__(self, left: QWidget, right: QWidget, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._left = left
        self._right = right
        self._is_vertical = False

        self._box_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._box_layout.setContentsMargins(0, 0, 0, 0)
        self._box_layout.setSpacing(16)
        self._box_layout.addWidget(self._left, 1)
        self._box_layout.addWidget(self._right, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        is_narrow = self.width() < 860
        if is_narrow != self._is_vertical:
            self._is_vertical = is_narrow
            self._box_layout.setDirection(
                QBoxLayout.Direction.TopToBottom if is_narrow else QBoxLayout.Direction.LeftToRight
            )


# ---------------------------------------------------------------------------
# Errors Details Dialog
# ---------------------------------------------------------------------------

class ErrorsDialog(QDialog):
    """Displays inaccessible items and skipped system paths."""

    def __init__(self, errors: list[dict[str, str]], skipped_count: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scan Warnings & Inaccessible Items")
        self.resize(760, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QLabel(f"{len(errors)} could not be read, {skipped_count} skipped (protected system folders).")
        header.setStyleSheet("font-size: 15px; font-weight: 600; background: transparent;")
        layout.addWidget(header)

        table = QTableWidget(len(errors), 2)
        table.setHorizontalHeaderLabels(["Path", "Reason"])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(0, 460)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)

        for row, err in enumerate(errors):
            path_item = QTableWidgetItem(err.get("path", ""))
            reason_item = QTableWidgetItem(err.get("reason", ""))
            table.setItem(row, 0, path_item)
            table.setItem(row, 1, reason_item)

        layout.addWidget(table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = PillButton("Close", primary=True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)


# ---------------------------------------------------------------------------
# AnalyzerPage Widget
# ---------------------------------------------------------------------------

class AnalyzerPage(QWidget):
    """Main widget for the Analyzer screen."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("analyzerPage")

        self._scan_result: Optional[ScanResult] = None
        self._worker: Optional[ScanWorker] = None
        self._active_cat_filter: Optional[str] = None
        self._legend_buttons: dict[str, QPushButton] = {}

        self._build_ui()

        # Connect app_state listener
        app_state.add_scan_listener(self._on_app_state_scan_updated)

        # If a scan already exists in app_state, display it
        existing = app_state.get_latest_scan()
        if existing:
            self._display_scan_result(existing)

    # -----------------------------------------------------------------------
    # UI Layout
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(32, 28, 32, 32)
        root_layout.setSpacing(20)

        # 1. Header
        header = PageHeader(
            "Analyzer",
            "Drill into any folder and see exactly what's eating your space.",
        )
        root_layout.addWidget(header)

        # 2. Folder Selection Bar (inside a Card)
        folder_card = Card()
        folder_layout = QVBoxLayout()
        folder_layout.setSpacing(12)

        # Top row: Path input + Choose folder + Scan button
        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        self._path_input = QLineEdit()
        self._path_input.setPlaceholderText("Select a folder to scan...")
        default_dir = str(Path.home() / "Downloads") if (Path.home() / "Downloads").exists() else str(Path.home())
        self._path_input.setText(default_dir)
        input_row.addWidget(self._path_input, 1)

        self._choose_btn = PillButton("Choose folder", primary=False)
        self._choose_btn.clicked.connect(self._browse_folder)
        input_row.addWidget(self._choose_btn)

        self._scan_btn = PillButton("Scan", primary=True)
        self._scan_btn.clicked.connect(self._toggle_scan)
        input_row.addWidget(self._scan_btn)

        folder_layout.addLayout(input_row)

        # Quick-pick pills row
        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)

        quick_label = QLabel("Quick pick:")
        quick_label.setStyleSheet("color: #6B6B72; font-size: 12px; font-weight: 500; background: transparent;")
        quick_row.addWidget(quick_label)

        home = Path.home()
        for name, folder in [("Downloads", home / "Downloads"), ("Documents", home / "Documents"), ("Desktop", home / "Desktop")]:
            if folder.exists():
                qp_btn = QPushButton(name)
                qp_btn.setObjectName("quickPickPill")
                qp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                target_str = str(folder)
                qp_btn.clicked.connect(lambda checked=False, p=target_str: self._set_path_and_scan(p))
                quick_row.addWidget(qp_btn)

        quick_row.addStretch()
        folder_layout.addLayout(quick_row)

        folder_card.body_layout.addLayout(folder_layout)
        root_layout.addWidget(folder_card)

        # 3. Progress Card (Hidden by default)
        self._progress_card = Card()
        prog_layout = QVBoxLayout()
        prog_layout.setSpacing(8)

        prog_top = QHBoxLayout()
        self._prog_status_lbl = QLabel("Scanning folder...")
        self._prog_status_lbl.setStyleSheet("font-weight: 600; font-size: 14px; background: transparent;")
        self._prog_counts_lbl = QLabel("0 files scanned · 0 B")
        self._prog_counts_lbl.setStyleSheet("color: #6B6B72; font-size: 13px; background: transparent;")
        prog_top.addWidget(self._prog_status_lbl)
        prog_top.addStretch()
        prog_top.addWidget(self._prog_counts_lbl)
        prog_layout.addLayout(prog_top)

        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, 0)  # Indeterminate
        prog_layout.addWidget(self._prog_bar)

        self._prog_folder_lbl = QLabel("Starting...")
        self._prog_folder_lbl.setStyleSheet("color: #6B6B72; font-size: 12px; background: transparent;")
        prog_layout.addWidget(self._prog_folder_lbl)

        self._progress_card.body_layout.addLayout(prog_layout)
        self._progress_card.hide()
        root_layout.addWidget(self._progress_card)

        # 4. Results Container (StatCards + Summary line + Breakdown/Folders Cards + Files Card)
        self._results_container = QWidget()
        results_layout = QVBoxLayout(self._results_container)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(16)

        # Stat cards row
        stat_row = QHBoxLayout()
        stat_row.setSpacing(16)

        self._sc_files = StatCard("Files Found", "-")
        self._sc_size = StatCard("Total Size", "-")
        self._sc_folders = StatCard("Folders", "-")
        self._sc_errors = StatCard("Errors / Skipped", "-")

        stat_row.addWidget(self._sc_files)
        stat_row.addWidget(self._sc_size)
        stat_row.addWidget(self._sc_folders)
        stat_row.addWidget(self._sc_errors)
        results_layout.addLayout(stat_row)

        # Sub-stat line with "View scan details" link
        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(4, 0, 4, 0)
        self._summary_lbl = QLabel("Scanned on -")
        self._summary_lbl.setStyleSheet("color: #6B6B72; font-size: 12px; background: transparent;")
        summary_row.addWidget(self._summary_lbl)
        summary_row.addStretch()

        self._view_details_btn = QPushButton("View scan details")
        self._view_details_btn.setObjectName("linkButton")
        self._view_details_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view_details_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #2347E6;
                font-size: 12px;
                font-weight: 500;
                text-decoration: underline;
                padding: 0;
            }
            QPushButton:hover {
                color: #1a37c4;
            }
        """)
        self._view_details_btn.clicked.connect(self._show_error_details)
        summary_row.addWidget(self._view_details_btn)
        results_layout.addLayout(summary_row)

        # ── Two-Column Row: What's using space + Biggest folders ────────
        # Left Card: "What's using your space"
        self._space_card = Card("What's using your space")
        space_content = QHBoxLayout()
        space_content.setSpacing(20)

        self._donut_chart = DonutChart()
        self._donut_chart.setFixedSize(190, 190)
        self._donut_chart.segment_clicked.connect(self._on_category_clicked)
        space_content.addWidget(self._donut_chart)

        # Legend list
        self._legend_layout = QVBoxLayout()
        self._legend_layout.setSpacing(4)
        self._legend_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        space_content.addLayout(self._legend_layout, 1)

        self._space_card.body_layout.addLayout(space_content)

        # Right Card: "Biggest folders"
        self._folders_card = Card("Biggest folders")
        self._folders_vbox = QVBoxLayout()
        self._folders_vbox.setSpacing(6)
        self._folders_card.body_layout.addLayout(self._folders_vbox)

        # Responsive container holding both cards
        self._two_card_row = ResponsiveCardsRow(self._space_card, self._folders_card)
        results_layout.addWidget(self._two_card_row)

        # Files Table Card
        table_card = Card()
        table_vbox = QVBoxLayout()
        table_vbox.setSpacing(12)

        # Filter bar inside table card
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        table_title = QLabel("Largest Files")
        table_title.setStyleSheet("font-size: 16px; font-weight: 600; color: #111113; background: transparent;")
        filter_row.addWidget(table_title)

        filter_row.addStretch()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search file name...")
        self._search_input.setFixedWidth(200)
        self._search_input.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self._search_input)

        self._cat_combo = QComboBox()
        self._cat_combo.addItem("All Categories")
        for cat in CATEGORIES:
            self._cat_combo.addItem(cat)
        self._cat_combo.currentIndexChanged.connect(self._on_cat_combo_changed)
        filter_row.addWidget(self._cat_combo)

        self._size_combo = QComboBox()
        self._size_combo.addItem("Any size", None)
        self._size_combo.addItem("≥ 10 MB", 10 * 1024 * 1024)
        self._size_combo.addItem("≥ 100 MB", 100 * 1024 * 1024)
        self._size_combo.addItem("≥ 500 MB", 500 * 1024 * 1024)
        self._size_combo.addItem("≥ 1 GB", 1024 * 1024 * 1024)
        self._size_combo.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self._size_combo)

        table_vbox.addLayout(filter_row)

        # Table View
        self._table_model = FileTableModel()
        self._table_view = QTableView()
        self._table_view.setModel(self._table_model)
        self._table_view.setSortingEnabled(True)
        self._table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table_view.setShowGrid(False)
        self._table_view.verticalHeader().hide()
        self._table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_view.customContextMenuRequested.connect(self._show_context_menu)
        self._table_view.doubleClicked.connect(self._on_row_double_clicked)

        # Column widths
        header_view = self._table_view.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table_view.setColumnWidth(0, 320)
        self._table_view.setColumnWidth(1, 100)
        self._table_view.setColumnWidth(2, 110)
        self._table_view.setColumnWidth(3, 140)

        self._table_view.setMinimumHeight(380)
        table_vbox.addWidget(self._table_view)

        # Table empty placeholder label
        self._table_empty_lbl = QLabel("No files match the current filters.")
        self._table_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table_empty_lbl.setStyleSheet("color: #6B6B72; font-size: 14px; padding: 40px; background: transparent;")
        self._table_empty_lbl.hide()
        table_vbox.addWidget(self._table_empty_lbl)

        table_card.body_layout.addLayout(table_vbox)
        results_layout.addWidget(table_card)

        self._results_container.hide()
        root_layout.addWidget(self._results_container)

        # 5. Initial Empty State Card (Before first scan)
        self._empty_card = Card()
        empty_layout = QVBoxLayout()
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setContentsMargins(40, 60, 40, 60)
        empty_layout.setSpacing(10)

        empty_icon = QLabel("📁")
        empty_icon.setStyleSheet("font-size: 40px; background: transparent;")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)

        empty_title = QLabel("Choose a folder to see what's using your space")
        empty_title.setObjectName("comingNextTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)

        empty_desc = QLabel("Select a folder above or choose Downloads, Documents, or Desktop to begin.")
        empty_desc.setObjectName("comingNextBody")
        empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_desc)

        self._empty_card.body_layout.addLayout(empty_layout)
        root_layout.addWidget(self._empty_card)

        root_layout.addStretch()

    # -----------------------------------------------------------------------
    # Actions & Slots
    # -----------------------------------------------------------------------

    def _browse_folder(self) -> None:
        curr = self._path_input.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select Folder to Scan", curr)
        if chosen:
            self._path_input.setText(chosen)

    def _set_path_and_scan(self, path: str) -> None:
        self._path_input.setText(path)
        self._start_scan()

    def _toggle_scan(self) -> None:
        if self._worker and self._worker.isRunning():
            self._cancel_scan()
        else:
            self._start_scan()

    def _start_scan(self) -> None:
        path = self._path_input.text().strip()
        if not path or not os.path.isdir(path):
            self._path_input.setFocus()
            return

        # Update button to Cancel
        self._scan_btn.setText("Cancel")
        self._scan_btn.setObjectName("pillCancel")
        self._scan_btn.style().unpolish(self._scan_btn)
        self._scan_btn.style().polish(self._scan_btn)

        self._choose_btn.setEnabled(False)
        self._empty_card.hide()
        self._results_container.hide()

        # Clear previous charts and legends
        self._donut_chart.clear()
        self._clear_layout(self._legend_layout)
        self._clear_layout(self._folders_vbox)

        # Show progress card
        self._prog_status_lbl.setText("Scanning folder...")
        self._prog_counts_lbl.setText("0 files scanned · 0 B")
        self._prog_folder_lbl.setText(f"Scanning: {path}")
        self._progress_card.show()

        # Launch worker
        self._worker = ScanWorker(path)
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.scan_finished.connect(self._on_scan_finished)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.start()

    def _cancel_scan(self) -> None:
        if self._worker:
            self._prog_status_lbl.setText("Stopping scan...")
            self._scan_btn.setEnabled(False)
            self._worker.cancel()

    def _on_scan_progress(self, files: int, bytes_count: int, curr_folder: str) -> None:
        self._prog_counts_lbl.setText(f"{files:,} files scanned · {format_bytes(bytes_count)}")
        fm = self._prog_folder_lbl.fontMetrics()
        elided = fm.elidedText(curr_folder, Qt.TextElideMode.ElideMiddle, max(100, self._progress_card.width() - 80))
        self._prog_folder_lbl.setText(f"In: {elided}")

    def _on_scan_finished(self, result: ScanResult) -> None:
        self._scan_result = result
        app_state.set_latest_scan(result)
        self._display_scan_result(result)

    def _on_app_state_scan_updated(self, result: ScanResult) -> None:
        if result is not self._scan_result:
            self._scan_result = result
            self._display_scan_result(result)

    def _display_scan_result(self, result: ScanResult) -> None:
        self._scan_result = result
        # Reset button to Scan
        self._scan_btn.setText("Scan")
        self._scan_btn.setObjectName("pillPrimary")
        self._scan_btn.setEnabled(True)
        self._scan_btn.style().unpolish(self._scan_btn)
        self._scan_btn.style().polish(self._scan_btn)
        self._choose_btn.setEnabled(True)

        self._progress_card.hide()
        self._empty_card.hide()

        # Update StatCards
        self._sc_files.set_number(f"{result.total_files:,}")
        self._sc_size.set_number(format_bytes(result.total_bytes))
        self._sc_folders.set_number(f"{len(result.folder_sizes):,}")
        total_errs = len(result.errors) + result.skipped_count
        self._sc_errors.set_number(f"{total_errs:,}")
        self._sc_errors.set_sub(f"{len(result.errors)} could not be read, {result.skipped_count} skipped")
        self._sc_errors.setToolTip(
            f"{len(result.errors)} could not be read, {result.skipped_count} skipped (protected system folders)"
        )

        # Summary line
        now_str = datetime.datetime.fromtimestamp(result.finished_at).strftime("%Y-%m-%d %H:%M")
        status_note = " (Cancelled)" if result.cancelled else ""
        dur_str = f" in {result.duration_seconds:.2f}s" if result.duration_seconds > 0 else ""
        self._summary_lbl.setText(
            f"Scanned: {result.root_path} on {now_str}{status_note}{dur_str}. "
            f"{len(result.errors)} could not be read, {result.skipped_count} skipped (protected system folders)."
        )

        # ── Populate Category Breakdown (Donut + Legend) ──────────────
        cat_summaries = summarize_by_category(result)
        donut_segments: list[tuple[str, int, str]] = []
        self._clear_layout(self._legend_layout)
        self._legend_buttons.clear()

        for c in cat_summaries:
            cat_name = c["category"]
            color = CATEGORY_COLORS.get(cat_name, "#8A8A93")
            donut_segments.append((cat_name, c["total_bytes"], color))

            # Create interactive legend row
            row_btn = QPushButton()
            row_btn.setObjectName("legendButton")
            row_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            row_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: 1px solid transparent;
                    border-radius: 8px;
                    padding: 4px 8px;
                    min-height: 26px;
                    max-height: 26px;
                    text-align: left;
                }
                QPushButton:hover {
                    background-color: #F8F8FA;
                    border-color: #E6E6E8;
                }
            """)

            row_layout = QHBoxLayout(row_btn)
            row_layout.setContentsMargins(4, 2, 4, 2)
            row_layout.setSpacing(8)

            row_layout.addWidget(ColorDot(color, size=10))

            cat_lbl = QLabel(cat_name)
            cat_lbl.setStyleSheet("font-size: 13px; font-weight: 500; color: #111113; background: transparent;")
            row_layout.addWidget(cat_lbl)

            count_lbl = QLabel(f"({c['file_count']:,})")
            count_lbl.setStyleSheet("font-size: 12px; color: #6B6B72; background: transparent;")
            row_layout.addWidget(count_lbl)

            row_layout.addStretch()

            size_pct_lbl = QLabel(f"{format_bytes(c['total_bytes'])}  ·  {c['percent_of_total']:.1f}%")
            size_pct_lbl.setStyleSheet("font-size: 12px; font-weight: 500; color: #111113; background: transparent;")
            row_layout.addWidget(size_pct_lbl)

            row_btn.clicked.connect(lambda checked=False, cn=cat_name: self._on_category_clicked(cn))
            self._legend_layout.addWidget(row_btn)
            self._legend_buttons[cat_name] = row_btn

        self._donut_chart.set_segments(donut_segments)

        # ── Populate Biggest Folders Card ─────────────────────────────
        self._clear_layout(self._folders_vbox)
        top_subfolders = largest_folders(result, limit=10)

        if not top_subfolders:
            no_sub_lbl = QLabel("This folder has no subfolders.")
            no_sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_sub_lbl.setStyleSheet("color: #6B6B72; font-size: 13px; padding: 30px; background: transparent;")
            self._folders_vbox.addWidget(no_sub_lbl)
        else:
            for f in top_subfolders:
                folder_row = FolderRowWidget(
                    folder_path=f["path"],
                    total_bytes=f["total_bytes"],
                    percent=f["percent_of_scan"],
                )
                self._folders_vbox.addWidget(folder_row)

        self._folders_vbox.addStretch()

        # Update table filters and show results
        self._apply_filters()
        self._results_container.show()

    def _on_scan_failed(self, error_msg: str) -> None:
        self._scan_btn.setText("Scan")
        self._scan_btn.setObjectName("pillPrimary")
        self._scan_btn.setEnabled(True)
        self._scan_btn.style().unpolish(self._scan_btn)
        self._scan_btn.style().polish(self._scan_btn)
        self._choose_btn.setEnabled(True)
        self._progress_card.hide()
        self._summary_lbl.setText(f"Scan failed: {error_msg}")
        self._results_container.show()

    def _on_category_clicked(self, category: str) -> None:
        """Toggle category filter from donut segment or legend row click."""
        if self._active_cat_filter == category:
            # Clear filter
            self._active_cat_filter = None
            self._cat_combo.setCurrentText("All Categories")
        else:
            self._active_cat_filter = category
            self._cat_combo.setCurrentText(category)

        self._update_legend_highlight()
        self._apply_filters()

    def _on_cat_combo_changed(self) -> None:
        selected = self._cat_combo.currentText()
        self._active_cat_filter = selected if selected != "All Categories" else None
        self._update_legend_highlight()
        self._apply_filters()

    def _update_legend_highlight(self) -> None:
        """Highlight active category legend button."""
        for cat_name, btn in self._legend_buttons.items():
            if self._active_cat_filter == cat_name:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #EDF1FD;
                        border: 1px solid #2347E6;
                        border-radius: 8px;
                        padding: 4px 8px;
                        min-height: 26px;
                        max-height: 26px;
                        text-align: left;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: 1px solid transparent;
                        border-radius: 8px;
                        padding: 4px 8px;
                        min-height: 26px;
                        max-height: 26px;
                        text-align: left;
                    }
                    QPushButton:hover {
                        background-color: #F8F8FA;
                        border-color: #E6E6E8;
                    }
                """)

    def _apply_filters(self) -> None:
        if not self._scan_result:
            return

        term = self._search_input.text().strip() or None
        cat = self._active_cat_filter
        min_size = self._size_combo.currentData()

        # Filter top 200 files
        matched = filter_files(
            self._scan_result,
            category=cat,
            min_size=min_size,
            name_contains=term,
            limit=200,
            sort_by="size",
            descending=True,
        )

        self._table_model.set_files(matched)

        if not matched:
            self._table_view.hide()
            self._table_empty_lbl.show()
        else:
            self._table_empty_lbl.hide()
            self._table_view.show()

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        """Remove all child widgets from a layout."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout():
                # Clear sub-layout recursively
                sub = item.layout()
                while sub.count():
                    sub_item = sub.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()

    def _show_error_details(self) -> None:
        if not self._scan_result:
            return
        dlg = ErrorsDialog(self._scan_result.errors, self._scan_result.skipped_count, self)
        dlg.exec()

    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        file = self._table_model.get_file(index.row())
        if file and os.path.exists(file.path):
            try:
                os.startfile(file.path)
            except Exception as e:
                print(f"[OmniStore] Failed to open file: {e}")

    def _show_context_menu(self, pos) -> None:  # noqa: ANN001
        index = self._table_view.indexAt(pos)
        if not index.isValid():
            return

        file = self._table_model.get_file(index.row())
        if not file:
            return

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
            if os.path.exists(file.path):
                os.startfile(file.path)
        elif action == act_open_folder:
            if os.path.exists(file.path):
                norm_p = os.path.normpath(file.path)
                subprocess.run(["explorer", f"/select,{norm_p}"], check=False)
            elif os.path.exists(file.parent_folder):
                os.startfile(file.parent_folder)
        elif action == act_copy:
            QGuiApplication.clipboard().setText(file.path)


def build_analyzer_scroll() -> QScrollArea:
    """Convenience factory to wrap AnalyzerPage in a QScrollArea."""
    page = AnalyzerPage()
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(page)
    return sa
