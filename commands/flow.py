"""
commands/flow.py
================
Execution flow coordinating routing, tool execution, and streaming explanation.
Guarantees event order: routed -> tool_result -> explain_chunk* -> explain_done.
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterator, List, Optional

from commands.basic_parser import ParsedCommand, parse_basic
from commands.events import FlowEvent
from commands.explain_basic import explain_basic
from commands.tools import TOOL_SCHEMAS, execute_tool, validate_tool_call
from engine.drives import DriveInfo
from engine.duplicates import DuplicateResult
from engine.models import ScanResult
from gemma.prompts import ROUTER_SYSTEM, build_explain_messages

log = logging.getLogger(__name__)

OFFLINE_HELP_NOTICE = (
    "I didn't recognize that command. Try asking:\n"
    "• What is taking the most space?\n"
    "• Show my 10 largest files\n"
    "• Find duplicate files\n"
    "• Files older than 1 year\n"
    "• I need 5 GB free\n"
    "• Category breakdown"
)


@dataclass
class CommandContext:
    scan: Optional[ScanResult] = None
    duplicates: Optional[DuplicateResult] = None
    drives: Optional[List[DriveInfo]] = None


def run_command(
    text: str,
    ctx: CommandContext,
    provider: Any,
    cancel: threading.Event | None = None,
) -> Iterator[FlowEvent]:
    """
    Execute user request following the strict event sequence:
    routed -> tool_result -> explain_chunk* -> explain_done.

    Parameters
    ----------
    text: User query string
    ctx: Active CommandContext (scan, duplicates, drives)
    provider: GemmaProvider instance or None
    cancel: Cancellation event
    """
    t_start = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - t_start) * 1000)

    if cancel and cancel.is_set():
        yield FlowEvent(kind="notice", text="Operation cancelled.", elapsed_ms=elapsed())
        return

    # Check for destructive commands first
    destructive_terms = ["delete", "remove", "clean", "wipe", "erase", "trash", "unlink", "rm", "format"]
    if any(term in text.lower() for term in destructive_terms):
        yield FlowEvent(
            kind="notice",
            text="OmniStore never deletes, moves, or wipes files from chat. "
                 "To review and remove files safely into your Recycle Bin, click 'Review in Cleanup' below.",
            elapsed_ms=elapsed(),
        )
        return

    tool_name: Optional[str] = None
    tool_args: dict[str, Any] = {}
    routed_by = "basic"
    provider_online = False

    # 1. Routing Phase
    if provider is not None:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            # 6 s timeout for Gemma routing
            def _ask_gemma_router():
                messages = [
                    {"role": "system", "content": ROUTER_SYSTEM},
                    {"role": "user", "content": text},
                ]
                return provider.chat(
                    messages,
                    tools=TOOL_SCHEMAS,
                    options={"num_ctx": 1024, "num_predict": 60},
                )

            future = executor.submit(_ask_gemma_router)
            reply = future.result(timeout=6.0)

            if reply and reply.tool_calls:
                tc = reply.tool_calls[0]
                ok, cleaned_args, _ = validate_tool_call(tc.name, tc.arguments)
                if ok:
                    tool_name = tc.name
                    tool_args = cleaned_args
                    routed_by = "gemma"
                    provider_online = True
            elif reply and not reply.error:
                provider_online = True
        except concurrent.futures.TimeoutError:
            log.warning("Gemma routing timed out after 6 s, falling back to basic parser")
        except Exception as exc:
            log.warning("Gemma routing failed (%s), falling back to basic parser", exc)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    # Fallback to basic parser if Gemma didn't route
    if tool_name is None:
        basic_cmd: Optional[ParsedCommand] = parse_basic(text)
        if basic_cmd is not None:
            tool_name = basic_cmd.tool
            tool_args = basic_cmd.args
            routed_by = "basic"

    # If both failed: emit notice with help
    if tool_name is None:
        yield FlowEvent(kind="notice", text=OFFLINE_HELP_NOTICE, elapsed_ms=elapsed())
        return

    # Emit routed event
    yield FlowEvent(
        kind="routed",
        data={"tool": tool_name, "args": tool_args, "routed_by": routed_by},
        elapsed_ms=elapsed(),
    )

    if cancel and cancel.is_set():
        return

    # Check scan requirement
    if ctx.scan is None:
        yield FlowEvent(
            kind="notice",
            text="No folder has been scanned yet. Please scan a folder in the Analyzer tab first.",
            elapsed_ms=elapsed(),
        )
        return

    # 2. Tool Result Phase
    tool_res = execute_tool(tool_name, tool_args, ctx.scan, ctx.duplicates)
    if not tool_res.ok:
        yield FlowEvent(
            kind="error",
            text=tool_res.error or "Tool execution failed.",
            elapsed_ms=elapsed(),
        )
        return

    yield FlowEvent(
        kind="tool_result",
        data=tool_res.data,
        elapsed_ms=elapsed(),
    )

    if cancel and cancel.is_set():
        return

    # 3. Explanation Phase
    explain_source = "basic"
    chunks_emitted = 0

    if provider_online and provider is not None:
        try:
            summary_payload = tool_res.summary if tool_res.summary else tool_res.data
            messages = build_explain_messages(text, tool_name, summary_payload)
            stream_start = time.perf_counter()

            for chunk in provider.chat_stream(
                messages,
                max_tokens=200,
                cancel=cancel,
                options={"num_ctx": 2048},
            ):
                if cancel and cancel.is_set():
                    break
                # Hard stop after 20 s total since flow start
                if (time.perf_counter() - stream_start) > 20.0 or (time.perf_counter() - t_start) > 25.0:
                    yield FlowEvent(
                        kind="notice",
                        text="Explanation timed out, results above are complete.",
                        elapsed_ms=elapsed(),
                    )
                    break
                if chunk:
                    chunks_emitted += 1
                    yield FlowEvent(kind="explain_chunk", text=chunk, elapsed_ms=elapsed())

            if chunks_emitted > 0:
                explain_source = "gemma"
        except Exception as exc:
            log.warning("Gemma explanation streaming failed: %s", exc)

    # If Gemma was offline or failed to stream explanation chunks, use explain_basic
    if chunks_emitted == 0:
        explain_source = "basic"
        for chunk in explain_basic(tool_name, tool_res.data):
            if cancel and cancel.is_set():
                break
            yield FlowEvent(kind="explain_chunk", text=chunk, elapsed_ms=elapsed())

    # 4. Final explain_done event
    yield FlowEvent(kind="explain_done", source=explain_source, elapsed_ms=elapsed())
