# engine/__init__.py
# Pure-Python storage engine — no PySide6 imports allowed here.

from engine.duplicates import (
    DuplicateGroup,
    DuplicateResult,
    build_duplicate_summary,
    find_duplicates,
)
from engine.models import FileRecord, ScanResult
from engine.scanner import scan_folder

__all__ = [
    "DuplicateGroup",
    "DuplicateResult",
    "FileRecord",
    "ScanResult",
    "build_duplicate_summary",
    "find_duplicates",
    "scan_folder",
]
