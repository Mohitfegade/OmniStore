"""
engine/cleanup.py
=================
Conservative file-removal engine for OmniStore (Planning and Data Models).

All deletions are sent to the Windows Recycle Bin (via send2trash).
Permanent deletion (os.remove, shutil.rmtree) is strictly forbidden in this codebase.

No PySide6 / Qt imports. This module is safe to run headless.

Public API
----------
CleanupItem        -- describes one file queued for review / removal
CleanupPlan        -- validated plan with blocked items and warnings
CleanupOutcome     -- result after execution

build_plan(items, duplicate_result)  -> CleanupPlan
build_cleanup_summary(plan_or_outcome) -> dict

Re-exported from engine.cleanup_exec:
verify_duplicate_before_delete(item) -> (ok: bool, reason: str)
execute_plan(plan, confirmed, progress_cb, cancel_check) -> CleanupOutcome
"""

from __future__ import annotations

import ctypes
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed reasons (exact strings -- the UI and Gemma layer use these)
# ---------------------------------------------------------------------------
REASON_DUPLICATE = "Exact duplicate"
REASON_LARGE     = "Large file you chose to review"
REASON_OLD       = "Old file you chose to review"
_VALID_REASONS   = {REASON_DUPLICATE, REASON_LARGE, REASON_OLD}


# ---------------------------------------------------------------------------
# Protected locations (case-insensitive, resolved paths)
# ---------------------------------------------------------------------------

def _protected_roots() -> list[str]:
    """Return a list of case-normalised absolute paths that are off-limits."""
    roots: list[str] = []

    # Windows system directories
    win = os.environ.get("SystemRoot") or r"C:\Windows"
    pf  = os.environ.get("ProgramFiles") or r"C:\Program Files"
    pf86 = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    pd  = os.environ.get("ProgramData") or r"C:\ProgramData"
    app = os.environ.get("APPDATA") or ""
    local_app = os.environ.get("LOCALAPPDATA") or ""

    for p in (win, pf, pf86, pd, app, local_app):
        if p:
            roots.append(os.path.normcase(os.path.abspath(p)))

    # OmniStore project folder: two levels up from this file
    try:
        omni_root = os.path.normcase(
            os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        )
        roots.append(omni_root)
    except Exception:
        pass

    return roots


_PROTECTED_FOLDER_NAMES = {"system volume information", "$recycle.bin"}


def _is_protected_path(path: str) -> bool:
    """
    Return True if *path* is inside a protected location.
    Uses case-insensitive comparison on resolved absolute paths.
    """
    try:
        norm = os.path.normcase(os.path.abspath(path))
    except Exception:
        return True  # If we cannot resolve it, treat as protected

    # Check prefix against protected roots
    for root in _protected_roots():
        if norm == root or norm.startswith(root + os.sep):
            return True

    # Check if any component in the path matches protected folder names
    parts = Path(norm).parts
    for part in parts:
        if part.lower() in _PROTECTED_FOLDER_NAMES:
            return True

    return False


# ---------------------------------------------------------------------------
# Drive type check (removable / network -> Recycle Bin may not apply)
# ---------------------------------------------------------------------------

_DRIVE_REMOVABLE = 2
_DRIVE_REMOTE    = 4


def _get_raw_drive_type(path: str) -> int:
    try:
        drive = os.path.splitdrive(path)[0] + "\\"
        return ctypes.windll.kernel32.GetDriveTypeW(drive)  # type: ignore[attr-defined]
    except Exception:
        return 0


def _is_safe_drive(path: str) -> bool:
    """Return True if the Recycle Bin can safely be used for this path."""
    t = _get_raw_drive_type(path)
    return t not in (_DRIVE_REMOVABLE, _DRIVE_REMOTE)


# ---------------------------------------------------------------------------
# "Looks important" heuristic -- warn but do not block
# ---------------------------------------------------------------------------

_IMPORTANT_EXTS = {
    "docx", "doc", "xlsx", "xls", "pptx", "ppt", "pdf",
    "jpg", "jpeg", "png", "heic", "heif", "gif", "tiff", "tif",
    "mp4", "mov", "avi", "mkv",
    "py", "js", "ts", "sql", "db", "sqlite",
    "key", "pem", "p12", "pfx", "crt",
}

_IMPORTANT_FOLDER_KEYWORDS = {
    "documents", "pictures", "desktop", "onedrive", "photos",
}

_WARNING_TEXT = (
    "This looks like a personal document or media file. "
    "Double-check before removing."
)


def _looks_important(path: str) -> bool:
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    if ext in _IMPORTANT_EXTS:
        return True
    norm_parts = [p.lower() for p in Path(path).parts]
    for kw in _IMPORTANT_FOLDER_KEYWORDS:
        if any(kw in part for part in norm_parts):
            return True
    return False


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CleanupItem:
    """One file queued for review / removal."""
    path: str
    name: str
    size_bytes: int
    modified_ts: float
    reason: str                         # One of _VALID_REASONS
    group_id: Optional[str] = None      # Set for REASON_DUPLICATE
    keep_path: Optional[str] = None     # Which copy to keep (duplicates only)


@dataclass
class CleanupPlan:
    """Validated plan output from build_plan()."""
    items: List[CleanupItem] = field(default_factory=list)
    total_bytes: int = 0
    blocked: List[Dict[str, str]] = field(default_factory=list)   # [{"path": str, "reason": str}]
    warnings: List[Dict[str, str]] = field(default_factory=list)  # [{"path": str, "message": str}]


@dataclass
class CleanupOutcome:
    """Result of execute_plan()."""
    succeeded: List[Dict[str, Any]] = field(default_factory=list)
    failed: List[Dict[str, str]] = field(default_factory=list)
    skipped: List[Dict[str, str]] = field(default_factory=list)
    bytes_recovered_estimate: int = 0
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Public Planning API
# ---------------------------------------------------------------------------

def build_plan(
    items: List[CleanupItem],
    duplicate_result: Optional[Any] = None,  # Optional[DuplicateResult]
) -> CleanupPlan:
    """
    Validate every CleanupItem and produce a CleanupPlan.

    Items that fail validation are moved into plan.blocked.
    Items that pass but look important get a warning entry.
    The plan.items list contains only safe-to-proceed files.
    """
    plan_items: List[CleanupItem] = []
    blocked: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    to_remove_paths = set()

    # 1. Per-item validation
    for item in items:
        p = item.path
        reason = _validate_single(item)
        if reason:
            blocked.append({"path": p, "reason": reason})
            continue

        plan_items.append(item)
        to_remove_paths.add(os.path.normcase(os.path.abspath(p)))

        if _looks_important(p):
            warnings.append({"path": p, "message": _WARNING_TEXT})

    # 2. Duplicate group safety: ensure at least one copy survives
    if duplicate_result is not None:
        plan_items, extra_blocked = _enforce_group_safety(
            plan_items, duplicate_result, to_remove_paths
        )
        blocked.extend(extra_blocked)

    total = sum(i.size_bytes for i in plan_items)

    return CleanupPlan(
        items=plan_items,
        total_bytes=total,
        blocked=blocked,
        warnings=warnings,
    )


def _validate_single(item: CleanupItem) -> Optional[str]:
    """
    Return a plain-English block reason if the item must be excluded,
    or None if it passes validation.
    """
    p = item.path

    if item.reason not in _VALID_REASONS:
        return f"Unrecognised reason: {item.reason!r}"

    if _is_protected_path(p):
        return (
            "This path is in a protected system location (Windows, Program Files, AppData, "
            "or the OmniStore installation folder) and cannot be removed."
        )

    if not _is_safe_drive(p):
        return (
            "Files on removable or network drives can't be safely recycled in this version."
        )

    if not os.path.isfile(p):
        return "File no longer exists at the recorded path."

    try:
        st = os.stat(p)
        if st.st_size != item.size_bytes:
            return "This file changed since the scan (size differs). Please rescan."
        if abs(st.st_mtime - item.modified_ts) > 2.0:
            return "This file changed since the scan (modified time differs). Please rescan."
    except OSError as exc:
        return f"Cannot access file: {exc}"

    if item.reason == REASON_DUPLICATE:
        if not item.keep_path:
            return "No 'keep_path' specified for a duplicate item."
        if not os.path.isfile(item.keep_path):
            return "The copy marked to keep no longer exists."

    return None


def _enforce_group_safety(
    plan_items: List[CleanupItem],
    duplicate_result: Any,
    to_remove_paths: set,
) -> tuple[List[CleanupItem], List[Dict[str, str]]]:
    """Ensure at least one copy in each duplicate group survives."""
    from engine.duplicates import DuplicateResult  # local import to avoid circular
    if not isinstance(duplicate_result, DuplicateResult):
        return plan_items, []

    extra_blocked: List[Dict[str, str]] = []

    plan_by_path = {
        os.path.normcase(os.path.abspath(it.path)): it
        for it in plan_items
    }

    for group in duplicate_result.groups:
        group_paths_norm = [
            os.path.normcase(os.path.abspath(f.path)) for f in group.files
        ]
        in_plan = [p for p in group_paths_norm if p in plan_by_path]
        all_in_plan = len(in_plan) == len(group_paths_norm)

        if all_in_plan:
            group_items = [plan_by_path[p] for p in in_plan]
            oldest = min(group_items, key=lambda i: i.modified_ts)
            for it in group_items:
                if it is oldest:
                    plan_items = [x for x in plan_items if x is not it]
                    extra_blocked.append({
                        "path": it.path,
                        "reason": (
                            "Blocked to prevent removing all copies of this group. "
                            "At least one copy must be kept."
                        ),
                    })
                    break

    return plan_items, extra_blocked


# ---------------------------------------------------------------------------
# Re-exported execution functions (from engine.cleanup_exec)
# ---------------------------------------------------------------------------

from engine.cleanup_exec import (  # noqa: E402
    execute_plan,
    verify_duplicate_before_delete,
)


# ---------------------------------------------------------------------------
# Gemma summary
# ---------------------------------------------------------------------------

def build_cleanup_summary(plan_or_outcome: CleanupPlan | CleanupOutcome) -> Dict[str, Any]:
    """
    Compact dict (<2 KB JSON) describing a CleanupPlan or CleanupOutcome.
    Safe to serialise and pass to the Gemma tool-calling layer.
    """
    if isinstance(plan_or_outcome, CleanupPlan):
        plan = plan_or_outcome
        reasons: Dict[str, int] = {}
        for it in plan.items:
            reasons[it.reason] = reasons.get(it.reason, 0) + 1
        return {
            "type": "CleanupPlan",
            "item_count": len(plan.items),
            "total_bytes": plan.total_bytes,
            "blocked_count": len(plan.blocked),
            "warnings_count": len(plan.warnings),
            "reasons": reasons,
            "note": "Files will be sent to Recycle Bin, not permanently deleted.",
        }

    if isinstance(plan_or_outcome, CleanupOutcome):
        out = plan_or_outcome
        return {
            "type": "CleanupOutcome",
            "succeeded_count": len(out.succeeded),
            "failed_count": len(out.failed),
            "skipped_count": len(out.skipped),
            "bytes_recovered_estimate": out.bytes_recovered_estimate,
            "duration_seconds": round(out.duration_seconds, 3),
            "note": "Succeeded files are in the Recycle Bin and can be restored.",
        }

    return {"type": "unknown", "error": "Unrecognised object passed to build_cleanup_summary"}
