"""
commands/agent.py
=================
Agent loop coordinating user requests, tool selection, deterministic execution,
and plain-English explanation via Gemma 4.

RULES:
------
1. Gemma NEVER receives raw file contents or full unvalidated paths.
2. Gemma CANNOT delete, move, copy, rename, or execute files.
3. Every fact stated in the explanation MUST come from the tool results.
4. Enforces maximum 2 tool rounds and 4 tool calls total.
5. All payloads are sanitized and logged to the AI audit log.
6. No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from commands.basic_parser import parse_basic
from commands.tools import TOOL_SCHEMAS, ToolResult, execute_tool, validate_tool_call
from engine.duplicates import DuplicateResult
from engine.models import ScanResult
from gemma.config import GemmaSettings, load_settings
from gemma.ollama_provider import OllamaProvider
from gemma.privacy import AuditLog, PayloadTooLarge, estimate_payload_bytes, sanitize_for_model
from gemma.provider import GemmaProvider, ToolCall

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are OmniStore's local storage assistant.
Your job is to help users understand disk usage, find large or old files, and inspect duplicates.

STRICT OPERATING RULES:
1. You can ONLY use the provided tools to inspect storage data.
2. NEVER invent, hallucinate, or assume any file name, size, extension, date, or folder path.
3. If a request requires actions you cannot perform (such as deleting, moving, copying, or opening files), state clearly that you are a read-only analysis assistant and point the user to the Cleanup or Duplicates tabs in OmniStore.
4. If no scan exists, advise the user to scan a folder in the Analyzer tab first.
5. Keep explanations direct, concise, and grounded 100% in the tool results returned.
"""

EXPLANATION_SYSTEM_PROMPT = """You are OmniStore's storage explainer.
Provide a clear, concise plain-English explanation of the tool results.

STRICT OPERATING RULES:
1. Limit to at most 3 short sentences or a short bullet list of at most 5 items.
2. Use human-readable sizes (the size_human fields, e.g. "150 MB", "2.4 GB") and file or folder names.
3. NEVER mention group IDs, raw byte counts, or unformatted timestamps.
4. Mention "up to" for any reclaimable or potential space.
5. State ONLY facts directly present in the tool results.
6. NEVER claim a file is safe to delete.
7. If results are empty, clearly state that no matching files were found.
"""

OFFLINE_HELP_MESSAGE = (
    "I couldn't recognize this command in offline mode.\n\n"
    "Try one of these supported queries:\n"
    "• Largest files\n"
    "• What is taking up the most space?\n"
    "• Find duplicate files\n"
    "• Videos larger than 1 GB\n"
    "• Files not opened in 6 months\n"
    "• PDFs modified last month\n"
    "• Show ways to free 5 GB\n"
    "• Scan overview"
)

StageCallback = Callable[[str, Dict[str, Any]], None]


@dataclass
class AgentResponse:
    """The complete response from the OmniStore agent."""
    ok: bool
    mode: str                          # "gemma" | "basic" | "unavailable"
    tool_runs: List[ToolResult] = field(default_factory=list)
    explanation: str = ""
    error: Optional[str] = None
    payload_bytes_sent: int = 0
    duration_ms: float = 0.0


def _build_deterministic_explanation(tools: List[ToolResult]) -> str:
    """Generate a clean, factual explanation without an LLM."""
    parts: List[str] = []
    for r in tools:
        if not r.ok:
            parts.append(f"Tool {r.name} error: {r.error}")
            continue
        data = r.data or {}
        summary = r.summary or {}
        if r.name == "get_scan_overview":
            files_count = data.get("total_files", 0)
            sz = summary.get("total_size_human") or f"{data.get('total_bytes', 0):,} bytes"
            parts.append(f"Scan overview: {files_count} files totaling {sz}.")
        elif r.name == "get_duplicate_summary":
            groups = data.get("total_groups", 0)
            dup_files = data.get("total_duplicate_files", 0)
            rec = summary.get("reclaimable_human") or f"{data.get('total_reclaimable_bytes', 0):,} bytes"
            if groups == 0:
                parts.append("No duplicate files found.")
            else:
                parts.append(f"Found {groups} duplicate groups ({dup_files} files) with up to {rec} reclaimable space.")
        elif r.name in ("find_largest_files", "filter_files"):
            items = data.get("items", [])
            if not items:
                parts.append("No matching files found.")
            else:
                tot_sz = summary.get("total_size_human") or f"{summary.get('total_bytes', 0):,} bytes"
                top_items = items[:3]
                names = [f"{it.get('name', '')} ({it.get('size_human', '')})" for it in top_items]
                parts.append(f"Found {len(items)} matching files totaling {tot_sz}. Top files: {', '.join(names)}.")
        elif r.name == "get_largest_folders":
            folders = data.get("folders", [])
            if not folders:
                parts.append("No folders found.")
            else:
                top_f = [f"{f.get('name', f.get('folder', ''))} ({f.get('size_human', '')})" for f in folders[:3]]
                parts.append(f"Largest folders: {', '.join(top_f)}.")
        elif r.name == "get_category_breakdown":
            categories = data.get("categories", [])
            top_c = [f"{c.get('category', '')} ({c.get('size_human', '')})" for c in categories[:3]]
            parts.append(f"Storage breakdown by category: {', '.join(top_c)}.")
        elif r.name == "suggest_free_space":
            candidates = data.get("candidates", [])
            cum_h = data.get("cumulative_human", "")
            target_gb = summary.get("target_gb", "")
            if not candidates:
                parts.append("No candidates found to free space.")
            else:
                reached_txt = "Target can be reached." if data.get("target_reached") else "Target not fully reached."
                parts.append(
                    f"Found {len(candidates)} review candidates offering up to {cum_h} of potential space "
                    f"for target {target_gb} GB. {reached_txt}"
                )
    return " ".join(parts) if parts else "No matching results found."


def handle_user_request_staged(
    text: str,
    scan_result: Optional[ScanResult],
    duplicate_result: Optional[DuplicateResult] = None,
    provider: Optional[GemmaProvider] = None,
    settings: Optional[GemmaSettings] = None,
    on_stage: Optional[StageCallback] = None,
    cancel_token: Optional[Callable[[], bool]] = None,
) -> AgentResponse:
    """
    Executes user request in stages:
    1. on_stage("interpreting", {})
    2. Intent resolution via Gemma OR fast_mode rule-based basic_parser
    3. Deterministic tool execution on scan_result
    4. on_stage("tools_ready", {"tool_runs": list[ToolResult], "mode": "gemma" | "basic"})
    5. Explanation generation via provider.chat_stream:
       - on_stage("explanation_chunk", {"text": chunk}) for each token/chunk
    6. on_stage("done", {"response": AgentResponse})
    Returns AgentResponse.
    """
    t_start = time.perf_counter()

    def _emit(stage: str, payload: Dict[str, Any]) -> None:
        if on_stage:
            try:
                on_stage(stage, payload)
            except Exception as e:
                log.warning("on_stage callback error: %s", e)

    # 1. Active scan guard
    if scan_result is None:
        res = AgentResponse(
            ok=True,
            mode="unavailable",
            tool_runs=[],
            explanation="No folder has been scanned yet. Please select and scan a folder in the Analyzer tab first.",
            duration_ms=round((time.perf_counter() - t_start) * 1000.0, 1),
        )
        _emit("done", {"response": res})
        return res

    _emit("interpreting", {})

    if cancel_token and cancel_token():
        res = AgentResponse(ok=False, mode="unavailable", error="Cancelled by user")
        _emit("done", {"response": res})
        return res

    cfg = settings or load_settings()
    llm = provider or OllamaProvider(cfg)
    status = llm.health()

    mode = "gemma"
    tool_calls: List[ToolCall] = []
    direct_reply_text: Optional[str] = None

    # Step A: Intent resolution
    if cfg.fast_mode:
        basic_calls = parse_basic(text)
        if basic_calls:
            tool_calls = basic_calls
            mode = "basic"
        elif status.ok and cfg.enabled:
            # Fall back to Gemma
            pass
        else:
            # Cannot parse and Gemma unavailable
            res = AgentResponse(
                ok=True,
                mode="unavailable",
                tool_runs=[],
                explanation=OFFLINE_HELP_MESSAGE,
                duration_ms=round((time.perf_counter() - t_start) * 1000.0, 1),
            )
            _emit("done", {"response": res})
            return res

    if not tool_calls and (not status.ok or not cfg.enabled):
        # Gemma is offline/disabled; try basic parser
        basic_calls = parse_basic(text)
        if basic_calls:
            tool_calls = basic_calls
            mode = "basic"
        else:
            res = AgentResponse(
                ok=True,
                mode="unavailable",
                tool_runs=[],
                explanation=OFFLINE_HELP_MESSAGE,
                error=status.message if not status.ok else "Gemma disabled",
                duration_ms=round((time.perf_counter() - t_start) * 1000.0, 1),
            )
            _emit("done", {"response": res})
            return res

    if not tool_calls and status.ok and cfg.enabled:
        # Ask Gemma to identify intent via tool schemas
        folder_name = scan_result.root_path.rstrip("\\/").split("\\")[-1] or scan_result.root_path
        sys_msg = (
            f"{SYSTEM_PROMPT}\n\nCURRENT CONTEXT:\n"
            f"An active scan is currently loaded for folder '{folder_name}' with {scan_result.total_files} files "
            f"({scan_result.total_bytes} bytes). Always call the appropriate tool to answer user storage queries."
        )
        prompt_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": text},
        ]
        first_reply = llm.chat(prompt_messages, tools=TOOL_SCHEMAS)
        if first_reply.error or (not first_reply.tool_calls and not first_reply.text):
            # Gemma errored; fallback to basic parser
            basic_calls = parse_basic(text)
            if basic_calls:
                tool_calls = basic_calls
                mode = "basic"
            else:
                res = AgentResponse(
                    ok=True,
                    mode="unavailable",
                    tool_runs=[],
                    explanation=OFFLINE_HELP_MESSAGE,
                    error=first_reply.error,
                    duration_ms=round((time.perf_counter() - t_start) * 1000.0, 1),
                )
                _emit("done", {"response": res})
                return res
        elif first_reply.tool_calls:
            tool_calls = first_reply.tool_calls
            mode = "gemma"
        else:
            # Gemma responded with conversational text and no tool calls
            direct_reply_text = first_reply.text.strip()
            mode = "gemma"

    # Step B: Direct conversational reply with no tool calls
    if direct_reply_text is not None:
        _emit("tools_ready", {"tool_runs": [], "mode": mode})
        _emit("explanation_chunk", {"text": direct_reply_text})
        duration = (time.perf_counter() - t_start) * 1000.0
        res = AgentResponse(
            ok=True,
            mode=mode,
            tool_runs=[],
            explanation=direct_reply_text,
            duration_ms=round(duration, 1),
        )
        _emit("done", {"response": res})
        return res

    # Step C: Execute tool calls (limits: max 2 rounds, max 4 calls)
    MAX_TOTAL_CALLS = 4
    executed_tools: List[ToolResult] = []
    tool_names_invoked: List[str] = []
    total_payload_bytes = 0

    for i, tc in enumerate(tool_calls[:MAX_TOTAL_CALLS]):
        if cancel_token and cancel_token():
            break
        tool_names_invoked.append(tc.name)
        valid_ok, cleaned_args, val_err = validate_tool_call(tc.name, tc.arguments)
        if not valid_ok:
            res_item = ToolResult(
                name=tc.name,
                ok=False,
                data={},
                summary={},
                error=val_err or "Invalid tool arguments.",
            )
        else:
            res_item = execute_tool(tc.name, cleaned_args, scan_result, duplicate_result)

        executed_tools.append(res_item)

        # Estimate payload size for audit logging
        try:
            sanitized = sanitize_for_model(res_item.summary if res_item.ok else {"error": res_item.error})
        except PayloadTooLarge:
            compressed = dict(res_item.summary)
            if "top_10" in compressed:
                compressed["top_10"] = compressed["top_10"][:3]
            sanitized = sanitize_for_model(compressed)
        total_payload_bytes += estimate_payload_bytes(sanitized)

    # IMMEDIATELY emit tools_ready so UI can render table / charts
    _emit("tools_ready", {"tool_runs": executed_tools, "mode": mode})

    if cancel_token and cancel_token():
        res = AgentResponse(
            ok=True,
            mode=mode,
            tool_runs=executed_tools,
            explanation="Operation cancelled.",
            duration_ms=round((time.perf_counter() - t_start) * 1000.0, 1),
        )
        _emit("done", {"response": res})
        return res

    # Step D: Explanation generation
    explanation = ""
    # If Gemma is online, attempt streaming explanation
    if status.ok and cfg.enabled:
        folder_name = scan_result.root_path.rstrip("\\/").split("\\")[-1] or scan_result.root_path
        expl_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
            {"role": "user", "content": text},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for i, tc in enumerate(tool_calls[:MAX_TOTAL_CALLS])
                ],
            },
        ]
        for res_item in executed_tools:
            try:
                sanitized_sum = sanitize_for_model(res_item.summary if res_item.ok else {"error": res_item.error})
            except PayloadTooLarge:
                sanitized_sum = {"summary": "Results found"}
            expl_messages.append({
                "role": "tool",
                "name": res_item.name,
                "content": json.dumps(sanitized_sum),
            })

        expl_messages.append({
            "role": "user",
            "content": f"Summarize the tool results answering my query: '{text}'",
        })

        chunks: List[str] = []
        try:
            for chunk in llm.chat_stream(
                expl_messages,
                options={"num_predict": 220},
                cancel_token=cancel_token,
            ):
                chunks.append(chunk)
                _emit("explanation_chunk", {"text": chunk})
            explanation = "".join(chunks).strip()
        except Exception as exc:
            log.warning("Streaming explanation error: %s", exc)

    # Fallback to deterministic explanation if Gemma did not provide one
    if not explanation:
        explanation = _build_deterministic_explanation(executed_tools)
        _emit("explanation_chunk", {"text": explanation})

    # Step E: AI Audit Log
    AuditLog.append(
        model=cfg.model if mode == "gemma" else "basic_parser",
        tool_names=tool_names_invoked,
        payload_bytes=total_payload_bytes,
        sanitized_payload=[
            {"tool": r.name, "ok": r.ok, "summary": r.summary}
            for r in executed_tools
        ],
        duration_ms=(time.perf_counter() - t_start) * 1000.0,
    )

    duration = (time.perf_counter() - t_start) * 1000.0
    final_response = AgentResponse(
        ok=True,
        mode=mode,
        tool_runs=executed_tools,
        explanation=explanation,
        payload_bytes_sent=total_payload_bytes,
        duration_ms=round(duration, 1),
    )
    _emit("done", {"response": final_response})
    return final_response


def handle_user_request(
    text: str,
    scan_result: Optional[ScanResult],
    duplicate_result: Optional[DuplicateResult] = None,
    provider: Optional[GemmaProvider] = None,
    settings: Optional[GemmaSettings] = None,
) -> AgentResponse:
    """Wraps handle_user_request_staged for backwards compatibility."""
    return handle_user_request_staged(
        text=text,
        scan_result=scan_result,
        duplicate_result=duplicate_result,
        provider=provider,
        settings=settings,
        on_stage=None,
    )
