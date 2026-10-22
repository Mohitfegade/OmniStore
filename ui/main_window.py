"""
ui/main_window.py
=================
OmniStore application shell.

Layout
------
┌─────────────────────────────────────────────────────────────────┐
│  [■ OmniStore]  ·  [ Dashboard  Analyzer  Duplicates … ]  ·    │  ← top bar
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   QStackedWidget  (one page per nav item)                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Each page begins with a PageHeader (title + one-line description).
Non-dashboard pages show a "coming next" placeholder card.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import app_state
from ui import theme
from ui.components import (
    Card,
    PageHeader,
    PillButton,
)
from ui.analyzer import build_analyzer_scroll
from ui.dashboard import build_dashboard_scroll
from ui.duplicates import build_duplicates_scroll
from ui.cleanup import build_cleanup_scroll
from ui.command_center import build_command_center_scroll
from ui.gemma_status import GemmaStatusBadge
from commands.flow import CommandContext
from workers.gemma_worker import WarmupWorker


# ---------------------------------------------------------------------------
# Nav definition
# ---------------------------------------------------------------------------

_NAV_ITEMS = [
    ("Dashboard",       "A bird's-eye view of your storage."),
    ("Analyzer",        "Drill into any folder and see exactly what's eating your space."),
    ("Duplicates",      "Find and remove identical files scattered across your drives."),
    ("Cleanup",         "One-click removal of junk: temp files, logs, and caches."),
    ("Command Center",  "Run storage commands and review their history."),
]


# ---------------------------------------------------------------------------
# Individual page builders
# ---------------------------------------------------------------------------

def _scroll_page(inner: QWidget) -> QScrollArea:
    """Wrap *inner* in a scroll area with the correct background."""
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(inner)
    return sa


def _build_coming_next_card(page_title: str) -> Card:
    card = Card()
    card.setObjectName("card")

    badge = QLabel("⚡  Coming Next")
    badge.setObjectName("sectionHeading")

    title_lbl = QLabel(f"{page_title} is being built.")
    title_lbl.setObjectName("comingNextTitle")

    body_lbl = QLabel(
        "This screen will be wired up in the next task. "
        "The scaffold, design system, and navigation are already in place — "
        "only the feature logic needs to be added here."
    )
    body_lbl.setObjectName("comingNextBody")
    body_lbl.setWordWrap(True)

    card.body_layout.addWidget(badge)
    card.body_layout.addWidget(title_lbl)
    card.body_layout.addWidget(body_lbl)

    return card


def _make_page(
    title: str,
    subtitle: str,
    content: Optional[QWidget] = None,
    action: Optional[QWidget] = None,
) -> QScrollArea:
    """
    Build a standard page: padded outer widget with a PageHeader at top,
    then either *content* or a "coming next" card.
    """
    outer = QWidget()
    outer.setObjectName("pageOuter")
    vbox = QVBoxLayout(outer)
    vbox.setContentsMargins(32, 28, 32, 32)
    vbox.setSpacing(24)

    header = PageHeader(title, subtitle, action=action)
    vbox.addWidget(header)

    if content is not None:
        vbox.addWidget(content)
    else:
        vbox.addWidget(_build_coming_next_card(title))

    vbox.addStretch()

    return _scroll_page(outer)


# ---------------------------------------------------------------------------
# Dashboard page  (the feature-rich first screen)
# ---------------------------------------------------------------------------

def _build_dashboard_page() -> QScrollArea:
    return build_dashboard_scroll()


# ---------------------------------------------------------------------------
# Top Bar
# ---------------------------------------------------------------------------

class TopBar(QFrame):
    """
    The application top bar.

    Exposes `nav_buttons` — a list of QPushButton in nav order — so
    MainWindow can wire click events.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(20, 0, 20, 0)
        root.setSpacing(0)

        # ── Logo ────────────────────────────────────────────────────
        logo_mark = QLabel("OS")
        logo_mark.setObjectName("logoMark")
        logo_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_mark.setFixedSize(36, 36)

        logo_text = QLabel("OmniStore")
        logo_text.setObjectName("logoText")

        logo_row = QHBoxLayout()
        logo_row.setSpacing(10)
        logo_row.setContentsMargins(0, 0, 0, 0)
        logo_row.addWidget(logo_mark)
        logo_row.addWidget(logo_text)

        root.addLayout(logo_row)

        # ── Stretch left ────────────────────────────────────────────
        root.addStretch()

        # ── Nav pill container ──────────────────────────────────────
        self._pill_container = QFrame()
        self._pill_container.setObjectName("navPillContainer")

        pill_layout = QHBoxLayout(self._pill_container)
        pill_layout.setContentsMargins(4, 4, 4, 4)
        pill_layout.setSpacing(2)

        self.nav_buttons: list[QPushButton] = []
        for label, _ in _NAV_ITEMS:
            btn = QPushButton(label)
            btn.setProperty("class", "navBtn")
            btn.setObjectName("navBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(False)
            # Store a CSS class property used in _set_active
            btn.setProperty("navActive", False)
            pill_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        root.addWidget(self._pill_container)

        # ── Stretch right ───────────────────────────────────────────
        root.addStretch()
        self.status_badge = GemmaStatusBadge(self)
        root.addWidget(self.status_badge)

    def set_active(self, index: int) -> None:
        """Update nav button styles to reflect the active page index."""
        for i, btn in enumerate(self.nav_buttons):
            if i == index:
                btn.setProperty("class", "navBtnActive")
                btn.setObjectName("navBtnActive")
            else:
                btn.setProperty("class", "navBtn")
                btn.setObjectName("navBtn")
            # Force style re-polish so the QSS objectName rules apply
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Application shell window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OmniStore")
        self.setMinimumSize(1200, 760)

        # ── Central widget ──────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)

        root_vbox = QVBoxLayout(central)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(0)

        # ── Top bar ─────────────────────────────────────────────────
        self._top_bar = TopBar()
        root_vbox.addWidget(self._top_bar)

        # ── Page stack ──────────────────────────────────────────────
        self._stack = QStackedWidget()
        root_vbox.addWidget(self._stack)

        # Build pages
        self._pages: list[QScrollArea] = []

        dashboard_page = _build_dashboard_page()
        self._pages.append(dashboard_page)
        self._stack.addWidget(dashboard_page)

        analyzer_page = build_analyzer_scroll()
        self._pages.append(analyzer_page)
        self._stack.addWidget(analyzer_page)

        duplicates_page = build_duplicates_scroll()
        self._pages.append(duplicates_page)
        self._stack.addWidget(duplicates_page)

        cleanup_page = build_cleanup_scroll()
        self._pages.append(cleanup_page)
        self._stack.addWidget(cleanup_page)

        command_center_page = build_command_center_scroll()
        self._pages.append(command_center_page)
        self._stack.addWidget(command_center_page)

        # ── Wire Command Center context and cleanup routing ─────────
        self._command_center = getattr(command_center_page, "command_center_page", None)
        if self._command_center:
            self._command_center.reviewInCleanupRequested.connect(self._on_command_center_review_cleanup)

        def _update_command_center_ctx(*_args) -> None:
            if self._command_center:
                self._command_center.set_context(CommandContext(
                    scan=app_state.get_latest_scan(),
                    duplicates=app_state.get_latest_duplicates(),
                    drives=None,
                ))

        app_state.add_scan_listener(lambda s: _update_command_center_ctx())
        app_state.add_duplicates_listener(lambda d: _update_command_center_ctx())
        _update_command_center_ctx()

        # ── Gemma status & WarmupWorker ─────────────────────────────
        self._warmed_up = False
        self._warmup_worker = None

        def _on_gemma_status_changed(connected: bool) -> None:
            if self._command_center:
                self._command_center.set_gemma_available(connected)
            if connected and not self._warmed_up:
                self._warmed_up = True
                self._warmup_worker = WarmupWorker()
                self._warmup_worker.start()

        self._top_bar.status_badge.connectionChanged.connect(_on_gemma_status_changed)

        # ── Wire nav buttons ────────────────────────────────────────
        for i, btn in enumerate(self._top_bar.nav_buttons):
            # Use default-argument capture to freeze `i` in the lambda
            btn.clicked.connect(lambda checked=False, idx=i: self._switch_page(idx))

        # Wire global navigation listener
        app_state.add_nav_listener(self._switch_page)

        # Start on Dashboard
        self._switch_page(0)

    def _on_command_center_review_cleanup(self, items: list) -> None:
        """Handle reviewInCleanupRequested from Command Center."""
        app_state.set_pending_cleanup(items)
        self._switch_page(3)

    def _switch_page(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._top_bar.set_active(index)
