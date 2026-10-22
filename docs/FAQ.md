# OmniStore — Frequently Asked Questions (FAQ)

> Honest, code-verified answers to common questions about OmniStore.

---

### 1. Does OmniStore delete my files permanently?

**No.** OmniStore never uses permanent deletion functions (`os.remove`, `os.unlink`, or `shutil.rmtree` are completely absent from the codebase). 

When you choose to clean up files in the Cleanup Center:
- Files are moved to the native **Windows Recycle Bin** using `send2trash`.
- Deletion requires your explicit confirmation via a confirmation dialog.
- You can restore any deleted file at any time directly from the Recycle Bin.
- For duplicate files, OmniStore enforces a "keep-one-copy" invariant so original files are never discarded.

---

### 2. What does Gemma see? Does it read my file contents?

**No.** Gemma never sees, reads, or transmits the contents of your files.

- Only high-level filesystem metadata is analyzed: file names, relative paths, file extensions, size in bytes, and last modified/accessed timestamps.
- Tools exposed to Gemma are strictly read-only analysis functions (`commands/tools.py`). There are no tools that can read file bodies, write files, open files, or execute shell commands.
- Every single byte of data exchanged with Gemma is logged transparently to the local audit log.

---

### 3. Does OmniStore work offline?

**Yes.** OmniStore is built offline-first.

- The Dashboard, Storage Analyzer, Duplicates Manager, and Safe Cleanup Center are pure local Python modules that require zero internet connection.
- When Ollama or Gemma is unavailable, the Command Center seamlessly falls back to a deterministic rule-based natural language parser (`commands/basic_parser.py`) with zero downtime.
- Even with Gemma enabled, all inference runs 100% locally on your machine via Ollama (`127.0.0.1:11434`). No telemetry or cloud API calls are ever made.

---

### 4. Why use Gemma 4 for storage intelligence?

Traditional storage tools either force users to manually click through complex directory trees or use rigid, technical SQL-like queries.

Local Gemma 4 bridges this gap:
- **Natural Language Understanding**: Users can ask questions in conversational English (e.g., *"What is taking up the most space?"*, *"Show ways to free 5 GB"*).
- **Function Calling**: Gemma accurately identifies the user's intent and selects the exact deterministic engine tool required with validated parameters.
- **Contextual Synthesis**: After the engine calculates verified facts, Gemma synthesizes a concise, plain-English explanation that highlights where space is concentrated and suggests logical review steps.

---

### 5. What happens if Ollama is not installed or offline?

OmniStore handles this gracefully without crashing or degrading core functionality:
- The top-bar status pill displays a neutral gray badge: **`○ Gemma offline`** (or red if connection refused).
- The Command Center displays a helpful banner: *"Gemma is offline. OmniStore is running in fast Basic mode."*
- All 6 suggestion chips and free-form questions continue to work using the offline rule-based parser.
- Clicking the status badge opens a settings dialog with exact instructions on how to install Ollama and pull `gemma4:e2b`.

---

### 6. Where are logs and audit trails stored?

All logs are stored locally on your machine in standard user application folders:
- **AI Query & Prompt Audit Log**: `%LOCALAPPDATA%\OmniStore\ai_audit_log.jsonl`  
  Records timestamp, query text, tool name, sanitized payload bytes, Gemma response, and latency for every single AI interaction.
- **Cleanup Action Log**: `cleanup_log_<timestamp>.jsonl` (in project directory)  
  Records every file moved to the Recycle Bin with its original path, size, and timestamp.
