"""
commands/basic_parser.py
========================
Deterministic rule-based intent parser for OmniStore.
Provides instant, offline command interpretation without Gemma.

Maps natural language requests to a ParsedCommand dataclass.
Returns None when intent cannot be identified with high confidence,
on gibberish, or for any destructive request (delete, remove, move, wipe, clean).
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from commands.tools import validate_tool_call


@dataclass(frozen=True)
class ParsedCommand:
    tool: str
    args: Dict[str, Any]
    confidence: float
    rule: str


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

_DESTRUCTIVE_WORDS = [
    "delete", "remove", "move", "clean", "wipe", "erase", "trash",
    "unlink", "rm", "destroy", "purge", "format",
]


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
    """Extract limit (e.g. 'top 20', 'first 5', '10 largest files')."""
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
    """Parse time offsets in days, months, or years into total days."""
    if re.search(r"\blast\s+week\b", text, re.IGNORECASE):
        return 7
    if re.search(r"\blast\s+month\b", text, re.IGNORECASE):
        return 30
    if re.search(r"\blast\s+year\b", text, re.IGNORECASE):
        return 365
    if re.search(r"\brecently\b", text, re.IGNORECASE) or re.search(r"haven't opened", text, re.IGNORECASE):
        return 180

    m = re.search(r"(\d+(?:\.\d+)?)\s*(days?|months?|years?|weeks?)\b", text, re.IGNORECASE)
    if m:
        num = float(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("d"):
            return int(num)
        elif unit.startswith("w"):
            return int(num * 7)
        elif unit.startswith("m"):
            return int(num * 30)
        elif unit.startswith("y"):
            return int(num * 365)
    return None


def parse_basic(text: str) -> Optional[ParsedCommand]:
    """
    Parse a user query deterministically using regex and keyword rules.
    Returns a ParsedCommand or None if unrecognized, gibberish, or destructive.
    """
    if not text or not isinstance(text, str):
        return None

    s = text.strip()
    if not s:
        return None

    low = s.lower()

    # Rule 0: Safety Guard — anything asking to delete/remove/move/clean/wipe must NOT map to a tool
    for word in _DESTRUCTIVE_WORDS:
        if re.search(rf"\b{word}\b", low):
            return None

    # Check for category mentions
    matched_category = None
    for kw, cat_name in _CATEGORY_SYNONYMS.items():
        if re.search(rf"\b{kw}\b", low):
            matched_category = cat_name
            break

    # Rule 1: Free space suggestions ("I need N GB free", "free up N GB", "ways to free N GB", "need 5 GB")
    if (
        re.search(r"\b(?:i\s+need|need|free\s+up|ways\s+to\s+free|want\s+to\s+free)\s+(\d+(?:\.\d+)?)\s*(?:gb|mb|gigabytes?|gigs?)\b", low)
        or (("need" in low or "free" in low) and ("space" in low or "gb" in low or "mb" in low) and re.search(r"\d+", low))
    ):
        target_gb = _parse_size_in_gb(low)
        if target_gb is None or target_gb <= 0:
            target_gb = 5.0
        target_gb = max(0.1, min(target_gb, 5000.0))
        ok, args, _ = validate_tool_call("suggest_free_space", {"target_gb": target_gb})
        if ok:
            return ParsedCommand(tool="suggest_free_space", args=args, confidence=0.95, rule="suggest_free_space")

    # Rule 2: Duplicates ("find duplicates", "duplicate files", "show duplicates", "duplicates")
    if re.search(r"\bduplicates?\b", low) or "identical files" in low:
        limit = _parse_limit(low, default=5)
        ok, args, _ = validate_tool_call("get_duplicate_summary", {"max_groups": min(limit, 50)})
        if ok:
            return ParsedCommand(tool="get_duplicate_summary", args=args, confidence=0.95, rule="duplicates")

    # Rule 3: Biggest / Largest folders ("biggest folders", "largest folders", "what is taking up the most space")
    if (
        "most space" in low
        or "most storage" in low
        or "space hogs" in low
        or ("taking" in low and ("space" in low or "storage" in low))
        or re.search(r"\b(?:largest|biggest)\s+folders?\b", low)
        or re.search(r"\bfolders?\s+(?:taking|using)\b", low)
    ):
        limit = _parse_limit(low, default=5)
        ok, args, _ = validate_tool_call("get_largest_folders", {"limit": limit})
        if ok:
            return ParsedCommand(tool="get_largest_folders", args=args, confidence=0.90, rule="largest_folders")

    # Rule 4: Old files ("older than N days/months/years", "not opened in", "haven't opened")
    if re.search(r"\b(?:older\s+than|not\s+opened\s+in|not\s+accessed\s+in|haven't\s+opened|not\s+used\s+in)\b", low):
        days = _parse_days(low)
        if days is not None:
            limit = _parse_limit(low, default=20)
            call_args: Dict[str, Any] = {"modified_before_days": days, "limit": limit}
            if matched_category:
                call_args["category"] = matched_category
            ok, args, _ = validate_tool_call("filter_files", call_args)
            if ok:
                return ParsedCommand(tool="filter_files", args=args, confidence=0.90, rule="old_files")

    # Rule 5: Drive usage / free space ("drive usage", "free space on drive", "disk usage", "storage overview", "scan overview")
    if (
        re.search(r"\b(?:drive\s+usage|disk\s+usage|free\s+space\s+on|storage\s+usage|drive\s+space)\b", low)
        or low in ["scan overview", "storage overview", "overview", "disk overview", "storage summary", "summary"]
    ):
        ok, args, _ = validate_tool_call("get_scan_overview", {})
        if ok:
            return ParsedCommand(tool="get_scan_overview", args=args, confidence=0.90, rule="drive_usage")

    # Rule 6: Category breakdown / File types ("file types", "category breakdown", "breakdown by category", "by type")
    if (
        "category breakdown" in low
        or "breakdown by category" in low
        or "by category" in low
        or "file types" in low
        or "by file type" in low
        or low == "categories"
    ):
        ok, args, _ = validate_tool_call("get_category_breakdown", {})
        if ok:
            return ParsedCommand(tool="get_category_breakdown", args=args, confidence=0.90, rule="category_breakdown")

    # Rule 7: Category + Size filter ("videos larger than 500 MB", "images bigger than 10 mb", "pdfs larger than 5 mb")
    size_mb = _parse_size_in_mb(low)
    has_size_comp = any(w in low for w in ["larger", "bigger", "greater", "above", "exceeding", "more than", ">", "min"])

    if matched_category and (size_mb is not None or has_size_comp):
        limit = _parse_limit(low, default=20)
        filter_args: Dict[str, Any] = {"category": matched_category, "limit": limit}
        if size_mb is not None:
            filter_args["min_size_mb"] = size_mb
        if "pdf" in low:
            filter_args["extensions"] = ["pdf"]
        ok, args, _ = validate_tool_call("filter_files", filter_args)
        if ok:
            return ParsedCommand(tool="filter_files", args=args, confidence=0.90, rule="category_size_filter")

    # Rule 8: Generic files larger than size ("files larger than 100 MB", "files bigger than 2 GB")
    if size_mb is not None and any(w in low for w in ["file", "files", "larger", "bigger", "over"]):
        limit = _parse_limit(low, default=20)
        ok, args, _ = validate_tool_call("filter_files", {"min_size_mb": size_mb, "limit": limit})
        if ok:
            return ParsedCommand(tool="filter_files", args=args, confidence=0.85, rule="generic_size_filter")

    # Rule 9: Largest / biggest files (+ "top N", optional category)
    if (
        re.search(r"\b(?:largest|biggest)\s+files?\b", low)
        or re.search(r"\b(?:top|first)\s+\d+\s+files?\b", low)
        or low in ["largest files", "biggest files", "top files", "largest", "biggest"]
    ):
        limit = _parse_limit(low, default=10)
        call_args = {"limit": limit}
        if matched_category:
            call_args["category"] = matched_category
        ok, args, _ = validate_tool_call("find_largest_files", call_args)
        if ok:
            return ParsedCommand(tool="find_largest_files", args=args, confidence=0.90, rule="largest_files")

    # Rule 10: Just category mentioned with intention to see files ("show videos", "list images", "documents")
    if matched_category and any(w in low for w in ["show", "find", "list", "view", "get", "all"]):
        limit = _parse_limit(low, default=10)
        filter_args = {"category": matched_category, "limit": limit}
        if "pdf" in low:
            filter_args["extensions"] = ["pdf"]
        ok, args, _ = validate_tool_call("filter_files", filter_args)
        if ok:
            return ParsedCommand(tool="filter_files", args=args, confidence=0.85, rule="category_list")

    # Unrecognized / gibberish -> return None
    return None
