"""
gemma/provider.py
=================
Abstract interface and data models for Gemma LLM providers.
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProviderStatus:
    """Status report from provider health check."""
    ok: bool
    message: str
    model: str
    models_available: List[str] = field(default_factory=list)
    latency_ms: Optional[float] = None


@dataclass
class ToolCall:
    """A tool call requested by the model."""
    name: str
    arguments: Dict[str, Any]


@dataclass
class ProviderReply:
    """Response returned from model invocation."""
    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    raw_model: str = ""
    duration_ms: float = 0.0
    error: Optional[str] = None


class GemmaProvider(ABC):
    """Abstract base class for local Gemma LLM providers."""
    name: str = "base"
    is_local: bool = True

    @abstractmethod
    def health(self) -> ProviderStatus:
        """Check provider reachability, latency, and available models."""
        ...

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> ProviderReply:
        """Send chat messages and optional tool schemas to the model."""
        ...

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
        cancel_token: Optional[Any] = None,
    ):
        """Yield text tokens/chunks as they stream from the model."""
        reply = self.chat(messages, tools=None, options=options)
        if reply.text:
            yield reply.text

    def warm_up(self) -> bool:
        """Lightweight warmup request to load model weights into VRAM."""
        return self.health().ok
