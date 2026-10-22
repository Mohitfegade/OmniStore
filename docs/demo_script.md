# OmniStore Demo Script (3 Minutes)

This script is designed for presenting OmniStore and the Command Center to judges and evaluators using the standardized demo folder (`C:\Users\Mohit\OmniStore_Demo`).

---

## 🎯 Demo Goal
Show how OmniStore pairs local private AI (**Gemma 4** via Ollama) with a high-performance deterministic engine:
1. **Immediate Results**: Real files appear within seconds from validated deterministic tools.
2. **Streaming Plain-English Explanations**: Gemma explains the findings directly underneath.
3. **Guaranteed Safety**: Gemma has zero delete/modify tools; any cleanup action must be confirmed by the user in the Cleanup center.
4. **Offline Resilience**: Even if Gemma is offline, the deterministic parser keeps the Command Center fully functional.

---

## ⏱️ Minute-by-Minute Presentation Script

### Minute 0:00 – 0:45 | Overview & Scanning
1. **Launch OmniStore** (`python main.py`).
2. **Point out the Top Bar**:
   - Show the green status badge: **`● Gemma 4 (local) connected`**.
   - *Key Talking Point:* "OmniStore runs Gemma 4 entirely on this laptop through Ollama. No data, file content, or personal files ever leave this device."
3. **Navigate to Analyzer (Nav #2)**:
   - Click "Choose folder" or use the Quick Pick pill to select `C:\Users\Mohit\OmniStore_Demo`.
   - Click **"Scan"**. The scan completes in under 200 ms, showing file category breakdown, largest files, and folder trees.
   - *Key Talking Point:* "Our scanning and hashing engine is completely deterministic, pure Python, and lightning-fast."

### Minute 0:45 – 2:00 | Command Center & Gemma 4
1. **Switch to Command Center (Nav #5)**.
2. **Test Query 1 (Space Hogs)**:
   - Click the suggestion chip: **"What is taking up the most space?"**
   - Click **"Ask"** (watch it switch to "Stop" during processing).
   - **Show the result:**
     - A tool chip appears: `✓ get largest folders`.
     - The real results render **immediately** as visual hatched progress bars showing the top folders (`Videos`, `Backup`, etc.).
     - Immediately following, Gemma streams a concise, 2-sentence explanation:
       *"The Videos folder takes up the largest amount of storage at 60 MB, followed by the Backup folder at 20 MB."*
   - *Key Talking Point:* "Notice the speed architecture: the UI doesn't wait for LLM completion to show data. Real numbers appear on screen first, and Gemma's explanation streams in right after."
3. **Test Query 2 (Duplicates & Safety Hand-off)**:
   - Click the suggestion chip: **"Find duplicate files"** (or type it).
   - **Show the result:**
     - Tool chip: `✓ get duplicate summary`.
     - Compact table lists duplicate copies with exact file names, sizes, and paths.
     - A banner appears: *"Found duplicate extra copies ready to review"* with a button **"Review in Cleanup"**.
     - Notice the disclaimer: *"Nothing is changed until you confirm in Cleanup."*
   - Click **"Review in Cleanup"**:
     - OmniStore automatically switches to the **Cleanup Center**, queuing only the redundant copies while preserving the original.
     - *Key Talking Point:* "Gemma 4 has strictly zero delete, rename, or move tools. It cannot touch files. It only analyzes and flags items for review in the protected Cleanup module."

### Minute 2:00 – 2:30 | Privacy & Audit Transparency
1. **Switch back to Command Center**.
2. **Audit Footer**:
   - Scroll to the bottom of any response card and point out:
     `Shared with the model: 482 bytes. View details`
   - Click **"View details"** to open the **AI Audit Log dialog**.
   - Show the exact JSON payload sent to Ollama: only aggregate numbers, sanitized file names, and tool summaries.
   - *Key Talking Point:* "Complete user transparency. Every byte shared with the local model is inspectable in our persistent audit log."

### Minute 2:30 – 3:00 | Offline Resilience ("Try it without Gemma")
1. Click the status badge in the top bar to open **Gemma Settings**.
2. Uncheck **"Enable Gemma 4 Local AI"** (or toggle **"Fast Mode"**).
3. The top banner immediately updates to: **`⚠️ Gemma is offline, using basic commands`**.
4. In the Command Center, click: **"Show ways to free 5 GB"**.
5. The result appears in under 0.1 seconds using the deterministic rule-based parser!
6. *Key Talking Point:* "If the user is on battery power, doesn't have Ollama running, or wants instant results, OmniStore falls back to a deterministic parser that maps queries directly to engine tools with zero downtime."

---

## 🛠️ Try it Without Gemma
Even on systems without Ollama or a GPU:
1. Open OmniStore settings from the top-bar badge.
2. Uncheck **"Enable Gemma 4 Local AI"**.
3. Type any of the supported queries:
   - `largest files`
   - `what is taking up the most space?`
   - `find duplicate files`
   - `videos larger than 10 mb`
   - `files not opened in 6 months`
   - `PDFs modified last month`
   - `ways to free 5 GB`
   - `overview`
4. The app runs 100% deterministically with sub-millisecond query execution.

---

## 🔧 Troubleshooting Guide

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| **Top badge shows "Gemma offline"** | Ollama service is not running | Start the Ollama application or run `ollama serve` in a terminal. |
| **Model not found error** | `gemma4:e2b` has not been pulled yet | Run `ollama pull gemma4:e2b` in PowerShell. |
| **First query takes 15–20s** | Cold start model weight loading into VRAM | OmniStore runs a background warm-up worker at startup. Ensure app has been open for 10s before demoing. |
| **Port conflict / connection refused** | Ollama listening on non-default port | Verify Ollama is reachable at `http://localhost:11434/api/tags`. |

---

## 📋 Demo Day Checklist
- [ ] Ensure Ollama is running in background tray.
- [ ] Verify `ollama list` shows `gemma4:e2b`.
- [ ] Run `python tests/make_demo_data.py --force` to ensure fresh demo data in `C:\Users\Mohit\OmniStore_Demo`.
- [ ] Launch `python main.py` at least 30 seconds before presentation to allow the warmup worker to load model weights into VRAM.
- [ ] Close heavy background applications (games, browser instances with 50 tabs) to ensure maximum VRAM for local inference.
