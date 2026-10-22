# OmniStore — Submission Documentation

> **One place to understand, find, and manage all your storage.**  
> Built with Python 3.11+ and PySide6 for Windows 10/11.  
> **Author:** Mohit Fegade

---

## 1. Executive Summary

OmniStore is a modern, high-performance desktop storage intelligence application for Windows. It provides transparent insights into local storage consumption, detects duplicate files across drives, enables safe, non-destructive cleanup via the Windows Recycle Bin, and introduces a conversational **Command Center** powered by local Google Gemma 4 models running via Ollama.

OmniStore was designed with an uncompromising philosophy of safety, privacy, and architectural purity:
1. **Zero Permanent Deletion**: Files are never permanently removed using `os.remove` or `shutil.rmtree`. All deletions route through the OS Recycle Bin (`send2trash`) and require explicit user confirmation.
2. **Strict Architecture Isolation**: The core engine (`engine/`), tool commands (`commands/`), and LLM provider (`gemma/`) are pure Python with zero UI dependencies (`no PySide6 / Qt imports`).
3. **Local & Private AI**: Gemma runs 100% locally on `127.0.0.1:11434`. File contents are never read or transmitted; only file names, dates, and sizes are analyzed. Every payload is recorded in a local audit log (`ai_audit_log.jsonl`).
4. **Fast Staged Flow**: Command Center delivers real visual tool results in 1–3 seconds using deterministic engine tools, followed by streaming natural-language explanations from Gemma.
5. **Deterministic Offline Fallback**: If Ollama or Gemma is offline, OmniStore automatically falls back to an offline rule-based parser with zero downtime.
6. **64-bit Integer Safety**: All Qt signals for file sizes and byte counts use 64-bit safe `object` signals, preventing 32-bit overflow on multi-terabyte drives.

---

## 2. Architecture & Directory Structure

```
OmniStore/
├── main.py                  # Application entry point & Qt lifecycle
├── requirements.txt         # Pinned production dependencies (PySide6, psutil, Send2Trash)
├── app_state.py             # Central reactive state manager & observer bus
├── docs/                    # Technical specifications, contracts, and demo guides
│   ├── submission.md        # This submission overview
│   ├── status.md            # Component audit & readiness checklist
│   ├── demo_script.md       # 90-second judge walkthrough script
│   ├── contract_command_center.md # Command Center staged flow specification
│   ├── contract_gemma.md    # Gemma provider contract & privacy rules
│   ├── contract_cleanup.md  # Safe cleanup contracts & send2trash protocol
│   ├── signal_fix.md        # 64-bit signal overflow architectural fix
│   └── gemma_architecture.md # Gemma integration & fact-checking architecture
├── assets/
│   └── fonts/               # Static Inter and Inter Tight typography
├── engine/                  # Pure-Python deterministic storage intelligence
│   ├── scanner.py           # Multi-threaded filesystem scanner with category mapping
│   ├── duplicates.py        # 3-tier duplicate detection (size -> sample -> SHA256)
│   ├── drives.py            # Drive geometry and mount-point analysis via psutil
│   ├── cleanup.py           # Cleanup candidate identification (empty, old, temp)
│   ├── cleanup_exec.py      # Non-destructive send2trash execution & audit logging
│   ├── categories.py        # Extension-to-category taxonomy
│   ├── query.py             # In-memory file querying, filtering, and sorting
│   └── models.py            # Dataclasses (ScanResult, FileInfo, DuplicateGroup)
├── commands/                # Read-only tool suite & staged flow engine
│   ├── tools.py             # 7 deterministic read-only tools
│   ├── flow.py              # Generator-based staged flow (FlowEvent iterator)
│   ├── events.py            # FlowEvent data structures (routed, tool_result, explain)
│   ├── basic_parser.py      # Rule-based offline natural language parser
│   ├── explain_basic.py     # Deterministic explanation generator for offline mode
│   └── agent.py             # Legacy staged agent adapter
├── gemma/                   # Local Google Gemma model integration
│   ├── ollama_provider.py   # Ollama HTTP API client (tags, chat, function calling)
│   ├── prompts.py           # System prompts, tool schemas, and safety guidelines
│   ├── privacy.py           # Local AI audit logging and privacy validation
│   ├── config.py            # Gemma connection settings & localhost validator
│   └── provider.py          # Abstract base provider interface
├── workers/                 # QThread non-blocking background workers
│   ├── scan_worker.py       # Background drive/folder scan worker
│   ├── duplicate_worker.py  # Background duplicate calculation worker
│   ├── cleanup_worker.py    # Background safe deletion worker
│   ├── drive_worker.py      # Background drive geometry polling worker
│   └── gemma_worker.py      # Staged CommandWorker & model warmup worker
└── ui/                      # PySide6 desktop interface
    ├── main_window.py       # Shell layout, navigation bar, and page stack
    ├── theme.py             # Design tokens, color system, and QSS styling
    ├── components.py        # Reusable cards, badges, buttons, and headers
    ├── dashboard.py         # Module 1: Storage overview & drive status
    ├── analyzer.py          # Module 2: Treemap analysis & folder breakdown
    ├── duplicates.py        # Module 3: Duplicate file manager with side-by-side view
    ├── cleanup.py           # Module 4: Safe cleanup center with category queues
    ├── cleanup_dialogs.py   # Confirmation dialogs for deletion review
    ├── command_center.py    # Module 5: Conversational Command Center page
    ├── command_widgets.py   # Suggestion chips, ResultCard, ExplanationCard
    ├── charts.py            # Custom storage distribution charts
    └── gemma_status.py      # Top-bar connection status pill & settings modal
```

---

## 3. Five Core Application Modules

### Module 1: Dashboard (`ui/dashboard.py`)
- Real-time disk drive capacity meters (Total, Used, Free).
- Storage health overview with visual status cards.
- Quick action launchers to jump directly to scanning, duplicates, or cleanup.

### Module 2: Storage Analyzer (`ui/analyzer.py`)
- Deep directory scanning with progress updates.
- File category distribution charts (Videos, Documents, Archives, Audio, Pictures, Code, Other).
- Interactive largest folders tree table with instant drill-down.

### Module 3: Duplicates Manager (`ui/duplicates.py`)
- 3-stage duplicate detection: file size matching -> 4 KB header/footer sample -> full SHA256 checksum.
- Duplicate group cards displaying wasted space and all file copies.
- "Keep Oldest", "Keep Newest", and manual selection actions.

### Module 4: Safe Cleanup Center (`ui/cleanup.py`, `engine/cleanup_exec.py`)
- Categorized cleanup queues: Temporary files, System caches, Old downloads, Zero-byte files, and Duplicate copies.
- Non-destructive execution: moves items to Windows Recycle Bin (`send2trash`).
- Audit logging of every deleted item to `cleanup_log_*.jsonl`.

### Module 5: Command Center (`ui/command_center.py`, `commands/flow.py`)
- Natural-language storage exploration via plain English.
- 6 one-click suggestion chips for common questions:
  1. *"What is taking up the most space?"*
  2. *"Find duplicate files"*
  3. *"Videos larger than 1 GB"*
  4. *"Files I haven't opened in 6 months"*
  5. *"PDFs modified last month"*
  6. *"Show ways to free 5 GB"*
- Two-stage progressive rendering: tool results arrive in under 2 seconds; Gemma stream finishes shortly after.
- Offline graceful fallback: automatic banner notice, zero crashes, basic rule-based explanation.

---

## 4. Safety & Privacy Guarantees

| Requirement | Implementation | Verification |
|---|---|---|
| **No Permanent Deletion** | No `os.remove`, `os.unlink`, or `shutil.rmtree` in project code. All deletions call `send2trash.send2trash()`. | AST scan in `tests/check_signals.py` and `tests/check_command_flow.py`. |
| **No UI in Pure Modules** | `engine/`, `commands/`, and `gemma/` do not import PySide6, PyQt5, or PyQt6. | Import validation in `tests/check_command_flow.py`. |
| **Local Only LLM** | Ollama requests strictly validate `127.0.0.1` or `localhost`. External URLs rejected. | Tested in `gemma/config.py` and `tests/check_gemma.py`. |
| **No File Content in AI** | Prompts and tools only send metadata (filename, path, byte size, timestamp). | Audited in `ai_audit_log.jsonl`. |
| **Conservative AI Wording** | Gemma and basic explanations use "up to" for savings; never label user data as "junk" or "safe to delete". | Checked in `tests/check_command_flow.py`. |
| **64-bit Signal Safety** | Large scans (>2 GB / >4 GB) pass byte totals through `Signal(object)` to prevent 32-bit signed integer overflow. | Verified in `tests/check_signals.py` and `tests/test_large_scan_ui.py`. |

---

## 5. Verification & Test Suite

All 14 tests in the `tests/` directory run standalone with zero failures:

```powershell
# Run the complete test suite
& "d:\OmniStore\.venv\Scripts\python.exe" -c "
import os, subprocess, sys
for f in sorted([f for f in os.listdir('tests') if f.endswith('.py') and f.startswith(('check_', 'test_'))]):
    res = subprocess.run([sys.executable, os.path.join('tests', f)], capture_output=True, text=True)
    status = 'PASS' if res.returncode == 0 else f'FAIL ({res.returncode})'
    print(f'{f:30} {status}')
"
```

### Verified Test Results:
| Test File | Description | Status |
|---|---|---|
| `check_basic_parser.py` | 18 natural language query patterns against basic rule-based parser | **PASS** |
| `check_cleanup.py` | Safe cleanup engine candidate gathering & non-destructive send2trash | **PASS** |
| `check_command_flow.py` | End-to-end staged flow (static rules, demo scan, 6 queries, latency benchmark) | **PASS** |
| `check_drives.py` | Disk drive discovery, geometry, and space calculation | **PASS** |
| `check_duplicates.py` | Multi-tier duplicate detection and group organization | **PASS** |
| `check_gemma.py` | Ollama connection, local model warmup, fact-checking assertions, audit log | **PASS** |
| `check_query.py` | In-memory filtering by category, size, modification date, extension | **PASS** |
| `check_scanner.py` | Pure-Python filesystem scanner with category aggregation | **PASS** |
| `check_signals.py` | AST audit for unsafe signal types + 5 GB integer emission tests | **PASS** |
| `check_tools.py` | All 7 read-only engine tools and argument schema compliance | **PASS** |
| `check_ui_chips.py` | Live UI execution of all 6 suggestion chips in Command Center | **PASS** |
| `test_cleanup_ui.py` | Cleanup UI widgets, queue checkboxes, and confirmation modal | **PASS** |
| `test_duplicates_ui.py` | Duplicates UI table, group selection, and keep-oldest filters | **PASS** |
| `test_e2e_cleanup_flow.py` | End-to-end cleanup workflow from scan to recycle bin | **PASS** |
| `test_large_scan_ui.py` | High-volume file scan (100,000 synthetic files) UI stability | **PASS** |

---

## 6. How to Run & Demo

### 1. Requirements & Setup
```powershell
cd d:\OmniStore
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Prepare Demo Data
```powershell
python tests/make_demo_data.py
```
This safely creates a sandbox demo dataset at `C:\Users\<User>\OmniStore_Demo` containing mock videos, duplicate documents, old installers, and empty files.

### 3. Launch OmniStore
```powershell
python main.py
```

### 4. Judge Walkthrough (90 seconds)
1. **Dashboard**: Note drive meters and system storage health.
2. **Analyzer**: Click "Scan Folder", select `C:\Users\<User>\OmniStore_Demo`. Watch category breakdown and interactive folder tree render in real time.
3. **Duplicates**: Switch to "Duplicates". See identified duplicate groups, click "Auto-select Oldest", then "Send Selected to Cleanup".
4. **Cleanup Center**: See items queued for deletion. Note clear explanation: *"Items will be moved to the Windows Recycle Bin."* Click "Clean Up" and confirm.
5. **Command Center**: Click the "✦ Command Center" tab. Click the chip *"What is taking up the most space?"*. Observe results card render in ~2 seconds, followed by Gemma's streaming explanation.
