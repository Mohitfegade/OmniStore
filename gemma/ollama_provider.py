"""
gemma/ollama_provider.py
========================
Ollama HTTP provider implementation for local Gemma models.

Endpoints:
- GET  /api/tags   -- Health check and model discovery
- POST /api/chat   -- Non-streaming chat and function-calling inference

SAFETY & PRIVACY:
- Only localhost/127.0.0.1 is permitted.
- Does not stream or expose raw sockets.
- Handles connection refusal, timeouts, missing models, and malformed JSON.
- No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Iterator, List, Optional

from gemma.config import GemmaSettings, validate_local_host
from gemma.privacy import AuditLog
from gemma.provider import GemmaProvider, ProviderReply, ProviderStatus, ToolCall

log = logging.getLogger(__name__)


class OllamaProvider(GemmaProvider):
    """Local LLM provider interfacing with an Ollama daemon."""
    name: str = "ollama"
    is_local: bool = True

    def __init__(self, settings: Optional[GemmaSettings] = None) -> None:
        self.settings = settings or GemmaSettings()
        validate_local_host(self.settings.host)

    def health(self) -> ProviderStatus:
        """
        Check if Ollama is running and whether the target model is available.
        Reports latency in milliseconds.
        """
        validate_local_host(self.settings.host)
        url = self.settings.host.rstrip("/") + "/api/tags"

        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OmniStore/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency = (time.perf_counter() - t0) * 1000.0

            models_raw = data.get("models", [])
            available: List[str] = [m.get("name", "") for m in models_raw if m.get("name")]

            target = self.settings.model.lower()
            # Check exact or prefix match (e.g. "gemma4:e2b" or "gemma4:e2b-...")
            found = any(m.lower() == target or m.lower().startswith(target) for m in available)

            if not found:
                return ProviderStatus(
                    ok=False,
                    message=f"Model '{self.settings.model}' not found in Ollama. Run: ollama pull {self.settings.model}",
                    model=self.settings.model,
                    models_available=available,
                    latency_ms=round(latency, 1),
                )

            return ProviderStatus(
                ok=True,
                message=f"Connected to Ollama ({self.settings.model})",
                model=self.settings.model,
                models_available=available,
                latency_ms=round(latency, 1),
            )

        except urllib.error.URLError as exc:
            return ProviderStatus(
                ok=False,
                message="Ollama is not running. Start Ollama and try again.",
                model=self.settings.model,
                models_available=[],
                latency_ms=None,
            )
        except Exception as exc:
            return ProviderStatus(
                ok=False,
                message=f"Ollama health check failed: {exc}",
                model=self.settings.model,
                models_available=[],
                latency_ms=None,
            )

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> ProviderReply:
        """
        Send a chat completion request to Ollama's /api/chat endpoint.
        """
        validate_local_host(self.settings.host)
        url = self.settings.host.rstrip("/") + "/api/chat"

        opts = {
            "num_ctx": self.settings.num_ctx,
            "temperature": self.settings.temperature,
        }
        if options:
            opts.update(options)

        payload: Dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": "30m",
            "options": opts,
        }
        if tools:
            payload["tools"] = tools

        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "OmniStore/1.0",
            },
            method="POST",
        )

        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.settings.timeout_s) as resp:
                raw_json = json.loads(resp.read().decode("utf-8"))
                duration = (time.perf_counter() - t0) * 1000.0

            msg = raw_json.get("message", {})
            content = msg.get("content", "") or ""
            raw_tools = msg.get("tool_calls", [])

            tool_calls: List[ToolCall] = []

            # 1. Parse native tool calls
            for tc in raw_tools:
                fn = tc.get("function", {})
                fn_name = fn.get("name")
                fn_args = fn.get("arguments", {})
                if isinstance(fn_args, str):
                    try:
                        fn_args = json.loads(fn_args)
                    except Exception:
                        fn_args = {}
                if fn_name:
                    tool_calls.append(ToolCall(name=fn_name, arguments=fn_args or {}))

            # 2. Fallback parser if model returned tool JSON in text
            if not tool_calls and content:
                fallback_calls = self._fallback_parse_tool_calls(content)
                if fallback_calls:
                    tool_calls = fallback_calls

            return ProviderReply(
                text=content,
                tool_calls=tool_calls,
                raw_model=raw_json.get("model", self.settings.model),
                duration_ms=round(duration, 1),
                error=None,
            )

        except urllib.error.HTTPError as exc:
            duration = (time.perf_counter() - t0) * 1000.0
            if exc.code == 404:
                err = f"Model '{self.settings.model}' not found in Ollama. Run: ollama pull {self.settings.model}"
            else:
                err = f"Ollama HTTP error {exc.code}: {exc.reason}"
            return ProviderReply(
                text="",
                tool_calls=[],
                raw_model=self.settings.model,
                duration_ms=round(duration, 1),
                error=err,
            )
        except urllib.error.URLError as exc:
            duration = (time.perf_counter() - t0) * 1000.0
            return ProviderReply(
                text="",
                tool_calls=[],
                raw_model=self.settings.model,
                duration_ms=round(duration, 1),
                error="Could not connect to Ollama (http://localhost:11434). Is Ollama running?",
            )
        except TimeoutError:
            duration = (time.perf_counter() - t0) * 1000.0
            return ProviderReply(
                text="",
                tool_calls=[],
                raw_model=self.settings.model,
                duration_ms=round(duration, 1),
                error=f"Ollama request timed out after {self.settings.timeout_s}s.",
            )
        except Exception as exc:
            duration = (time.perf_counter() - t0) * 1000.0
            return ProviderReply(
                text="",
                tool_calls=[],
                raw_model=self.settings.model,
                duration_ms=round(duration, 1),
                error=f"Ollama invocation error: {exc}",
            )

    @staticmethod
    def _fallback_parse_tool_calls(content: str) -> List[ToolCall]:
        """Attempt to extract tool call JSON embedded in Markdown or raw text."""
        calls: List[ToolCall] = []

        # Find code blocks ```json ... ``` or ``` ... ```
        code_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        candidates = list(code_blocks)

        # Also search for standalone JSON objects with "name" or "tool"
        for block in re.findall(r"\{[^{}]*(?:name|tool)[^{}]*\}", content):
            candidates.append(block)

        for text in candidates:
            try:
                parsed = json.loads(text.strip())
                if isinstance(parsed, dict):
                    name = parsed.get("name") or parsed.get("tool")
                    args = parsed.get("arguments") or parsed.get("parameters") or {}
                    if name and isinstance(name, str):
                        calls.append(ToolCall(name=name, arguments=args if isinstance(args, dict) else {}))
                elif isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("tool")
                            args = item.get("arguments") or item.get("parameters") or {}
                            if name and isinstance(name, str):
                                calls.append(ToolCall(name=name, arguments=args if isinstance(args, dict) else {}))
            except Exception:
                continue

        return calls

    def warm_up(self, tools: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Lightweight warmup request to load model weights and tool engine into VRAM with keep_alive='30m'."""
        validate_local_host(self.settings.host)
        url = self.settings.host.rstrip("/") + "/api/chat"
        payload: Dict[str, Any] = {
            "model": self.settings.model,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
            "think": False,
            "keep_alive": "30m",
            "options": {"num_predict": 1, "num_ctx": 1024},
        }
        if tools:
            payload["tools"] = tools
        else:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": "get_scan_overview",
                        "description": "storage overview",
                        "parameters": {"type": "object"},
                    },
                }
            ]
        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={"Content-Type": "application/json", "User-Agent": "OmniStore/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.status == 200
        except Exception as exc:
            log.warning("Ollama warm_up failed: %s", exc)
            return False

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        *,
        max_tokens: int = 200,
        cancel: Optional[threading.Event] = None,
        options: Optional[Dict[str, Any]] = None,
        cancel_token: Optional[Callable[[], bool]] = None,
    ) -> Iterator[str]:
        """
        Streaming chat yielding text chunks as they arrive from Ollama NDJSON stream.
        Passes keep_alive="30m", think=False, num_predict=max_tokens for explanation calls.
        Logs timing to AuditLog without file contents.
        """
        validate_local_host(self.settings.host)
        url = self.settings.host.rstrip("/") + "/api/chat"

        opts = {
            "num_ctx": self.settings.num_ctx,
            "temperature": self.settings.temperature,
            "num_predict": max_tokens,
        }
        if options:
            opts.update(options)

        payload: Dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "stream": True,
            "think": False,
            "keep_alive": "30m",
            "options": opts,
        }

        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "OmniStore/1.0",
            },
            method="POST",
        )

        t0 = time.perf_counter()
        first_token_ms: Optional[float] = None
        chunk_count = 0
        total_chars = 0

        try:
            with urllib.request.urlopen(req, timeout=self.settings.timeout_s) as resp:
                for raw_line in resp:
                    if (cancel and cancel.is_set()) or (cancel_token and cancel_token()):
                        log.info("chat_stream cancelled by caller")
                        break

                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue

                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        if first_token_ms is None:
                            first_token_ms = (time.perf_counter() - t0) * 1000.0
                        chunk_count += 1
                        total_chars += len(chunk)
                        yield chunk

                    if data.get("done", False):
                        break

            duration_ms = (time.perf_counter() - t0) * 1000.0
            AuditLog.append(
                model=self.settings.model,
                tool_names=["explanation_stream"],
                payload_bytes=len(body_bytes),
                sanitized_payload={"stream": True, "chunks": chunk_count, "chars": total_chars},
                duration_ms=duration_ms,
                first_token_ms=first_token_ms,
            )

        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            log.warning("chat_stream error: %s", exc)
            AuditLog.append(
                model=self.settings.model,
                tool_names=["explanation_stream"],
                payload_bytes=len(body_bytes),
                sanitized_payload={"error": str(exc)},
                duration_ms=duration_ms,
                first_token_ms=first_token_ms,
            )
            return
