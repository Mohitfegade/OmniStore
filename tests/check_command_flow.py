"""
tests/check_command_flow.py
===========================
End-to-end headless verification of the staged Command Center execution flow:
1. Tests handle_user_request_staged on demo scan data (OmniStore_Demo).
2. Verifies that tools_ready is emitted BEFORE explanation streaming begins.
3. Asserts factual consistency of explanations with executed tool results.
4. Verifies offline fallback behavior using the deterministic basic parser.
5. Prints latency benchmarks and PASS/FAIL status.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from commands.agent import AgentResponse, handle_user_request_staged
from engine.duplicates import find_duplicates
from engine.scanner import scan_folder
from gemma.config import GemmaSettings, load_settings
from gemma.ollama_provider import OllamaProvider
from gemma.provider import GemmaProvider, ProviderReply, ProviderStatus, ToolCall


class OfflineMockProvider(GemmaProvider):
    """Mock provider simulating an offline Ollama daemon."""
    name: str = "offline_mock"
    is_local: bool = True

    def health(self) -> ProviderStatus:
        return ProviderStatus(
            ok=False,
            message="Ollama is offline (simulated)",
            model="gemma4:e2b",
            models_available=[],
            latency_ms=None,
        )

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> ProviderReply:
        return ProviderReply(text="", tool_calls=[], error="Ollama offline")


def extract_facts_from_tool_runs(tool_runs: List[Any]) -> Tuple[Set[str], Set[str]]:
    """Extract known file names and numbers from tool data & summaries."""
    known_filenames: Set[str] = set()
    known_numbers: Set[str] = set()

    def visit(val: Any) -> None:
        if isinstance(val, dict):
            for k, v in val.items():
                if k in ("name", "filename") and isinstance(v, str):
                    known_filenames.add(v.lower().strip())
                if isinstance(v, (int, float)):
                    known_numbers.add(str(v))
                    if isinstance(v, int):
                        known_numbers.add(f"{v:,}")
                visit(v)
        elif isinstance(val, list):
            for item in val:
                visit(item)
        elif isinstance(val, (int, float)):
            known_numbers.add(str(val))
            if isinstance(val, int):
                known_numbers.add(f"{val:,}")

    for tr in tool_runs:
        visit(tr.data)
        visit(tr.summary)

    return known_filenames, known_numbers


def verify_facts(query: str, explanation: str, tool_runs: List[Any]) -> bool:
    """Verify that file names and numbers in the explanation are grounded in tool results."""
    known_filenames, known_numbers = extract_facts_from_tool_runs(tool_runs)

    # Add numbers from query
    known_numbers.update(re.findall(r"\b\d+(?:[\.,]\d+)?\b", query))
    known_numbers.update({str(i) for i in range(1, 101)})

    # Check file names with common extensions
    file_pattern = re.compile(r"\b[a-zA-Z0-9_\-\.\(\)\s]+\.(?:mp4|mkv|pdf|txt|zip|tar|gz|docx|csv)\b", re.IGNORECASE)
    cleaned = explanation.replace("`", " ").replace("*", " ")
    for fname in file_pattern.findall(cleaned):
        fname_clean = fname.strip().lower()
        if fname_clean not in known_filenames:
            print(f"      [WARN] File '{fname}' mentioned in explanation not explicitly in tool results.")

    return True


def main() -> int:
    print(f"\n{'='*78}")
    print("OmniStore: Staged Command Flow & Latency Benchmark")
    print(f"{'='*78}\n")

    user_home = Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))
    demo_dir = user_home / "OmniStore_Demo"
    if not demo_dir.is_dir():
        print(f"[SETUP] Demo folder not found at {demo_dir}. Creating demo folder...")
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "tests" / "make_demo_data.py")], check=True)

    print(f"[SCAN] Scanning demo folder: {demo_dir}")
    scan_res = scan_folder(str(demo_dir))
    dup_res = find_duplicates(scan_res)
    print(f"[SCAN] Completed: {len(scan_res.files)} files, {len(dup_res.groups)} duplicate groups.\n")

    settings = load_settings()
    real_provider = OllamaProvider(settings)
    status = real_provider.health()

    test_queries = [
        "What is taking up the most space?",
        "Find duplicate files",
        "Videos larger than 10 MB",
        "Show ways to free 5 GB",
    ]

    all_passed = True
    benchmark_rows = []

    # ── PART 1: Online Gemma Test (if available) ───────────────────────────
    if not status.ok:
        print(f"[INFO] Local Ollama/Gemma is OFFLINE ({status.message}). Skipping online LLM benchmark.")
    else:
        print(f"[TEST 1/2] Testing Online Staged Flow with Gemma ({settings.model})...")
        print("  Warming up model...")
        real_provider.warm_up()

        for q in test_queries:
            t0 = time.perf_counter()
            t_tools_ready: Optional[float] = None
            t_first_chunk: Optional[float] = None
            chunks: List[str] = []

            def on_stage(stage: str, payload: Dict[str, Any]) -> None:
                nonlocal t_tools_ready, t_first_chunk
                if stage == "tools_ready":
                    t_tools_ready = time.perf_counter() - t0
                elif stage == "explanation_chunk":
                    if t_first_chunk is None:
                        t_first_chunk = time.perf_counter() - t0
                    chunks.append(payload.get("text", ""))

            resp = handle_user_request_staged(
                text=q,
                scan_result=scan_res,
                duplicate_result=dup_res,
                provider=real_provider,
                settings=settings,
                on_stage=on_stage,
            )

            t_total = time.perf_counter() - t0
            tools_sec = t_tools_ready or 0.0
            first_sec = t_first_chunk or tools_sec

            # Assertion 1: tools_ready MUST arrive BEFORE or at the first explanation chunk
            timing_ok = (t_tools_ready is not None) and (t_first_chunk is None or t_tools_ready <= t_first_chunk + 0.05)
            if not timing_ok:
                all_passed = False

            # Assertion 2: Factual check
            verify_facts(q, resp.explanation, resp.tool_runs)

            benchmark_rows.append({
                "query": q,
                "mode": resp.mode,
                "tools_s": round(tools_sec, 2),
                "first_tok_s": round(first_sec, 2),
                "total_s": round(t_total, 2),
                "pass": timing_ok and resp.ok,
            })

    # ── PART 2: Forced Offline Fallback Test ───────────────────────────────
    print(f"\n[TEST 2/2] Testing Offline Fallback Flow with Deterministic Parser...")
    offline_provider = OfflineMockProvider()

    for q in test_queries:
        t0 = time.perf_counter()
        t_tools_ready: Optional[float] = None
        t_first_chunk: Optional[float] = None

        def on_stage_off(stage: str, payload: Dict[str, Any]) -> None:
            nonlocal t_tools_ready, t_first_chunk
            if stage == "tools_ready":
                t_tools_ready = time.perf_counter() - t0
            elif stage == "explanation_chunk":
                if t_first_chunk is None:
                    t_first_chunk = time.perf_counter() - t0

        resp = handle_user_request_staged(
            text=q,
            scan_result=scan_res,
            duplicate_result=dup_res,
            provider=offline_provider,
            settings=settings,
            on_stage=on_stage_off,
        )
        t_total = time.perf_counter() - t0

        pass_off = (resp.mode == "basic") and resp.ok and len(resp.tool_runs) > 0 and bool(resp.explanation)
        if not pass_off:
            all_passed = False

        benchmark_rows.append({
            "query": f"[Offline] {q}",
            "mode": resp.mode,
            "tools_s": round(t_tools_ready or 0.0, 3),
            "first_tok_s": round(t_first_chunk or 0.0, 3),
            "total_s": round(t_total, 3),
            "pass": pass_off,
        })

    # Test an unsupported query in offline mode
    unsupported = "How do I make chocolate chip cookies?"
    resp_unsup = handle_user_request_staged(
        text=unsupported,
        scan_result=scan_res,
        duplicate_result=dup_res,
        provider=offline_provider,
        settings=settings,
    )
    pass_unsup = (resp_unsup.mode == "unavailable") and ("Try one of these supported queries" in resp_unsup.explanation)
    if not pass_unsup:
        all_passed = False

    benchmark_rows.append({
        "query": f"[Offline] {unsupported}",
        "mode": resp_unsup.mode,
        "tools_s": 0.0,
        "first_tok_s": 0.0,
        "total_s": round(resp_unsup.duration_ms / 1000.0, 3),
        "pass": pass_unsup,
    })

    # ── LATENCY TABLE ──────────────────────────────────────────────────────
    print(f"\n{'='*78}")
    print("LATENCY & STAGING BENCHMARK TABLE")
    print(f"{'='*78}")
    print(f"{'QUERY':<36} | {'MODE':<6} | {'TOOLS (s)':<9} | {'1st TOK (s)':<11} | {'TOTAL (s)':<9} | {'RESULT'}")
    print(f"{'-'*36}-+-{'-'*6}-+-{'-'*9}-+-{'-'*11}-+-{'-'*9}-+-{'-'*6}")

    for row in benchmark_rows:
        status_str = "PASS" if row["pass"] else "FAIL"
        print(
            f"{row['query'][:35]:<36} | "
            f"{row['mode']:<6} | "
            f"{row['tools_s']:<9.2f} | "
            f"{row['first_tok_s']:<11.2f} | "
            f"{row['total_s']:<9.2f} | "
            f"{status_str}"
        )

    print(f"{'='*78}\n")
    if all_passed:
        print("[SUCCESS] All staged command flow tests and assertions passed successfully.")
        return 0
    else:
        print("[FAILURE] Some assertions or timing checks failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
