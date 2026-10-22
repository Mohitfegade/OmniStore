"""
ui/gemma_status.py
==================
Gemma 4 status indicator badge and settings dialog for OmniStore.

Classes:
--------
GemmaStatusBadge    -- Top-bar pill badge displaying connection state (green connected,
                       muted grey offline/basic mode) with a refresh action and click-to-configure.
GemmaSettingsDialog -- Modal dialog to configure host (localhost-only), select model from
                       /api/tags, test connection latency, toggle Gemma, and inspect the audit log.
AuditLogDialog      -- Read-only viewer of the sanitized payloads sent to the local model.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QCursor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gemma.config import GemmaSettings, load_settings, save_settings
from gemma.privacy import AuditLog
from gemma.provider import ProviderStatus
from ui import theme
from ui.components import PillButton
from workers.gemma_worker import GemmaHealthWorker, GemmaWarmupWorker

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GemmaStatusBadge
# ---------------------------------------------------------------------------

class GemmaStatusBadge(QWidget):
    """
    Top-bar status pill widget displaying Gemma 4 connection status.

    - Connected: Green pill with "Gemma 4 (local) connected"
    - Offline: Muted grey pill with "Gemma offline, basic mode"
    - Click pill: opens GemmaSettingsDialog
    - Click refresh button: triggers a background health check
    """
    connectionChanged = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("gemmaStatusBadge")
        self._settings = load_settings()
        self._is_connected = False
        self._worker: Optional[GemmaHealthWorker] = None
        self._warmup_worker: Optional[GemmaWarmupWorker] = None
        self._has_warmed_up = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Pill container
        self._pill = QFrame()
        self._pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pill.mousePressEvent = self._on_pill_clicked  # type: ignore

        pill_layout = QHBoxLayout(self._pill)
        pill_layout.setContentsMargins(10, 4, 10, 4)
        pill_layout.setSpacing(6)

        # Indicator dot
        self._dot = QLabel("●")
        self._dot.setObjectName("statusDot")
        pill_layout.addWidget(self._dot)

        # Status text
        self._label = QLabel("Checking Gemma…")
        self._label.setObjectName("statusText")
        font = theme.create_safe_font(theme.FONT_BODY, 9, QFont.Weight.Medium)
        self._label.setFont(font)
        pill_layout.addWidget(self._label)

        layout.addWidget(self._pill)

        # Refresh button
        self._refresh_btn = QPushButton("↻")
        self._refresh_btn.setFixedSize(24, 24)
        self._refresh_btn.setToolTip("Check Gemma status")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {theme.BORDER}; border-radius: 12px; background: {theme.SURFACE}; "
            f"color: {theme.MUTED}; font-size: 13px; font-weight: bold; padding: 0px; }} "
            f"QPushButton:hover {{ background: #EAEAEB; color: {theme.INK}; }}"
        )
        self._refresh_btn.clicked.connect(self.check_health)
        layout.addWidget(self._refresh_btn)

        # Set initial offline look
        self._render_state(False, "Gemma checking…", "")

        # Launch initial health check
        self.check_health()

    def check_health(self) -> None:
        """Trigger an asynchronous health check."""
        if self._worker and self._worker.isRunning():
            return
        self._label.setText("Checking…")
        self._settings = load_settings()
        if not self._settings.enabled:
            self._render_state(False, "Gemma offline, basic mode", "Gemma is disabled in settings.")
            return

        self._worker = GemmaHealthWorker(self._settings, self)
        self._worker.status_ready.connect(self._on_status_ready)
        self._worker.failed.connect(self._on_status_failed)
        self._worker.start()

    def _on_status_ready(self, status: ProviderStatus) -> None:
        self._is_connected = status.ok
        if status.ok:
            lat = f"{status.latency_ms:.0f} ms" if status.latency_ms is not None else ""
            tooltip = f"Model: {status.model}\nLatency: {lat}\nProvider: Local Ollama\nClick to configure"
            if not self._has_warmed_up:
                self._has_warmed_up = True
                self._render_state(True, "Gemma warming up…", tooltip)
                self._warmup_worker = GemmaWarmupWorker(self._settings, self)
                self._warmup_worker.finished.connect(lambda ok: self._render_state(True, "Gemma 4 (local) connected", tooltip))
                self._warmup_worker.failed.connect(lambda err: self._render_state(True, "Gemma 4 (local) connected", tooltip))
                self._warmup_worker.start()
            else:
                self._render_state(True, "Gemma 4 (local) connected", tooltip)
        else:
            tooltip = f"Offline: {status.message}\nClick to configure local Gemma 4 / Ollama"
            self._render_state(False, "Gemma offline, basic mode", tooltip)

    def _on_status_failed(self, error: str) -> None:
        self._is_connected = False
        self._render_state(False, "Gemma offline, basic mode", f"Error: {error}\nClick to configure")

    def _render_state(self, connected: bool, text: str, tooltip: str) -> None:
        self._label.setText(text)
        self._pill.setToolTip(tooltip)
        if connected:
            self._dot.setStyleSheet("color: #22A447; font-size: 10px; background: transparent;")
            self._label.setStyleSheet("color: #166534; background: transparent; font-weight: 600;")
            self._pill.setStyleSheet(
                "QFrame { background-color: #E8F8EE; border: 1px solid #86EFAC; border-radius: 13px; } "
                "QFrame:hover { background-color: #DCF4E4; border-color: #4ADE80; }"
            )
        else:
            self._dot.setStyleSheet("color: #8C8C94; font-size: 10px; background: transparent;")
            self._label.setStyleSheet("color: #55555C; background: transparent; font-weight: 500;")
            self._pill.setStyleSheet(
                "QFrame { background-color: #ECECED; border: 1px solid #D4D4D8; border-radius: 13px; } "
                "QFrame:hover { background-color: #E2E2E4; border-color: #A1A1AA; }"
            )
        self.connectionChanged.emit(connected)

    def _on_pill_clicked(self, event) -> None:
        dlg = GemmaSettingsDialog(self)
        if dlg.exec():
            self.check_health()


# ---------------------------------------------------------------------------
# GemmaSettingsDialog
# ---------------------------------------------------------------------------

class GemmaSettingsDialog(QDialog):
    """
    Modal dialog for configuring local Gemma settings, testing connection latency,
    and opening the AI Audit Log.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gemma 4 Local AI Settings")
        self.setMinimumWidth(500)
        self.setObjectName("gemmaSettingsDialog")
        self._settings = load_settings()
        self._health_worker: Optional[GemmaHealthWorker] = None

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title / Header
        title = QLabel("Gemma 4 Local AI Settings")
        title.setFont(theme.create_safe_font(theme.FONT_TITLE, 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {theme.INK};")
        layout.addWidget(title)

        subtitle = QLabel("Deterministic reasoning and natural language tool routing powered by local Ollama.")
        subtitle.setFont(theme.create_safe_font(theme.FONT_BODY, 9))
        subtitle.setStyleSheet(f"color: {theme.MUTED};")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Enable checkbox
        self._enable_check = QCheckBox("Enable Gemma 4 Local AI")
        self._enable_check.setChecked(self._settings.enabled)
        self._enable_check.setStyleSheet(f"font-size: 10pt; font-weight: 600; color: {theme.INK};")
        layout.addWidget(self._enable_check)

        # Fast mode checkbox
        self._fast_mode_check = QCheckBox("Fast Mode (try instant rule-based parser first)")
        self._fast_mode_check.setChecked(self._settings.fast_mode)
        self._fast_mode_check.setStyleSheet(f"font-size: 9pt; color: {theme.INK};")
        layout.addWidget(self._fast_mode_check)

        # Form Frame
        form_frame = QFrame()
        form_frame.setStyleSheet(
            f"QFrame {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER}; border-radius: 12px; padding: 14px; }}"
        )
        form_layout = QVBoxLayout(form_frame)
        form_layout.setSpacing(12)

        # Host
        host_label = QLabel("Ollama Host (Localhost only):")
        host_label.setFont(theme.create_safe_font(theme.FONT_BODY, 9, QFont.Weight.Medium))
        form_layout.addWidget(host_label)

        self._host_edit = QLineEdit(self._settings.host)
        self._host_edit.setPlaceholderText("http://localhost:11434")
        self._host_edit.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {theme.BORDER}; border-radius: 6px; padding: 6px 10px; font-size: 10pt; background: #FAFAFA; }}"
        )
        form_layout.addWidget(self._host_edit)

        # Model
        model_label = QLabel("Model:")
        model_label.setFont(theme.create_safe_font(theme.FONT_BODY, 9, QFont.Weight.Medium))
        form_layout.addWidget(model_label)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.addItem(self._settings.model)
        self._model_combo.setStyleSheet(
            f"QComboBox {{ border: 1px solid {theme.BORDER}; border-radius: 6px; padding: 6px 10px; font-size: 10pt; background: #FAFAFA; }}"
        )
        form_layout.addWidget(self._model_combo)

        # Test Connection button & status
        test_row = QHBoxLayout()
        test_row.setSpacing(10)

        self._test_btn = QPushButton("Test connection")
        self._test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._test_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER}; border-radius: 8px; "
            f"padding: 6px 14px; font-weight: 600; color: {theme.INK}; }} "
            f"QPushButton:hover {{ background: #F3F3F4; }}"
        )
        self._test_btn.clicked.connect(self._run_test_connection)
        test_row.addWidget(self._test_btn)

        self._test_status_lbl = QLabel("")
        self._test_status_lbl.setFont(theme.create_safe_font(theme.FONT_BODY, 9))
        test_row.addWidget(self._test_status_lbl)
        test_row.addStretch()

        form_layout.addLayout(test_row)
        layout.addWidget(form_frame)

        # Privacy guarantee text
        privacy_card = QFrame()
        privacy_card.setStyleSheet("QFrame { background: #F0F4FF; border: 1px solid #D0DCFF; border-radius: 10px; padding: 10px; }")
        priv_layout = QVBoxLayout(privacy_card)
        priv_layout.setContentsMargins(10, 8, 10, 8)
        priv_layout.setSpacing(4)

        priv_heading = QLabel("🔒 Privacy Guarantee")
        priv_heading.setFont(theme.create_safe_font(theme.FONT_BODY, 9, QFont.Weight.Bold))
        priv_heading.setStyleSheet("color: #1E40AF; background: transparent;")
        priv_layout.addWidget(priv_heading)

        priv_text = QLabel(
            "Gemma runs locally through Ollama. Your files are never uploaded. "
            "Only file names, sizes, dates and totals are shared with the local model."
        )
        priv_text.setFont(theme.create_safe_font(theme.FONT_BODY, 9))
        priv_text.setStyleSheet("color: #1E3A8A; background: transparent;")
        priv_text.setWordWrap(True)
        priv_layout.addWidget(priv_text)

        layout.addWidget(privacy_card)

        # Audit log button
        self._audit_btn = QPushButton("View what was sent to the model (Audit Log)")
        self._audit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._audit_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px dashed {theme.BORDER}; border-radius: 8px; "
            f"padding: 8px; font-weight: 500; color: {theme.BLUE}; }} "
            f"QPushButton:hover {{ background: #F8F9FA; border-style: solid; }}"
        )
        self._audit_btn.clicked.connect(self._open_audit_log)
        layout.addWidget(self._audit_btn)

        # Bottom Buttons (Save / Cancel)
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER}; border-radius: 8px; "
            f"padding: 8px 18px; color: {theme.INK}; font-weight: 500; }}"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        save_btn = QPushButton("Save Settings")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.BLUE}; border: none; border-radius: 8px; "
            f"padding: 8px 20px; color: #FFFFFF; font-weight: 600; }} "
            f"QPushButton:hover {{ background: #1B38BA; }}"
        )
        save_btn.clicked.connect(self._save_settings)
        btn_box.addWidget(save_btn)

        layout.addLayout(btn_box)

    def _run_test_connection(self) -> None:
        host = self._host_edit.text().strip()
        # Verify localhost rule
        if not ("localhost" in host or "127.0.0.1" in host or "::1" in host):
            self._test_status_lbl.setText("❌ Only localhost/127.0.0.1 is permitted.")
            self._test_status_lbl.setStyleSheet("color: #DC2626;")
            return

        self._test_btn.setEnabled(False)
        self._test_status_lbl.setText("Testing connection…")
        self._test_status_lbl.setStyleSheet(f"color: {theme.MUTED};")

        test_settings = GemmaSettings(
            provider="ollama",
            host=host,
            model=self._model_combo.currentText().strip() or "gemma4:e2b",
            enabled=True,
            timeout_s=10,
        )

        self._health_worker = GemmaHealthWorker(test_settings, self)
        self._health_worker.status_ready.connect(self._on_test_ready)
        self._health_worker.failed.connect(self._on_test_failed)
        self._health_worker.start()

    def _on_test_ready(self, status: ProviderStatus) -> None:
        self._test_btn.setEnabled(True)
        if status.ok:
            lat = f"({status.latency_ms:.1f} ms)" if status.latency_ms is not None else ""
            self._test_status_lbl.setText(f"✓ Connected {lat}")
            self._test_status_lbl.setStyleSheet("color: #16A34A; font-weight: 600;")
            # Populate models in combo if available
            current = self._model_combo.currentText().strip()
            self._model_combo.clear()
            for m in status.models_available:
                self._model_combo.addItem(m)
            if current and self._model_combo.findText(current) >= 0:
                self._model_combo.setCurrentText(current)
            elif current:
                self._model_combo.addItem(current)
                self._model_combo.setCurrentText(current)
        else:
            self._test_status_lbl.setText(f"❌ {status.message[:50]}")
            self._test_status_lbl.setStyleSheet("color: #DC2626;")

    def _on_test_failed(self, error: str) -> None:
        self._test_btn.setEnabled(True)
        self._test_status_lbl.setText(f"❌ Failed: {error[:40]}")
        self._test_status_lbl.setStyleSheet("color: #DC2626;")

    def _save_settings(self) -> None:
        host = self._host_edit.text().strip()
        model = self._model_combo.currentText().strip()
        enabled = self._enable_check.isChecked()

        try:
            new_settings = GemmaSettings(
                provider="ollama",
                host=host,
                model=model,
                num_ctx=self._settings.num_ctx,
                temperature=self._settings.temperature,
                timeout_s=self._settings.timeout_s,
                enabled=enabled,
                fast_mode=self._fast_mode_check.isChecked(),
            )
            save_settings(new_settings)
            self.accept()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Host", str(exc))

    def _open_audit_log(self) -> None:
        dlg = AuditLogDialog(self)
        dlg.exec()


# ---------------------------------------------------------------------------
# AuditLogDialog
# ---------------------------------------------------------------------------

class AuditLogDialog(QDialog):
    """
    Read-only inspection dialog displaying what has been sent to the local model.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Audit Log — Shared Data Inspection")
        self.resize(780, 520)
        self._records = AuditLog.read_recent(50)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        heading = QLabel("Local AI Audit Log")
        heading.setFont(theme.create_safe_font(theme.FONT_TITLE, 13, QFont.Weight.Bold))
        layout.addWidget(heading)

        sub = QLabel("Every request sent to Gemma 4 is logged locally. OmniStore only transmits sanitized file metadata.")
        sub.setFont(theme.create_safe_font(theme.FONT_BODY, 9))
        sub.setStyleSheet(f"color: {theme.MUTED};")
        layout.addWidget(sub)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Table of records
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Timestamp", "Model", "Tools Used", "Payload Bytes", "Preview"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self._populate_table()
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self._table)

        # Detail preview
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 8, 0, 0)
        preview_layout.setSpacing(4)

        detail_lbl = QLabel("Sanitized Payload Detail:")
        detail_lbl.setFont(theme.create_safe_font(theme.FONT_BODY, 9, QFont.Weight.Bold))
        preview_layout.addWidget(detail_lbl)

        self._payload_view = QTextEdit()
        self._payload_view.setReadOnly(True)
        self._payload_view.setFont(theme.create_safe_font("Consolas", 9))
        self._payload_view.setStyleSheet("QTextEdit { background: #FAFAFA; border: 1px solid #E4E4E7; border-radius: 6px; }")
        preview_layout.addWidget(self._payload_view)

        splitter.addWidget(preview_container)
        splitter.setSizes([260, 200])

        layout.addWidget(splitter)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER}; border-radius: 6px; "
            f"padding: 6px 16px; color: {theme.INK}; font-weight: 500; }}"
        )
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        if self._records:
            self._table.selectRow(0)

    def _populate_table(self) -> None:
        self._table.setRowCount(len(self._records))
        for row, rec in enumerate(self._records):
            dt_str = rec.get("datetime", "")
            model_str = rec.get("model", "")
            tools_str = ", ".join(rec.get("tool_names", [])) or "(none)"
            bytes_str = f"{rec.get('payload_bytes', 0):,} B"
            payload = rec.get("sanitized_payload", {})
            preview_str = json.dumps(payload, ensure_ascii=False)[:80]

            self._table.setItem(row, 0, QTableWidgetItem(dt_str))
            self._table.setItem(row, 1, QTableWidgetItem(model_str))
            self._table.setItem(row, 2, QTableWidgetItem(tools_str))
            self._table.setItem(row, 3, QTableWidgetItem(bytes_str))
            self._table.setItem(row, 4, QTableWidgetItem(preview_str))

    def _on_row_selected(self) -> None:
        selected = self._table.selectedItems()
        if not selected:
            self._payload_view.setPlainText("")
            return
        row = selected[0].row()
        if 0 <= row < len(self._records):
            rec = self._records[row]
            payload = rec.get("sanitized_payload", {})
            self._payload_view.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))
