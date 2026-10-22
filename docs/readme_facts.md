# OmniStore — Verified Facts Registry

> This table contains strictly verified facts derived from code AST, automated test executions, and live demo measurements.  
> Documentation, README, and submission artifacts may ONLY use facts marked as **VERIFIED: yes**.

| Fact | Source (File / Test) | Verified |
|---|---|---|
| Python version is 3.13.7 (compatible with Python 3.11+) | Runtime environment (`sys.version`) | yes |
| PySide6 version is 6.12.0 | Runtime `PySide6.__version__` & `requirements.txt` | yes |
| psutil version is 7.2.2 | Runtime `psutil.__version__` & `requirements.txt` | yes |
| Send2Trash version is 2.1.0 | `pip freeze` & `requirements.txt` | yes |
| Operating System supported is Windows 10 & Windows 11 (64-bit) | `engine/drives.py`, platform testing | yes |
| License is MIT (2026, Mohit) | `LICENSE` file | yes |
| Author is Mohit (solo developer) | Project metadata | yes |
| Repository remote URL is `https://github.com/Mohitfegade/OmniStore.git` | `git remote -v` | yes |
| Permanent deletion is completely disabled (`os.remove`, `os.unlink`, `shutil.rmtree` forbidden) | AST check in `tests/check_command_flow.py` & `tests/check_signals.py` | yes |
| Deletions strictly use Windows Recycle Bin (`send2trash.send2trash`) after explicit user confirmation | `engine/cleanup_exec.py`, `ui/cleanup_dialogs.py` | yes |
| `engine/`, `commands/`, `gemma/` contain zero PySide6 / Qt imports | AST check in `tests/check_command_flow.py` | yes |
| Local AI model configured is `gemma4:e2b` via Ollama | `gemma/config.py`, `tests/check_gemma.py` | yes |
| Local AI host is strictly validated to `127.0.0.1` / `localhost` | `gemma/config.py`, `gemma/ollama_provider.py` | yes |
| Local AI never reads or transmits file contents (only file names, sizes, dates, totals) | `gemma/prompts.py`, `commands/tools.py` | yes |
| Local AI audit log path is `%LOCALAPPDATA%\OmniStore\ai_audit_log.jsonl` | `gemma/privacy.py`, `tests/check_gemma.py` | yes |
| Exact count of read-only tools exposed to Gemma / basic parser is 7 | `commands/tools.py` (`TOOL_SCHEMAS`) | yes |
| Tool 1 name: `get_scan_overview` (High-level storage statistics: total files, total size, categories, top folders) | `commands/tools.py` | yes |
| Tool 2 name: `find_largest_files` (Largest files optionally filtered by category or minimum size) | `commands/tools.py` | yes |
| Tool 3 name: `filter_files` (Precise filtering by extension, size range, age, access time, category) | `commands/tools.py` | yes |
| Tool 4 name: `get_largest_folders` (Subfolders consuming the most disk space) | `commands/tools.py` | yes |
| Tool 5 name: `get_category_breakdown` (Storage breakdown by category with counts, bytes, percentages) | `commands/tools.py` | yes |
| Tool 6 name: `get_duplicate_summary` (Duplicate file groups and estimated reclaimable space) | `commands/tools.py` | yes |
| Tool 7 name: `suggest_free_space` (Candidates to free target space: duplicate copies, old files, empty files) | `commands/tools.py` | yes |
| All reclaimable space claims use the conservative qualifier "up to" | `commands/tools.py`, `tests/check_command_flow.py` | yes |
| Forbidden terms: "junk", "safe to delete" are never emitted | `tests/check_command_flow.py` fact assertions | yes |
| Offline fallback mode is deterministic rule-based parser with zero downtime | `commands/basic_parser.py`, `commands/explain_basic.py` | yes |
| Number of suggestion chips on Command Center is 6 | `ui/command_center.py` (`SUGGESTION_CHIPS`) | yes |
| Chip 1: "What is taking up the most space?" | `ui/command_center.py` | yes |
| Chip 2: "Find duplicate files" | `ui/command_center.py` | yes |
| Chip 3: "Videos larger than 1 GB" | `ui/command_center.py` | yes |
| Chip 4: "Files I haven't opened in 6 months" | `ui/command_center.py` | yes |
| Chip 5: "PDFs modified last month" | `ui/command_center.py` | yes |
| Chip 6: "Show ways to free 5 GB" | `ui/command_center.py` | yes |
| Demo dataset location is `C:\Users\Mohit\OmniStore_Demo` | `tests/make_demo_data.py` | yes |
| Demo dataset file count is 17 files | `tests/make_demo_data.py`, live scan | yes |
| Demo dataset total size is 314,009,600 bytes (~299.5 MB) | Live scan | yes |
| Demo dataset duplicate groups count is 3 groups | `engine/duplicates.py`, live run | yes |
| Demo dataset duplicate files count is 7 duplicate copies | `engine/duplicates.py`, live run | yes |
| Demo dataset reclaimable bytes from duplicates is 47,237,120 bytes (~45.0 MB) | `engine/duplicates.py`, live run | yes |
| Inter & Inter Tight static TTF fonts are present in `assets/fonts/` | `assets/fonts/Inter.ttf`, `InterTight.ttf` | yes |
| 64-bit safe signals: `Signal(object)` prevents 32-bit integer overflow on scans > 2 GB / 4 GB | `workers/scan_worker.py`, `tests/check_signals.py` | yes |
| Total automated test scripts in `tests/` is 15 | `tests/` directory | yes |
| All 15 test scripts pass with exit code 0 | `tests/` test run | yes |
| Graphify knowledge graph is present in `graphify-out/` (907 nodes, 2380 edges, 50 communities) | `graphify-out/graph.json` | yes |
| Real UI screenshots exist in `docs/screenshots/` (6 images) | `docs/screenshots/` directory | yes |
| Demo video is NOT recorded (no video link, badge, or placeholder) | Hard rule | yes |
