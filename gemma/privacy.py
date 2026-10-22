"""
gemma/privacy.py
================
Privacy guard and audit logger for all model interactions.

Strict privacy rules:
1. Allow-list only: Only metadata fields (name, size, category, date, counts, totals) are allowed.
2. Shortened paths: Absolute paths are shortened to the last two parts.
3. Long names truncated to 60 characters.
4. File contents are NEVER transmitted.
5. Max payload size: 6 KB (6144 bytes). Raises PayloadTooLarge if exceeded.
6. Audit log: Every payload sent to the model is recorded in %LOCALAPPDATA%\\OmniStore\\ai_audit_log.jsonl.
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

log = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 6 * 1024  # 6 KB


class PayloadTooLarge(Exception):
    """Raised when the serialized payload exceeds the 6 KB safety ceiling."""
    pass


# Strict allowed field names across queries, summaries, and tools
_ALLOWED_FIELDS: Set[str] = {
    # File record metadata
    "name",
    "size_bytes",
    "category",
    "modified_date",
    "extension",
    "folder",
    "parent_folder",
    "root_path",
    # Aggregates & counts
    "count",
    "counts",
    "totals",
    "percentages",
    "total_files",
    "total_bytes",
    "duration_seconds",
    "errors_count",
    "skipped_count",
    "percent_of_total",
    "file_count",
    "percent_of_scan",
    # Duplicates metadata
    "total_groups",
    "total_duplicate_files",
    "total_reclaimable_bytes",
    "min_size_bytes",
    "copies",
    "reclaimable_bytes",
    "group_id",
    # Container keys
    "files",
    "categories",
    "top_folders",
    "top_files",
    "folders",
    "top_groups",
    "top_10",
    "data",
    "summary",
    "type",
    "note",
    # Human-readable and candidate metadata
    "size_human",
    "total_size_human",
    "reclaimable_human",
    "path",
    "target_gb",
    "target_bytes",
    "target_human",
    "cumulative_bytes",
    "cumulative_human",
    "target_reached",
    "candidates",
    "top_candidates",
    "potential",
    "reason",
    "keep_path",
}


def estimate_payload_bytes(obj: Any) -> int:
    """Return the length of the UTF-8 JSON representation of obj."""
    try:
        return len(json.dumps(obj, default=str, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return len(str(obj).encode("utf-8"))


def _shorten_path(path_str: str) -> str:
    """Shorten an absolute path to its last two path components (e.g. 'Videos/holiday.mp4')."""
    if not path_str or not isinstance(path_str, str):
        return ""
    try:
        parts = Path(path_str).parts
        if len(parts) >= 2:
            return str(Path(parts[-2]) / parts[-1])
        return str(Path(path_str))
    except Exception:
        return path_str[-40:]


def _sanitize_value(val: Any) -> Any:
    if isinstance(val, dict):
        sanitized = {}
        for k, v in val.items():
            if str(k) in _ALLOWED_FIELDS:
                sanitized[str(k)] = _sanitize_value(v)
        return sanitized
    elif isinstance(val, list):
        return [_sanitize_value(item) for item in val]
    elif isinstance(val, str):
        # Truncate strings to max 60 chars (or shorten if looks like path)
        if "\\" in val or "/" in val:
            return _shorten_path(val)
        return val[:60]
    elif isinstance(val, (int, float, bool)) or val is None:
        return val
    else:
        return str(val)[:60]


def sanitize_for_model(obj: Any) -> Any:
    """
    Sanitize an object before passing it to the local model:
    - Retains only allowed metadata fields.
    - Shortens paths.
    - Truncates strings over 60 characters.
    - Never includes file contents.
    - Enforces a 6 KB maximum payload size.
    """
    cleaned = _sanitize_value(obj)
    size = estimate_payload_bytes(cleaned)
    if size > MAX_PAYLOAD_BYTES:
        raise PayloadTooLarge(
            f"Sanitized payload size ({size} bytes) exceeds safety ceiling of {MAX_PAYLOAD_BYTES} bytes."
        )
    return cleaned


# ---------------------------------------------------------------------------
# Audit Logger
# ---------------------------------------------------------------------------

class AuditLog:
    """
    Maintains a persistent, user-inspectable audit log of every model invocation
    in %LOCALAPPDATA%\\OmniStore\\ai_audit_log.jsonl.
    """

    @staticmethod
    def _log_path() -> Path:
        local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        d = Path(local_app) / "OmniStore"
        d.mkdir(parents=True, exist_ok=True)
        return d / "ai_audit_log.jsonl"

    @classmethod
    def append(
        cls,
        model: str,
        tool_names: List[str],
        payload_bytes: int,
        sanitized_payload: Any,
        duration_ms: Optional[float] = None,
        first_token_ms: Optional[float] = None,
    ) -> None:
        """Append an audit record for this LLM interaction."""
        record: Dict[str, Any] = {
            "timestamp": time.time(),
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": model,
            "tool_names": tool_names,
            "payload_bytes": payload_bytes,
            "sanitized_payload": sanitized_payload,
        }
        if duration_ms is not None:
            record["duration_ms"] = round(duration_ms, 1)
        if first_token_ms is not None:
            record["first_token_ms"] = round(first_token_ms, 1)
        try:
            with open(cls._log_path(), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            log.warning("Failed to append to AI audit log: %s", exc)

    @classmethod
    def read_recent(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """Read recent audit records in reverse chronological order."""
        path = cls._log_path()
        if not path.is_file():
            return []

        records: List[Dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()

            for line in reversed(lines):
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        continue
                if len(records) >= limit:
                    break
        except Exception as exc:
            log.warning("Failed to read AI audit log: %s", exc)

        return records
