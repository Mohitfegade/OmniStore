"""
ui/cleanup_dialogs.py
=====================
Confirmation dialog and Result card for the OmniStore Cleanup Center.

Classes:
--------
ConfirmDialog       -- Modal dialog with file list, warnings, required review checkbox,
                       and Cancel as default.
CleanupResultCard   -- Post-cleanup result card showing items recycled, recovered space,
                       failures/skipped lists, and an "Open Recycle Bin" button.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from engine.cleanup import CleanupOutcome, CleanupPlan
from engine.drives import format_bytes
from ui.components import Card, PillButton

_WARNING_ICON = "⚠"
_OK_ICON      = "✓"


class ConfirmDialog(QDialog):
    """
    Modal confirmation dialog before sending files to the Windows Recycle Bin.

    Safety requirements:
    - Lists files (up to 15, then "… and N more")
    - Shows total reclaimable bytes
    - Shows warning count if files look important
    - Mandatory checkbox: "I have reviewed these files and want to move them to the Recycle Bin."
    - Cancel is the default button
    - Confirm button is disabled until the checkbox is checked
    """

    def __init__(
        self,
        plan: CleanupPlan,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm — Move files to Recycle Bin")
        self.setMinimumWidth(560)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header
        hdr = QLabel(
            f"<b>You are about to move {len(plan.items)} file(s) to the Recycle Bin.</b><br>"
            f"You can restore them from the Recycle Bin if needed."
        )
        hdr.setWordWrap(True)
        layout.addWidget(hdr)

        # File list preview (up to 15)
        shown = plan.items[:15]
        remainder = len(plan.items) - len(shown)

        file_list_widget = QWidget()
        fl = QVBoxLayout(file_list_widget)
        fl.setContentsMargins(10, 10, 10, 10)
        fl.setSpacing(6)
        file_list_widget.setStyleSheet(
            "background:#F6F6F8; border:1px solid #E6E6E8; border-radius:8px;"
        )

        for item in shown:
            row = QHBoxLayout()
            icon = QLabel("📄")
            icon.setFixedWidth(20)
            name_lbl = QLabel(item.name)
            name_lbl.setStyleSheet("font-weight:600; font-size:13px; background:transparent;")
            size_lbl = QLabel(format_bytes(item.size_bytes))
            size_lbl.setStyleSheet("color:#6B6B72; font-size:12px; background:transparent;")
            size_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(icon)
            row.addWidget(name_lbl, 1)
            row.addWidget(size_lbl)
            fl.addLayout(row)

        if remainder > 0:
            more_lbl = QLabel(f"… and {remainder} more file(s)")
            more_lbl.setStyleSheet("color:#6B6B72; font-size:12px; font-style:italic; background:transparent;")
            fl.addWidget(more_lbl)

        layout.addWidget(file_list_widget)

        # Total bytes
        total_lbl = QLabel(f"<b>Total:</b> up to {format_bytes(plan.total_bytes)}")
        layout.addWidget(total_lbl)

        # Warnings count if sensitive files are present
        if plan.warnings:
            warn_lbl = QLabel(
                f"{_WARNING_ICON}  {len(plan.warnings)} file(s) flagged as possibly important. "
                f"Review the warnings in the plan before proceeding."
            )
            warn_lbl.setStyleSheet("color:#B45309; font-size:13px; font-weight:500;")
            warn_lbl.setWordWrap(True)
            layout.addWidget(warn_lbl)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color:#E6E6E8;")
        layout.addWidget(div)

        # Mandatory review checkbox
        self._checkbox = QCheckBox("I have reviewed these files and want to move them to the Recycle Bin.")
        self._checkbox.stateChanged.connect(self._on_check_changed)
        layout.addWidget(self._checkbox)

        # Dialog Buttons
        self._btn_box = QDialogButtonBox()
        self._cancel_btn = self._btn_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        self._confirm_btn = self._btn_box.addButton(
            "Move to Recycle Bin", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.setStyleSheet(
            "QPushButton { background:#EF4444; color:#fff; border-radius:6px; padding:8px 20px; font-weight:600; }"
            "QPushButton:disabled { background:#D1D5DB; color:#9CA3AF; }"
        )
        self._cancel_btn.setDefault(True)

        self._btn_box.accepted.connect(self.accept)
        self._btn_box.rejected.connect(self.reject)
        layout.addWidget(self._btn_box)

    def _on_check_changed(self, state: int) -> None:
        self._confirm_btn.setEnabled(state == Qt.CheckState.Checked.value)


class CleanupResultCard(Card):
    """
    Card displayed after cleanup execution finishes.
    Shows outcome, errors (if any), and an 'Open Recycle Bin' button.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.setSpacing(12)

        self._hdr_lbl = QLabel()
        self._hdr_lbl.setStyleSheet("font-size:15px; font-weight:600; background:transparent;")
        self._hdr_lbl.setWordWrap(True)
        layout.addWidget(self._hdr_lbl)

        self._detail_lbl = QLabel()
        self._detail_lbl.setStyleSheet("color:#6B6B72; font-size:13px; background:transparent;")
        self._detail_lbl.setWordWrap(True)
        layout.addWidget(self._detail_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        open_rb_btn = PillButton("Open Recycle Bin", primary=False)
        open_rb_btn.clicked.connect(self._open_recycle_bin)
        btn_row.addWidget(open_rb_btn)
        btn_row.addStretch()

        layout.addLayout(btn_row)
        self.body_layout.addLayout(layout)

    def display_outcome(self, outcome: CleanupOutcome) -> None:
        n_ok = len(outcome.succeeded)
        n_fail = len(outcome.failed)
        n_skip = len(outcome.skipped)

        hdr = (
            f"{_OK_ICON}  {n_ok} file(s) moved to the Recycle Bin "
            f"(about {format_bytes(outcome.bytes_recovered_estimate)})."
        )
        self._hdr_lbl.setText(hdr)

        parts = []
        if n_fail:
            parts.append(f"{n_fail} file(s) could not be recycled.")
        if n_skip:
            parts.append(f"{n_skip} file(s) skipped (changed since scan).")
        if outcome.failed:
            for f in outcome.failed[:5]:
                parts.append(f"  • {os.path.basename(f['path'])}: {f['reason']}")
        self._detail_lbl.setText("\n".join(parts) if parts else "")
        self.show()

    def display_error(self, error_msg: str) -> None:
        self._hdr_lbl.setText("An error occurred during recycling.")
        self._detail_lbl.setText(error_msg)
        self.show()

    def _open_recycle_bin(self) -> None:
        """Open the Windows Recycle Bin folder in Explorer."""
        try:
            os.startfile("shell:RecycleBinFolder")
        except Exception:
            try:
                subprocess.Popen(["explorer.exe", "shell:RecycleBinFolder"])
            except Exception:
                pass

    @property
    def _result_hdr(self) -> QLabel:
        return self._hdr_lbl

    @property
    def _result_detail(self) -> QLabel:
        return self._detail_lbl
