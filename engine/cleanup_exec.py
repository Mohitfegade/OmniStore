"""
engine/cleanup_exec.py
======================
Execution engine for OmniStore cleanup operations.

All deletions are performed using send2trash.send2trash() — sending files to the
Windows Recycle Bin. Permanent deletion (e.g. os.remove, shutil.rmtree) is strictly
forbidden in this codebase.

No PySide6 / Qt imports. This module is safe to run headless.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Lazy / local type imports to avoid circular dependencies
from engine.cleanup import CleanupItem, CleanupOutcome, CleanupPlan, REASON_DUPLICATE

log = logging.getLogger(__name__)

_FULL_HASH_CHUNK = 1024 * 1024  # 1 MB chunks, blake2b digest_size=32


def _log_dir() -> Path:
    local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    d = Path(local_app) / "OmniStore"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _append_log(entry: dict) -> None:
    """Append an audit record to cleanup_log.jsonl."""
    try:
        log_path = _log_dir() / "cleanup_log.jsonl"
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.warning("Failed to write cleanup log: %s", exc)


def _full_hash(path: str, expected_size: int) -> tuple[Optional[str], Optional[str]]:
    """
    Return (hash_hex, error_msg). Uses blake2b digest_size=32, 1 MB chunks.
    Matches engine/duplicates.py implementation.
    """
    try:
        st = os.stat(path)
        if st.st_size != expected_size:
            return None, f"File size changed ({st.st_size} != {expected_size})"
        hasher = hashlib.blake2b(digest_size=32)
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(_FULL_HASH_CHUNK)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest(), None
    except OSError as exc:
        return None, str(exc)


def verify_duplicate_before_delete(item: CleanupItem) -> tuple[bool, str]:
    """
    Re-hash item.path and item.keep_path immediately before recycling to confirm
    they are still byte-identical.
    Returns (True, "") if identical, or (False, reason_string) otherwise.
    """
    if item.reason != REASON_DUPLICATE:
        return True, ""

    if not item.keep_path:
        return False, "No keep_path recorded for this duplicate item."

    if not os.path.isfile(item.path):
        return False, f"File to remove no longer exists: {item.path}"

    if not os.path.isfile(item.keep_path):
        return False, f"Copy being kept no longer exists: {item.keep_path}"

    try:
        size_to_remove = os.path.getsize(item.path)
        size_to_keep = os.path.getsize(item.keep_path)
    except OSError as exc:
        return False, f"Cannot stat file: {exc}"

    if size_to_remove != size_to_keep:
        return False, "Files differ in size — no longer identical."

    hash_remove, err = _full_hash(item.path, size_to_remove)
    if hash_remove is None:
        return False, f"Cannot hash file to remove: {err}"

    hash_keep, err = _full_hash(item.keep_path, size_to_keep)
    if hash_keep is None:
        return False, f"Cannot hash file to keep: {err}"

    if hash_remove != hash_keep:
        return False, "No longer identical to the copy being kept."

    return True, ""


def execute_plan(
    plan: CleanupPlan,
    confirmed: bool,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> CleanupOutcome:
    """
    Execute the CleanupPlan by sending each item to the Windows Recycle Bin.

    Parameters
    ----------
    plan : CleanupPlan
        The validated plan to execute.
    confirmed : bool
        Must be True or ValueError is raised.
    progress_cb : callable(done, total, current_path) -> None, optional
    cancel_check : callable() -> bool, optional

    Returns
    -------
    CleanupOutcome
    """
    if not confirmed:
        raise ValueError(
            "execute_plan() refused: confirmed=False. "
            "The user must explicitly confirm before any files are recycled."
        )

    import send2trash  # lazy import — send2trash is the only deletion mechanism

    start = time.perf_counter()
    succeeded: List[Dict[str, Any]] = []
    failed: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    total = len(plan.items)

    for idx, item in enumerate(plan.items):
        if cancel_check and cancel_check():
            for rem in plan.items[idx:]:
                skipped.append({"path": rem.path, "reason": "Operation cancelled by user."})
            break

        if progress_cb:
            try:
                progress_cb(idx, total, item.path)
            except Exception:
                pass

        # 1. Existence and stat check
        if not os.path.isfile(item.path):
            skipped.append({
                "path": item.path,
                "reason": "File no longer exists on disk (may have been moved or removed).",
            })
            _append_log({
                "timestamp": time.time(), "path": item.path,
                "reason": item.reason, "result": "skipped", "detail": "File not found",
            })
            continue

        try:
            current_st = os.stat(item.path)
            if current_st.st_size != item.size_bytes:
                skipped.append({
                    "path": item.path,
                    "reason": f"File size changed ({current_st.st_size} != {item.size_bytes} bytes).",
                })
                _append_log({
                    "timestamp": time.time(), "path": item.path,
                    "reason": item.reason, "result": "skipped", "detail": "Size changed",
                })
                continue
        except OSError as exc:
            failed.append({"path": item.path, "reason": f"Cannot stat file: {exc}"})
            continue

        # 2. Duplicate re-verification check
        if item.reason == REASON_DUPLICATE:
            ok, reason = verify_duplicate_before_delete(item)
            if not ok:
                skipped.append({"path": item.path, "reason": f"Verification failed: {reason}"})
                _append_log({
                    "timestamp": time.time(), "path": item.path,
                    "reason": item.reason, "result": "skipped",
                    "detail": f"Duplicate verify failed: {reason}",
                })
                continue

        # 3. Send to Recycle Bin
        try:
            send2trash.send2trash(item.path)
        except Exception as exc:
            err_msg = _friendly_error(exc)
            log.warning("send2trash failed for %s: %s", item.path, exc)
            failed.append({"path": item.path, "reason": err_msg})
            _append_log({
                "timestamp": time.time(), "path": item.path,
                "reason": item.reason, "result": "failed", "detail": str(exc),
            })
            continue

        # 4. Confirm the file is gone from its original path
        if os.path.exists(item.path):
            failed.append({
                "path": item.path,
                "reason": "File still exists at original path after recycling.",
            })
            _append_log({
                "timestamp": time.time(), "path": item.path,
                "reason": item.reason, "result": "failed", "detail": "File still present",
            })
            continue

        succeeded.append({
            "path": item.path,
            "name": item.name,
            "size_bytes": item.size_bytes,
            "reason": item.reason,
        })
        _append_log({
            "timestamp": time.time(), "path": item.path,
            "size_bytes": item.size_bytes,
            "reason": item.reason, "result": "recycled",
        })

    if progress_cb:
        try:
            progress_cb(total, total, "")
        except Exception:
            pass

    bytes_recovered = sum(s["size_bytes"] for s in succeeded)
    duration = time.perf_counter() - start

    return CleanupOutcome(
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        bytes_recovered_estimate=bytes_recovered,
        duration_seconds=duration,
    )


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, PermissionError):
        return "Permission denied — the file may be in use or read-only."
    if isinstance(exc, FileNotFoundError):
        return "File not found (may have already been moved or deleted)."
    msg = str(exc)
    return msg if msg else f"Unexpected error: {type(exc).__name__}"
