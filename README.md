# OmniStore

> **One place to understand, find, and manage all your storage.**

A Windows desktop storage management app built with Python + PySide6.

---

## Requirements

- Windows 11 (tested) / Windows 10
- Python 3.11 or newer

---

## Setup & Run

```powershell
# 1. Clone / navigate to the project folder
cd d:\OmniStore

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate it
.venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run the app
python main.py
```

> **Tip:** If `Activate.ps1` is blocked by execution policy, run:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

---

## Project Structure

```
omnistore/
├── main.py              # Entry point
├── requirements.txt
├── README.md
├── docs/                # Architecture & contracts (contract_gemma.md, gemma_architecture.md)
├── assets/
│   └── fonts/           # Inter & Inter Tight .ttf files
├── engine/              # Pure-Python storage logic (no UI imports)
├── commands/            # Read-only tool schemas & agent loop (no UI imports)
├── gemma/               # Local Ollama provider, config, & privacy guards (no UI imports)
├── workers/             # QThread workers for background tasks
└── ui/
    ├── theme.py         # Design tokens + global QSS stylesheet
    ├── components.py    # Reusable widgets (Card, StatCard, PillButton …)
    ├── gemma_status.py  # Gemma status pill badge & settings dialog
    └── main_window.py   # Shell with top-bar nav + QStackedWidget pages
```

---

## Command Center & Local Gemma 4 AI

The **Command Center** allows users to explore their storage using conversational English.

### Key Features:
- **Fast Staged Flow**: Real results (compact tables, visual bars) appear within 1–2 seconds from deterministic engine tools; the Gemma explanation streams underneath directly afterward.
- **7 Deterministic Read-Only Tools**: Scan overview, largest files, flexible filtering, largest folders, category breakdown, duplicate summary, and the new `suggest_free_space` tool (which compiles review candidates from duplicates, old files, and empty files).
- **Strict Safety Isolation**: Gemma is strictly read-only and has NO tools that can delete, move, rename, copy, or open files. It never sees file contents—only names, dates, sizes, and totals. Deletion is only possible via explicit user confirmation in the **Cleanup Center** using `send2trash`.
- **Honest & Conservative Wording**: Uses "up to" for all reclaimable space estimates; strictly forbids words like "junk" or "safe to delete".
- **Offline Deterministic Fallback**: If Gemma/Ollama is offline or disabled, OmniStore uses a rule-based parser that maps queries directly to engine tools with zero downtime and provides structured basic explanations.
- **Audit Transparency**: Every byte shared with Gemma is sanitized (names and numbers only, no file contents) and logged to the local AI Audit Log viewer (`ai_audit_log.jsonl`).

### Quick Setup:
1. Install [Ollama](https://ollama.com).
2. Pull the model:
   ```powershell
   ollama pull gemma4:e2b
   ```
3. Start OmniStore (`python main.py`). The top-bar badge will show **`● Gemma 4 (local) connected`** in green.
4. For a 90-second judge walkthrough and presentation questions, see [docs/demo_script.md](docs/demo_script.md).

---

## Verification & Testing

OmniStore includes automated test suites to verify tools, parser rules, and command flows:

```powershell
# 1. Verify pure-Python deterministic basic parser
python tests/check_basic_parser.py

# 2. Verify read-only tool suite & schemas
python tests/check_tools.py

# 3. Verify local Gemma model integration & privacy
python tests/check_gemma.py

# 4. End-to-end staged command flow & latency benchmark
python tests/check_command_flow.py
```

---

## Font Notes

Place the **Inter** and **Inter Tight** static `.ttf` files inside `assets/fonts/`.
The app loads every `.ttf` it finds there at startup and falls back to *Segoe UI*
gracefully if the folder is empty.

