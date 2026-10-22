"""
ui/components.py
================
Reusable widgets used across all OmniStore screens.

Widgets
-------
Card              – styled QFrame (white surface, 20px radius, BORDER)
StatCard          – label + big number (Inter Tight) + optional sub-text
PageHeader        – light title + subtitle on left, optional action on right
PillButton        – primary (blue) / secondary (white+border) pill buttons
HatchedProgressBar– custom QPainter widget with solid fill + white diagonal stripes
"""

from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QBrush,
    QPainterPath,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ui import theme


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------

class Card(QFrame):
    """
    A white surface card with a 20-px radius border.

    Usage
    -----
    card = Card()
    card.body_layout.addWidget(some_widget)

    Or pass a title string to get an automatic heading row above the body.
    """

    def __init__(
        self,
        title: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        if title:
            lbl = QLabel(title)
            lbl.setObjectName("sectionHeading")
            outer.addWidget(lbl)

        # Consumers add children to body_layout
        self.body_layout: QVBoxLayout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(8)
        outer.addLayout(self.body_layout)


# ---------------------------------------------------------------------------
# StatCard
# ---------------------------------------------------------------------------

class StatCard(QFrame):
    """
    A compact metric card.

    Layout (top → bottom):
        label_text   – small muted label (e.g. "Total Used")
        number_text  – big Inter Tight number (e.g. "247 GB")
        sub_text     – optional small note (e.g. "of 512 GB")
    """

    def __init__(
        self,
        label: str,
        number: str,
        sub: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(4)

        self._label = QLabel(label)
        self._label.setObjectName("statLabel")

        self._number = QLabel(number)
        self._number.setObjectName("statNumber")

        layout.addWidget(self._label)
        layout.addWidget(self._number)

        self._sub = QLabel(sub)
        self._sub.setObjectName("statSub")
        if not sub:
            self._sub.hide()
        layout.addWidget(self._sub)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Public helpers for live updates

    def set_number(self, text: str) -> None:
        self._number.setText(text)

    def set_sub(self, text: str) -> None:
        self._sub.setText(text)
        if text:
            self._sub.show()
        else:
            self._sub.hide()

    def set_label(self, text: str) -> None:
        self._label.setText(text)


# ---------------------------------------------------------------------------
# PageHeader
# ---------------------------------------------------------------------------

class PageHeader(QWidget):
    """
    A full-width row: title + subtitle on the left; optional action widgets
    (e.g. a PillButton) packed on the right.

    Usage
    -----
    header = PageHeader("Dashboard", "A bird's-eye view of your storage.")
    header = PageHeader("Analyzer", "…", action=PillButton("Scan", primary=True))
    """

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        action: Optional[QWidget] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        # ── Left: title + subtitle ──────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(2)
        left.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("pageTitle")
        left.addWidget(title_lbl)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setObjectName("pageSubtitle")
            left.addWidget(sub_lbl)

        row.addLayout(left)
        row.addStretch()

        # ── Right: optional action widget ───────────────────────────
        if action is not None:
            row.addWidget(action)


# ---------------------------------------------------------------------------
# PillButton
# ---------------------------------------------------------------------------

class PillButton(QPushButton):
    """
    Pill-shaped push button.

    primary=True  → blue background, white text  (#pillPrimary)
    primary=False → white background, border     (#pillSecondary)
    """

    def __init__(
        self,
        text: str,
        primary: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("pillPrimary" if primary else "pillSecondary")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Prevent the button from expanding vertically beyond its natural size
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def set_primary(self, primary: bool = True) -> None:
        """Switch between primary and secondary styling dynamically."""
        self.setObjectName("pillPrimary" if primary else "pillSecondary")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


# ---------------------------------------------------------------------------
# HatchedProgressBar
# ---------------------------------------------------------------------------

class HatchedProgressBar(QWidget):
    """
    Custom QPainter widget — a rounded progress bar whose filled portion is
    rendered with diagonal hatch lines in *accent_color* over a light track.

    Parameters
    ----------
    value        : int  0–100
    accent_color : str  hex colour string (e.g. theme.BLUE)
    """

    _TRACK_HEIGHT = 12   # px
    _RADIUS       = 6    # px  (half of track height → full pill)
    _STRIPE_STEP  = 8    # px  gap between diagonal stripes

    def __init__(
        self,
        value: int = 0,
        accent_color: str = theme.BLUE,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._value = max(0, min(100, value))
        self._accent = QColor(accent_color)
        self.setMinimumHeight(self._TRACK_HEIGHT + 2)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # ------------------------------------------------------------------
    # Public API

    def set_value(self, value: int) -> None:
        self._value = max(0, min(100, value))
        self.update()

    def set_accent(self, color: str) -> None:
        self._accent = QColor(color)
        self.update()

    # ------------------------------------------------------------------
    # Painting

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self._TRACK_HEIGHT
        y = (self.height() - h) // 2
        r = self._RADIUS

        track_rect = QRectF(0, y, w, h)
        filled_w   = int(w * self._value / 100)

        # ── 1. Track: light neutral grey pill ──────────────────────
        track_color = QColor("#E2E2E5")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(track_color))
        painter.drawRoundedRect(track_rect, r, r)

        if filled_w <= 0:
            painter.end()
            return

        # ── 2. Clip to the filled portion ──────────────────────────
        # We clip to the pill shape intersected with [0 .. filled_w]
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(0, y, w, h), r, r)
        fill_clip = QPainterPath()
        fill_clip.addRect(QRectF(0, y, filled_w, h))
        final_clip = clip_path.intersected(fill_clip)
        painter.setClipPath(final_clip)

        # ── 3. Solid accent fill at full opacity ────────────────────
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._accent))
        painter.drawRect(QRectF(0, y, filled_w, h))

        # ── 4. White diagonal stripes at ~35 % opacity on top ──────
        stripe = QColor(255, 255, 255, 90)   # ~35 % white
        pen = QPen(stripe, 1.8)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        step = self._STRIPE_STEP
        start = -(h + step)
        end   = filled_w + h + step
        x_off = start
        while x_off <= end:
            # Diagonal: top-left to bottom-right (\)
            painter.drawLine(int(x_off), y, int(x_off + h), y + h)
            x_off += step

        painter.end()



