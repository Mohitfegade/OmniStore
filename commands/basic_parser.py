"""
commands/basic_parser.py
========================
Deterministic rule-based intent parser for OmniStore.
Provides instant, offline command interpretation when Gemma is disabled or offline,
or during fast_mode execution.

Maps natural language requests to validated ToolCall objects without LLM inference.
Returns None when intent cannot be identified with high confidence (never guesses).
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

import re
from typing import List, Optional

from commands.tools import validate_tool_call
from gemma.provider import ToolCall

# ---------------------------------------------------------------------------
# Unit & Number Parsing Helpers
# ---------------------------------------------------------------------------

_SIZE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(tb|terabytes?|gb|gigabytes?|gigs?|mb|megabytes?|kb|kilobytes?|b|bytes?)\b",
    re.IGNORECASE,
)

_CATEGORY_SYNONYMS = {
    "video": "Videos",
    "videos": "Videos",
    "movie": "Videos",
    "movies": "Videos",
    "clip": "Videos",
    "clips": "Videos",
    "audio": "Audio",
    "music": "Audio",
    "song": "Audio",
    "songs": "Audio",
    "image": "Images",
    "images": "Images",
    "photo": "Images",
    "photos": "Images",
    "picture": "Images",
    "pictures": "Images",
    "document": "Documents",
    "documents": "Documents",
    "doc": "Documents",
    "docs": "Documents",
    "pdf": "Documents",
    "pdfs": "Documents",
    "archive": "Archives",
    "archives": "Archives",
    "zip": "Archives",
    "zips": "Archives",
    "installer": "Installers",
    "installers": "Installers",
    "setup": "Installers",
    "exe": "Installers",
    "code": "Code",
}


def _parse_size_in_mb(text: str) -> Optional[float]:
    """Extract a size from text and return it converted to megabytes (MB)."""
    m = _SIZE_PATTERN.search(text)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).lower()

    if unit.startswith("t"):
        return val * 1024 * 1024
    elif unit.startswith("g"):
        return val * 1024
    elif unit.startswith("m"):
        return val
    elif unit.startswith("k"):
        return val / 1024
    else:
        return val / (1024 * 1024)


def _parse_size_in_gb(text: str) -> Optional[float]:
    """Extract a size from text and return it converted to gigabytes (GB)."""
    mb = _parse_size_in_mb(text)
    if mb is not None:
        return mb / 1024.0

    # Fallback: check standalone number if prompt asks "free up N"
    m_num = re.search(r"\b(\d+(?:\.\d+)?)\b", text)
    if m_num:
        try:
            return float(m_num.group(1))
        except ValueError:
            return None
    return None


def _parse_limit(text: str, default: int = 10) -> int:
    """Extract limit (e.g. 'top 20', 'first 5', '15 largest files')."""
    m = re.search(r"\b(?:top|first|show|list)\s+(\d+)\b", text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 200:
            return val
    m2 = re.search(r"\b(\d+)\s+(?:largest|biggest|files|folders|items|groups)\b", text, re.IGNORECASE)
    if m2:
        val = int(m2.group(1))
        if 1 <= val <= 200:
            return val
    return default


def _parse_days(text: str) -> Optional[int]:
    """Parse time offsets in days, months, or years."""
    # Specific patterns
    if re.search(r"\blast\s+week\b", text, re.IGNORECASE):
        return 7
    if re.search(r"\blast\s+month\b", text, re.IGNORECASE):
        return 30
    if re.search(r"\blast\s+year\b", text, re.IGNORECASE):
        return 365
    if re.search(r"\brecently\b", text, re.IGNORECASE) or re.search(r"haven't opened", text, re.IGNORECASE):
        return 180

    m = re.search(r"(\d+)\s*(days?|months?|years?|weeks?)\b", text, re.IGNORECASE)
    if m:
        num = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("d"):
            return num
        elif unit.startswith("w"):
            return num * 7
        elif unit.startswith("m"):
            return num * 30
        elif unit.startswith("y"):
            return num * 365
    return None


# ---------------------------------------------------------------------------
# Main Parse Function
# ---------------------------------------------------------------------------

def parse_basic(text: str) -> Optional[List[ToolCall]]:
    """
    Parse a user query deterministically.
    Returns a list containing the matched ToolCall or None if unrecognized.
    """
    if not text or not isinstance(text, str):
        return None

    s = text.strip()
    low = s.lower()

    # Reject mutation or destructive requests (our tools are strictly read-only analysis tools)
    if any(verb in low for verb in ["delete", "remove", "erase", "trash", "purge", "destroy", "move", "rename", "copy"]):
        return None

    # Rule 1: Overview / Summary
    if any(p in low for p in [
        "overview", "summary", "scan overview", "storage summary",
        "disk overview", "show overview", "storage overview", "system overview"
    ]):
        ok, args, _ = validate_tool_call("get_scan_overview", {})
        if ok:
            return [ToolCall(name="get_scan_overview", arguments=args)]

    # Rule 2: Free space suggestion ("free up N GB", "ways to free N GB", "clean up N GB")
    if any(kw in low for kw in ["free", "clear space", "reclaim"]) and any(kw in low for kw in ["space", "gb", "mb", "storage", "up", "ways"]):
        target_gb = _parse_size_in_gb(low)
        if target_gb is None or target_gb <= 0:
            target_gb = 5.0  # sensible default
        target_gb = max(0.1, min(target_gb, 1000.0))
        ok, args, _ = validate_tool_call("suggest_free_space", {"target_gb": target_gb})
        if ok:
            return [ToolCall(name="suggest_free_space", arguments=args)]

    # Rule 3: Duplicates ("find duplicates", "duplicate files", "find exact copies", "duplicates")
    if "duplicate" in low or "duplicates" in low or "identical files" in low:
        limit = _parse_limit(low, default=5)
        ok, args, _ = validate_tool_call("get_duplicate_summary", {"max_groups": min(limit, 50)})
        if ok:
            return [ToolCall(name="get_duplicate_summary", arguments=args)]

    # Rule 4: Folders taking most space ("biggest folders", "largest folders", "what is taking up the most space")
    if (
        "most space" in low
        or "most storage" in low
        or "space hogs" in low
        or ("taking up" in low and ("space" in low or "storage" in low))
        or ("biggest" in low and "folder" in low)
        or ("largest" in low and "folder" in low)
    ):
        limit = _parse_limit(low, default=5)
        ok, args, _ = validate_tool_call("get_largest_folders", {"limit": limit})
        if ok:
            return [ToolCall(name="get_largest_folders", arguments=args)]

    # Rule 5: Category breakdown ("categories", "category breakdown", "by category", "file types")
    if "category" in low or "categories" in low or "type breakdown" in low or "by type" in low:
        ok, args, _ = validate_tool_call("get_category_breakdown", {})
        if ok:
            return [ToolCall(name="get_category_breakdown", arguments=args)]

    # Rule 6: Filter by access / modified date ("not opened in", "haven't opened", "modified last", "old files")
    not_opened = any(kw in low for kw in ["not opened", "haven't opened", "not accessed", "unopened", "inactive"])
    modified = "modified" in low or "updated" in low or "changed" in low

    if not_opened:
        days = _parse_days(low) or 180
        limit = _parse_limit(low, default=20)
        ok, args, _ = validate_tool_call("filter_files", {"not_accessed_for_days": days, "limit": limit})
        if ok:
            return [ToolCall(name="filter_files", arguments=args)]

    if modified:
        days = _parse_days(low) or 30
        limit = _parse_limit(low, default=20)
        call_args = {"modified_after_days": days, "limit": limit}
        # Check if specific extension/category is mentioned (e.g. PDFs)
        if "pdf" in low:
            call_args["category"] = "Documents"
            call_args["extensions"] = ["pdf"]
        ok, args, _ = validate_tool_call("filter_files", call_args)
        if ok:
            return [ToolCall(name="filter_files", arguments=args)]

    # Rule 7: Category + Size filter ("videos larger than 10 mb", "pdfs bigger than 50mb", "installers > 100mb")
    matched_category = None
    for kw, cat_name in _CATEGORY_SYNONYMS.items():
        # Match whole word
        if re.search(rf"\b{kw}\b", low):
            matched_category = cat_name
            break

    size_mb = _parse_size_in_mb(low)
    has_size_filter = any(w in low for w in ["larger", "greater", "bigger", "more than", "above", "exceeding", ">", "min"])

    if matched_category and (size_mb is not None or has_size_filter):
        limit = _parse_limit(low, default=20)
        filter_args = {"category": matched_category, "limit": limit}
        if size_mb is not None:
            filter_args["min_size_mb"] = size_mb
        if "pdf" in low:
            filter_args["extensions"] = ["pdf"]
        ok, args, _ = validate_tool_call("filter_files", filter_args)
        if ok:
            return [ToolCall(name="filter_files", arguments=args)]

    # Rule 8: Generic files larger than size ("files larger than 500 MB")
    if (size_mb is not None) and any(w in low for w in ["file", "files", "item", "items", "larger", "bigger", "over"]):
        limit = _parse_limit(low, default=20)
        ok, args, _ = validate_tool_call("filter_files", {"min_size_mb": size_mb, "limit": limit})
        if ok:
            return [ToolCall(name="filter_files", arguments=args)]

    # Rule 9: Largest files / biggest files ("largest files", "biggest files", "top 10 files")
    if "largest file" in low or "largest files" in low or "biggest file" in low or "biggest files" in low or "top files" in low:
        limit = _parse_limit(low, default=10)
        call_args = {"limit": limit}
        if matched_category:
            call_args["category"] = matched_category
        ok, args, _ = validate_tool_call("find_largest_files", call_args)
        if ok:
            return [ToolCall(name="find_largest_files", arguments=args)]

    # No rule matched with high confidence — return None (never guess)
    return None
