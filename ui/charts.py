"""
ui/charts.py
============
Custom QPainter chart widgets for OmniStore.
Renders saturated design system tokens without pastels.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QToolTip, QWidget

from engine.drives import format_bytes
from ui import theme


CATEGORY_COLORS: dict[str, str] = {
    "Videos": theme.BLUE,       # #2347E6
    "Images": theme.PINK,       # #F0397F
    "Audio": theme.ORANGE,      # #F26B2E
    "Documents": theme.GREEN,   # #22A447
    "Archives": "#7A2FE0",
    "Code": "#0A8F9C",
    "Installers": "#111113",
    "Other": "#8A8A93",
}


class DonutChart(QWidget):
    """
    Custom QPainter donut chart widget.

    Parameters
    ----------
    segments : list of (label, value, color_hex)
    """

    segment_clicked: Signal = Signal(str)

    def __init__(
        self,
        segments: Optional[List[Tuple[str, int, str]]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._segments: list[tuple[str, int, str]] = list(segments) if segments else []
        self._hovered_index: int = -1
        self._slice_angles: list[tuple[float, float, str, int, float]] = []  # (start_deg, span_deg, label, value, pct)

        self.setMouseTracking(True)
        self.setMinimumSize(180, 180)
        self.setSizePolicy(self.sizePolicy().Policy.Expanding, self.sizePolicy().Policy.Expanding)

    def set_segments(self, segments: List[Tuple[str, int, str]]) -> None:
        """Update segments data and repaint."""
        self._segments = list(segments)
        self._hovered_index = -1
        self.update()

    def clear(self) -> None:
        self._segments = []
        self._hovered_index = -1
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0

        size = min(w, h)
        outer_r = max(20.0, (size / 2.0) - 12.0)
        inner_r = outer_r * 0.64

        total_val = sum(val for _, val, _ in self._segments)
        self._slice_angles.clear()

        # ── Empty state: draw neutral gray ring ───────────────────────
        if total_val <= 0 or not self._segments:
            outer_rect = QRectF(cx - outer_r, cy - outer_r, outer_r * 2, outer_r * 2)
            inner_rect = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)

            path = QPainterPath()
            path.addEllipse(outer_rect)
            inner_path = QPainterPath()
            inner_path.addEllipse(inner_rect)
            donut = path.subtracted(inner_path)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#E2E2E5")))
            painter.drawPath(donut)

            # Center text: 0 B
            painter.setPen(QColor(theme.MUTED))
            font = QFont(theme._resolve_title_font(), 16)
            painter.setFont(font)
            painter.drawText(QRectF(cx - inner_r, cy - 14, inner_r * 2, 28), Qt.AlignmentFlag.AlignCenter, "0 B")
            painter.end()
            return

        # ── Draw Segments ─────────────────────────────────────────────
        start_angle = 90.0  # Start at top (12 o'clock)
        gap = 2.0 if len(self._segments) > 1 else 0.0

        outer_rect = QRectF(cx - outer_r, cy - outer_r, outer_r * 2, outer_r * 2)
        inner_rect = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)

        for i, (label, val, col_hex) in enumerate(self._segments):
            if val <= 0:
                continue

            span = (val / total_val) * 360.0
            pct = (val / total_val) * 100.0

            # Store angle info for hit testing (normalized in 0-360 degrees)
            self._slice_angles.append((start_angle, span, label, val, pct))

            # Apply gap
            draw_start = start_angle + (gap / 2.0)
            draw_span = span - gap
            if draw_span <= 0.5:
                draw_span = span

            # Construct donut sector path
            path = QPainterPath()
            path.arcMoveTo(outer_rect, draw_start)
            path.arcTo(outer_rect, draw_start, -draw_span)
            path.arcTo(inner_rect, draw_start - draw_span, draw_span)
            path.closeSubpath()

            # Slight expansion or bright highlight if hovered
            col = QColor(col_hex)
            if i == self._hovered_index:
                col = col.lighter(115)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(col))
            painter.drawPath(path)

            start_angle -= span

        # ── Center Text: Total size ───────────────────────────────────
        title_font_name = theme._resolve_title_font()
        total_str = format_bytes(total_val)

        painter.setPen(QColor(theme.INK))
        font_total = QFont(title_font_name, 17, QFont.Weight.DemiBold)
        painter.setFont(font_total)
        painter.drawText(
            QRectF(cx - inner_r, cy - 16, inner_r * 2, 24),
            Qt.AlignmentFlag.AlignCenter,
            total_str,
        )

        painter.setPen(QColor(theme.MUTED))
        font_sub = QFont(theme._resolve_body_font(), 10, QFont.Weight.Medium)
        painter.setFont(font_sub)
        painter.drawText(
            QRectF(cx - inner_r, cy + 8, inner_r * 2, 18),
            Qt.AlignmentFlag.AlignCenter,
            "Total Space",
        )

        painter.end()

    # ------------------------------------------------------------------
    # Hit testing & Tooltip
    # ------------------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position() if hasattr(event, "position") else event.pos()
        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        size = min(w, h)
        outer_r = (size / 2.0) - 12.0
        inner_r = outer_r * 0.64

        dx = pos.x() - cx
        dy = pos.y() - cy
        dist = math.hypot(dx, dy)

        matched_idx = -1
        if inner_r <= dist <= outer_r:
            # Angle in degrees counter-clockwise from positive x-axis (3 o'clock)
            # In screen coords, dy is downward positive
            theta = math.degrees(math.atan2(-dy, dx))
            if theta < 0:
                theta += 360.0

            # Map slice angles (start at 90 deg and proceed clockwise / downward)
            for idx, (start_deg, span_deg, label, val, pct) in enumerate(self._slice_angles):
                # Normalizing angles
                deg_from_start = (start_deg - theta) % 360.0
                if deg_from_start <= span_deg:
                    matched_idx = idx
                    QToolTip.showText(
                        QCursor.pos(),
                        f"<b>{label}</b><br>{format_bytes(val)} ({pct:.1f}%)",
                        self,
                    )
                    break

        if matched_idx != self._hovered_index:
            self._hovered_index = matched_idx
            self.update()

        if matched_idx == -1:
            QToolTip.hideText()

        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hovered_index != -1:
            self._hovered_index = -1
            self.update()
        QToolTip.hideText()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._hovered_index != -1:
            if 0 <= self._hovered_index < len(self._slice_angles):
                label = self._slice_angles[self._hovered_index][2]
                self.segment_clicked.emit(label)
        super().mousePressEvent(event)
