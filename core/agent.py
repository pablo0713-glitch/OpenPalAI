from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import time

import aiofiles

from config.settings import Settings
from core.librarian_agent import LibrarianAgent
from core.model_adapter import ModelAdapter
from core.persona import (
    MessageContext,
    build_system_prompt_blocks,
    get_agent_config,
    get_identity_files_meta,
    get_identity_files_text,
    _get_platform_awareness,
)
from core.rate_limiter import RateLimiter
from core.tools import ToolRegistry
from memory.base import AbstractMemoryStore
from memory.library_store import LibraryStore
from memory.person_map import PersonMap
from memory.schemas import ConversationFile

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
STM_MAX_ENTRIES = 10
MEMORY_CAP = 2000
USER_CAP   = 1200


def _get_role(turn: dict) -> str:
    return turn.get("role") if isinstance(turn, dict) else getattr(turn, "role", "")


def _get_content(turn: dict):
    return turn.get("content") if isinstance(turn, dict) else getattr(turn, "content", None)


def _content_text(content: str | list[dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content

    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            text = str(block.get("text", "")).strip()
            if text:
                parts.append(text)
        elif btype == "image":
            source = block.get("source") or {}
            media_type = source.get("media_type", "image")
            parts.append(f"[Image attachment: {media_type}]")

    return "\n\n".join(parts).strip()


def _is_tool_result_turn(turn: dict) -> bool:
    content = _get_content(turn)
    return (
        _get_role(turn) == "user"
        and isinstance(content, list)
        and bool(content)
        and any(
            (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "tool_result"
            for b in content
        )
    )


def _sanitize_history(history: list) -> list:
    """Ensure history ends on an assistant turn so the model sees clean context.

    Strips two classes of tail corruption:
    1. Dangling tool-use cycle: assistant[tool_use] + user[tool_result] with no
       following assistant turn. Caused by the model returning empty mid-loop.
    2. Accumulated unresponded user messages: consecutive plain user turns saved
       when every previous response returned a fallback. These pile up and cause
       the model to keep returning empty (self-reinforcing loop).

    History should always end with an assistant turn (or be empty). The caller
    appends the new user message separately after sanitization.
    """
    if not history:
        return history

    n_before = len(history)

    # Pass 1 — strip a dangling tool-use cycle at the very tail
    if _is_tool_result_turn(history[-1]):
        history = history[:-1]
        if history and _get_role(history[-1]) == "assistant":
            history = history[:-1]

    # Pass 2 — strip any remaining plain user turns at the tail
    while history and _get_role(history[-1]) == "user" and not _is_tool_result_turn(history[-1]):
        history = history[:-1]

    # Pass 3 — ensure history starts with a user turn; a leading assistant turn
    # violates role-alternation and causes the API to return empty responses.
    while history and _get_role(history[0]) != "user":
        history = history[1:]

    if len(history) != n_before:
        logger.warning(
            "Sanitized history: %d → %d turns (stripped tail/leading role violations)",
            n_before, len(history),
        )

    return history


@dataclass
class AgentResponse:
    text: str
    sl_actions: list[dict] = field(default_factory=list)
    was_rate_limited: bool = False
    was_refused: bool = False


class AgentCore:
    def __init__(
        self,
        adapter: ModelAdapter,
        memory: AbstractMemoryStore,
        tool_registry: ToolRegistry,
        rate_limiter: RateLimiter,
        settings: Settings,
        person_map: Optional[PersonMap] = None,
        library_store: Optional[LibraryStore] = None,
    ) -> None:
        self._adapter = adapter
        self._memory = memory
        self._tools = tool_registry
        self._rate_limiter = rate_limiter
        self._settings = settings
        self._person_map = person_map
        self._library_store = library_store
        self._last_prompt: dict[str, str] = {}
        self._last_exchange: dict[str, dict] = {}

    async def handle_message(self, message: str | list[dict[str, Any]], context: MessageContext) -> AgentResponse:
        if not self._rate_limiter.check(context.user_id):
            return AgentResponse(
                text="Give me a second — you're moving fast. Try again in a moment.",
                was_rate_limited=True,
            )

        message_content = message
        message_text = _content_text(message_content)

        history = await self._memory.get_history(context.user_id, context.channel_id)
        facts = await self._memory.get_facts(context.user_id)

        memory_files = ""
        stm_bridge = ""
        if self._person_map:
            person_id = self._person_map.get_person_id(context.user_id) or context.user_id
            context.person_id = person_id
            if person_id:
                memory_files = await self._load_memory_files(person_id)
            linked_ids = self._person_map.get_linked_ids(context.user_id)
            if linked_ids:
                stm_bridge = await self._load_stm_bridge(linked_ids)
        else:
            context.person_id = context.user_id

        # Always-on library modules → uncached Block 2 (preserves Block 0 cache)
        library_context = ""
        if self._library_store:
            always_on = self._library_store.get_always_on(context.platform)
            if always_on:
                cap = getattr(self._settings, "library_always_on_cap", 4000)
                parts = []
                total = 0
                for m in always_on:
                    chunk = f"### {m.title}\n{m.content}"
                    if total + len(chunk) > cap:
                        break
                    parts.append(chunk)
                    total += len(chunk)
                if parts:
                    library_context = "## Active Library Modules\n\n" + "\n\n---\n\n".join(parts)

        system_blocks = build_system_prompt_blocks(
            context, facts, memory_files, stm_bridge, library_context
        )
        # Flatten for debug display (blocks are passed directly to the adapter)
        system_flat = "\n\n".join(b["text"] for b in system_blocks)
        self._last_prompt[context.user_id] = system_flat

        # Structured metadata for the debug "Prompt Blocks" view
        _cfg = get_agent_config()
        _pa = _get_platform_awareness(_cfg, context.platform)
        _addl = _cfg.get("additional_context", "") or ""
        _identity_meta = get_identity_files_meta()
        _prompt_sections = {
            "identity_files": _identity_meta,
            "identity_files_text": get_identity_files_text(),
            "identity_fallback": not bool(_identity_meta),
            "platform": context.platform,
            "platform_awareness_chars": len(_pa),
            "platform_awareness_text": _pa,
            "additional_context_chars": len(_addl.strip()),
            "additional_context_text": _addl.strip(),
            "memory_files_text": memory_files,
            "memory_files_chars": len(memory_files),
            "stm_bridge_text": stm_bridge,
            "stm_bridge_chars": len(stm_bridge),
            "block0_chars": len(system_blocks[0]["text"]) if system_blocks else 0,
            "block1_chars": len(system_blocks[1]["text"]) if len(system_blocks) > 1 else 0,
            "block2_chars": len(system_blocks[2]["text"]) if len(system_blocks) > 2 else 0,
            "has_block1": len(system_blocks) > 1,
            "has_block2": len(system_blocks) > 2,
            "library_context_chars": len(library_context),
        }
        messages = _sanitize_history(list(history)) + [{"role": "user", "content": message_content}]

        sl_action_queue: list[dict] = []
        try:
            reply_text, assistant_turns = await self._run_tool_loop(
                messages, system_blocks, context, sl_action_queue
            )
            self._last_exchange[context.user_id] = {
                "ts": time.time(),
                "platform": context.platform,
                "display_name": context.display_name,
                "user_message": message_text,
                "system_prompt": system_flat,
                "messages": messages,
                "reply_text": reply_text,
                "assistant_turns": assistant_turns,
                "prompt_sections": _prompt_sections,
            }
        except Exception as exc:
            logger.exception("Error in tool loop: %s", exc)
            return AgentResponse(
                text="Something went sideways on my end. Give me a moment and try again.",
            )

        if not reply_text:
            logger.warning("Empty reply_text for user %s — returning fallback", context.user_id)
            return AgentResponse(text="I lost that one — something cut me off mid-thought. Ask me again?")

        person_id = context.person_id or context.user_id

        # Save user turn only after a successful response — prevents accumulating
        # unresponded user messages in history when the model returns empty.
        await self._memory.append_turn(
            context.user_id, context.channel_id, context.platform, "user", message_content,
            context.display_name, person_id=person_id,
        )

        # Persist only the final assistant text reply. Intermediate tool_use /
        # tool_result turns and mixed text+tool_use turns are discarded — the
        # final reply already incorporates everything the tools returned. Storing
        # intermediate turns balloons context and creates consecutive same-role
        # turns that cause the model to return empty responses.
        final_reply: dict | None = None
        for turn in reversed(assistant_turns):
            if turn.get("role") != "assistant":
                continue
            content = turn.get("content")
            if not content:
                continue
            if isinstance(content, list):
                text_blocks = [
                    b for b in content
                    if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "text"
                ]
                if text_blocks:
                    final_reply = {"role": "assistant", "content": text_blocks}
                    break
            elif isinstance(content, str) and content:
                final_reply = turn
                break

        if final_reply:
            await self._memory.append_turn(
                context.user_id, context.channel_id, context.platform,
                final_reply["role"], final_reply["content"],
                person_id=person_id,
            )

        # Fire-and-forget STM entry generation
        asyncio.create_task(
            self._append_stm_entry(context.user_id, message_text, reply_text)
        )

        return AgentResponse(text=reply_text, sl_actions=sl_action_queue)

    def get_last_prompt(self, user_id: str) -> str | None:
        return self._last_prompt.get(user_id)

    def get_last_exchange(self, user_id: str) -> dict | None:
        return self._last_exchange.get(user_id)

    def all_tracked_users(self) -> list[str]:
        return list(self._last_prompt.keys())

    async def get_conversation_history(self, user_id: str, channel_id: str) -> list[dict[str, str]]:
        history = await self._memory.get_history(user_id, channel_id)
        rendered: list[dict[str, str]] = []
        for turn in history:
            role = _get_role(turn)
            if role not in {"user", "assistant"}:
                continue
            text = _content_text(_get_content(turn) or "")
            if not text:
                continue
            rendered.append({
                "role": "agent" if role == "assistant" else "user",
                "text": text,
            })
        return rendered

    async def _load_memory_files(self, person_id: str) -> str:
        """Load MEMORY.md + USER.md for person_id, formatted Hermes-style with § delimiters."""
        safe = person_id.replace("/", "_").replace(":", "_")
        mem_dir = Path(self._settings.memory_dir) / safe
        parts: list[str] = []
        for fname, cap, label in (
            ("MEMORY.md", MEMORY_CAP, "MEMORY (agent's notes)"),
            ("USER.md",   USER_CAP,   "USER (owner profile)"),
        ):
            path = mem_dir / fname
            if not path.exists():
                continue
            try:
                content = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if not content:
                continue
            # Enforce cap — trim by §-delimited entries, not raw slice
            if len(content) > cap:
                from core.tool_handlers.memory import _trim_to_cap
                content = _trim_to_cap(content, cap)
            pct = int(len(content) * 100 / cap)
            header = f"{label} [{pct}% — {len(content)}/{cap} chars]"
            parts.append(f"{header}\n{content}")
        return "\n\n".join(parts)

    async def _load_stm_bridge(self, linked_ids: list[str]) -> str:
        """Load STM entries from linked platform UIDs for cross-platform context."""
        parts: list[str] = []
        for uid in linked_ids:
            platform = uid.split("_")[0].upper()
            safe = uid.replace("/", "_").replace(":", "_")
            stm_path = Path(self._settings.memory_dir) / safe / "stm.json"
            if not stm_path.exists():
                continue
            try:
                data = json.loads(stm_path.read_text(encoding="utf-8"))
                entries = data.get("entries", [])
            except (OSError, json.JSONDecodeError):
                continue
            if not entries:
                continue
            summaries = "\n---\n".join(e.get("summary", "") for e in entries if e.get("summary"))
            if summaries:
                parts.append(f"## Recent Activity — {platform}\n{summaries}")
        if not parts:
            return ""
        return "\n\n".join(parts)

    async def _append_stm_entry(self, user_id: str, user_message: str, reply_text: str) -> None:
        """Generate a 1–2 sentence summary of this exchange and append to stm.json."""
        try:
            summary = await self._adapter.create_simple(
                system="",
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Summarize this exchange in 1–2 sentences, third person. "
                            "Focus on what was discussed or decided. Max 120 characters.\n\n"
                            f"User: {user_message}\n\nAssistant: {reply_text}"
                        ),
                    }
                ],
                max_tokens=60,
            )
            if not summary:
                return
            safe = user_id.replace("/", "_").replace(":", "_")
            stm_path = Path(self._settings.memory_dir) / safe / "stm.json"
            stm_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = json.loads(stm_path.read_text(encoding="utf-8")) if stm_path.exists() else {}
            except (OSError, json.JSONDecodeError):
                data = {}
            entries: list[dict] = data.get("entries", [])
            entries.append({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "summary": summary.strip(),
            })
            if len(entries) > STM_MAX_ENTRIES:
                entries = entries[-STM_MAX_ENTRIES:]
            stm_path.write_text(
                json.dumps({"user_id": user_id, "entries": entries}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("STM append failed for %s: %s", user_id, exc)

    async def _run_tool_loop(
        self,
        messages: list,
        system_blocks: list[dict],
        context: MessageContext,
        action_queue: list[dict],
    ) -> tuple[str, list[dict]]:
        tool_definitions = self._tools.get_definitions(context)
        accumulated_turns: list[dict] = []
        empty_retried = False

        for round_num in range(MAX_TOOL_ROUNDS + 1):
            tool_choice: dict = {"type": "none"} if round_num == MAX_TOOL_ROUNDS else {"type": "auto"}

            response = await self._adapter.create(
                system=system_blocks,
                messages=messages,
                tools=tool_definitions,
                tool_choice=tool_choice,
                max_tokens=self._settings.max_tokens,
            )

            assistant_turn = {"role": "assistant", "content": response.history_content}
            accumulated_turns.append(assistant_turn)
            messages = messages + [assistant_turn]

            if response.stop_reason in ("end_turn", "max_tokens"):
                if not response.text and not empty_retried:
                    logger.warning(
                        "Empty text at stop_reason=%s for user %s — retrying",
                        response.stop_reason, context.user_id,
                    )
                    empty_retried = True
                    accumulated_turns.pop()
                    messages = messages[:-1]
                    continue
                if not response.text:
                    logger.warning("Still empty after retry for user %s", context.user_id)
                return response.text, accumulated_turns

            if response.stop_reason == "tool_use":
                tool_results = []
                for tc in response.tool_calls:
                    result = await self._tools.dispatch(tc.name, tc.input, context, action_queue)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": result,
                    })
                tool_result_turn = {"role": "user", "content": tool_results}
                accumulated_turns.append(tool_result_turn)
                messages = messages + [tool_result_turn]
                continue

            return response.text, accumulated_turns

        return "I lost my train of thought. Try asking again.", accumulated_turns
