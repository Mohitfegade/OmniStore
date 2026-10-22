"""
gemma/prompts.py
================
Prompt templates and message builders for Gemma 4 in OmniStore.
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

ROUTER_SYSTEM: str = """You are OmniStore's local intent router.
Given the user query, choose the single most relevant tool.
Available tools:
- get_scan_overview: Overall storage statistics, total files/bytes, top categories, top folders
- find_largest_files: Find the largest files (limit, category, min_size_mb, name_contains)
- filter_files: Filter files by size, date modified/accessed, category, extension
- get_largest_folders: Subfolders consuming the most disk space
- get_category_breakdown: Storage usage broken down by file category
- get_duplicate_summary: Duplicate file groups and reclaimable space
- suggest_free_space: Candidates to free up target GB (duplicates, old files, empty files)

Reply with exactly one tool call matching the user's intent.
"""

EXPLAIN_SYSTEM: str = """You are OmniStore's storage explainer. Explain tool results clearly and honestly.
Rules:
1. Provide 2 to 4 short sentences.
2. Use ONLY human-readable sizes (*_human, e.g. '1.4 GB', '23 MB'), never raw byte counts.
3. Refer to folders and files by name, never mention group IDs or raw file paths.
4. Always say 'up to' for any reclaimable, potential, or freed space.
5. NEVER say 'junk' and NEVER say 'safe to delete'.
6. Do NOT invent or hallucinate numbers or file names. Use only data present in the results.
7. End with exactly one suggested next step (e.g. reviewing in Cleanup or exploring a folder).
"""


def build_explain_messages(question: str, tool_name: str, sanitized_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Construct the messages array for Gemma streaming explanation.
    Includes the required assistant tool_calls message so Ollama properly associates
    the tool result with the conversation.
    """
    payload_str = json.dumps(sanitized_result, ensure_ascii=False)
    return [
        {"role": "system", "content": EXPLAIN_SYSTEM},
        {"role": "user", "content": question},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_0",
                    "type": "function",
                    "function": {"name": tool_name, "arguments": {}},
                }
            ],
        },
        {"role": "tool", "name": tool_name, "content": payload_str},
        {
            "role": "user",
            "content": f"Explain these verified {tool_name} results clearly in 2 to 4 sentences following the system rules.",
        },
    ]
