"""
app_state.py
============
Shared global state for OmniStore.
Stores the latest ScanResult, DuplicateResult, and pending cleanup items so
other screens (Duplicates, Cleanup, Command Center) can access and act on
scanned data without rescanning.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from engine.duplicates import DuplicateResult
from engine.models import ScanResult

_latest_scan: Optional[ScanResult] = None
_scan_listeners: List[Callable[[ScanResult], None]] = []

_latest_duplicates: Optional[DuplicateResult] = None
_dup_listeners: List[Callable[[DuplicateResult], None]] = []

_pending_cleanup: List[dict[str, Any]] = []
_cleanup_listeners: List[Callable[[List[dict[str, Any]]], None]] = []

_nav_listeners: List[Callable[[int], None]] = []


# ---------------------------------------------------------------------------
# ScanResult State
# ---------------------------------------------------------------------------

def get_latest_scan() -> Optional[ScanResult]:
    """Return the most recently completed ScanResult, or None."""
    return _latest_scan


def set_latest_scan(result: ScanResult) -> None:
    """Update the latest scan result and notify any registered listeners."""
    global _latest_scan
    _latest_scan = result
    for listener in _scan_listeners:
        try:
            listener(result)
        except Exception:
            pass


def add_scan_listener(callback: Callable[[ScanResult], None]) -> None:
    """Register a callback to be called whenever a new ScanResult is saved."""
    if callback not in _scan_listeners:
        _scan_listeners.append(callback)


# ---------------------------------------------------------------------------
# DuplicateResult State
# ---------------------------------------------------------------------------

def get_latest_duplicates() -> Optional[DuplicateResult]:
    """Return the most recently completed DuplicateResult, or None."""
    return _latest_duplicates


def set_latest_duplicates(result: DuplicateResult) -> None:
    """Update the latest duplicate result and notify registered listeners."""
    global _latest_duplicates
    _latest_duplicates = result
    for listener in _dup_listeners:
        try:
            listener(result)
        except Exception:
            pass


def add_duplicates_listener(callback: Callable[[DuplicateResult], None]) -> None:
    """Register a callback to be called whenever a new DuplicateResult is saved."""
    if callback not in _dup_listeners:
        _dup_listeners.append(callback)


# ---------------------------------------------------------------------------
# Pending Cleanup State
# ---------------------------------------------------------------------------

def get_pending_cleanup() -> List[dict[str, Any]]:
    """Return the current list of items queued for review in Cleanup."""
    return list(_pending_cleanup)


def set_pending_cleanup(items: List[dict[str, Any]]) -> None:
    """Queue files for review in Cleanup with reasons."""
    global _pending_cleanup
    _pending_cleanup = list(items)
    for listener in _cleanup_listeners:
        try:
            listener(_pending_cleanup)
        except Exception:
            pass


def add_cleanup_listener(callback: Callable[[List[dict[str, Any]]], None]) -> None:
    """Register a callback to be notified when pending cleanup items change."""
    if callback not in _cleanup_listeners:
        _cleanup_listeners.append(callback)


# ---------------------------------------------------------------------------
# Navigation State
# ---------------------------------------------------------------------------

def navigate_to(page_index: int) -> None:
    """Request application navigation to a specific page index."""
    for listener in _nav_listeners:
        try:
            listener(page_index)
        except Exception:
            pass


def add_nav_listener(callback: Callable[[int], None]) -> None:
    """Register a callback for page navigation requests."""
    if callback not in _nav_listeners:
        _nav_listeners.append(callback)


# ---------------------------------------------------------------------------
# Post-Cleanup Refresh State
# ---------------------------------------------------------------------------

def apply_cleanup_outcome(outcome: Any) -> None:
    """
    Refresh application state after files have been recycled:
    - Removes recycled files from _latest_scan
    - Updates duplicate groups in _latest_duplicates
    - Clears _pending_cleanup
    """
    global _latest_scan, _latest_duplicates, _pending_cleanup
    import os

    recycled_paths = {
        os.path.normcase(os.path.abspath(s["path"]))
        for s in getattr(outcome, "succeeded", [])
    }
    if not recycled_paths:
        return

    # 1. Update _latest_scan
    if _latest_scan is not None:
        remaining_files = [
            f for f in _latest_scan.files
            if os.path.normcase(os.path.abspath(f.path)) not in recycled_paths
        ]
        _latest_scan.files = remaining_files
        _latest_scan.total_files = len(remaining_files)
        _latest_scan.total_bytes = sum(f.size_bytes for f in remaining_files)
        for listener in _scan_listeners:
            try:
                listener(_latest_scan)
            except Exception:
                pass

    # 2. Update _latest_duplicates
    if _latest_duplicates is not None:
        from engine.duplicates import DuplicateGroup
        updated_groups = []
        for g in _latest_duplicates.groups:
            rem = [
                f for f in g.files
                if os.path.normcase(os.path.abspath(f.path)) not in recycled_paths
            ]
            if len(rem) >= 2:
                updated_groups.append(DuplicateGroup(
                    group_id=g.group_id,
                    size_bytes=g.size_bytes,
                    files=rem,
                    hash_hex=g.hash_hex,
                    copies=len(rem),
                    reclaimable_bytes=(len(rem) - 1) * g.size_bytes,
                ))
        _latest_duplicates.groups = updated_groups
        _latest_duplicates.total_groups = len(updated_groups)
        _latest_duplicates.total_duplicate_files = sum(g.copies for g in updated_groups)
        _latest_duplicates.total_reclaimable_bytes = sum(g.reclaimable_bytes for g in updated_groups)
        for listener in _dup_listeners:
            try:
                listener(_latest_duplicates)
            except Exception:
                pass

    # 3. Clear pending cleanup
    set_pending_cleanup([])
