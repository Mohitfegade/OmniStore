# Graph Report - OmniStore  (2026-10-22)

## Corpus Check
- 71 files · ~69,615 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 3 file(s) not represented in the graph (top: .ttf 2, (none) 1)

## Summary
- 907 nodes · 2380 edges · 50 communities (30 shown, 20 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 195 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `9fa724aa`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- ExplanationCard
- cleanup_exec.py
- Signal & Font Safety Audit
- FileRecord
- Windows Drive Enumeration
- gemma_worker.py
- engine/duplicates.py
- os
- Local Gemma Provider & Gateway
- Pending Cleanup Navigation State
- Basic Rule-Based Parser
- Privacy Audit Logging
- run_command
- UI Automation & Screenshots
- ScanResult
- tools.py
- GemmaStatusBadge
- format_bytes
- test_duplicates_ui.py
- OmniStore — Submission Documentation
- Recycle Bin Dialogs & Outcome
- dashboard.py
- check_cleanup.py
- build_plan
- Judge Demo & Cleanup Page
- CommandCenterPage
- Staged Agent Response Dispatcher
- UI Integration Test Suite
- ResultCard
- Synthetic Demo Data Generation
- ._on_send
- ollama_provider.py
- Custom Progress Bar Widgets
- Dashboard Page Scroll Container
- Background Command Worker
- Cleanup Candidate Table Widget
- OmniStore — Submission Readiness Status
- Cleanup Queue State Management
- Latest Scan Result Accessor
- Gemma Chat Streaming Interface
- ChipRow
- _is_protected_path
- Cleanup Confirmation Dialog
- get_latest_duplicates
- Gemma Contract Documentation
- Gemma Provider Specifications

## God Nodes (most connected - your core abstractions)
1. `ScanResult` - 44 edges
2. `format_bytes()` - 35 edges
3. `CleanupPage` - 34 edges
4. `scan_folder()` - 33 edges
5. `OllamaProvider` - 33 edges
6. `AnalyzerPage` - 33 edges
7. `FileRecord` - 32 edges
8. `DuplicateResult` - 31 edges
9. `find_duplicates()` - 31 edges
10. `handle_user_request_staged()` - 27 edges

## Surprising Connections (you probably didn't know these)
- `Offline Deterministic Fallback Mode` --references--> `parse_basic()`  [INFERRED]
  README.md → commands/basic_parser.py
- `CleanupItem & CleanupPlan & CleanupOutcome Models` --implements--> `CleanupPlan`  [INFERRED]
  docs/contract_cleanup.md → engine/cleanup.py
- `Local AI Audit Log & Zero-Trust Privacy Gate` --rationale_for--> `OllamaProvider`  [INFERRED]
  docs/gemma_architecture.md → gemma/ollama_provider.py
- `FlowEvent Streaming Lifecycle` --implements--> `FlowEvent`  [INFERRED]
  docs/contract_command_center.md → commands/events.py
- `Blockers Resolution Log` --references--> `FlowEvent`  [INFERRED]
  docs/status.md → commands/events.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **OmniStore Safety and Privacy Architecture** — readme_safety_isolation, docs_contract_cleanup_send2trash_safety, docs_gemma_architecture_privacy_audit, docs_contract_gemma_localhost_security [INFERRED 0.85]
- **Staged Command Center Flow** — docs_contract_command_center_staged_flow, docs_contract_command_center_flow_events, readme_offline_fallback [INFERRED 0.85]

## Communities (50 total, 20 thin omitted)

### Community 0 - "ExplanationCard"
Cohesion: 0.19
Nodes (3): ExplanationCard, NoticeCard, UserBubble

### Community 1 - "cleanup_exec.py"
Cohesion: 0.11
Nodes (11): Pre-Recycle Duplicate Blake2b Re-hash Verification, _append_log(), execute_plan(), _friendly_error(), _full_hash(), _log_dir(), verify_duplicate_before_delete(), Command Center & Gemma 4 (+3 more)

### Community 2 - "Signal & Font Safety Audit"
Cohesion: 0.06
Nodes (13): Safe Font Point Size Guard, Arbitrary Precision Object Signal Migration, Qt 32-bit Integer Signal Overflow Audit, check_ast_signals(), check_font_guards(), check_large_value_emission(), main(), create_safe_font() (+5 more)

### Community 3 - "FileRecord"
Cohesion: 0.08
Nodes (4): FileRecord, FileTableModel, DuplicateCopyRow, DuplicateGroupCard

### Community 4 - "Windows Drive Enumeration"
Cohesion: 0.12
Nodes (5): DriveInfo, StatCard, _bar_color(), DashboardPage, DriveCard

### Community 5 - "gemma_worker.py"
Cohesion: 0.13
Nodes (6): GemmaSettings, _on_gemma_status_changed(), GemmaHealthWorker, GemmaRequestWorker, GemmaWarmupWorker, WarmupWorker

### Community 6 - "engine/duplicates.py"
Cohesion: 0.15
Nodes (9): build_duplicate_summary(), _compute_full_hash(), _compute_quick_hash(), DuplicateGroup, find_duplicates(), call_progress(), on_chunk_read(), get_default_demo_dir() (+1 more)

### Community 7 - "os"
Cohesion: 0.14
Nodes (7): _is_reparse_point_or_link(), scan_folder(), _should_skip_directory(), check_static_rules(), run_test_suite(), get_default_downloads_folder(), main()

### Community 9 - "Pending Cleanup Navigation State"
Cohesion: 0.10
Nodes (6): add_cleanup_listener(), add_duplicates_listener(), navigate_to(), Card, PageHeader, PillButton

### Community 10 - "Basic Rule-Based Parser"
Cohesion: 0.08
Nodes (12): parse_basic(), _parse_days(), _parse_limit(), _parse_size_in_gb(), _parse_size_in_mb(), ParsedCommand, explain_basic(), build_explain_messages() (+4 more)

### Community 12 - "Privacy Audit Logging"
Cohesion: 0.14
Nodes (6): AuditLog, estimate_payload_bytes(), PayloadTooLarge, sanitize_for_model(), _sanitize_value(), _shorten_path()

### Community 13 - "run_command"
Cohesion: 0.14
Nodes (7): FlowEvent, run_command(), FlowEvent Streaming Lifecycle, Command Center Architecture Contract, suggest_free_space Tool Contract, Blockers Resolution Log, CommandWorker

### Community 14 - "UI Automation & Screenshots"
Cohesion: 0.15
Nodes (7): main(), run(), wait_until_worker_done(), run_test(), MainWindow, apply_theme(), load_fonts()

### Community 15 - "ScanResult"
Cohesion: 0.06
Nodes (7): add_scan_listener(), ScanResult, AnalyzerPage, ColorDot, ErrorsDialog, ResponsiveCardsRow, DonutChart

### Community 16 - "tools.py"
Cohesion: 0.07
Nodes (27): _compact_summary_item(), execute_tool(), _file_record_to_dict(), _strip_control_chars(), validate_tool_call(), Strict JSON Schema Input Validation Gate, Local AI Gemma Architecture, category_for() (+19 more)

### Community 17 - "GemmaStatusBadge"
Cohesion: 0.05
Nodes (10): add_nav_listener(), ProviderStatus, build_analyzer_scroll(), build_cleanup_scroll(), build_command_center_scroll(), build_duplicates_scroll(), AuditLogDialog, GemmaSettingsDialog (+2 more)

### Community 18 - "format_bytes"
Cohesion: 0.09
Nodes (10): format_bytes(), DuplicateResult, _bar(), main(), on_progress(), on_progress(), DuplicatesPage, build_stylesheet() (+2 more)

### Community 19 - "test_duplicates_ui.py"
Cohesion: 0.20
Nodes (6): get_pending_cleanup(), set_latest_duplicates(), set_latest_scan(), run_chips_benchmark(), run_tests(), wait_for_worker()

### Community 20 - "OmniStore — Submission Documentation"
Cohesion: 0.11
Nodes (17): 1. Executive Summary, 1. Requirements & Setup, 2. Architecture & Directory Structure, 2. Prepare Demo Data, 3. Five Core Application Modules, 3. Launch OmniStore, 4. Judge Walkthrough (90 seconds), 4. Safety & Privacy Guarantees (+9 more)

### Community 21 - "Recycle Bin Dialogs & Outcome"
Cohesion: 0.15
Nodes (5): build_cleanup_summary(), CleanupOutcome, CleanupPlan, CleanupResultCard, _rel_path()

### Community 22 - "dashboard.py"
Cohesion: 0.11
Nodes (4): _get_drive_type(), _get_volume_label(), list_drives(), DriveWorker

### Community 23 - "check_cleanup.py"
Cohesion: 0.31
Nodes (4): _cleanup_temp(), _find_group_a(), _make_temp_copy(), run_tests()

### Community 24 - "build_plan"
Cohesion: 0.16
Nodes (9): CleanupItem & CleanupPlan & CleanupOutcome Models, Cleanup Center Contract Specification, build_plan(), CleanupItem, _enforce_group_safety(), _get_raw_drive_type(), _is_safe_drive(), _looks_important() (+1 more)

### Community 25 - "Judge Demo & Cleanup Page"
Cohesion: 0.16
Nodes (3): Honesty, Speed, and Zero-Trust Key Takeaways, 90-Second Judge Walkthrough Demo Script, CleanupPage

### Community 27 - "Staged Agent Response Dispatcher"
Cohesion: 0.14
Nodes (8): AgentResponse, _build_deterministic_explanation(), handle_user_request(), handle_user_request_staged(), _parse_basic_calls(), ToolResult, GemmaProvider, ToolCall

### Community 28 - "UI Integration Test Suite"
Cohesion: 0.40
Nodes (4): run_tests(), _wait_for_worker(), run_e2e(), _wait_worker()

### Community 30 - "Synthetic Demo Data Generation"
Cohesion: 0.31
Nodes (4): create_demo_data(), get_default_demo_dir(), main(), _write_file_chunks()

### Community 32 - "ollama_provider.py"
Cohesion: 0.15
Nodes (7): load_settings(), save_settings(), _settings_path(), extract_facts_from_tool_runs(), visit(), main(), verify_explanation_facts()

### Community 34 - "Dashboard Page Scroll Container"
Cohesion: 0.22
Nodes (5): build_dashboard_scroll(), _build_coming_next_card(), _build_dashboard_page(), _make_page(), _scroll_page()

### Community 37 - "OmniStore — Submission Readiness Status"
Cohesion: 0.33
Nodes (5): Architecture Isolation Rules, File & Component Audit, Full Test Suite Verification, OmniStore — Submission Readiness Status, Signal Overflow Fix (32-bit → object)

## Knowledge Gaps
- **7 isolated node(s):** `Pre-Recycle Duplicate Blake2b Re-hash Verification`, `OmniStore Core Python Dependencies`, `suggest_free_space Tool Contract`, `Safe Font Point Size Guard`, `Honesty, Speed, and Zero-Trust Key Takeaways` (+2 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 365 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ScanResult` connect `ScanResult` to `Signal & Font Safety Audit`, `Background Command Worker`, `gemma_worker.py`, `engine/duplicates.py`, `Latest Scan Result Accessor`, `os`, `Basic Rule-Based Parser`, `Application Bootstrap & Main`, `tools.py`, `format_bytes`, `test_duplicates_ui.py`, `CommandCenterPage`, `Staged Agent Response Dispatcher`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Are the 18 inferred relationships involving `ScanResult` (e.g. with `add_scan_listener()` and `get_latest_scan()`) actually correct?**
  _`ScanResult` has 18 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Pre-Recycle Duplicate Blake2b Re-hash Verification`, `OmniStore Core Python Dependencies`, `suggest_free_space Tool Contract` to the rest of the system?**
  _7 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `cleanup_exec.py` be split into smaller, more focused modules?**
  _Cohesion score 0.11067193675889328 - nodes in this community are weakly interconnected._
- **Why does `AnalyzerPage` connect `ScanResult` to `Signal & Font Safety Audit`, `FileRecord`, `Windows Drive Enumeration`, `Pending Cleanup Navigation State`, `Application Bootstrap & Main`, `UI Automation & Screenshots`, `GemmaStatusBadge`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Should `Signal & Font Safety Audit` be split into smaller, more focused modules?**
  _Cohesion score 0.058279370952821465 - nodes in this community are weakly interconnected._
- **Why does `OllamaProvider` connect `Local Gemma Provider & Gateway` to `ollama_provider.py`, `gemma_worker.py`, `os`, `Gemma Chat Streaming Interface`, `Application Bootstrap & Main`, `Privacy Audit Logging`, `tools.py`, `GemmaStatusBadge`, `test_duplicates_ui.py`, `CommandCenterPage`, `Staged Agent Response Dispatcher`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._