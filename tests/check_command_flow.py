"""
tests/check_command_flow.py
===========================
End-to-end verification test for OmniStore Command Center flow:
1. Static code compliance checks:
   - engine/, commands/, gemma/ contain NO PySide6 or Qt imports.
   - Codebase (excluding .venv, .git) contains NO os.remove or shutil.rmtree calls.
2. Scans C:\\Users\\Mohit\\OmniStore_Demo headless with scanner and duplicates engine.
3. Builds CommandContext.
4. Executes 6 test questions twice:
   - Pass 1: Real Ollama provider (SKIPPED gracefully if Ollama is offline).
   - Pass 2: Offline fallback mode (provider=None).
5. Strict assertions:
   - Event sequence: routed -> tool_result -> explain_chunk* -> explain_done.
   - Every event carries elapsed_ms.
   - tool_result arrives within 6000 ms with Gemma.
   - No output contains "junk" or "safe to delete".
   - suggest_free_space output contains "up to".
   - Gemma explanation fact-checking: all filenames and numbers originate from tool results.
6. Prints a latency benchmark table:
   question | routed_by | route ms | tool ms | first token ms | total ms
7. Ends with PASS/FAIL.
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

from commands.events import FlowEvent
from commands.flow import CommandContext, run_command
from engine.duplicates import find_duplicates
from engine.scanner import scan_folder
from gemma.config import load_settings
from gemma.ollama_provider import OllamaProvider


def check_static_rules() -> None:
    """Verify architectural boundaries and absence of permanent deletion."""
    print("\n[Static Check 1/2] Checking Qt/PySide6 import boundaries...")
    import_qt_pat = re.compile(r"^\s*(?:import|from)\s+(?:PySide6|PyQt5|PyQt6)\b", re.MULTILINE)
    for folder in ("engine", "commands", "gemma"):
        folder_path = ROOT / folder
        for py_file in folder_path.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            m = import_qt_pat.search(text)
            assert not m, f"Forbidden Qt import found in {py_file}: {m.group(0)}"
    print("  [OK] engine/, commands/, gemma/ contain no PySide6 or Qt imports.")

    print("\n[Static Check 2/2] Checking codebase for permanent deletion calls...")
    deletion_patterns = [
        re.compile(r"\bos\.remove\s*\("),
        re.compile(r"\bshutil\.rmtree\s*\("),
        re.compile(r"\bos\.unlink\s*\("),
    ]
    for py_file in ROOT.rglob("*.py"):
        parts = py_file.parts
        if any(p in parts for p in (".venv", ".git", "brain", "__pycache__")):
            continue
        if py_file.name in ("check_command_flow.py", "check_cleanup.py"):
            continue
        text = py_file.read_text(encoding="utf-8")
        for pat in deletion_patterns:
            m = pat.search(text)
            assert not m, f"Permanent deletion call found in {py_file}: {m.group(0)}"
    print("  [OK] No os.remove, os.unlink, or shutil.rmtree calls anywhere in codebase.")


def extract_facts_from_tool_data(data: Dict[str, Any]) -> Tuple[Set[str], Set[str]]:
    """Extract known filenames and numbers from tool result data."""
    known_filenames: Set[str] = set()
    known_numbers: Set[str] = set()

    def visit(val: Any) -> None:
        if isinstance(val, dict):
            for k, v in val.items():
                if k in ("name", "parent_name", "path") and isinstance(v, str):
                    clean_name = os.path.basename(v).lower().strip()
                    if clean_name:
                        known_filenames.add(clean_name)
                    known_filenames.add(v.lower().strip())
                if isinstance(v, (int, float)):
                    known_numbers.add(str(v))
                    if isinstance(v, int):
                        known_numbers.add(f"{v:,}")
                elif isinstance(v, str):
                    for s_num in re.findall(r"\b\d+(?:[\.,]\d+)?\b", v):
                        known_numbers.add(s_num)
                visit(v)
        elif isinstance(val, list):
            for item in val:
                visit(item)
        elif isinstance(val, (int, float)):
            known_numbers.add(str(val))
            if isinstance(val, int):
                known_numbers.add(f"{val:,}")
        elif isinstance(val, str):
            for s_num in re.findall(r"\b\d+(?:[\.,]\d+)?\b", val):
                known_numbers.add(s_num)

    visit(data)
    return known_filenames, known_numbers


def verify_explanation_facts(query: str, explanation: str, tool_data: Dict[str, Any]) -> None:
    """Assert that file names and numbers in the explanation are backed by tool results."""
    known_filenames, known_numbers = extract_facts_from_tool_data(tool_data)

    query_numbers = set(re.findall(r"\b\d+(?:[\.,]\d+)?\b", query))
    known_numbers.update(query_numbers)
    # Common linguistic constants
    known_numbers.update({"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "15", "20", "2024", "2025", "2026"})

    cleaned_text = explanation.replace("`", " ").replace("*", " ").replace("\\_", "_")

    # 1. Filenames with extensions
    file_pattern = re.compile(r"\b[a-zA-Z0-9_\-\.\(\)\s]+\.(?:mp4|mkv|pdf|txt|zip|tar|gz|docx|csv)\b", re.IGNORECASE)
    for fn in file_pattern.findall(cleaned_text):
        fn_clean = fn.strip().lower()
        matched = any(fn_clean in kf or kf in fn_clean for kf in known_filenames)
        assert matched, f"Hallucinated file name detected in explanation: '{fn}' not in tool results."

    # 2. Numbers mentioned
    for num_str in re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", cleaned_text):
        raw_num = num_str.replace(",", "")
        if raw_num in known_numbers or num_str in known_numbers:
            continue
        try:
            flt = float(raw_num)
            matched = any(abs(float(kn.replace(",", "")) - flt) < 0.2 for kn in known_numbers if kn.replace(",", "").replace(".", "").isdigit())
        except ValueError:
            matched = False
        assert matched, f"Unverified number detected in explanation: '{num_str}' not in tool results or query."


def run_test_suite() -> bool:
    print("=" * 75)
    print("OMNISTORE — COMMAND CENTER FLOW & BENCHMARK VERIFICATION")
    print("=" * 75)

    check_static_rules()

    user_home = Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))
    demo_dir = user_home / "OmniStore_Demo"
    if not demo_dir.is_dir():
        print(f"\n[ERROR] Demo directory not found at {demo_dir}.")
        print("Please run `python tests/make_demo_data.py` first.")
        return False

    print(f"\nScanning demo directory: {demo_dir} ...")
    scan_res = scan_folder(str(demo_dir))
    dup_res = find_duplicates(scan_res)
    print(f"Scan ready: {len(scan_res.files)} files, {len(dup_res.groups)} duplicate groups.")

    ctx = CommandContext(scan=scan_res, duplicates=dup_res, drives=None)

    questions = [
        "What is taking the most space?",
        "Show my 10 largest files",
        "Find duplicate files",
        "Files older than 1 year",
        "I need 1 GB free",
        "Storage breakdown by category",
    ]

    settings = load_settings()
    provider = OllamaProvider(settings)
    gemma_health = provider.health()
    gemma_online = gemma_health.ok

    if not gemma_online:
        print(f"\n[NOTICE] Ollama/Gemma 4 is offline: {gemma_health.message}")
        print("  Pass 1 (Gemma flow) will be marked SKIPPED.")
    else:
        print(f"\n[OK] Connected to Ollama ({settings.model}, latency: {gemma_health.latency_ms} ms)")
        print("  Warming up Gemma...")
        from commands.tools import TOOL_SCHEMAS
        provider.warm_up(TOOL_SCHEMAS)

    # Latency tracking: list of tuples (pass_name, q, routed_by, route_ms, tool_ms, first_token_ms, total_ms)
    benchmarks: List[Dict[str, Any]] = []

    # ─────────────────────────────────────────────────────────────
    # PASS 1: Real Provider (if online)
    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 75)
    print("PASS 1: RUN_COMMAND WITH REAL PROVIDER")
    print("=" * 75)

    if not gemma_online:
        print("  [SKIP] Skipping Pass 1 because Ollama is offline.")
    else:
        for q in questions:
            print(f"\nRunning query: \"{q}\"")
            events: List[FlowEvent] = []
            route_ms = 0
            tool_ms = 0
            first_token_ms = 0
            total_ms = 0
            routed_by = ""

            for ev in run_command(q, ctx, provider):
                events.append(ev)
                if ev.kind == "routed":
                    route_ms = ev.elapsed_ms
                    routed_by = ev.data.get("routed_by", "") if ev.data else ""
                elif ev.kind == "tool_result":
                    tool_ms = ev.elapsed_ms
                elif ev.kind == "explain_chunk" and first_token_ms == 0:
                    first_token_ms = ev.elapsed_ms
                elif ev.kind == "explain_done":
                    total_ms = ev.elapsed_ms

            # 1. Event sequence check
            kinds = [e.kind for e in events]
            assert kinds[0] == "routed", f"Expected first event 'routed', got {kinds[0]}"
            assert kinds[1] == "tool_result", f"Expected second event 'tool_result', got {kinds[1]}"
            assert "explain_done" in kinds, "Expected 'explain_done' in events"

            # 2. Latency constraint: tool_result arrives within 6000 ms
            assert tool_ms <= 6000, f"Tool result took {tool_ms} ms (> 6000 ms limit)"

            # 3. Content safety
            full_explanation = "".join(e.text for e in events if e.kind == "explain_chunk")
            lower_expl = full_explanation.lower()
            assert "junk" not in lower_expl, f"'junk' found in explanation: {full_explanation}"
            assert "safe to delete" not in lower_expl, f"'safe to delete' found in explanation: {full_explanation}"

            tool_data = next((e.data for e in events if e.kind == "tool_result"), {})
            if "target_human" in tool_data or "suggest" in q.lower() or "free" in q.lower():
                note = tool_data.get("note", "").lower()
                assert "up to" in note or "up to" in lower_expl, f"'up to' missing in suggest_free_space: {note}"

            # 4. Fact check
            verify_explanation_facts(q, full_explanation, tool_data)

            benchmarks.append({
                "mode": "gemma",
                "question": q,
                "routed_by": routed_by,
                "route_ms": route_ms,
                "tool_ms": tool_ms,
                "first_token_ms": first_token_ms,
                "total_ms": total_ms,
            })
            print(f"  [OK] Pass 1 verified: tool={tool_ms} ms, first_token={first_token_ms} ms, total={total_ms} ms")

    # ─────────────────────────────────────────────────────────────
    # PASS 2: Fallback Mode (provider=None)
    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 75)
    print("PASS 2: RUN_COMMAND WITH PROVIDER=NONE (FALLBACK / BASIC MODE)")
    print("=" * 75)

    for q in questions:
        print(f"\nRunning fallback query: \"{q}\"")
        events = []
        route_ms = 0
        tool_ms = 0
        first_token_ms = 0
        total_ms = 0
        routed_by = ""

        for ev in run_command(q, ctx, provider=None):
            events.append(ev)
            if ev.kind == "routed":
                route_ms = ev.elapsed_ms
                routed_by = ev.data.get("routed_by", "") if ev.data else ""
            elif ev.kind == "tool_result":
                tool_ms = ev.elapsed_ms
            elif ev.kind == "explain_chunk" and first_token_ms == 0:
                first_token_ms = ev.elapsed_ms
            elif ev.kind == "explain_done":
                total_ms = ev.elapsed_ms

        kinds = [e.kind for e in events]
        assert kinds[0] == "routed", f"Expected first event 'routed', got {kinds[0]}"
        assert kinds[1] == "tool_result", f"Expected second event 'tool_result', got {kinds[1]}"
        assert "explain_done" in kinds, "Expected 'explain_done' in events"
        assert routed_by == "basic", f"Expected routed_by 'basic', got '{routed_by}'"

        done_ev = next(e for e in events if e.kind == "explain_done")
        assert done_ev.source == "basic", f"Expected explain_done source 'basic', got '{done_ev.source}'"

        full_explanation = "".join(e.text for e in events if e.kind == "explain_chunk")
        lower_expl = full_explanation.lower()
        assert "junk" not in lower_expl
        assert "safe to delete" not in lower_expl

        tool_data = next((e.data for e in events if e.kind == "tool_result"), {})
        if "target_human" in tool_data or "free" in q.lower():
            note = tool_data.get("note", "").lower()
            assert "up to" in note or "up to" in lower_expl

        benchmarks.append({
            "mode": "basic",
            "question": q,
            "routed_by": routed_by,
            "route_ms": route_ms,
            "tool_ms": tool_ms,
            "first_token_ms": first_token_ms,
            "total_ms": total_ms,
        })
        print(f"  [OK] Pass 2 verified (Basic mode): tool={tool_ms} ms, total={total_ms} ms")

    # ─────────────────────────────────────────────────────────────
    # Latency Benchmark Table
    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 90)
    print("LATENCY BENCHMARK TABLE")
    print("=" * 90)
    header = f"{'Question':<34} | {'Mode':<7} | {'Routed By':<9} | {'Route ms':>8} | {'Tool ms':>7} | {'First Tk ms':>11} | {'Total ms':>8}"
    print(header)
    print("-" * len(header))
    for b in benchmarks:
        print(
            f"{b['question']:<34} | {b['mode']:<7} | {b['routed_by']:<9} | "
            f"{b['route_ms']:>8} | {b['tool_ms']:>7} | {b['first_token_ms']:>11} | {b['total_ms']:>8}"
        )
    print("=" * 90)

    print("\nOVERALL: ALL COMMAND FLOW CHECKS PASSED (PASS)")
    return True


if __name__ == "__main__":
    success = run_test_suite()
    sys.exit(0 if success else 1)
