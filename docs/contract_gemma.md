# Contract: OmniStore Gemma Integration

This contract defines the interfaces, dataclasses, signatures, tool schemas, and UI components for connecting OmniStore to Gemma 4 via Ollama. All modules must follow this contract exactly without renaming.

---

## 1. Provider Layer (`gemma/provider.py`)

No PySide6/Qt imports.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class ProviderStatus:
    ok: bool
    message: str
    model: str
    models_available: List[str] = field(default_factory=list)
    latency_ms: Optional[float] = None

@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]

@dataclass
class ProviderReply:
    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    raw_model: str = ""
    duration_ms: float = 0.0
    error: Optional[str] = None

class GemmaProvider(ABC):
    name: str
    is_local: bool

    @abstractmethod
    def health(self) -> ProviderStatus:
        """Check provider reachability, latency, and available models."""
        ...

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> ProviderReply:
        """Send chat messages and optional tool definitions to the model."""
        ...
```

---

## 2. Configuration (`gemma/config.py`)

No PySide6/Qt imports.

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

def load_settings() -> GemmaSettings:
    """Load settings from %LOCALAPPDATA%\\OmniStore\\settings.json or default."""
    ...

def save_settings(settings: GemmaSettings) -> None:
    """Persist settings to %LOCALAPPDATA%\\OmniStore\\settings.json. Enforce localhost/127.0.0.1."""
    ...
```

**Security Constraint**: Only local hosts (`localhost`, `127.0.0.1`, `::1`) are permitted. Reject any remote/external host with a `ValueError`.

---

## 3. Ollama Provider (`gemma/ollama_provider.py`)

No PySide6/Qt imports.

```python
class OllamaProvider(GemmaProvider):
    def __init__(self, settings: GemmaSettings) -> None: ...
    def health(self) -> ProviderStatus: ...
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> ProviderReply: ...
```

**Model Options**:
- Send `"think": False` to skip reasoning trace.
- Send `"stream": False`.
- Parse native `tool_calls` as well as text fallback if the model outputs JSON tool calls in the body.
- Handle connection errors, timeouts, missing models gracefully without unhandled exceptions.

---

## 4. Privacy & Audit (`gemma/privacy.py`)

No PySide6/Qt imports.

```python
class PayloadTooLarge(Exception):
    pass

def estimate_payload_bytes(obj: Any) -> int: ...

def sanitize_for_model(obj: Any) -> Any:
    """
    Allow-list only: name, size_bytes, category, modified_date, extension, folder, counts, totals, percentages.
    Shorten absolute paths to last two parts. Truncate names to 60 chars.
    Never include file contents.
    Raise PayloadTooLarge if JSON payload exceeds 6 KB (6144 bytes).
    """
    ...

class AuditLog:
    @staticmethod
    def append(model: str, tool_names: List[str], payload_bytes: int, sanitized_payload: Any) -> None:
        """Append record to %LOCALAPPDATA%\\OmniStore\\ai_audit_log.jsonl."""
        ...

    @staticmethod
    def read_recent(limit: int = 50) -> List[Dict[str, Any]]:
        """Read recent audit records for UI inspection."""
        ...
```

---

## 5. Tools Registry (`commands/tools.py`)

No PySide6/Qt imports.

```python
TOOL_SCHEMAS: List[Dict[str, Any]]  # Function-calling JSON schemas for:
# - get_scan_overview
# - find_largest_files
# - filter_files
# - get_largest_folders
# - get_category_breakdown
# - get_duplicate_summary

def validate_tool_call(name: str, arguments: Dict[str, Any]) -> tuple[bool, Dict[str, Any], Optional[str]]:
    """Validate schema, type, ranges (limit 1..200, sizes >= 0, days 0..36500), strip control chars, max str len 100."""
    ...

@dataclass
class ToolResult:
    name: str
    ok: bool
    data: Dict[str, Any]
    summary: Dict[str, Any]
    error: Optional[str] = None

def execute_tool(
    name: str,
    cleaned_args: Dict[str, Any],
    scan_result: Optional[ScanResult],
    duplicate_result: Optional[DuplicateResult] = None,
) -> ToolResult:
    """Execute validated tool over real scan data. Caps data to <= 200 items and summary to < 2 KB."""
    ...
```

**Safety Constraint**: NO tools for delete, move, copy, rename, open, or shell execution.

---

## 6. Agent Loop (`commands/agent.py`)

No PySide6/Qt imports.

```python
@dataclass
class AgentResponse:
    ok: bool
    mode: str                    # "gemma" | "unavailable"
    tool_runs: List[ToolResult]
    explanation: str
    error: Optional[str] = None
    payload_bytes_sent: int = 0
    duration_ms: float = 0.0

def handle_user_request(
    text: str,
    scan_result: Optional[ScanResult],
    duplicate_result: Optional[DuplicateResult],
    provider: Optional[GemmaProvider] = None,
    settings: Optional[GemmaSettings] = None,
) -> AgentResponse:
    """
    Coordinate request -> tool selection -> deterministic execution -> explanation.
    Enforces maximum 2 tool rounds and 4 tool calls total.
    """
    ...

def try_basic_mode(
    text: str,
    scan_result: Optional[ScanResult],
    duplicate_result: Optional[DuplicateResult],
) -> Optional[AgentResponse]:
    """Hook for fallback deterministic parser (returns None for now)."""
    ...
```

---

## 7. Workers & UI (`workers/gemma_worker.py`, `ui/gemma_status.py`)

### Workers (`workers/gemma_worker.py`)
- `GemmaHealthWorker(QThread)`: emits `status_ready(ProviderStatus)`, `failed(str)`.
- `GemmaRequestWorker(QThread)`: emits `response_ready(AgentResponse)`, `failed(str)`.

### UI (`ui/gemma_status.py`)
- `GemmaStatusBadge(QWidget)`:
  - Displays pill in top bar:
    - Green: `"Gemma 4 (local) connected"` (with tooltip showing model & latency).
    - Grey: `"Gemma offline, basic mode"`.
  - Refresh button / click re-runs health check or opens settings.
- `GemmaSettingsDialog(QDialog)`:
  - Localhost host field (enforced localhost).
  - Model dropdown from `/api/tags`.
  - "Test connection" button.
  - "Enable Gemma" toggle.
  - "View what was sent to the model" audit log viewer.
  - Disclaimer text: `"Gemma runs locally through Ollama. Your files are never uploaded. Only file names, sizes, dates and totals are shared with the local model."`
