"""
engine/models.py
================
Data structures representing scanned files and scan results.
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True, slots=True)
class FileRecord:
    """Represents a single file discovered during a scan."""
    path: str
    name: str
    extension: str         # lowercase without dot, e.g. "pdf", "mp4"
    size_bytes: int
    modified_ts: float     # POSIX timestamp
    accessed_ts: float     # POSIX timestamp
    parent_folder: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "modified_ts": self.modified_ts,
            "accessed_ts": self.accessed_ts,
            "parent_folder": self.parent_folder,
        }


@dataclass(slots=True)
class ScanResult:
    """Complete structured result of a folder scan."""
    root_path: str
    files: List[FileRecord] = field(default_factory=list)
    folder_sizes: Dict[str, int] = field(default_factory=dict)  # total bytes per folder including subfolders
    total_files: int = 0
    total_bytes: int = 0
    errors: List[dict[str, str]] = field(default_factory=list)  # [{"path": ..., "reason": ...}]
    skipped_count: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0
    cancelled: bool = False

    @property
    def duration_seconds(self) -> float:
        """Total duration of the scan in seconds."""
        return max(0.0, self.finished_at - self.started_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_path": self.root_path,
            "total_files": self.total_files,
            "total_bytes": self.total_bytes,
            "duration_seconds": round(self.duration_seconds, 3),
            "errors": self.errors,
            "skipped_count": self.skipped_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cancelled": self.cancelled,
            "files_count": len(self.files),
        }
