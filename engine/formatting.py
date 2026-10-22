"""
engine/formatting.py
====================
Text and size formatting helpers for OmniStore.
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

import os
from pathlib import Path


def format_size(n: int) -> str:
    """
    Format byte count into a human-readable binary string: e.g. "1.4 GB", "23 MB", "0 B".
    Uses 1024-based units consistent with the rest of OmniStore.
    """
    if n is None or n < 0:
        return "0 B"
    val = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if val < 1024.0 or unit == "PB":
            if unit in ("B", "KB"):
                return f"{val:.0f} {unit}"
            formatted = f"{val:.1f}"
            if formatted.endswith(".0"):
                return f"{int(val)} {unit}"
            return f"{formatted} {unit}"
        val /= 1024.0
    return f"{val:.1f} PB"


def display_name(path: str) -> str:
    """
    Return clean folder or file name.
    For drive roots (e.g. 'C:\\', 'D:/', 'E:'), returns the drive letter (e.g. 'C:').
    """
    if not path:
        return ""
    p_clean = path.strip()
    drive, rest = os.path.splitdrive(p_clean)
    if drive and (not rest or rest in ("\\", "/", "\\\\", "//")):
        return drive.upper()

    name = Path(p_clean).name
    if not name:
        name = p_clean.rstrip("\\/").split("\\")[-1].split("/")[-1]
    return name or p_clean
