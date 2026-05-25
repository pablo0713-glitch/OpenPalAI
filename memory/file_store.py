from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import aiofiles

from memory.base import AbstractMemoryStore
from memory.schemas import ConversationFile, FactsFile
from memory.session_index import SessionIndex
from memory.vector_store import VectorMemoryStore


class FileMemoryStore(AbstractMemoryStore):
    """Phase 1 memory: JSON files on disk, one per user/channel pair."""

    def __init__(
        self,
        memory_dir: str,
        max_history: int,
        session_index: SessionIndex | None = None,
        vector_store: VectorMemoryStore | None = None,
    ) -> None:
        self._memory_dir = memory_dir
        self._max_history = max_history
        self._session_index = session_index
        self._vector_store = vector_store
        # Per-(user_id, channel_id) locks to prevent write races
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    # ------------------------------------------------------------------ paths

    def _conv_path(self, user_id: str, channel_id: str) -> str:
        user_dir = os.path.join(self._memory_dir, _safe(user_id))
        os.makedirs(user_dir, exist_ok=True)
        return os.path.join(user_dir, f"{_safe(channel_id)}.json")

    def _facts_path(self, user_id: str) -> str:
        user_dir = os.path.join(self._memory_dir, _safe(user_id))
        os.makedirs(user_dir, exist_ok=True)
        return os.path.join(user_dir, "_facts.json")

    def _lock(self, user_id: str, channel_id: str) -> asyncio.Lock:
        key = (user_id, channel_id)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    # -------------------------------------------------------------- history

    async def get_history(self, user_id: str, channel_id: str) -> list[dict[str, Any]]:
        path = self._conv_path(user_id, channel_id)
        data = await _read_json(path)
        if data is None:
            return []
        cf = ConversationFile.model_validate(data)
        return _sanitize_tool_pairs(cf.turns)

    async def append_turn(
        self,
        user_id: str,
        channel_id: str,
        platform: str,
        role: str,
        content: str | list[Any],
        display_name: str = "",
        *,
        person_id: str = "",
    ) -> None:
        async with self._lock(user_id, channel_id):
            path = self._conv_path(user_id, channel_id)
            data = await _read_json(path)
            if data is None:
                cf = ConversationFile(
                    user_id=user_id, channel_id=channel_id, platform=platform
                )
            else:
                cf = ConversationFile.model_validate(data)

            cf.turns.append({"role": role, "content": _serialize_content(content)})
            cf.updated_at = _now()

            if len(cf.turns) > self._max_history:
                cf.turns = _sanitize_tool_pairs(cf.turns[-self._max_history :])

            await _write_json(path, _cf_to_dict(cf))

        if self._session_index is not None:
            text = content if isinstance(content, str) else _text_from_content(content)
            if text:
                asyncio.create_task(
                    self._index_and_vectorize(
                        user_id, channel_id, platform, role, text, display_name,
                        person_id=person_id,
                    )
                )

    async def _index_and_vectorize(
        self,
        user_id: str,
        channel_id: str,
        platform: str,
        role: str,
        text: str,
        display_name: str,
        *,
        person_id: str = "",
    ) -> None:
        """Fire-and-forget: index in FTS5 and (if available) ChromaDB."""
        session_id = await self._session_index.index_turn(
            user_id, channel_id, platform, role, text, _now(), display_name
        )
        if self._vector_store is not None and session_id is not None and person_id:
            metadata = {
                "user_id": user_id,
                "channel_id": channel_id,
                "platform": platform,
                "role": role,
                "timestamp": _now(),
                "display_name": display_name,
                "importance": -1.0,
            }
            await self._vector_store.add_turn(person_id, session_id, text, metadata)

    async def trim_history(self, user_id: str, channel_id: str, max_turns: int) -> None:
        async with self._lock(user_id, channel_id):
            path = self._conv_path(user_id, channel_id)
            data = await _read_json(path)
            if data is None:
                return
            cf = ConversationFile.model_validate(data)
            if len(cf.turns) > max_turns:
                cf.turns = _sanitize_tool_pairs(cf.turns[-max_turns:])
                cf.updated_at = _now()
                await _write_json(path, _cf_to_dict(cf))

    # --------------------------------------------------------------- facts

    async def get_facts(self, user_id: str) -> dict[str, str]:
        path = self._facts_path(user_id)
        data = await _read_json(path)
        if data is None:
            return {}
        return FactsFile.model_validate(data).facts

    async def get_all_conversations(self, user_id: str) -> list:
        """Return all ConversationFile objects for a user_id (all channels)."""
        user_dir = os.path.join(self._memory_dir, _safe(user_id))
        if not os.path.exists(user_dir):
            return []
        result = []
        for filename in os.listdir(user_dir):
            if filename.endswith(".json") and not filename.startswith("_"):
                data = await _read_json(os.path.join(user_dir, filename))
                if data:
                    try:
                        result.append(ConversationFile.model_validate(data))
                    except Exception:
                        pass
        return result

    async def upsert_fact(self, user_id: str, key: str, value: str) -> None:
        # Use a channel-keyed lock scoped to facts
        async with self._lock(user_id, "_facts"):
            path = self._facts_path(user_id)
            data = await _read_json(path)
            ff = FactsFile.model_validate(data) if data else FactsFile(user_id=user_id)
            ff.facts[key] = value
            ff.updated_at = _now()
            await _write_json(path, ff.model_dump())


# ----------------------------------------------------------------------- utils

def _safe(name: str) -> str:
    """Sanitize a string for use as a filename component."""
    return name.replace("/", "_").replace("\\", "_").replace(":", "_")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _read_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        return json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return None


def _text_from_content(content: Any) -> str:
    """Extract a plain-text string from a content block list for indexing."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif hasattr(item, "type") and str(item.type) == "text":
                parts.append(getattr(item, "text", ""))
        return " ".join(p for p in parts if p)
    return ""


def _serialize_content(content: Any) -> Any:
    """Convert Anthropic SDK content blocks to plain JSON-serializable dicts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        result = []
        for item in content:
            if isinstance(item, dict):
                result.append(item)
            elif hasattr(item, "type"):
                # Anthropic SDK objects — extract fields directly to avoid Pydantic serialization
                d: dict[str, Any] = {"type": str(item.type)}
                for attr in ("text", "id", "name", "input", "content", "tool_use_id"):
                    val = getattr(item, attr, None)
                    if val is not None:
                        d[attr] = val
                result.append(d)
            else:
                result.append(str(item))
        return result
    return content


def _cf_to_dict(cf) -> dict:
    """Build a plain dict from ConversationFile without going through Pydantic serialization."""
    return {
        "schema_version": cf.schema_version,
        "user_id": cf.user_id,
        "channel_id": cf.channel_id,
        "platform": cf.platform,
        "created_at": cf.created_at,
        "updated_at": cf.updated_at,
        "turns": cf.turns,
    }


async def _write_json(path: str, data: dict) -> None:
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, indent=2, ensure_ascii=False))


def _sanitize_tool_pairs(turns: list[dict]) -> list[dict]:
    """Drop orphaned tool_result / tool_use blocks left by history trimming.

    History trim is a naive tail-slice that can cut an assistant tool_use turn
    without removing the following user tool_result turn, producing a 400 from
    the Anthropic API ("unexpected tool_use_id in tool_result blocks").

    Pass 1 — drop tool_result blocks whose tool_use_id has no matching tool_use
              in the immediately preceding assistant turn.
    Pass 2 — drop tool_use blocks from assistant turns that have no matching
              tool_result in the immediately following user turn (can occur when
              pass 1 empties that user turn and drops it entirely).
    """
    # Drop empty-content turns — they are invalid API messages and confuse the model.
    turns = [t for t in turns if t.get("content")]

    if len(turns) < 2:
        return turns

    # Pass 1
    p1: list[dict] = []
    for turn in turns:
        content = turn.get("content")
        if turn.get("role") == "user" and isinstance(content, list):
            valid_ids: set[str] = set()
            if p1 and p1[-1].get("role") == "assistant":
                prev = p1[-1].get("content", [])
                if isinstance(prev, list):
                    valid_ids = {
                        b["id"] for b in prev
                        if isinstance(b, dict) and b.get("type") == "tool_use" and "id" in b
                    }
            filtered = [
                b for b in content
                if not (
                    isinstance(b, dict)
                    and b.get("type") == "tool_result"
                    and b.get("tool_use_id") not in valid_ids
                )
            ]
            if not filtered:
                continue
            p1.append({**turn, "content": filtered})
        else:
            p1.append(turn)

    # Pass 2
    final: list[dict] = []
    for i, turn in enumerate(p1):
        content = turn.get("content")
        if turn.get("role") == "assistant" and isinstance(content, list):
            tool_use_ids = {
                b["id"] for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use" and "id" in b
            }
            if tool_use_ids:
                nxt = p1[i + 1].get("content", []) if i + 1 < len(p1) else []
                served = {
                    b.get("tool_use_id")
                    for b in (nxt if isinstance(nxt, list) else [])
                    if isinstance(b, dict) and b.get("type") == "tool_result"
                }
                orphaned = tool_use_ids - served
                if orphaned:
                    filtered = [
                        b for b in content
                        if not (isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") in orphaned)
                    ]
                    if not filtered:
                        continue
                    final.append({**turn, "content": filtered})
                    continue
        final.append(turn)

    return final
