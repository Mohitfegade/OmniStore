# Contract: OmniStore Command Center

This contract defines the interfaces, signatures, dataclasses, signals, and invariants for the Command Center screen and staged execution flow in OmniStore. All modules must follow this contract exactly without renaming.

---

## 1. Staged Agent Flow (`commands/agent.py`)

No PySide6/Qt imports.

```python
from typing import Callable, Optional, Dict, Any, List
from engine.models import ScanResult
from engine.duplicates import DuplicateResult
from gemma.provider import GemmaProvider
from gemma.config import GemmaSettings
from commands.tools import ToolResult

StageCallback = Callable[[str, Dict[str, Any]], None]

def handle_user_request_staged(
    text: str,
    scan_result: Optional[ScanResult],
    duplicate_result: Optional[DuplicateResult] = None,
    provider: Optional[GemmaProvider] = None,
    settings: Optional[GemmaSettings] = None,
    on_stage: Optional[StageCallback] = None,
    cancel_token: Optional[Callable[[], bool]] = None,
) -> AgentResponse:
    """
    Executes user request in stages:
    1. on_stage("interpreting", {})
    2. Intent resolution via Gemma OR fast_mode rule-based basic_parser
    3. Deterministic tool execution on scan_result
    4. on_stage("tools_ready", {"tool_runs": list[ToolResult], "mode": "gemma" | "basic"})
    5. Explanation generation via provider.chat_stream:
       - on_stage("explanation_chunk", {"text": chunk}) for each token/chunk
    6. on_stage("done", {"response": AgentResponse})
    Returns AgentResponse.
    """
    ...

def handle_user_request(
    text: str,
    scan_result: Optional[ScanResult],
    duplicate_result: Optional[DuplicateResult] = None,
    provider: Optional[GemmaProvider] = None,
    settings: Optional[GemmaSettings] = None,
) -> AgentResponse:
    """Wraps handle_user_request_staged for backwards compatibility."""
    ...
```

### Explanation Prompt & Quality Rules:
- At most 3 short sentences or a short bullet list of at most 5 items.
- Always use human-readable sizes (the `size_human` fields) and file/folder names.
- Never mention group IDs or raw unformatted byte counts.
- Mention "up to" for reclaimable space.
- State only facts from the tool results. Never claim a file is safe to delete.
- If results are empty, say "No matching files found."

---

## 2. Tools Registry (`commands/tools.py`)

No PySide6/Qt imports.

### Updates to Existing Tools:
1. Every `ToolResult.summary` and `data` row gains `"size_human"` (e.g. `"150 MB"`, binary 1024-based units) next to `size_bytes`.
2. Folder entries in `get_largest_folders` and `get_scan_overview` include both `"name"` (last path component) and `"path"`.

### New Tool: `suggest_free_space`
- Schema parameter: `target_gb` (number, minimum 0.1, maximum 1000).
- Candidate sources:
  1. Exact duplicate copies, keeping the OLDEST copy of each group intact.
  2. Large files not accessed for 180+ days (labeled "review only").
- Returns:
  - `candidates`: list of items sorted descending by size, capped at 200 rows.
    Each item contains: `path`, `name`, `size_bytes`, `size_human`, `reason` ("Exact duplicate" or "Large file not opened recently"), `keep_path` (for duplicates, None otherwise), `potential` (str, e.g. "potential reclaimable"). Never label anything "safe".
  - `target_bytes`: target in bytes.
  - `cumulative_bytes`: total reclaimable/reviewable bytes across candidates.
  - `cumulative_human`: formatted string.
  - `target_reached`: bool, whether candidates meet or exceed `target_gb`.

---

## 3. Deterministic Basic Parser (`commands/basic_parser.py`)

No PySide6/Qt imports.

```python
from typing import Optional, List
from gemma.provider import ToolCall

def parse_basic(text: str) -> Optional[List[ToolCall]]:
    """
    Rule-based deterministic parser mapping common natural language queries to
    the exact same ToolCall objects Gemma would produce.
    Returns None if the intent is unrecognized (never guess).
    """
    ...
```

Supported query patterns:
- "largest files" / "biggest files" (+ optional top N) -> `find_largest_files(limit=N)`
- "what is taking up the most space/storage" -> `get_largest_folders(limit=5)`
- "<category> larger than N MB/GB" -> `filter_files(category=..., min_size_mb=...)`
- "files larger than N MB/GB" -> `filter_files(min_size_mb=...)`
- "find duplicates" / "duplicate files" -> `get_duplicate_summary(max_groups=5)`
- "files not opened in N days/months/years" or "haven't opened recently" (default 180 days) -> `filter_files(not_accessed_for_days=...)`
- "PDFs modified last month / last week / in the last N days" -> `filter_files(category="Documents", extensions=["pdf"], modified_after_days=...)`
- "ways to free N GB" / "free up N GB" -> `suggest_free_space(target_gb=N)`
- "biggest folders" -> `get_largest_folders(limit=5)`
- "overview" / "summary" -> `get_scan_overview()`

---

## 4. Provider Streaming & Speed (`gemma/ollama_provider.py`, `gemma/config.py`)

No PySide6/Qt imports.

### Config (`gemma/config.py`)
```python
@dataclass
class GemmaSettings:
    provider: str = "ollama"
    host: str = "http://localhost:11434"
    model: str = "gemma4:e2b"
    num_ctx: int = 8192
    temperature: float = 0.2
    timeout_s: int = 60
    enabled: bool = True
    fast_mode: bool = False   # When True, try parse_basic first before Gemma
```

### Provider (`gemma/ollama_provider.py`)
```python
class OllamaProvider(GemmaProvider):
    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
        cancel_token: Optional[Callable[[], bool]] = None,
    ) -> Iterator[str]:
        """
        Streaming chat yielding text chunks as they arrive from Ollama NDJSON stream.
        Passes keep_alive="30m", think=False, num_predict=220 for explanation calls.
        """
        ...

    def warm_up(self) -> bool:
        """Send a lightweight 1-token request with keep_alive="30m" to load model into VRAM."""
        ...
```

---

## 5. Background Worker (`workers/command_worker.py`)

```python
from PySide6.QtCore import QThread, Signal

class CommandWorker(QThread):
    interpreting = Signal()
    tools_ready = Signal(object)       # dict: {"tool_runs": list[ToolResult], "mode": str}
    explanation_chunk = Signal(str)    # text chunk
    finished = Signal(object)          # AgentResponse
    failed = Signal(str)

    def cancel(self) -> None: ...
```

### Warmup Worker (`workers/gemma_worker.py`)
```python
class GemmaWarmupWorker(QThread):
    finished = Signal(bool)
    failed = Signal(str)
```

---

## 6. Command Center UI (`ui/command_center.py`)

- `CommandCenterPage(QWidget)`:
  - Top card: input box with sparkle icon, placeholder `"What would you like to explore next?"`, `"Ask"` / `"Stop"` pill button, and 6 suggestion chips.
  - Feed: newest responses on top.
  - Response cards:
    - User query
    - Status pill / progress ("Understanding request...", "Looked up: largest folders")
    - Real results rendered immediately from `ToolResult.data`: compact table with `name`, `size_human`, `category`, `modified`, `folder`.
    - For folders/categories: interactive bars with `HatchedProgressBar`.
    - Gemma explanation streaming directly underneath with badge (`Gemma 4 (local)` or `Basic mode`).
    - Audit log link in footer: `"Shared with the model: N bytes. View details"`.
    - Result actions: right-click menu ("Open file", "Open containing folder", "Copy path").
    - For duplicate / suggest_free_space results: `"Review in Cleanup"` button. When clicked, pushes items to `app_state.set_pending_cleanup(...)` and calls `app_state.navigate_to(3)`.
    - Safety disclaimer: `"Nothing is changed until you confirm in Cleanup."`
  - Empty state: when no scan is loaded, shows button linking to Analyzer.
  - Offline banner: when Gemma is offline, shows `"Gemma is offline, using basic commands"`.
- Wired into `ui/main_window.py` at nav index 4 (`Command Center`).
