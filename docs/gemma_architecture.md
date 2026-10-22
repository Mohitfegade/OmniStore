# OmniStore Local AI Architecture: Gemma 4 + Ollama

OmniStore integrates **Gemma 4** (`gemma4:e2b`) running locally via **Ollama** (`http://localhost:11434`). Gemma acts **strictly as an intent interpreter and explainer**. It never has direct file access, never executes shell commands, and never makes state changes to your disk.

---

## 1. Architecture Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│                              USER QUERY                                │
│          "What is taking up the most space in my scan?"                │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        GEMMA 4 (Local Ollama)                          │
│               Interprets intent & chooses read-only tool               │
│               e.g. Call: find_largest_files(limit=10)                  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       INPUT VALIDATION GATE                            │
│    • Checks against strict JSON Schema                                 │
│    • Enforces numeric bounds (limit 1..200, sizes >= 0)                │
│    • Validates enums & strips control chars                            │
│    • Drops any unknown/unauthorized arguments                          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     DETERMINISTIC STORAGE ENGINE                       │
│    • Runs queries over real in-memory ScanResult                       │
│    • Zero hallucinated files or imaginary sizes                        │
│    • Hard-caps result set to <= 200 items                              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         PRIVACY & AUDIT GATE                           │
│    • Allow-list only: name, size, category, date, totals               │
│    • Shortens file paths to last two segments                          │
│    • NEVER includes file contents or personally identifying paths      │
│    • Caps payload < 2 KB (raises PayloadTooLarge if > 6 KB)            │
│    • Logs exact payload to ai_audit_log.jsonl for user inspection      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        GEMMA 4 (EXPLANATION)                           │
│        Generates a concise, plain-English summary using only           │
│        the verified data returned by the deterministic engine          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                           AGENT RESPONSE                               │
│       Delivered to UI with structured tool results & metadata          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Strict Safety & Data Boundaries

### What is Shared with the Local Model
- **Allowed Metadata Only**: File names (truncated to 60 chars), file size in bytes, high-level category (Videos, Documents, Archives, etc.), modified date, extension, parent directory name (truncated to 40 chars), category totals, file counts, and duplicate group counts.
- **Path Sanitization**: Deep absolute paths like `C:\Users\Username\Documents\Personal\file.txt` are shortened to relative trailing components `Personal\file.txt` before being sent to the model.
- **Payload Limits**: All tool summaries are compacted to under 2 KB JSON. Any payload exceeding 6 KB raises `PayloadTooLarge` and is refused.
- **Audit Logging**: Every single transmission to the model is appended to `%LOCALAPPDATA%\OmniStore\ai_audit_log.jsonl`. Users can click **"View what was sent to the model"** at any time in the UI to inspect the exact JSON sent.

### What is NEVER Shared with the Model
- **NO File Contents**: File contents, file bytes, or text within files are NEVER read or sent to Gemma.
- **NO External Network Transmission**: Only local hosts (`localhost` / `127.0.0.1`) are permitted. External or remote hosts are strictly rejected.

### What Gemma CANNOT Do
1. **Cannot delete files**: There is no delete tool exposed to the model.
2. **Cannot move or rename files**: No filesystem mutation tools exist in the tool registry.
3. **Cannot open files**: The model cannot trigger file launches or shell executions.
4. **Cannot run shell commands**: No shell execution or system commands are exposed.
5. **Cannot invent file facts**: The model only explains real numbers computed deterministically by our engine from actual scan data.

---

## 3. Tool Registry

OmniStore provides 6 validated, read-only tools:

| Tool Name | Parameters | Engine Function | Purpose |
| :--- | :--- | :--- | :--- |
| `get_scan_overview` | *None* | `build_scan_summary` | Total files, total bytes, top categories & folders |
| `find_largest_files` | `limit`, `category`, `min_size_mb`, `name_contains` | `largest_files` | List largest files matching optional filters |
| `filter_files` | `category`, `extensions`, `min_size_mb`, `max_size_mb`, `modified_before_days`, `limit`, `sort_by`, `descending` | `filter_files` | Multi-criteria file search |
| `get_largest_folders` | `limit` | `largest_folders` | Deepest space consumers by directory |
| `get_category_breakdown`| *None* | `summarize_by_category` | Bytes and counts across all file categories |
| `get_duplicate_summary` | `max_groups` | `build_duplicate_summary` | Exact duplicate groups, file counts & reclaimable space |

---

## 4. Setting Up Ollama & Gemma 4 Locally

### 1. Install Ollama
Download and install Ollama from [ollama.com](https://ollama.com).

### 2. Pull the Gemma 4 Model
Open your terminal and run:
```powershell
ollama pull gemma4:e2b
```

### 3. Verify Ollama is Running
Ollama runs in the background and serves requests at `http://localhost:11434`. You can test it by running:
```powershell
curl http://localhost:11434/api/tags
```

---

## 5. UI Integration & Status Badge

OmniStore features a live **Gemma Status Badge** in the top navigation bar:
- **Green Pill (`● Gemma 4 (local) connected`)**: Ollama is running, reachable with sub-millisecond to low-millisecond latency, and `gemma4:e2b` is available.
- **Grey Pill (`● Gemma offline, basic mode`)**: Ollama is offline, unreachable, or disabled in settings. OmniStore gracefully falls back to deterministic basic mode.
- **Clicking the Pill**: Opens the **Gemma 4 Local AI Settings Dialog** to:
  - Test connection latency.
  - Choose between installed local models.
  - Enable or disable Gemma.
  - View the local AI Audit Log.

---

## 6. Troubleshooting

- **Badge shows "Gemma offline, basic mode"**:
  - Check if Ollama is running in your system tray or run `ollama serve`.
  - Open Settings by clicking the badge and click **Test connection**.
- **Model not found error**:
  - Run `ollama list` in PowerShell to check if `gemma4:e2b` is installed.
  - Run `ollama pull gemma4:e2b`.
- **First request latency**:
  - When Gemma 4 is first invoked after being cold, Ollama loads model weights into RAM/VRAM (~15-20 seconds). Subsequent requests execute in ~1-2 seconds.
- **Port Conflict**:
  - Verify that no other process is bound to port 11434 (`Get-Process -Id (Get-NetTCPConnection -LocalPort 11434).OwningProcess`).
