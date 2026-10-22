"""
main.py
=======
OmniStore entry point.

1. Creates QApplication.
2. Applies design system (fonts + QSS) via ui.theme.apply_theme().
3. Shows the MainWindow.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

# Configure logging before any imports that use `logging`
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)-8s %(name)s — %(message)s",
    stream=sys.stdout,
)

from ui.theme import apply_theme
from ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("OmniStore")
    app.setApplicationDisplayName("OmniStore")
    app.setOrganizationName("OmniStore")

    # Apply fonts + global stylesheet
    apply_theme(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
