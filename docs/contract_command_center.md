# Contract: OmniStore Command Center (PROMPT 8)

> **Contract Adjustments Noted at the Top:**
> 1. `commands/basic_parser.py`: The function `parse_basic(text: str) -> ParsedCommand | None` now returns a single `@dataclass(frozen=True) ParsedCommand` or `None` (rather than `list[ToolCall]`).
> 2. `commands/tools.py`: `suggest_free_space` validator limit for `target_gb` is increased to `0.1` .. `5000.0` (from 1000.0). The returned payload provides the exact required shape (`target_human`, `reachable`, `total_up_to_bytes`, `total_up_to_human`, `suggestions`, `note`), while also retaining `candidates` for backwards compatibility.
> 3. `commands/flow.py`: `CommandContext` defines `scan: Optional[ScanResult] = None`, `duplicates: Optional[DuplicateResult] = None`, and `drives: Optional[List[DriveInfo]] = None` using models from `engine.models` and `engine.drives`.
> 4. `workers/gemma_worker.py`: Adds `CommandWorker(text, ctx, provider)` emitting `eventReady(object)` (each `FlowEvent`) and `WarmupWorker` emitting `done(bool)`, while preserving existing health check workers.
> 5. `gemma/ollama_provider.py`: `chat_stream` signature is `(self, messages: list[dict], *, max_tokens: int = 200, cancel: threading.Event | None = None) -> Iterator[str]` with `keep_alive="30m"`, `think: False`, and low temperature.

---

## 1. Engine Formatting (`engine/formatting.py`)

No PySide6/Qt imports.

```python
def format_size(n: int) -> str:
    """Format byte count into human-readable binary string: e.g. '1.4 GB', '23 MB', '0 B'."""
    ...

def display_name(path: str) -> str:
    """Return file/folder name; for drive roots return the drive letter (e.g. 'C:')."""
    ...
```

---

## 2. Tools Registry (`commands/tools.py`)

No PySide6/Qt imports.
- Keep all existing 6 tools: `get_scan_overview`, `find_largest_files`, `filter_files`, `get_largest_folders`, `get_category_breakdown`, `get_duplicate_summary`.
- Every size field gets a sibling `"<field>_human"` via `format_size`.
- Every folder/file entry gets `"name"` and `"parent_name"` (via `display_name`), never only a raw path or group id.
- 7th read-only tool: `suggest_free_space(target_gb: float) -> dict`
  - Deterministic. Builds suggestions from:
    (a) exact duplicate extra copies if duplicate results exist,
    (b) largest files older than 365 days,
    (c) empty files (size == 0).
  - Stops when running total reaches target.
  - Returns:
    ```python
    {
        "target_human": str,
        "reachable": bool,
        "total_up_to_bytes": int,
        "total_up_to_human": str,
        "suggestions": [
            {
                "label": str,
                "reason": str,
                "count": int,
                "size_bytes": int,
                "size_human": str,
                "paths": list[str]
            }
        ],
        "note": str  # Always contains "up to" and states the user must review everything
    }
    ```
  - Schema validator: `target_gb` from `0.1` to `5000.0`.
  - Asserted tool count: 7.

---

## 3. Basic Parser (`commands/basic_parser.py`)

No PySide6/Qt imports, no Gemma dependency.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ParsedCommand:
    tool: str
    args: dict
    confidence: float
    rule: str

def parse_basic(text: str) -> ParsedCommand | None:
    ...
```

Rules (case-insensitive, regex/keyword):
- Largest/biggest files (+ "top N", default 10) -> `find_largest_files`
- File types/category breakdown (+ "videos", "images", "documents", etc.) -> `filter_files` or `get_category_breakdown`
- Biggest folders -> `get_largest_folders`
- Duplicates -> `get_duplicate_summary`
- Old files ("older than N days/months/years" converted to days) -> `filter_files` with `modified_before_days`
- "I need N GB/MB free" / "free up N GB" -> `suggest_free_space` with `target_gb`
- Drive usage / free space -> `get_scan_overview` or drive usage
- Destructive commands asking to delete / remove / move / clean / wipe must NOT map to a tool: return `None`.
- Gibberish / unrecognized queries -> return `None`.

---

## 4. Gemma Provider (`gemma/ollama_provider.py`)

No PySide6/Qt imports.

```python
import threading
from typing import Iterator

def warm_up(self) -> bool:
    """Send a lightweight 1-token request with keep_alive='30m'."""
    ...

def chat_stream(
    self,
    messages: list[dict],
    *,
    max_tokens: int = 200,
    cancel: threading.Event | None = None
) -> Iterator[str]:
    """Stream token chunks via Ollama NDJSON API; keep_alive='30m', think=False, low temperature."""
    ...
```
- Reuses localhost-only guard and audit logging for every call.

---

## 5. Gemma Prompts (`gemma/prompts.py`)

No PySide6/Qt imports.

```python
ROUTER_SYSTEM: str
# Minimal: tool names + one line each + "reply with exactly one tool call". Identical prefix every call.

EXPLAIN_SYSTEM: str
# Rules: 2 to 4 short sentences; use only *_human sizes, never raw byte counts;
# refer to folders/files by name; never mention group ids;
# say "up to" for reclaimable space; never say junk / safe to delete;
# do not invent numbers; end with one suggested next step.

def build_explain_messages(question: str, tool_name: str, sanitized_result: dict) -> list[dict]:
    ...
```

---

## 6. Flow Events (`commands/events.py`)

No PySide6/Qt imports.

```python
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass(frozen=True)
class FlowEvent:
    kind: str             # "routed" | "tool_result" | "explain_chunk" | "explain_done" | "notice" | "error"
    text: str = ""
    data: Optional[Dict[str, Any]] = None
    elapsed_ms: int = 0
    source: str = ""      # "gemma" | "basic"
```

Kinds:
- `"routed"`: `data` contains `{"tool": str, "args": dict, "routed_by": "gemma" | "basic"}`
- `"tool_result"`: `data` contains executor output dictionary
- `"explain_chunk"`: `text` contains streaming chunk
- `"explain_done"`: `source` is `"gemma"` | `"basic"`
- `"notice"`: informative message (e.g. asking to scan a folder first, or explaining no destructive commands)
- `"error"`: error message

---

## 7. Command Flow (`commands/flow.py`)

No PySide6/Qt imports.

```python
import threading
from dataclasses import dataclass
from typing import Iterator, Optional, List
from engine.models import ScanResult
from engine.duplicates import DuplicateResult
from engine.drives import DriveInfo
from commands.events import FlowEvent

@dataclass
class CommandContext:
    scan: Optional[ScanResult] = None
    duplicates: Optional[DuplicateResult] = None
    drives: Optional[List[DriveInfo]] = None

def run_command(
    text: str,
    ctx: CommandContext,
    provider: Any,
    cancel: threading.Event | None = None
) -> Iterator[FlowEvent]:
    ...
```

Order is guaranteed: `routed -> tool_result -> explain_chunk* -> explain_done`.
- Routing: If provider connected, ask Gemma with 6 s timeout. On timeout/error/invalid tool/offline, fall back to `parse_basic` (`routed_by: "basic"`). If both fail, emit `"notice"` listing example questions.
- Missing scan guard: Tools needing scan data when `ctx.scan is None` emit `"notice"` asking to scan a folder first.
- Explanation: Stream from Gemma via `chat_stream`. Hard stop after 20 s with a `"notice"` ("Explanation timed out, results above are complete"). If Gemma offline or fails, emit deterministic explanation from `commands/explain_basic.py` (`source: "basic"`).
- Every event carries `elapsed_ms` since `run_command` invocation.

---

## 8. Basic Explanation (`commands/explain_basic.py`)

No PySide6/Qt imports.

```python
from typing import Iterator

def explain_basic(tool_name: str, result: dict) -> Iterator[str]:
    """Deterministic 2 to 4 sentence explanation using real result data and strict wording rules ('up to', no 'junk', no 'safe to delete')."""
    ...
```

---

## 9. Command Widgets (`ui/command_widgets.py`)

PySide6 UI widgets.

```python
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

class ChipRow(QWidget):
    chipClicked = Signal(str)
    def set_chips(self, chips: list[str]) -> None: ...
    def set_enabled_state(self, enabled: bool) -> None: ...

class UserBubble(QWidget):
    def __init__(self, text: str, parent: QWidget | None = None) -> None: ...

class ResultCard(QWidget):
    reviewInCleanup = Signal(list)
    def set_result(self, tool_name: str, data: dict) -> None: ...
    # Shows real rows with *_human sizes; button "Review in Cleanup" appears only when data has candidate paths.

class ExplanationCard(QWidget):
    def set_pending(self) -> None: ...
    def append(self, text: str) -> None: ...
    def finish(self, source: str) -> None: ...
    # Displays badge "Explained by Gemma 4 (local)" or "Basic mode".

class NoticeCard(QWidget):
    def __init__(self, text: str, parent: QWidget | None = None) -> None: ...
```

Styling:
- White cards, 20px radius, 1px `#E6E6E8` border, pill buttons, Inter / Inter Tight.
- All plain `QLabel` instances have a transparent background (enforced in `ui/theme.py`).

---

## 10. Workers (`workers/gemma_worker.py`)

PySide6 QThread workers.

```python
from PySide6.QtCore import QThread, Signal

class CommandWorker(QThread):
    eventReady = Signal(object)  # Emits FlowEvent instances

    def __init__(self, text: str, ctx: CommandContext, provider: Any, parent=None): ...
    def cancel(self) -> None: ...

class WarmupWorker(QThread):
    done = Signal(bool)

    def __init__(self, provider: Any, parent=None): ...
```

---

## 11. Command Center UI (`ui/command_center.py`)

PySide6 UI screen.

```python
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget
from commands.flow import CommandContext

class CommandCenterPage(QWidget):
    reviewInCleanupRequested = Signal(list)

    def set_context(self, ctx: CommandContext) -> None: ...
    def set_gemma_available(self, available: bool) -> None: ...
```

Layout & Features:
- Title + subtitle.
- Conversation scroll area (empty state shows 5 suggestion chips):
  1. "What is taking the most space?"
  2. "Show my 10 largest files"
  3. "Find duplicate files"
  4. "Files older than 1 year"
  5. "I need 5 GB free"
- Input pill with Send and Stop buttons.
- Small latency line under each answer (`"results in 2.1 s, explained in 9.8 s"`).
- If no scan exists: chips are disabled and an inline `"Scan a folder first"` button navigates to Analyzer (`app_state.navigate_to(1)`).
- `"Review in Cleanup"` emits `reviewInCleanupRequested(list)` which queues files to `app_state.set_pending_cleanup(items)` and navigates to Cleanup (`app_state.navigate_to(3)`). Never deletes files directly.
