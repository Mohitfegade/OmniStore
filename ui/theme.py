"""
ui/theme.py
===========
Design tokens (named constants) and the global QSS stylesheet for OmniStore.

Font loading: scans assets/fonts/ for every *.ttf file and registers them with
QFontDatabase.  Falls back to "Segoe UI" if the folder is missing or empty,
logging a warning instead of crashing.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colour tokens
# ---------------------------------------------------------------------------
BG       = "#F3F3F2"   # window / page background
SURFACE  = "#FFFFFF"   # card / panel surface
BORDER   = "#E6E6E8"   # 1-px borders & dividers

INK      = "#111113"   # primary text
MUTED    = "#6B6B72"   # secondary / helper text

NAV_ACTIVE = "#1A1A1A"  # active nav pill (dark background, white text)

BLUE   = "#2347E6"   # primary accent – CTAs, links
PINK   = "#F0397F"
PURPLE = "#7C3AED"   # secondary accent - tools & categories
GREEN  = "#22A447"
ORANGE = "#F26B2E"
DANGER = "#D92D20"   # destructive actions

# ---------------------------------------------------------------------------
# Typography tokens
# ---------------------------------------------------------------------------
FONT_TITLE    = "Inter Tight"   # page titles, big numbers
FONT_HEADING  = "Inter Tight"   # section headings, card titles
FONT_BODY     = "Inter"         # all other text
FONT_FALLBACK = "Segoe UI"

# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------
_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

_registered_families: list[str] = []


def load_fonts() -> list[str]:
    """
    Register every .ttf found in assets/fonts/ with QFontDatabase.

    Returns a list of family names that were successfully registered.
    Call this once, after QApplication is created.
    """
    global _registered_families

    if not _FONTS_DIR.exists():
        log.warning(
            "Font directory not found: %s — falling back to '%s'.",
            _FONTS_DIR,
            FONT_FALLBACK,
        )
        return []

    ttf_files = sorted(_FONTS_DIR.glob("*.ttf"))
    if not ttf_files:
        log.warning(
            "No .ttf files found in %s — falling back to '%s'.",
            _FONTS_DIR,
            FONT_FALLBACK,
        )
        return []

    families_seen: set[str] = set()
    for ttf in ttf_files:
        font_id = QFontDatabase.addApplicationFont(str(ttf))
        if font_id < 0:
            log.warning("Failed to load font: %s", ttf.name)
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        for fam in families:
            if fam not in families_seen:
                families_seen.add(fam)
                log.info("Registered font family: '%s'  (%s)", fam, ttf.name)

    _registered_families = sorted(families_seen)
    if _registered_families:
        print(
            f"[OmniStore] Fonts loaded: {', '.join(_registered_families)}"
        )
    return _registered_families


def _resolve_body_font() -> str:
    """Return FONT_BODY if registered, else FONT_FALLBACK."""
    if FONT_BODY in _registered_families:
        return FONT_BODY
    return FONT_FALLBACK


def _resolve_title_font() -> str:
    """Return FONT_TITLE if registered, else FONT_FALLBACK."""
    if FONT_TITLE in _registered_families:
        return FONT_TITLE
    return FONT_FALLBACK


# ---------------------------------------------------------------------------
# Global QSS stylesheet
# ---------------------------------------------------------------------------
# We use f-strings so the token constants flow straight in.
# The stylesheet is intentionally written out in full so every widget class
# has an explicit rule rather than relying on accidental inheritance.

def build_stylesheet() -> str:
    body  = _resolve_body_font()
    title = _resolve_title_font()

    return f"""
/* ── Global reset ─────────────────────────────────────────────── */
* {{
    font-family: "{body}", "{FONT_FALLBACK}", sans-serif;
    font-size: 14px;
    color: {INK};
    outline: none;
}}

QMainWindow,
QWidget {{
    background-color: {BG};
}}

/* ── Global QLabel default: transparent background ─────────────── */
QLabel {{
    background-color: transparent;
    background: transparent;
}}

QScrollArea,
QScrollArea > QWidget > QWidget {{
    background-color: transparent;
    border: none;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 32px;
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 3px;
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Top bar ───────────────────────────────────────────────────── */
QFrame#topBar {{
    background-color: {SURFACE};
    border-bottom: 1px solid {BORDER};
    min-height: 56px;
    max-height: 56px;
}}

/* ── Logo label ────────────────────────────────────────────────── */
QLabel#logoMark {{
    background-color: {BLUE};
    border-radius: 10px;
    color: #FFFFFF;
    font-family: "{title}", "{FONT_FALLBACK}";
    font-size: 15px;
    font-weight: 600;
    padding: 0px 10px;
    min-width: 36px;
    max-width: 36px;
    min-height: 36px;
    max-height: 36px;
    qproperty-alignment: AlignCenter;
}}

QLabel#logoText {{
    font-family: "{title}", "{FONT_FALLBACK}";
    font-size: 15px;
    font-weight: 600;
    color: {INK};
    background: transparent;
}}

/* ── Badges & Pills ────────────────────────────────────────────── */
QLabel#driveTypeBadge {{
    font-size: 11px;
    font-weight: 500;
    color: {MUTED};
    background-color: {BG};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 2px 9px;
}}

/* ── Nav pill container ────────────────────────────────────────── */
QFrame#navPillContainer {{
    background-color: {BG};
    border: 1px solid {BORDER};
    border-radius: 20px;
    padding: 4px;
}}

/* ── Buttons (default pill-shaped) ────────────────────────────── */
QPushButton {{
    font-family: "{body}", "{FONT_FALLBACK}", sans-serif;
    font-size: 13px;
    font-weight: 500;
    min-height: 36px;
    max-height: 36px;
    border-radius: 18px;
    padding: 0px 22px;
    background-color: {SURFACE};
    color: {INK};
    border: 1px solid {BORDER};
    outline: none;
}}
QPushButton:hover {{
    border-color: #C0C0C4;
    background-color: #FAFAFA;
}}
QPushButton:pressed {{
    background-color: #F0F0F0;
}}
QPushButton:disabled {{
    background-color: {BORDER};
    color: {MUTED};
    border-color: {BORDER};
}}

/* Nav buttons — inactive */
QPushButton#navBtn,
QPushButton[objectName="navBtn"],
QPushButton[objectName^="navBtn_"] {{
    background-color: transparent;
    color: {MUTED};
    border: none;
    border-radius: 16px;
    padding: 0px 18px;
    font-size: 13px;
    font-weight: 500;
    min-height: 32px;
    max-height: 32px;
}}
QPushButton#navBtn:hover,
QPushButton[objectName="navBtn"]:hover,
QPushButton[objectName^="navBtn_"]:hover {{
    color: {INK};
    background-color: rgba(0,0,0,0.05);
}}

/* Nav buttons — active */
QPushButton#navBtnActive {{
    background-color: {NAV_ACTIVE};
    color: #FFFFFF;
    border: none;
    border-radius: 16px;
    padding: 0px 18px;
    font-size: 13px;
    font-weight: 500;
    min-height: 32px;
    max-height: 32px;
}}
QPushButton#navBtnActive:hover {{
    background-color: #2C2C2C;
}}

/* ── Card ──────────────────────────────────────────────────────── */
QFrame#card {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 20px;
}}
QFrame#card QLabel,
QFrame#card QWidget {{
    background-color: transparent;
    background: transparent;
}}

/* ── StatCard labels ───────────────────────────────────────────── */
QLabel#statLabel {{
    font-size: 12px;
    font-weight: 500;
    color: {MUTED};
    background: transparent;
}}
QLabel#statNumber {{
    font-family: "{title}", "{FONT_FALLBACK}";
    font-size: 32px;
    font-weight: 300;
    color: {INK};
    background: transparent;
}}
QLabel#statSub {{
    font-size: 12px;
    color: {MUTED};
    background: transparent;
}}

/* ── PageHeader ────────────────────────────────────────────────── */
QLabel#pageTitle {{
    font-family: "{title}", "{FONT_FALLBACK}";
    font-size: 28px;
    font-weight: 300;
    color: {INK};
    background: transparent;
}}
QLabel#pageSubtitle {{
    font-size: 13px;
    color: {MUTED};
    background: transparent;
}}

/* ── PillButton — primary ──────────────────────────────────────── */
QPushButton#pillPrimary {{
    background-color: {BLUE};
    color: #FFFFFF;
    border: none;
    border-radius: 18px;
    padding: 0px 22px;
    font-size: 13px;
    font-weight: 500;
    min-height: 36px;
    max-height: 36px;
}}
QPushButton#pillPrimary:hover {{
    background-color: #1a37c4;
}}
QPushButton#pillPrimary:pressed {{
    background-color: #1230a8;
}}
QPushButton#pillPrimary:disabled {{
    background-color: {BORDER};
    color: {MUTED};
}}

/* ── PillButton — secondary ────────────────────────────────────── */
QPushButton#pillSecondary {{
    background-color: {SURFACE};
    color: {INK};
    border: 1px solid {BORDER};
    border-radius: 18px;
    padding: 0px 22px;
    font-size: 13px;
    font-weight: 500;
    min-height: 36px;
    max-height: 36px;
}}
QPushButton#pillSecondary:hover {{
    border-color: #C0C0C4;
    background-color: #FAFAFA;
}}
QPushButton#pillSecondary:pressed {{
    background-color: #F0F0F0;
}}

/* ── PillButton — cancel/danger ────────────────────────────────── */
QPushButton#pillCancel {{
    background-color: #FFF1F0;
    color: {DANGER};
    border: 1px solid #FDA29B;
    border-radius: 18px;
    padding: 0px 22px;
    font-size: 13px;
    font-weight: 500;
    min-height: 36px;
    max-height: 36px;
}}
QPushButton#pillCancel:hover {{
    background-color: #FEE4E2;
}}

/* ── Quick-pick pills ──────────────────────────────────────────── */
QPushButton#quickPickPill {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 0px 14px;
    font-size: 12px;
    font-weight: 500;
    color: {INK};
    min-height: 28px;
    max-height: 28px;
}}
QPushButton#quickPickPill:hover {{
    background-color: #FAFAFA;
    border-color: #C0C0C4;
}}
QPushButton#quickPickPill:pressed {{
    background-color: #F0F0F0;
}}

/* ── Text link buttons ─────────────────────────────────────────── */
QPushButton#linkButton {{
    background: transparent;
    border: none;
    border-radius: 0px;
    color: {BLUE};
    font-size: 12px;
    font-weight: 500;
    text-decoration: underline;
    padding: 0;
    min-height: 18px;
    max-height: 22px;
}}
QPushButton#linkButton:hover {{
    color: #1a37c4;
    background: transparent;
    border: none;
}}

/* ── Category legend items ─────────────────────────────────────── */
QPushButton#legendButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 4px 8px;
    min-height: 26px;
    max-height: 26px;
    text-align: left;
}}
QPushButton#legendButton:hover {{
    background-color: #F8F8FA;
    border-color: {BORDER};
}}

/* ── "Coming next" placeholder card ───────────────────────────── */
QLabel#comingNextTitle {{
    font-family: "{title}", "{FONT_FALLBACK}";
    font-size: 16px;
    font-weight: 500;
    color: {INK};
    background: transparent;
}}
QLabel#comingNextBody {{
    font-size: 13px;
    color: {MUTED};
    background: transparent;
}}

/* ── Generic helper labels ─────────────────────────────────────── */
QLabel#sectionHeading {{
    font-size: 11px;
    font-weight: 600;
    color: {MUTED};
    letter-spacing: 0.06em;
    text-transform: uppercase;
    background: transparent;
}}

/* ── Form Controls ─────────────────────────────────────────────── */
QLineEdit {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 18px;
    padding: 0px 16px;
    font-size: 13px;
    color: {INK};
    min-height: 36px;
    max-height: 36px;
}}
QLineEdit:focus {{
    border: 1px solid {BLUE};
}}

QComboBox {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 18px;
    padding: 0px 16px;
    font-size: 13px;
    color: {INK};
    min-height: 36px;
    max-height: 36px;
    min-width: 120px;
}}
QComboBox:hover {{
    border-color: #C0C0C4;
}}
QComboBox::drop-down {{
    border: none;
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
    selection-background-color: #EDF1FD;
    selection-color: {INK};
    padding: 4px;
}}

/* ── Table & Headers ───────────────────────────────────────────── */
QTableView {{
    background-color: {SURFACE};
    border: none;
    gridline-color: #F0F0F2;
    selection-background-color: #EDF1FD;
    selection-color: {INK};
    font-size: 13px;
}}
QTableView::item {{
    padding: 8px 12px;
    border-bottom: 1px solid #F0F0F2;
}}
QTableView::item:selected {{
    background-color: #EDF1FD;
    color: {INK};
}}
QHeaderView::section {{
    background-color: {SURFACE};
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    padding: 8px 12px;
    border: none;
    border-bottom: 2px solid {BORDER};
}}

/* ── Progress Bar ──────────────────────────────────────────────── */
QProgressBar {{
    background-color: #E2E2E5;
    border: none;
    border-radius: 5px;
    max-height: 10px;
    min-height: 10px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {BLUE};
    border-radius: 5px;
}}

QDialog {{
    background-color: {BG};
}}
"""


def safe_font_size(size: Any, default: int = 10) -> int:
    """Ensure font point size is an integer > 0, falling back to default (10) if <= 0 or invalid."""
    try:
        val = int(size)
        return val if val > 0 else default
    except (TypeError, ValueError):
        return default


def create_safe_font(family: str, size: int = 10, weight: Optional[QFont.Weight] = None) -> QFont:
    """Safely construct a QFont with a guaranteed positive point size (> 0)."""
    pt = safe_font_size(size, 10)
    font = QFont(family, pt)
    if weight is not None:
        font.setWeight(weight)
    return font


def safe_set_point_size(font: QFont, size: int = 10) -> None:
    """Safely set point size on a QFont ensuring the value is > 0."""
    font.setPointSize(safe_font_size(size, 10))


def apply_theme(app: QApplication) -> None:
    """
    Load fonts and apply the global stylesheet to *app*.
    Call once right after QApplication is created.
    """
    load_fonts()
    app.setStyleSheet(build_stylesheet())

    # Set a sensible default application font
    body = _resolve_body_font()
    default_font = create_safe_font(body, 14)
    app.setFont(default_font)
