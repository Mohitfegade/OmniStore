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
- **Staged Speed Architecture**: Real results (compact tables, visual hatched progress bars) appear immediately from deterministic tools; the Gemma explanation streams underneath directly afterward.
- **Strict Safety Isolation**: Gemma is strictly read-only and has NO tools that can delete, move, rename, copy, or open files. All cleanup actions must be confirmed by the user in the **Cleanup Center**.
- **Offline Deterministic Fallback**: If Gemma/Ollama is offline or `fast_mode` is enabled, OmniStore uses a rule-based parser that maps queries directly to engine tools with zero downtime.
- **Audit Transparency**: Every byte shared with Gemma is sanitized (names and numbers only, no file contents) and logged to the AI Audit Log viewer.

### Quick Setup:
1. Install [Ollama](https://ollama.com).
2. Pull the model:
   ```powershell
   ollama pull gemma4:e2b
   ```
3. Start OmniStore (`python main.py`). The top-bar badge will show **`● Gemma 4 (local) connected`** in green.
4. For presentation details and judge walkthroughs, see [docs/demo_script.md](docs/demo_script.md).

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

