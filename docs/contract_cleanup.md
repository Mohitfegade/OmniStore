# Contract: OmniStore Cleanup Center

This contract defines the strict interfaces, types, signatures, signals, and UI widget class names for the OmniStore Cleanup Center. All modules must adhere to this contract.

---

## 1. Dataclasses (`engine/cleanup.py`)

No PySide6/Qt imports anywhere in engine modules.

```python
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

REASON_DUPLICATE = "Exact duplicate"
REASON_LARGE     = "Large file you chose to review"
REASON_OLD       = "Old file you chose to review"
VALID_REASONS    = {REASON_DUPLICATE, REASON_LARGE, REASON_OLD}

@dataclass
class CleanupItem:
    path: str
    name: str
    size_bytes: int
    modified_ts: float
    reason: str                     # One of VALID_REASONS
    group_id: Optional[str] = None  # Non-None for duplicates
    keep_path: Optional[str] = None # Path to kept copy for duplicates

@dataclass
class CleanupPlan:
    items: List[CleanupItem] = field(default_factory=list)
    total_bytes: int = 0
    blocked: List[Dict[str, str]] = field(default_factory=list)   # [{"path": str, "reason": str}]
    warnings: List[Dict[str, str]] = field(default_factory=list)  # [{"path": str, "message": str}]

@dataclass
class CleanupOutcome:
    succeeded: List[Dict[str, Any]] = field(default_factory=list) # [{"path": str, "size_bytes": int}]
    failed: List[Dict[str, str]] = field(default_factory=list)    # [{"path": str, "reason": str}]
    skipped: List[Dict[str, str]] = field(default_factory=list)   # [{"path": str, "reason": str}]
    bytes_recovered_estimate: int = 0
    duration_seconds: float = 0.0
```

---

## 2. Engine Function Signatures

### `engine/cleanup.py`
```python
def build_plan(
    items: List[CleanupItem],
    duplicate_result: Optional[Any] = None,
) -> CleanupPlan:
    """Validate candidate items, block unsafe/protected/missing items, enforce duplicate keep-one rules, and attach warnings."""
    ...

def build_cleanup_summary(plan_or_outcome: CleanupPlan | CleanupOutcome) -> Dict[str, Any]:
    """Return compact JSON-serializable dictionary (<2 KB) summarizing plan or outcome for Gemma layer."""
    ...
```

### `engine/cleanup_exec.py` (Re-exported by `engine/cleanup.py`)
```python
def verify_duplicate_before_delete(item: CleanupItem) -> tuple[bool, str]:
    """Re-hash item.path and item.keep_path (blake2b digest_size=32) right before recycling. Returns (True, '') if identical."""
    ...

def execute_plan(
    plan: CleanupPlan,
    confirmed: bool,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> CleanupOutcome:
    """Send files in plan to Windows Recycle Bin using send2trash only. Refuses if confirmed=False. Writes to cleanup_log.jsonl."""
    ...
```

---

## 3. Global State (`app_state.py`)

```python
def get_pending_cleanup() -> List[dict[str, Any]]: ...
def set_pending_cleanup(items: List[dict[str, Any]]) -> None: ...
def add_cleanup_listener(callback: Callable[[List[dict[str, Any]]], None]) -> None: ...
def apply_cleanup_outcome(outcome: CleanupOutcome) -> None:
    """Update ScanResult (remove recycled files), update DuplicateResult (refresh groups), and clear pending_cleanup."""
    ...
```

Items passed to `set_pending_cleanup` use the format:
```python
{
    "file": FileRecord,
    "reason": str,              # e.g. "Exact duplicate"
    "keep_path": Optional[str],
    "group_id": Optional[str],
}
```

---

## 4. Background Worker (`workers/cleanup_worker.py`)

```python
class CleanupWorker(QThread):
    progress = Signal(int, int, str)   # (done_count, total_count, current_file_path)
    finished = Signal(object)          # Emits CleanupOutcome
    failed   = Signal(str)             # Emits error message

    def __init__(self, plan: CleanupPlan, parent: Optional[QObject] = None) -> None: ...
    def cancel(self) -> None: ...
```

---

## 5. UI Classes & Widgets

### Dialogs & Result Card (`ui/cleanup_dialogs.py`)
- `ConfirmDialog(plan: CleanupPlan, parent: Optional[QWidget] = None)`
  - Lists files (up to 15, then "and N more")
  - Displays total bytes and flagged warning count
  - Mandatory confirmation checkbox: `"I have reviewed these files and want to move them to the Recycle Bin."`
  - `Cancel` button is default
  - `Move to Recycle Bin` button is disabled until checkbox is checked
- `CleanupResultCard(parent: Optional[QWidget] = None)`
  - Displays outcome header with recovered space estimate
  - Lists failures/skipped items if any
  - `"Open Recycle Bin"` button launching `explorer.exe shell:RecycleBinFolder`

### Cleanup Screen (`ui/cleanup.py`)
- `CandidateTable(parent: Optional[QWidget] = None)`: Opt-in candidate table (checkbox in column 0, unchecked by default)
- `PlanTable(on_remove: Callable[[int], None], parent: Optional[QWidget] = None)`: Current plan table with row Remove buttons and muted "Not included" section
- `CleanupPage(parent: Optional[QWidget] = None)`: Full page widget containing empty state, candidate tools card, review list card, summary card, progress card, result card
- `build_cleanup_scroll() -> QScrollArea`: Factory wrapping `CleanupPage` for navigation stack

### App Shell (`ui/main_window.py`)
- Mounted at navigation index 3 (Cleanup).
