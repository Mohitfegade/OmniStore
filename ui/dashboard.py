"""
ui/dashboard.py
===============
Dashboard page — shows real drive information from Windows.

Layout
------
PageHeader "Dashboard"  [Last updated HH:MM:SS]  [Refresh]
──────────────────────────────────────────────────────────
StatCards row: Total Capacity · Used · Free · Drives Connected
Muted note: "Showing drives Windows reports. No folders scanned yet."
──────────────────────────────────────────────────────────
Drive grid (2 per row):  one DriveCard per drive
──────────────────────────────────────────────────────────
(empty-state card if no drives found)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from engine.drives import DriveInfo, format_bytes
from ui import theme
from ui.components import (
    Card,
    HatchedProgressBar,
    PageHeader,
    PillButton,
    StatCard,
)
from workers.drive_worker import DriveWorker

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Colour helper for the progress bar
# ---------------------------------------------------------------------------

def _bar_color(pct: float) -> str:
    if pct >= 90.0:
        return theme.DANGER
    if pct >= 75.0:
        return theme.ORANGE
    return theme.BLUE


# ---------------------------------------------------------------------------
# Drive card widget
# ---------------------------------------------------------------------------

class DriveCard(QFrame):
    """
    A single drive card.

    Accessible drive:
        Title (label + mountpoint)  [type badge]
        "245.3 GB of 512 GB used" · "265 GB free"
        HatchedProgressBar
        "NTFS" small muted text

    Inaccessible drive:
        Title  [type badge]
        "Not available" + reason
    """

    def __init__(self, drive: DriveInfo, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        # ── Title row ───────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.setContentsMargins(0, 0, 0, 0)

        # Drive display name
        if drive.label:
            display_name = f"{drive.label} ({drive.mountpoint.rstrip(chr(92))})"
        else:
            display_name = drive.mountpoint

        name_lbl = QLabel(display_name)
        name_lbl.setObjectName("driveCardTitle")
        name_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {theme.INK}; background: transparent;"
        )

        # Type badge
        badge = QLabel(drive.drive_type)
        badge.setObjectName("driveTypeBadge")
        badge.setStyleSheet(
            f"""
            font-size: 11px;
            font-weight: 500;
            color: {theme.MUTED};
            background-color: {theme.BG};
            border: 1px solid {theme.BORDER};
            border-radius: 10px;
            padding: 2px 9px;
            """
        )

        title_row.addWidget(name_lbl)
        title_row.addStretch()
        title_row.addWidget(badge)
        layout.addLayout(title_row)

        if not drive.accessible:
            # ── Inaccessible state ───────────────────────────────────
            na_lbl = QLabel("Not available")
            na_lbl.setStyleSheet(
                f"font-size: 13px; font-weight: 500; color: {theme.MUTED}; background: transparent;"
            )
            layout.addWidget(na_lbl)

            if drive.error:
                err_lbl = QLabel(drive.error)
                err_lbl.setWordWrap(True)
                err_lbl.setStyleSheet(
                    f"font-size: 12px; color: {theme.MUTED}; background: transparent;"
                )
                layout.addWidget(err_lbl)
            return

        # ── Accessible state ─────────────────────────────────────────
        # "245.3 GB of 512.0 GB used"
        used_lbl = QLabel(
            f"{format_bytes(drive.used_bytes)} of {format_bytes(drive.total_bytes)} used"
        )
        used_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 500; color: {theme.INK}; background: transparent;"
        )

        # "265.3 GB free"
        free_lbl = QLabel(f"{format_bytes(drive.free_bytes)} free")
        free_lbl.setStyleSheet(
            f"font-size: 12px; color: {theme.MUTED}; background: transparent;"
        )

        # Progress bar
        color = _bar_color(drive.percent_used)
        bar = HatchedProgressBar(value=int(drive.percent_used), accent_color=color)

        # Filesystem label
        fs_lbl = QLabel(drive.filesystem)
        fs_lbl.setStyleSheet(
            f"font-size: 11px; color: {theme.MUTED}; background: transparent;"
        )

        layout.addWidget(used_lbl)
        layout.addWidget(free_lbl)
        layout.addWidget(bar)
        layout.addWidget(fs_lbl)


# ---------------------------------------------------------------------------
# Dashboard page widget
# ---------------------------------------------------------------------------

class DashboardPage(QWidget):
    """
    Self-contained Dashboard page widget.
    Call refresh() or wire the Refresh button to trigger a background reload.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # Keep a reference so QThread isn't garbage-collected mid-run
        self._worker: Optional[DriveWorker] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 32)
        root.setSpacing(20)

        # ── Header row ───────────────────────────────────────────────
        self._refresh_btn = PillButton("Refresh", primary=False)
        self._refresh_btn.clicked.connect(self._start_load)

        self._timestamp_lbl = QLabel("")
        self._timestamp_lbl.setObjectName("statSub")
        self._timestamp_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        header_action = QWidget()
        ha_layout = QHBoxLayout(header_action)
        ha_layout.setContentsMargins(0, 0, 0, 0)
        ha_layout.setSpacing(12)
        ha_layout.addWidget(self._timestamp_lbl)
        ha_layout.addWidget(self._refresh_btn)

        header = PageHeader(
            "Dashboard",
            "A bird's-eye view of your storage.",
            action=header_action,
        )
        root.addWidget(header)

        # ── Stat cards row ───────────────────────────────────────────
        stat_row_widget = QWidget()
        self._stat_row = QHBoxLayout(stat_row_widget)
        self._stat_row.setSpacing(12)
        self._stat_row.setContentsMargins(0, 0, 0, 0)

        self._sc_total  = StatCard("Total Capacity", "—")
        self._sc_used   = StatCard("Used", "—")
        self._sc_free   = StatCard("Free", "—")
        self._sc_drives = StatCard("Drives Connected", "—")

        for sc in (self._sc_total, self._sc_used, self._sc_free, self._sc_drives):
            self._stat_row.addWidget(sc)

        root.addWidget(stat_row_widget)

        # Muted note under stat cards
        note = QLabel("Showing drives Windows reports.  No folders have been scanned yet.")
        note.setObjectName("statSub")
        root.addWidget(note)

        # ── Status label (loading / error) ───────────────────────────
        self._status_lbl = QLabel("Loading drives…")
        self._status_lbl.setObjectName("statSub")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._status_lbl)
        self._status_lbl.hide()

        # ── Drive grid ───────────────────────────────────────────────
        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setSpacing(12)
        self._grid.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._grid_container)

        # ── Empty state card ─────────────────────────────────────────
        self._empty_card = Card()
        empty_lbl = QLabel("No drives were found.")
        empty_lbl.setObjectName("comingNextTitle")
        empty_sub = QLabel(
            "Windows didn't report any mounted drives. "
            "Try clicking Refresh or check that your drives are connected."
        )
        empty_sub.setObjectName("comingNextBody")
        empty_sub.setWordWrap(True)
        self._empty_card.body_layout.addWidget(empty_lbl)
        self._empty_card.body_layout.addWidget(empty_sub)
        self._empty_card.hide()
        root.addWidget(self._empty_card)

        root.addStretch()

        # Load immediately on construction
        self._start_load()

    # ------------------------------------------------------------------
    # Loading

    def _start_load(self) -> None:
        """Kick off a background drive scan."""
        self._refresh_btn.setEnabled(False)
        self._status_lbl.setText("Loading drives…")
        self._status_lbl.show()
        self._grid_container.hide()
        self._empty_card.hide()

        self._worker = DriveWorker.run_once(
            on_ready=self._on_drives_ready,
            on_error=self._on_error,
        )
        # Re-enable button when the thread finishes (success or error)
        self._worker.finished.connect(lambda: self._refresh_btn.setEnabled(True))

    def _on_drives_ready(self, drives: list[DriveInfo]) -> None:
        """Called on the main thread when the worker emits drives_ready."""
        self._status_lbl.hide()
        self._update_stat_cards(drives)
        self._rebuild_grid(drives)
        now = datetime.now().strftime("%H:%M:%S")
        self._timestamp_lbl.setText(f"Last updated {now}")

    def _on_error(self, message: str) -> None:
        self._status_lbl.setText(f"Error: {message}")
        self._status_lbl.show()
        self._grid_container.hide()
        self._empty_card.hide()

    # ------------------------------------------------------------------
    # Stats

    def _update_stat_cards(self, drives: list[DriveInfo]) -> None:
        accessible = [d for d in drives if d.accessible]
        total_cap  = sum(d.total_bytes for d in accessible)
        total_used = sum(d.used_bytes  for d in accessible)
        total_free = sum(d.free_bytes  for d in accessible)

        self._sc_total.set_number(format_bytes(total_cap))
        self._sc_used.set_number(format_bytes(total_used))
        self._sc_free.set_number(format_bytes(total_free))
        self._sc_drives.set_number(str(len(drives)))

        if accessible and total_cap > 0:
            pct = total_used / total_cap * 100
            self._sc_used.set_sub(f"{pct:.0f}% of total")

    # ------------------------------------------------------------------
    # Drive grid

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _rebuild_grid(self, drives: list[DriveInfo]) -> None:
        self._clear_grid()

        if not drives:
            self._grid_container.hide()
            self._empty_card.show()
            return

        self._empty_card.hide()
        self._grid_container.show()

        for idx, drive in enumerate(drives):
            row = idx // 2
            col = idx % 2
            card = DriveCard(drive)
            self._grid.addWidget(card, row, col)

        # If odd number of drives, fill last cell with a spacer widget
        if len(drives) % 2 != 0:
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            last_row = (len(drives)) // 2
            self._grid.addWidget(spacer, last_row, 1)

        # Equal column widths
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)


# ---------------------------------------------------------------------------
# Factory for main_window.py
# ---------------------------------------------------------------------------

def build_dashboard_scroll() -> QScrollArea:
    """
    Wrap DashboardPage in a QScrollArea and return it for use in the
    QStackedWidget.
    """
    page = DashboardPage()
    page.setObjectName("pageOuter")

    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(page)
    return sa
