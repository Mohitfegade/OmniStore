"""
engine/scanner.py
=================
Iterative folder scanner for OmniStore.
Collects FileRecords, computes folder sizes, handles permissions and junctions safely.
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

from collections import defaultdict
import os
from pathlib import Path
import stat
import time
from typing import Callable, Optional, Set

from engine.models import FileRecord, ScanResult


# Folder names to skip regardless of drive
_SKIP_DIR_NAMES = {
    "$recycle.bin",
    "system volume information",
    "$winre_backup_partition.marker",
    "msocache",
    "recovery",
    "$windows.~bt",
    "$windows.~ws",
}

# Prefix paths to skip (normalized lowercase)
_SKIP_PATH_PREFIXES = (
    r"c:\windows",
    r"c:\programdata\microsoft",
    r"c:\recovery",
)


def _is_reparse_point_or_link(entry: os.DirEntry) -> bool:
    """Return True if entry is a symlink, directory junction, or reparse point."""
    try:
        if entry.is_symlink():
            return True
        if hasattr(entry, "is_junction") and entry.is_junction():
            return True
        st = entry.stat(follow_symlinks=False)
        attrs = getattr(st, "st_file_attributes", 0)
        if attrs and (attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            return True
    except (OSError, PermissionError):
        return True
    return False


def _should_skip_directory(dir_path: str, root_path: str) -> bool:
    """Return True if this directory is a protected or system location."""
    norm = os.path.normpath(dir_path).lower()
    norm_root = os.path.normpath(root_path).lower()

    # If the user explicitly chose this directory as the scan root, scan it
    if norm == norm_root:
        return False

    name = os.path.basename(norm)
    if name in _SKIP_DIR_NAMES:
        return True

    for prefix in _SKIP_PATH_PREFIXES:
        if norm == prefix or norm.startswith(prefix + os.sep):
            return True

    return False


def scan_folder(
    root: str,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> ScanResult:
    """
    Scan a directory tree iteratively using os.scandir.

    Parameters
    ----------
    root : str
        Directory path to scan.
    progress_cb : callable(files_scanned, bytes_scanned, current_folder) -> None, optional
        Throttled to at most ~10 calls per second.
    cancel_check : callable() -> bool, optional
        Polled regularly. If returns True, stops scanning and returns partial results.

    Returns
    -------
    ScanResult
    """
    started_at = time.time()
    norm_root = os.path.abspath(root)

    result = ScanResult(root_path=norm_root, started_at=started_at)

    if not os.path.exists(norm_root):
        result.errors.append({"path": norm_root, "reason": "Directory does not exist"})
        result.finished_at = time.time()
        return result

    if not os.path.isdir(norm_root):
        result.errors.append({"path": norm_root, "reason": "Path is not a directory"})
        result.finished_at = time.time()
        return result

    # Stack for iterative traversal (DFS)
    dir_stack: list[str] = [norm_root]
    visited_dirs: Set[str] = set()

    folder_size_map: dict[str, int] = defaultdict(int)
    folder_size_map[norm_root] = 0

    last_progress_time = 0.0
    progress_interval = 0.1  # ~10 times per second

    files_scanned = 0
    bytes_scanned = 0
    cancelled = False

    while dir_stack:
        if cancel_check and cancel_check():
            cancelled = True
            break

        current_dir = dir_stack.pop()

        # Avoid loops if already visited
        norm_current = os.path.normcase(os.path.realpath(current_dir))
        if norm_current in visited_dirs:
            continue
        visited_dirs.add(norm_current)

        # Check for system/protected locations
        if _should_skip_directory(current_dir, norm_root):
            result.skipped_count += 1
            result.errors.append({
                "path": current_dir,
                "reason": "Skipped protected system location",
            })
            continue

        # Throttle progress callback
        now = time.time()
        if progress_cb and (now - last_progress_time >= progress_interval):
            try:
                progress_cb(files_scanned, bytes_scanned, current_dir)
            except Exception:
                pass
            last_progress_time = now

        try:
            with os.scandir(current_dir) as it:
                subdirs: list[str] = []
                for entry in it:
                    if cancel_check and cancel_check():
                        cancelled = True
                        break

                    entry_path = entry.path

                    # Check for symlinks, junctions, reparse points
                    if _is_reparse_point_or_link(entry):
                        result.skipped_count += 1
                        continue

                    try:
                        if entry.is_dir(follow_symlinks=False):
                            subdirs.append(entry_path)
                            if entry_path not in folder_size_map:
                                folder_size_map[entry_path] = 0
                        elif entry.is_file(follow_symlinks=False):
                            try:
                                st = entry.stat(follow_symlinks=False)
                                size = st.st_size
                                mtime = st.st_mtime
                                atime = st.st_atime
                            except (OSError, PermissionError) as stat_err:
                                result.errors.append({"path": entry_path, "reason": str(stat_err)})
                                continue

                            ext = os.path.splitext(entry.name)[1].lstrip(".").lower()
                            record = FileRecord(
                                path=entry_path,
                                name=entry.name,
                                extension=ext,
                                size_bytes=size,
                                modified_ts=mtime,
                                accessed_ts=atime,
                                parent_folder=current_dir,
                            )
                            result.files.append(record)
                            files_scanned += 1
                            bytes_scanned += size

                            # Accumulate folder sizes up the directory tree to root
                            curr_ancestor = current_dir
                            norm_root_case = os.path.normcase(norm_root)
                            while True:
                                folder_size_map[curr_ancestor] += size
                                if os.path.normcase(curr_ancestor) == norm_root_case:
                                    break
                                parent = os.path.dirname(curr_ancestor)
                                if parent == curr_ancestor:
                                    break
                                curr_ancestor = parent

                    except (OSError, PermissionError) as entry_err:
                        result.errors.append({"path": entry_path, "reason": str(entry_err)})

                if cancelled:
                    break

                # Add subdirectories to stack
                dir_stack.extend(subdirs)

        except (PermissionError, FileNotFoundError, OSError) as dir_err:
            result.errors.append({"path": current_dir, "reason": str(dir_err)})

    result.total_files = files_scanned
    result.total_bytes = bytes_scanned
    result.folder_sizes = dict(folder_size_map)
    result.cancelled = cancelled
    result.finished_at = time.time()

    # Final progress callback
    if progress_cb:
        try:
            progress_cb(files_scanned, bytes_scanned, norm_root)
        except Exception:
            pass

    return result
