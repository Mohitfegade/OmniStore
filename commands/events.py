"""
commands/events.py
==================
Event dataclass for staged Command Center execution flow.
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class FlowEvent:
    """
    Event emitted during run_command flow.

    kinds:
    - 'routed': data contains {"tool": str, "args": dict, "routed_by": "gemma" | "basic"}
    - 'tool_result': data contains executor output dictionary
    - 'explain_chunk': text contains streaming explanation text
    - 'explain_done': source is "gemma" | "basic"
    - 'notice': text contains informational message (e.g. scan required, help examples)
    - 'error': text contains error message
    """
    kind: str
    text: str = ""
    data: Optional[Dict[str, Any]] = None
    elapsed_ms: int = 0
    source: str = ""
