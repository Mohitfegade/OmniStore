# Graph Report - OmniStore  (2026-10-22)

## Corpus Check
- 70 files · ~52,838 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 1 file(s) not represented in the graph (top: (none) 1)

## Summary
- 884 nodes · 2354 edges · 55 communities (30 shown, 25 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 195 edges (avg confidence: 0.92)
- Token cost: 1,250 input · 620 output

## Community Hubs (Navigation)
- Command Center UI & Flow
- Cleanup Center & Execution
- Signal & Font Safety Audit
- Duplicate Group Management
- Windows Drive Enumeration
- Gemma Configuration & Requests
- Agent & Tool Registry
- Filesystem Scanner Helpers
- Local Gemma Provider & Gateway
- Pending Cleanup Navigation State
- Basic Rule-Based Parser
- Privacy Audit Logging
- Deterministic Basic Explanations
- UI Automation & Screenshots
- Storage Analyzer Page
- Tools Verification Test Suite
- Duplicates Navigation & Scroll Area
- File Category Classifier
- Scan Result Event Broadcasting
- Staged Flow Events Model
- Recycle Bin Dialogs & Outcome
- Table Models & Context Menus
- Judge Demo & Cleanup Page
- UI Error Dialogs & Badges
- Staged Agent Response Dispatcher
- UI Integration Test Suite
- Gemma Status Pill Badge
- Synthetic Demo Data Generation
- Deterministic Tool Execution
- Drive CLI Diagnostic Test
- Custom Progress Bar Widgets
- Dashboard Page Scroll Container
- Background Command Worker
- Cleanup Candidate Table Widget
- Gemma Settings Dialog
- Cleanup Queue State Management
- Latest Scan Result Accessor
- Gemma Chat Streaming Interface
- Provider Health & Warmup
- Storage Donut Chart Widget
- Cleanup Confirmation Dialog
- Audit Log Viewer Dialog
- Top Navigation Bar Shell
- Duplicates Context Update Hook
- Folder Row List Widget
- Duplicate File Byte Hashing
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
- `FlowEvent Streaming Lifecycle` --implements--> `FlowEvent`  [INFERRED]
  docs/contract_command_center.md → commands/events.py
- `Strict JSON Schema Input Validation Gate` --references--> `validate_tool_call()`  [INFERRED]
  docs/gemma_architecture.md → commands/tools.py
- `Staged Latency: Deterministic First, Stream Second` --rationale_for--> `run_command()`  [INFERRED]
  docs/contract_command_center.md → commands/flow.py
- `CleanupItem & CleanupPlan & CleanupOutcome Models` --implements--> `CleanupPlan`  [INFERRED]
  docs/contract_cleanup.md → engine/cleanup.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **OmniStore Safety and Privacy Architecture** — readme_safety_isolation, docs_contract_cleanup_send2trash_safety, docs_gemma_architecture_privacy_audit, docs_contract_gemma_localhost_security [INFERRED 0.85]
- **Staged Command Center Flow** — docs_contract_command_center_staged_flow, docs_contract_command_center_flow_events, readme_offline_fallback [INFERRED 0.85]

## Communities (55 total, 25 thin omitted)

### Community 0 - "Command Center UI & Flow"
Cohesion: 0.06
Nodes (10): CommandContext, CommandCenterPage, _handle_event(), ChipRow, ExplanationCard, NoticeCard, ResultCard, UserBubble (+2 more)

### Community 1 - "Cleanup Center & Execution"
Cohesion: 0.05
Nodes (29): Pre-Recycle Duplicate Blake2b Re-hash Verification, CleanupItem & CleanupPlan & CleanupOutcome Models, Cleanup Center Contract Specification, build_cleanup_summary(), build_plan(), CleanupItem, CleanupPlan, _enforce_group_safety() (+21 more)

### Community 2 - "Signal & Font Safety Audit"
Cohesion: 0.05
Nodes (16): Safe Font Point Size Guard, Arbitrary Precision Object Signal Migration, Qt 32-bit Integer Signal Overflow Audit, check_ast_signals(), check_font_guards(), check_large_value_emission(), main(), build_stylesheet() (+8 more)

### Community 3 - "Duplicate Group Management"
Cohesion: 0.08
Nodes (4): set_latest_duplicates(), DuplicateCopyRow, DuplicateGroupCard, DuplicatesPage

### Community 4 - "Windows Drive Enumeration"
Cohesion: 0.08
Nodes (8): DriveInfo, _get_drive_type(), _get_volume_label(), list_drives(), _bar_color(), DashboardPage, DriveCard, DriveWorker

### Community 5 - "Gemma Configuration & Requests"
Cohesion: 0.11
Nodes (6): handle_user_request(), GemmaSettings, save_settings(), _settings_path(), GemmaProvider, GemmaRequestWorker

### Community 6 - "Agent & Tool Registry"
Cohesion: 0.14
Nodes (6): build_duplicate_summary(), _compute_full_hash(), _compute_quick_hash(), DuplicateGroup, DuplicateResult, FileRecord

### Community 7 - "Filesystem Scanner Helpers"
Cohesion: 0.13
Nodes (12): format_bytes(), _is_reparse_point_or_link(), scan_folder(), _should_skip_directory(), get_default_demo_dir(), main(), on_progress(), get_default_folder() (+4 more)

### Community 8 - "Local Gemma Provider & Gateway"
Cohesion: 0.11
Nodes (5): Strict JSON Schema Input Validation Gate, Local AI Gemma Architecture, validate_local_host(), OllamaProvider, run_chips_benchmark()

### Community 9 - "Pending Cleanup Navigation State"
Cohesion: 0.10
Nodes (7): add_cleanup_listener(), get_pending_cleanup(), navigate_to(), Card, PillButton, StatCard, _build_coming_next_card()

### Community 10 - "Basic Rule-Based Parser"
Cohesion: 0.15
Nodes (9): parse_basic(), _parse_days(), _parse_limit(), _parse_size_in_gb(), _parse_size_in_mb(), ParsedCommand, _strip_control_chars(), validate_tool_call() (+1 more)

### Community 12 - "Privacy Audit Logging"
Cohesion: 0.14
Nodes (6): AuditLog, estimate_payload_bytes(), PayloadTooLarge, sanitize_for_model(), _sanitize_value(), _shorten_path()

### Community 13 - "Deterministic Basic Explanations"
Cohesion: 0.10
Nodes (6): explain_basic(), run_command(), FlowEvent Streaming Lifecycle, Command Center Architecture Contract, suggest_free_space Tool Contract, build_explain_messages()

### Community 14 - "UI Automation & Screenshots"
Cohesion: 0.15
Nodes (7): main(), run(), wait_until_worker_done(), run_test(), MainWindow, apply_theme(), load_fonts()

### Community 16 - "Tools Verification Test Suite"
Cohesion: 0.15
Nodes (9): main(), test_execute_tool_on_demo_scan(), test_no_destructive_tools(), test_validate_extra_arguments(), test_validate_ranges_and_enums(), test_validate_string_sanitization(), test_validate_unknown_tools(), test_validate_valid_calls() (+1 more)

### Community 17 - "Duplicates Navigation & Scroll Area"
Cohesion: 0.11
Nodes (7): add_duplicates_listener(), add_nav_listener(), build_analyzer_scroll(), build_cleanup_scroll(), build_command_center_scroll(), build_duplicates_scroll(), _on_gemma_status_changed()

### Community 18 - "File Category Classifier"
Cohesion: 0.18
Nodes (6): category_for(), build_scan_summary(), filter_files(), largest_files(), largest_folders(), summarize_by_category()

### Community 19 - "Scan Result Event Broadcasting"
Cohesion: 0.16
Nodes (3): add_scan_listener(), set_latest_scan(), ScanResult

### Community 20 - "Staged Flow Events Model"
Cohesion: 0.17
Nodes (7): FlowEvent, load_settings(), check_static_rules(), extract_facts_from_tool_data(), visit(), run_test_suite(), verify_explanation_facts()

### Community 21 - "Recycle Bin Dialogs & Outcome"
Cohesion: 0.16
Nodes (3): CleanupOutcome, CleanupResultCard, _rel_path()

### Community 25 - "Judge Demo & Cleanup Page"
Cohesion: 0.18
Nodes (3): Honesty, Speed, and Zero-Trust Key Takeaways, 90-Second Judge Walkthrough Demo Script, CleanupPage

### Community 26 - "UI Error Dialogs & Badges"
Cohesion: 0.16
Nodes (3): ColorDot, ErrorsDialog, ResponsiveCardsRow

### Community 27 - "Staged Agent Response Dispatcher"
Cohesion: 0.19
Nodes (6): AgentResponse, _build_deterministic_explanation(), handle_user_request_staged(), _parse_basic_calls(), ToolResult, ToolCall

### Community 28 - "UI Integration Test Suite"
Cohesion: 0.26
Nodes (5): _wait_for_worker(), run_tests(), wait_for_worker(), run_e2e(), _wait_worker()

### Community 30 - "Synthetic Demo Data Generation"
Cohesion: 0.31
Nodes (4): create_demo_data(), get_default_demo_dir(), main(), _write_file_chunks()

### Community 31 - "Deterministic Tool Execution"
Cohesion: 0.27
Nodes (6): _compact_summary_item(), execute_tool(), _file_record_to_dict(), display_name(), format_size(), test_formatting_helpers()

### Community 32 - "Drive CLI Diagnostic Test"
Cohesion: 0.20
Nodes (6): _bar(), main(), extract_facts_from_tool_runs(), visit(), main(), verify_explanation_facts()

### Community 34 - "Dashboard Page Scroll Container"
Cohesion: 0.24
Nodes (4): build_dashboard_scroll(), _build_dashboard_page(), _make_page(), _scroll_page()

### Community 39 - "Latest Scan Result Accessor"
Cohesion: 0.43
Nodes (3): get_latest_scan(), run_tests(), _ts_to_str()

### Community 50 - "Duplicate File Byte Hashing"
Cohesion: 0.67
Nodes (3): find_duplicates(), call_progress(), on_chunk_read()

## Knowledge Gaps
- **7 isolated node(s):** `Pre-Recycle Duplicate Blake2b Re-hash Verification`, `suggest_free_space Tool Contract`, `Gemma Integration Contract`, `GemmaProvider Interface and Health Checks`, `Honesty, Speed, and Zero-Trust Key Takeaways` (+2 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 348 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **25 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ScanResult` connect `Scan Result Event Broadcasting` to `Command Center UI & Flow`, `Signal & Font Safety Audit`, `Duplicate Group Management`, `Background Command Worker`, `Gemma Configuration & Requests`, `Agent & Tool Registry`, `Latest Scan Result Accessor`, `Filesystem Scanner Helpers`, `Basic Rule-Based Parser`, `Storage Analyzer Page`, `Duplicate File Byte Hashing`, `File Category Classifier`, `Global App State Core`, `Storage Formatting & Config`, `Staged Agent Response Dispatcher`, `Deterministic Tool Execution`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Are the 18 inferred relationships involving `ScanResult` (e.g. with `add_scan_listener()` and `get_latest_scan()`) actually correct?**
  _`ScanResult` has 18 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Pre-Recycle Duplicate Blake2b Re-hash Verification`, `suggest_free_space Tool Contract`, `Gemma Integration Contract` to the rest of the system?**
  _7 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Command Center UI & Flow` be split into smaller, more focused modules?**
  _Cohesion score 0.06078316773816481 - nodes in this community are weakly interconnected._
- **Why does `AnalyzerPage` connect `Storage Analyzer Page` to `Custom Progress Bar Widgets`, `Signal & Font Safety Audit`, `Pending Cleanup Navigation State`, `Storage Donut Chart Widget`, `UI Automation & Screenshots`, `Duplicates Navigation & Scroll Area`, `Scan Result Event Broadcasting`, `Global App State Core`, `Table Models & Context Menus`, `UI Error Dialogs & Badges`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Should `Cleanup Center & Execution` be split into smaller, more focused modules?**
  _Cohesion score 0.0544464609800363 - nodes in this community are weakly interconnected._
- **Why does `OllamaProvider` connect `Local Gemma Provider & Gateway` to `Drive CLI Diagnostic Test`, `Command Center UI & Flow`, `Gemma Configuration & Requests`, `Agent & Tool Registry`, `Gemma Settings Dialog`, `Gemma Chat Streaming Interface`, `Provider Health & Warmup`, `Application Bootstrap & Main`, `Privacy Audit Logging`, `Staged Flow Events Model`, `Storage Formatting & Config`, `Staged Agent Response Dispatcher`, `Gemma Status Pill Badge`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._