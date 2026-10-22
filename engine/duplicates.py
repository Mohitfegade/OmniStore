"""
engine/duplicates.py
====================
Exact duplicate file detection for OmniStore.
Operates on structured ScanResult data in three staged passes:
  1. Size grouping (drops size groups of 1, drops 0-byte files, drops files < min_size)
  2. Quick hash (first 64 KB + last 64 KB for files > 128 KB)
  3. Full cryptographic hash (blake2b in 1 MB chunks) for surviving candidates

SAFETY NOTE:
This module is strictly read-only. It NEVER deletes, moves, or alters any file.
Reclaimable bytes is an UPPER BOUND estimate assuming that exactly one copy is
retained and all redundant copies in the group are removed. Actual space freed
on disk depends on file system cluster alignment, hard links, and user selections.

No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import os
import time
from typing import Callable, Dict, List, Optional

from engine.models import FileRecord, ScanResult


# Buffer constants
_QUICK_HASH_CHUNK = 64 * 1024       # 64 KB
_QUICK_HASH_THRESHOLD = 128 * 1024   # 128 KB
_FULL_HASH_CHUNK = 1024 * 1024      # 1 MB


@dataclass(slots=True)
class DuplicateGroup:
    """
    A cluster of byte-identical files.

    Attributes
    ----------
    group_id : str
        Unique identifier (e.g. "grp_1_hash").
    size_bytes : int
        Size of each file in the group.
    files : list[FileRecord]
        All identical file records in this group.
    hash_hex : str
        Hexadecimal full-content hash.
    copies : int
        Number of identical files.
    reclaimable_bytes : int
        Estimated upper bound of reclaimable storage: (copies - 1) * size_bytes.
    """
    group_id: str
    size_bytes: int
    files: List[FileRecord]
    hash_hex: str
    copies: int
    reclaimable_bytes: int = 0

    def __post_init__(self) -> None:
        if self.reclaimable_bytes == 0 and self.copies > 1:
            self.reclaimable_bytes = (self.copies - 1) * self.size_bytes


@dataclass(slots=True)
class DuplicateResult:
    """
    Complete summary of exact duplicate detection.
    """
    groups: List[DuplicateGroup] = field(default_factory=list)
    total_groups: int = 0
    total_duplicate_files: int = 0
    total_reclaimable_bytes: int = 0
    files_hashed: int = 0
    bytes_hashed: int = 0
    errors: List[dict[str, str]] = field(default_factory=list)  # [{"path": ..., "reason": ...}]
    duration_seconds: float = 0.0
    cancelled: bool = False
    min_size_bytes: int = 1024
    scanned_root: str = ""

    def to_dict(self) -> dict:
        return {
            "scanned_root": self.scanned_root,
            "total_groups": self.total_groups,
            "total_duplicate_files": self.total_duplicate_files,
            "total_reclaimable_bytes": self.total_reclaimable_bytes,
            "files_hashed": self.files_hashed,
            "bytes_hashed": self.bytes_hashed,
            "duration_seconds": round(self.duration_seconds, 3),
            "cancelled": self.cancelled,
            "min_size_bytes": self.min_size_bytes,
            "errors_count": len(self.errors),
        }


def _compute_quick_hash(path: str, size: int) -> tuple[Optional[str], int, Optional[str]]:
    """
    Compute a fast partial hash of a file:
    - First 64 KB
    - If size > 128 KB, also last 64 KB

    Returns
    -------
    (hash_hex or None, bytes_read, error_msg or None)
    """
    try:
        # Verify file exists and size matches
        st = os.stat(path)
        if st.st_size != size:
            return None, 0, f"Size changed from {size} to {st.st_size} bytes"

        hasher = hashlib.blake2b(digest_size=16)
        bytes_read = 0

        with open(path, "rb") as f:
            first_chunk = f.read(_QUICK_HASH_CHUNK)
            bytes_read += len(first_chunk)
            hasher.update(first_chunk)

            if size > _QUICK_HASH_THRESHOLD:
                f.seek(size - _QUICK_HASH_CHUNK)
                last_chunk = f.read(_QUICK_HASH_CHUNK)
                bytes_read += len(last_chunk)
                hasher.update(last_chunk)

        return hasher.hexdigest(), bytes_read, None

    except (PermissionError, FileNotFoundError, OSError) as e:
        return None, 0, str(e)


def _compute_full_hash(
    path: str,
    size: int,
    cancel_check: Optional[Callable[[], bool]] = None,
    chunk_progress_cb: Optional[Callable[[int], None]] = None,
) -> tuple[Optional[str], int, Optional[str]]:
    """
    Compute full blake2b content hash in 1 MB chunks.

    Returns
    -------
    (hash_hex or None, bytes_read, error_msg or None)
    """
    try:
        st = os.stat(path)
        if st.st_size != size:
            return None, 0, f"Size changed from {size} to {st.st_size} bytes"

        hasher = hashlib.blake2b(digest_size=32)
        bytes_read = 0

        with open(path, "rb") as f:
            while True:
                if cancel_check and cancel_check():
                    return None, bytes_read, "Cancelled"

                chunk = f.read(_FULL_HASH_CHUNK)
                if not chunk:
                    break

                hasher.update(chunk)
                n = len(chunk)
                bytes_read += n
                if chunk_progress_cb:
                    chunk_progress_cb(n)

        return hasher.hexdigest(), bytes_read, None

    except (PermissionError, FileNotFoundError, OSError) as e:
        return None, 0, str(e)


def find_duplicates(
    scan_result: ScanResult,
    min_size_bytes: int = 1024,
    progress_cb: Optional[Callable[[str, int, int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> DuplicateResult:
    """
    Identify byte-identical duplicate files in *scan_result*.

    Parameters
    ----------
    scan_result : ScanResult
        ScanResult containing discovered FileRecord items.
    min_size_bytes : int, default 1024
        Files smaller than this threshold and all 0-byte files are excluded.
    progress_cb : callable(stage_name, items_done, items_total, bytes_hashed) -> None, optional
        Invoked at most ~10 times per second during processing.
    cancel_check : callable() -> bool, optional
        Polled periodically. If True, processing stops immediately.

    Returns
    -------
    DuplicateResult
        Sorted list of DuplicateGroups by reclaimable bytes descending.
    """
    t0 = time.perf_counter()
    scanned_root = scan_result.root_path if scan_result else ""

    errors: list[dict[str, str]] = []
    total_bytes_hashed = 0
    files_hashed = 0

    # Rate-limited progress helper (~10 times per second)
    last_cb_time = 0.0

    def call_progress(stage: str, done: int, total: int, force: bool = False) -> None:
        nonlocal last_cb_time
        if not progress_cb:
            return
        now = time.perf_counter()
        if force or (now - last_cb_time >= 0.1):
            last_cb_time = now
            try:
                progress_cb(stage, done, total, total_bytes_hashed)
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # Stage 1: Comparing file sizes
    # -----------------------------------------------------------------------
    call_progress("Comparing file sizes", 0, len(scan_result.files) if scan_result else 0, force=True)

    size_map: dict[int, list[FileRecord]] = defaultdict(list)

    if scan_result and scan_result.files:
        for f in scan_result.files:
            # Ignore files below min_size_bytes and ALL zero-byte files
            if f.size_bytes >= min_size_bytes and f.size_bytes > 0:
                size_map[f.size_bytes].append(f)

    # Filter out sizes that have only 1 file
    candidate_size_groups: list[list[FileRecord]] = [
        flist for sz, flist in size_map.items() if len(flist) >= 2
    ]

    total_stage2_files = sum(len(flist) for flist in candidate_size_groups)

    if not candidate_size_groups or (cancel_check and cancel_check()):
        cancelled = bool(cancel_check and cancel_check())
        duration = time.perf_counter() - t0
        return DuplicateResult(
            groups=[],
            total_groups=0,
            total_duplicate_files=0,
            total_reclaimable_bytes=0,
            files_hashed=0,
            bytes_hashed=0,
            errors=errors,
            duration_seconds=duration,
            cancelled=cancelled,
            min_size_bytes=min_size_bytes,
            scanned_root=scanned_root,
        )

    # -----------------------------------------------------------------------
    # Stage 2: Quick check (first 64 KB + last 64 KB)
    # -----------------------------------------------------------------------
    stage2_done = 0
    candidate_quick_groups: list[list[FileRecord]] = []

    for group in candidate_size_groups:
        if cancel_check and cancel_check():
            duration = time.perf_counter() - t0
            return DuplicateResult(
                groups=[],
                total_groups=0,
                total_duplicate_files=0,
                total_reclaimable_bytes=0,
                files_hashed=files_hashed,
                bytes_hashed=total_bytes_hashed,
                errors=errors,
                duration_seconds=duration,
                cancelled=True,
                min_size_bytes=min_size_bytes,
                scanned_root=scanned_root,
            )

        quick_map: dict[str, list[FileRecord]] = defaultdict(list)
        for f in group:
            if cancel_check and cancel_check():
                break

            qhash, b_read, err = _compute_quick_hash(f.path, f.size_bytes)
            total_bytes_hashed += b_read
            stage2_done += 1

            if err:
                errors.append({"path": f.path, "reason": err})
            elif qhash:
                quick_map[qhash].append(f)

            call_progress("Quick check", stage2_done, total_stage2_files)

        # Retain only subgroups with 2 or more files
        for qhash, sublist in quick_map.items():
            if len(sublist) >= 2:
                candidate_quick_groups.append(sublist)

    call_progress("Quick check", stage2_done, total_stage2_files, force=True)

    # -----------------------------------------------------------------------
    # Stage 3: Confirming with full comparison
    # -----------------------------------------------------------------------
    total_stage3_files = sum(len(flist) for flist in candidate_quick_groups)
    stage3_done = 0

    call_progress("Confirming with full comparison", 0, total_stage3_files, force=True)

    duplicate_groups: list[DuplicateGroup] = []
    group_counter = 1

    for group in candidate_quick_groups:
        if cancel_check and cancel_check():
            duration = time.perf_counter() - t0
            return DuplicateResult(
                groups=duplicate_groups,
                total_groups=len(duplicate_groups),
                total_duplicate_files=sum(len(g.files) for g in duplicate_groups),
                total_reclaimable_bytes=sum(g.reclaimable_bytes for g in duplicate_groups),
                files_hashed=files_hashed,
                bytes_hashed=total_bytes_hashed,
                errors=errors,
                duration_seconds=duration,
                cancelled=True,
                min_size_bytes=min_size_bytes,
                scanned_root=scanned_root,
            )

        full_hash_map: dict[str, list[FileRecord]] = defaultdict(list)

        def on_chunk_read(chunk_bytes: int) -> None:
            nonlocal total_bytes_hashed
            total_bytes_hashed += chunk_bytes
            call_progress("Confirming with full comparison", stage3_done, total_stage3_files)

        for f in group:
            if cancel_check and cancel_check():
                break

            fhash, b_read, err = _compute_full_hash(
                f.path,
                f.size_bytes,
                cancel_check=cancel_check,
                chunk_progress_cb=on_chunk_read,
            )
            files_hashed += 1
            stage3_done += 1

            if err:
                if err != "Cancelled":
                    errors.append({"path": f.path, "reason": err})
            elif fhash:
                full_hash_map[fhash].append(f)

            call_progress("Confirming with full comparison", stage3_done, total_stage3_files)

        # For any hash with 2 or more files, create a DuplicateGroup
        for fhash, matching_files in full_hash_map.items():
            if len(matching_files) >= 2:
                size_ea = matching_files[0].size_bytes
                copies = len(matching_files)
                reclaimable = (copies - 1) * size_ea

                dup_group = DuplicateGroup(
                    group_id=f"dup_{group_counter}_{fhash[:8]}",
                    size_bytes=size_ea,
                    files=matching_files,
                    hash_hex=fhash,
                    copies=copies,
                    reclaimable_bytes=reclaimable,
                )
                duplicate_groups.append(dup_group)
                group_counter += 1

    call_progress("Confirming with full comparison", stage3_done, total_stage3_files, force=True)

    # Sort groups by reclaimable bytes descending (largest space saver first)
    duplicate_groups.sort(key=lambda g: g.reclaimable_bytes, reverse=True)

    total_groups = len(duplicate_groups)
    total_dup_files = sum(len(g.files) for g in duplicate_groups)
    total_reclaimable = sum(g.reclaimable_bytes for g in duplicate_groups)
    duration = time.perf_counter() - t0

    return DuplicateResult(
        groups=duplicate_groups,
        total_groups=total_groups,
        total_duplicate_files=total_dup_files,
        total_reclaimable_bytes=total_reclaimable,
        files_hashed=files_hashed,
        bytes_hashed=total_bytes_hashed,
        errors=errors,
        duration_seconds=duration,
        cancelled=bool(cancel_check and cancel_check()),
        min_size_bytes=min_size_bytes,
        scanned_root=scanned_root,
    )


def build_duplicate_summary(dup_result: DuplicateResult, max_groups: int = 5) -> dict:
    """
    Build a compact structured summary (under ~2 KB JSON) for Gemma/LLM tools.

    Parameters
    ----------
    dup_result : DuplicateResult
    max_groups : int, default 5

    Returns
    -------
    dict
    """
    top_groups: list[dict] = []
    for g in dup_result.groups[:max_groups]:
        file_entries = [
            {
                "name": f.name,
                "parent_folder": f.parent_folder,
                "modified_ts": f.modified_ts,
            }
            for f in g.files
        ]
        top_groups.append({
            "group_id": g.group_id,
            "size_bytes": g.size_bytes,
            "copies": g.copies,
            "reclaimable_bytes": g.reclaimable_bytes,
            "files": file_entries,
        })

    return {
        "scanned_root": dup_result.scanned_root,
        "total_groups": dup_result.total_groups,
        "total_duplicate_files": dup_result.total_duplicate_files,
        "total_reclaimable_bytes": dup_result.total_reclaimable_bytes,
        "duration_seconds": round(dup_result.duration_seconds, 3),
        "min_size_bytes": dup_result.min_size_bytes,
        "top_groups": top_groups,
        "errors_count": len(dup_result.errors),
    }
