# 90-Second Demo Script: OmniStore Command Center

**Focus**: Fast real results, honest explanations, strict local privacy, and offline resilience.

---

### Timing Breakdown

| Timestamp | Phase | What the Presenter Does | What the Presenter Says |
|:---|:---|:---|:---|
| **00:00 – 00:15** | **Privacy & Architecture** | Open OmniStore at Dashboard, show the green **Gemma 4 (local)** status pill in the top bar. | *"Welcome to OmniStore. Everything you see runs 100% locally on this machine. Our AI assistant, Gemma 4, operates under strict zero-trust privacy: it never sees file contents, never executes shell commands, and has zero capability to delete or move files. It acts purely as a semantic router and explainer."* |
| **00:15 – 00:35** | **Query 1: Instant Real Results** | Navigate to **Command Center**. Click the chip: **"What is taking the most space?"** | *"Notice how fast this is: within 1 to 2 seconds, real scanned folder data appears in an interactive table. Gemma then streams an explanation in plain English underneath, stating only verified facts and ending with an actionable next step. No hallucinations, no guessing."* |
| **00:35 – 00:55** | **Query 2: Reclaimable Space** | Type: **"I need 1 GB free"** and press Enter. | *"Now let's ask for space suggestions. The engine deterministically checks duplicate extra copies and files older than a year. Notice the language: OmniStore always says 'up to' because space is only potential until reviewed. We never say 'junk' or 'safe to delete'."* |
| **00:55 – 01:15** | **Safe Action: Review in Cleanup** | Click the **Review in Cleanup** pill button on the suggestion card. | *"Command Center never deletes directly. Clicking 'Review in Cleanup' seamlessly queues these files into our conservative Cleanup center. Files are only moved to the Windows Recycle Bin after explicit confirmation, preserving your original files."* |
| **01:15 – 01:30** | **Offline Fallback: Basic Mode** | Click the Gemma badge, toggle Gemma off in settings (or simulate offline), and ask: **"Find duplicate files"**. | *"Even if Ollama is closed or Gemma is offline, OmniStore never stops working. In Basic mode, our deterministic parser instantly routes queries and produces clear explanations with zero downtime."* |

---

### Key Takeaways for the Audience
1. **Speed**: Tool results appear first in 1–2 seconds; explanation streams immediately after.
2. **Honesty & Safety**: Strictly no delete/move tools exposed to the LLM. "Up to" wording enforced.
3. **Local-First Privacy**: Auditable JSONL log of every token exchange; zero cloud dependency.
4. **Resilience**: Full functionality maintained even when Gemma is offline.
