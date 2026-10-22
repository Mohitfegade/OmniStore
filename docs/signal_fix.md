# OmniStore: 32-bit Signal Overflow Audit and Fix Plan

## Problem Summary
In PySide6 / Qt, declaring a signal with argument type `int` (e.g., `Signal(int, int, str)`) maps the parameter to a C++ 32-bit signed integer (`int32_t`).
The maximum representable value is `2,147,483,647` (approx. 2.147 GB).
When scanning any directory containing more than ~2.147 GB of data, emitting the accumulated byte count raises:
```
OverflowError: Python int too large to convert to C long
```
at `workers/scan_worker.py` line ~66 (`self.progress.emit(files, bytes_count, curr_folder)`).
This halts scan progress, causing the UI to freeze mid-scan. A similar vulnerability exists in `workers/duplicate_worker.py` when hashing files totaling over 2.147 GB.

---

## 1. Full Audit of Signals in `workers/` and `ui/`

| File | Class | Signal Name | Current Types | Carries Large Value? | Status / Fix Required |
|---|---|---|---|---|---|
| `workers/scan_worker.py` | `ScanWorker` | `progress` | `Signal(int, int, str)` | **YES** (`bytes_scanned`, `files`) | **VULNERABLE (OverflowError)**. Fix: `Signal(object, object, str)` |
| `workers/scan_worker.py` | `ScanWorker` | `scan_finished` | `Signal(object)` | Object (`ScanResult`) | Safe |
| `workers/scan_worker.py` | `ScanWorker` | `failed` | `Signal(str)` | String | Safe |
| `workers/duplicate_worker.py` | `DuplicateWorker` | `progress` | `Signal(str, int, int, int)` | **YES** (`bytes_hashed`, `items`) | **VULNERABLE (OverflowError)**. Fix: `Signal(str, object, object, object)` |
| `workers/duplicate_worker.py` | `DuplicateWorker` | `finished` | `Signal(object)` | Object (`DuplicateResult`) | Safe |
| `workers/duplicate_worker.py` | `DuplicateWorker` | `failed` | `Signal(str)` | String | Safe |
| `workers/cleanup_worker.py` | `CleanupWorker` | `progress` | `Signal(int, int, str)` | Count (`done`, `total`) | Upgrade to `Signal(object, object, str)` for safety |
| `workers/cleanup_worker.py` | `CleanupWorker` | `finished` | `Signal(object)` | Object (`CleanupOutcome`) | Safe |
| `workers/cleanup_worker.py` | `CleanupWorker` | `failed` | `Signal(str)` | String | Safe |
| `workers/drive_worker.py` | `DriveWorker` | `drives_ready` | `Signal(list)` | List | Safe (or `Signal(object)`) |
| `workers/drive_worker.py` | `DriveWorker` | `error_occurred` | `Signal(str)` | String | Safe |
| `workers/gemma_worker.py` | `CommandWorker` | `eventReady` | `Signal(object)` | Object (`FlowEvent`) | Safe |
| `workers/gemma_worker.py` | `WarmupWorker` | `done` | `Signal(bool)` | Boolean | Safe |
| `workers/gemma_worker.py` | `GemmaHealthWorker` | `status_ready` | `Signal(object)` | Object (`ProviderStatus`) | Safe |
| `workers/gemma_worker.py` | `GemmaHealthWorker` | `failed` | `Signal(str)` | String | Safe |
| `workers/gemma_worker.py` | `GemmaRequestWorker` | `response_ready` | `Signal(object)` | Object (`AgentResponse`) | Safe |
| `workers/gemma_worker.py` | `GemmaRequestWorker` | `failed` | `Signal(str)` | String | Safe |
| `workers/gemma_worker.py` | `GemmaWarmupWorker` | `finished` | `Signal(bool)` | Boolean | Safe |
| `workers/gemma_worker.py` | `GemmaWarmupWorker` | `failed` | `Signal(str)` | String | Safe |
| `workers/command_worker.py` | `CommandWorker` | `interpreting` | `Signal()` | Empty | Safe |
| `workers/command_worker.py` | `CommandWorker` | `tools_ready` | `Signal(object)` | Object | Safe |
| `workers/command_worker.py` | `CommandWorker` | `explanation_chunk` | `Signal(str)` | String | Safe |
| `workers/command_worker.py` | `CommandWorker` | `finished` | `Signal(object)` | Object | Safe |
| `workers/command_worker.py` | `CommandWorker` | `failed` | `Signal(str)` | String | Safe |
| `ui/gemma_status.py` | `GemmaStatusBadge` | `connectionChanged` | `Signal(bool)` | Boolean | Safe |
| `ui/command_widgets.py` | `ChipRow` | `chipClicked` | `Signal(str)` | String | Safe |
| `ui/command_widgets.py` | `ResultCard` | `reviewInCleanup` | `Signal(list)` | List | Safe |
| `ui/command_center.py` | `CommandCenterPage` | `reviewInCleanupRequested` | `Signal(list)` | List | Safe |
| `ui/charts.py` | `DonutChart` | `segment_clicked` | `Signal(str)` | String | Safe |

---

## 2. Signals Identified for Fix
1. **`workers/scan_worker.py`**:
   - `progress: Signal = Signal(int, int, str)` -> `progress: Signal = Signal(object, object, str)`
   - Protects `bytes_scanned` and `files_scanned` with arbitrary-precision Python integers.
2. **`workers/duplicate_worker.py`**:
   - `progress: Signal = Signal(str, int, int, int)` -> `progress: Signal = Signal(str, object, object, object)`
   - Protects `bytes_hashed`, `items_done`, `items_total` with arbitrary-precision Python integers.
3. **`workers/cleanup_worker.py`**:
   - `progress: Signal = Signal(int, int, str)` -> `progress: Signal = Signal(object, object, str)`
   - Protects cleanup counts from any integer overflow.

---

## 3. Font Size Guards (`setPointSize` / `QFont`)
In Qt, passing `<= 0` to `QFont` point size generates warning: `QFont::setPointSize: Point size <= 0 (-1), must be greater than 0`.
Add `create_safe_font(family, size, weight)` in `ui/theme.py`:
- Fall back to default size `10` whenever `size <= 0` or invalid.
- Apply guards in `ui/theme.py`, `ui/components.py`, `ui/charts.py`, and `ui/gemma_status.py`.
