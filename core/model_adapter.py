from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI as _AsyncOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False


# ------------------------------------------------------------------ response types

@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ModelResponse:
    stop_reason: str                              # "end_turn" | "tool_use"
    text: str                                     # extracted text (may be empty)
    tool_calls: list[ToolCall] = field(default_factory=list)
    history_content: list = field(default_factory=list)   # Anthropic-format dicts


# ------------------------------------------------------------------ abstract base

class ModelAdapter(ABC):
    @abstractmethod
    async def create(
        self,
        *,
        system: str,
        messages: list,
        tools: list[dict],
        tool_choice: dict,
        max_tokens: int,
    ) -> ModelResponse: ...

    @abstractmethod
    async def create_simple(
        self,
        *,
        system: str,
        messages: list[dict],
        max_tokens: int,
    ) -> str:
        """No-tool call used by memory consolidation."""
        ...


# ------------------------------------------------------------------ Anthropic adapter

class AnthropicAdapter(ModelAdapter):
    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    async def create(self, *, system, messages, tools, tool_choice, max_tokens) -> ModelResponse:
        kwargs: dict = dict(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            tool_choice=tool_choice,
            messages=messages,
        )
        if isinstance(system, list):
            kwargs["extra_headers"] = {"anthropic-beta": "prompt-caching-2024-07-31"}
        response = await self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        history_content: list = []

        for block in response.content:
            btype = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)

            if btype == "text":
                text = getattr(block, "text", None) or (block.get("text", "") if isinstance(block, dict) else "")
                text_parts.append(text)
                history_content.append({"type": "text", "text": text})

            elif btype == "tool_use":
                bid   = getattr(block, "id",    None) or (block.get("id")    if isinstance(block, dict) else "")
                bname = getattr(block, "name",  None) or (block.get("name")  if isinstance(block, dict) else "")
                binput = getattr(block, "input", None) or (block.get("input", {}) if isinstance(block, dict) else {})
                tool_calls.append(ToolCall(id=bid, name=bname, input=binput))
                history_content.append({"type": "tool_use", "id": bid, "name": bname, "input": binput})

        if not text_parts and not tool_calls:
            logger.debug(
                "No text or tool_use in response.content (len=%d, stop=%s): %r",
                len(response.content), response.stop_reason, response.content,
            )

        raw_stop = response.stop_reason
        if raw_stop == "max_tokens":
            logger.warning("max_tokens hit — text=%d chars, tool_calls=%d", len("".join(text_parts)), len(tool_calls))
        stop_reason = "tool_use" if raw_stop == "tool_use" else raw_stop or "end_turn"
        return ModelResponse(
            stop_reason=stop_reason,
            text="\n".join(text_parts).strip(),
            tool_calls=tool_calls,
            history_content=history_content,
        )

    async def create_simple(self, *, system, messages, max_tokens) -> str:
        kwargs: dict = dict(model=self._model, max_tokens=max_tokens, messages=messages)
        if system:
            kwargs["system"] = system
        response = await self._client.messages.create(**kwargs)
        return response.content[0].text if response.content else ""


# ------------------------------------------------------------------ OpenAI-compatible adapter
# Handles: OpenAI, OpenRouter, Google Gemini (compat endpoint), Grok (xAI),
#          LM Studio, Ollama — any provider with an OpenAI-compatible /v1 API.

class OpenAICompatibleAdapter(ModelAdapter):
    def __init__(self, base_url: str, model: str, api_key: str = "openai") -> None:
        if not _OPENAI_AVAILABLE:
            raise ImportError("openai package required: pip install openai")
        self._model = model
        self._client = _AsyncOpenAI(base_url=base_url.rstrip("/"), api_key=api_key)

    async def create(self, *, system, messages, tools, tool_choice, max_tokens) -> ModelResponse:
        oai_messages = _to_openai_messages(_flatten_system_blocks(system), messages)
        oai_tools = _to_openai_tools(tools) if tools else None
        oai_tc = "auto" if tool_choice.get("type") == "auto" else "none"

        kwargs: dict = dict(model=self._model, messages=oai_messages, max_tokens=max_tokens)
        if oai_tools and oai_tc != "none":
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = oai_tc

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message
        finish = choice.finish_reason

        text = msg.content or ""
        tool_calls: list[ToolCall] = []
        history_content: list = []

        if text:
            history_content.append({"type": "text", "text": text})

        for tc in (msg.tool_calls or []):
            try:
                inp = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                inp = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=inp))
            history_content.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.function.name,
                "input": inp,
            })

        stop_reason = "tool_use" if (finish == "tool_calls" and tool_calls) else "end_turn"
        return ModelResponse(
            stop_reason=stop_reason,
            text=text,
            tool_calls=tool_calls,
            history_content=history_content,
        )

    async def create_simple(self, *, system, messages, max_tokens) -> str:
        oai_messages: list = []
        if system := _flatten_system_blocks(system):
            oai_messages.append({"role": "system", "content": system})
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            oai_messages.append({"role": msg["role"], "content": content})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=oai_messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""


# ------------------------------------------------------------------ conversion helpers

def _flatten_system_blocks(system: Any) -> str:
    """Flatten a list of system content blocks to a plain string (for non-Anthropic adapters)."""
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        return "\n\n".join(b.get("text", "") for b in system if isinstance(b, dict))
    return str(system) if system else ""


def _block_type(block: Any) -> str:
    if isinstance(block, dict):
        return block.get("type", "")
    return getattr(block, "type", "")


def _get_field(block: Any, field_name: str) -> Any:
    if isinstance(block, dict):
        return block.get(field_name)
    return getattr(block, field_name, None)


def _to_openai_messages(system: str, messages: list) -> list[dict]:
    result: list[dict] = [{"role": "system", "content": system}]

    for msg in messages:
        role = msg["role"] if isinstance(msg, dict) else getattr(msg, "role", "user")
        content = msg["content"] if isinstance(msg, dict) else getattr(msg, "content", "")

        if role == "user":
            if isinstance(content, str):
                result.append({"role": "user", "content": content})
            elif isinstance(content, list):
                tool_results = [b for b in content if _block_type(b) == "tool_result"]
                if tool_results:
                    for tr in tool_results:
                        result.append({
                            "role": "tool",
                            "tool_call_id": _get_field(tr, "tool_use_id") or "",
                            "content": str(_get_field(tr, "content") or ""),
                        })
                else:
                    user_parts: list[dict] = []
                    for block in content:
                        btype = _block_type(block)
                        if btype == "text":
                            text = _get_field(block, "text") or ""
                            if text:
                                user_parts.append({"type": "text", "text": text})
                        elif btype == "image":
                            source = _get_field(block, "source") or {}
                            media_type = source.get("media_type")
                            data = source.get("data")
                            if media_type and data:
                                user_parts.append({
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{media_type};base64,{data}"},
                                })

                    if not user_parts:
                        result.append({"role": "user", "content": ""})
                    elif len(user_parts) == 1 and user_parts[0]["type"] == "text":
                        result.append({"role": "user", "content": user_parts[0]["text"]})
                    else:
                        result.append({"role": "user", "content": user_parts})

        elif role == "assistant":
            if isinstance(content, str):
                result.append({"role": "assistant", "content": content})
            elif isinstance(content, list):
                text_parts: list[str] = []
                tc_list: list[dict] = []
                for block in content:
                    btype = _block_type(block)
                    if btype == "text":
                        text_parts.append(_get_field(block, "text") or "")
                    elif btype == "tool_use":
                        tc_list.append({
                            "id": _get_field(block, "id"),
                            "type": "function",
                            "function": {
                                "name": _get_field(block, "name"),
                                "arguments": json.dumps(_get_field(block, "input") or {}),
                            },
                        })
                out: dict = {"role": "assistant", "content": " ".join(text_parts) or ""}
                if tc_list:
                    out["tool_calls"] = tc_list
                result.append(out)

    return result


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


# ------------------------------------------------------------------ provider base URLs

_OPENAI_COMPAT_URLS: dict[str, str] = {
    "openai":     "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai/",
    "grok":       "https://api.x.ai/v1",
}

_LOCAL_PROVIDER_DEFAULTS: dict[str, str] = {
    "ollama":    "http://localhost:11434/v1",
    "lm_studio": "http://localhost:1234/v1",
}


# ------------------------------------------------------------------ factory

def create_adapter(settings: Any) -> ModelAdapter:
    provider = settings.model_provider

    if provider in _OPENAI_COMPAT_URLS:
        return OpenAICompatibleAdapter(
            base_url=_OPENAI_COMPAT_URLS[provider],
            model=settings.openai_model,
            api_key=settings.openai_api_key or "no-key",
        )

    if provider in _LOCAL_PROVIDER_DEFAULTS:
        base_url = settings.openai_base_url or _LOCAL_PROVIDER_DEFAULTS[provider]
        model = settings.ollama_model if provider == "ollama" else settings.openai_model
        return OpenAICompatibleAdapter(
            base_url=base_url,
            model=model,
            api_key="no-key",
        )

    # Default: Anthropic
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return AnthropicAdapter(client=client, model=settings.claude_model)
