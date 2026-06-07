from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import aiofiles


_CHANNEL_LABELS = {0: "local chat"}
_DEFAULT_CHANNEL_LABEL = "IM / /42"


class AvatarStore:
    """
    Global registry of SL avatars OpenPalAI has spoken with.
    Stored at {memory_dir}/known_avatars.json.

    File format
    ───────────
    {
      "schema_version": 1,
      "updated_at": "ISO8601",
      "avatars": {
        "sl_<uuid>": {
          "display_name": "Resident Name",
          "first_seen":   "ISO8601",
          "last_seen":    "ISO8601",
          "channels":     ["local chat", "IM / /42"]
        },
        ...
      }
    }
    """

    def __init__(self, memory_dir: str) -> None:
        self._path = os.path.join(memory_dir, "known_avatars.json")
        self._lock = asyncio.Lock()

    async def record_encounter(
        self,
        user_id: str,
        display_name: str,
        channel: int,
    ) -> None:
        """Upsert avatar entry; updates last_seen and merges channel label."""
        channel_label = _CHANNEL_LABELS.get(channel, _DEFAULT_CHANNEL_LABEL)
        now = _now()

        async with self._lock:
            data = await self._load()
            avatars: dict[str, Any] = data.get("avatars", {})

            entry = avatars.get(user_id)
            if entry is None:
                avatars[user_id] = {
                    "display_name": display_name,
                    "first_seen": now,
                    "last_seen": now,
                    "channels": [channel_label],
                }
            else:
                entry["display_name"] = display_name
                entry["last_seen"] = now
                if channel_label not in entry.get("channels", []):
                    entry.setdefault("channels", []).append(channel_label)

            data["avatars"] = avatars
            data["updated_at"] = now
            await self._save(data)

    def get_avatar(self, user_id: str) -> dict | None:
        """Synchronous read from cache — only valid after at least one async load."""
        return self._cache.get(user_id) if hasattr(self, "_cache") else None

    async def get_avatar_async(self, user_id: str) -> dict | None:
        data = await self._load()
        return data.get("avatars", {}).get(user_id)

    async def get_all(self) -> dict[str, Any]:
        data = await self._load()
        return data.get("avatars", {})

    # ------------------------------------------------------------------ internals

    async def _load(self) -> dict:
        if not os.path.exists(self._path):
            return {"schema_version": 1, "updated_at": _now(), "avatars": {}}
        try:
            async with aiofiles.open(self._path, "r", encoding="utf-8") as f:
                raw = await f.read()
            return json.loads(raw)
        except (json.JSONDecodeError, OSError):
            return {"schema_version": 1, "updated_at": _now(), "avatars": {}}

    async def _save(self, data: dict) -> None:
        async with aiofiles.open(self._path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
