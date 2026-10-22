# OmniStore — Hackathon Submission Writeup

> **Theme**: Best Use of Gemma  
> **Author**: Mohit (Solo Developer)  
> **Repository**: [https://github.com/Mohitfegade/OmniStore](https://github.com/Mohitfegade/OmniStore)  
> **Target OS**: Windows 10 / Windows 11 (64-bit)  
> **License**: MIT

---

## 1. Problem

Modern operating systems accumulate gigabytes of forgotten data: duplicate downloads, redundant backups, obsolete installer packages, and stale media files. Standard OS file explorers offer no contextual intelligence—they present nested folder trees that force users to manually hunt through hundreds of directories to determine what is consuming storage.

Third-party disk cleaning utilities often make the situation worse:
- They make unilateral decisions about user files, risking accidental data loss.
- They permanently delete files without OS Recycle Bin recovery options.
- Cloud-based storage analyzers require uploading directory metadata or file bodies to remote servers, violating personal privacy.
- They lack conversational intelligence, requiring users to learn arcane search syntax or filter configurations.

---

## 2. Solution

**OmniStore** is a local-first, privacy-respecting Windows desktop storage manager built with Python 3.13 and PySide6. It unifies storage intelligence into five focused workflows:
1. **Dashboard**: High-level drive capacity meters and immediate health metrics.
2. **Storage Analyzer**: Rapid filesystem scanning, file category breakdown, and folder space aggregation.
3. **Duplicates Manager**: Multi-stage byte-identical hash detection (size -> sample -> SHA256) with conservative auto-selection.
4. **Safe Cleanup Center**: Dedicated review queues where items are non-destructively moved to the Windows Recycle Bin (`send2trash`) only after explicit user confirmation.
5. **Command Center**: Natural-language storage exploration where users ask conversational English questions and receive verified engine results in under 2 seconds, accompanied by streaming explanations from local Google Gemma 4.

---

## 3. How Gemma 4 is Central

Gemma 4 is not an afterthought or cosmetic chatbot in OmniStore—it serves as the **semantic routing and contextual synthesis engine** for storage intelligence:

- **Conversational Function Calling**: When a user asks a free-form question (e.g. *"What is taking up the most space?"* or *"Show ways to free 5 GB"*), Gemma interprets the intent and picks the exact deterministic read-only tool required from `commands/tools.py`.
- **Fast Staged Flow**: Because LLMs should never be a performance bottleneck, OmniStore separates execution from explanation. The engine runs the tool immediately and displays verified results (visual tables, metric bars) in 1–2 seconds. Gemma streams its natural language explanation underneath directly afterward.
- **Privacy & Metadata Boundary**: Gemma runs 100% locally via Ollama on `127.0.0.1:11434`. It has **no access to file contents**; it receives only sanitized filesystem metadata (names, sizes, dates, categories, totals).
- **Strict Read-Only Isolation**: Gemma has zero tools to delete, move, rename, copy, or open files. It cannot modify files.
- **Fact-Checking Assertions**: Every number, file name, and byte count mentioned in Gemma's explanation must originate from the underlying deterministic tool result.
- **Deterministic Offline Fallback**: If Ollama or Gemma is offline, OmniStore seamlessly falls back to a rule-based parser (`commands/basic_parser.py`) with zero downtime.

---

## 4. Architecture

OmniStore enforces strict architectural boundaries. Pure Python modules have zero UI dependencies, ensuring the core engine and AI integrations can be tested completely headless.

```
┌─────────────────────────────────────────────────────────────┐
│                    PySide6 Desktop UI                       │
│  (Dashboard, Analyzer, Duplicates, Cleanup, CommandCenter)  │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Qt Signals / FlowEvents)
┌──────────────────────────────▼──────────────────────────────┐
│                    Background QThreads                      │
│   (ScanWorker, DuplicateWorker, CleanupWorker, CommandWorker)│
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                     Commands Layer                          │
│   (flow.py staged runner, 7 read-only tool schemas, events) │
├──────────────────────────────┬──────────────────────────────┤
│    Local Gemma Layer         │      Pure Engine Core        │
│   (OllamaProvider, privacy,  │   (scanner, duplicates,      │
│    localhost audit log)      │    drives, cleanup_exec)     │
│   *NO PySide6 / Qt*          │   *NO PySide6 / Qt*          │
└──────────────────────────────┴──────────────────────────────┘
                               │ (Safe Non-Destructive Delete)
┌──────────────────────────────▼──────────────────────────────┐
│                  Windows Recycle Bin                        │
│                (send2trash.send2trash)                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Safety Design

| Safety Invariant | Implementation Mechanism |
|---|---|
| **Zero Permanent Deletion** | Complete absence of `os.remove`, `os.unlink`, and `shutil.rmtree` in project code. All deletions call `send2trash`. |
| **Explicit User Confirmation** | Cleanup actions require clicking "Clean Up" in a modal displaying total items and reclaimable space. |
| **Keep-One-Copy Invariant** | Duplicate cleanup queues always preserve at least one original copy. |
| **Protected System Paths** | Critical directories (`Windows`, `Program Files`, `System32`) are protected against accidental selection. |
| **Changed-Since-Scan Check** | File modification timestamps are verified immediately before sending to the Recycle Bin to prevent deleting modified files. |
| **Conservative Terminology** | Reclaimable space estimates always use "up to". Unconditional deletion promises are strictly avoided in favor of transparent review. |
| **Full Audit Trail** | Every Recycle Bin action is appended to `cleanup_log_<timestamp>.jsonl`; every AI interaction is logged to `%LOCALAPPDATA%\OmniStore\ai_audit_log.jsonl`. |

---

## 6. What Was Verified (Automated Test Suite)

All 15 test scripts in `tests/` pass with zero failures:

| Test Script | What It Verifies | Status |
|---|---|---|
| `check_basic_parser.py` | 18 natural language query patterns against offline rule-based parser | **PASS** |
| `check_cleanup.py` | Safe candidate gathering, queue filters, and non-destructive send2trash | **PASS** |
| `check_command_flow.py` | Staged flow event sequence, sub-6s tool execution, fact-checking | **PASS** |
| `check_drives.py` | Drive discovery, filesystem types, and space calculation | **PASS** |
| `check_duplicates.py` | 3-tier hashing (size -> sample -> SHA256) duplicate group accuracy | **PASS** |
| `check_gemma.py` | Local Ollama connection, model warmup, AI audit log creation | **PASS** |
| `check_query.py` | In-memory file filtering by category, size, date, and extension | **PASS** |
| `check_scanner.py` | Multi-threaded filesystem scanner and category aggregation | **PASS** |
| `check_signals.py` | AST audit for unsafe signal types + 5 GB 64-bit integer emission tests | **PASS** |
| `check_tools.py` | All 7 read-only tool contracts and parameter schema compliance | **PASS** |
| `check_ui_chips.py` | Live UI execution of all 6 Command Center suggestion chips | **PASS** |
| `test_cleanup_ui.py` | Cleanup UI widgets, queue checkboxes, and confirmation modal | **PASS** |
| `test_duplicates_ui.py` | Duplicates table, group selection, and keep-oldest filters | **PASS** |
| `test_e2e_cleanup_flow.py` | End-to-end scan-to-recycle-bin safety workflow | **PASS** |
| `test_large_scan_ui.py` | High-volume file scan (100,000 synthetic files) UI stability | **PASS** |

---

## 7. Limitations (Honest)

- **Windows Only**: Designed and tested specifically for Windows 10 and Windows 11 with native Windows Recycle Bin integration.
- **Local LLM Inference Speed**: Gemma's explanation streaming speed depends on host CPU/GPU hardware. While engine tool results render in 1–2 seconds, full explanation text generation typically requires 6–12 seconds on local hardware.
- **Localhost Dependency for AI**: Natural-language reasoning requires an active Ollama instance with `gemma4:e2b`. When offline, the app runs in Basic mode with rule-based routing.

---

## 8. What is Next (Roadmap)

- **AI Cleanup Advisor**: Proactive suggestions explaining which duplicate sets have not been accessed in over 2 years.
- **Smart Folder Organizer**: Conversational suggestions for grouping loose files into standardized directory hierarchies.
- **Optional Hosted Gemma**: Support for users who prefer providing their own hosted Gemini/Gemma API key instead of running a local Ollama daemon.
- **Image Content Categorization**: On-device embedding models to cluster visual photos without cloud uploads.
- **Recorded Demonstration**: Guided interactive walkthrough.
