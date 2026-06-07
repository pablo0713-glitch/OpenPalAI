from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import aiofiles

from memory.file_store import _safe


class LocationStore:
    """
    Persists a running log of every distinct region/parcel OpenPalAI has visited
    in Second Life, stored at {memory_dir}/{safe(user_id)}/locations.json.

    Arrival logic
    ─────────────
    A visit is "new" when the region OR parcel name differs from the most recent
    entry.  Returning to a known parcel updates last_visited (and parcel_desc)
    rather than duplicating the record.

    File format
    ───────────
    {
      "schema_version": 1,
      "user_id": "sl_<uuid>",
      "updated_at": "ISO8601",
      "visits": [
        {
          "_key": "<region>\\x00<parcel>",   ← internal dedup key, stripped on read
          "region":      "Violet",
          "parcel":      "Violet Infohub",
          "parcel_desc": "Old welcome area ...",
          "first_visited": "ISO8601",
          "last_visited":  "ISO8601"
        },
        ...
      ]
    }

    Entries are ordered oldest → newest so slicing [-N:] gives the most recent N.
    """

    def __init__(self, memory_dir: str) -> None:
        self._memory_dir = memory_dir
        self._locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------ public

    async def record_visit(
        self,
        user_id: str,
        region: str,
        parcel: str,
        parcel_desc: str,
    ) -> bool:
        """
        Record a location visit.
        Returns True if this is a new distinct location (a parcel or region change),
        False if it is the same parcel as the most recent entry (only a refresh).
        """
        if not region or not parcel:
            return False

        async with self._lock(user_id):
            visits = await self._load(user_id)
            now = _now()
            key = f"{region}\x00{parcel}"

            # Same as the most recent entry → just refresh timestamps/desc
            if visits and visits[-1].get("_key") == key:
                visits[-1]["last_visited"] = now
                visits[-1]["parcel_desc"] = parcel_desc
                await self._save(user_id, visits)
                return False

            # Known location but not the most recent → update and move to tail
            existing = next((v for v in visits if v.get("_key") == key), None)
            if existing:
                existing["last_visited"] = now
                existing["parcel_desc"] = parcel_desc
                visits.remove(existing)
                visits.append(existing)
            else:
                visits.append({
                    "_key": key,
                    "region": region,
                    "parcel": parcel,
                    "parcel_desc": parcel_desc,
                    "first_visited": now,
                    "last_visited": now,
                })

            await self._save(user_id, visits)
            return True

    async def get_recent_visits(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recent `limit` visits, newest first, without the _key field."""
        visits = await self._load(user_id)
        recent = visits[-limit:][::-1]
        return [{k: v for k, v in entry.items() if k != "_key"} for entry in recent]

    # ------------------------------------------------------------------ internals

    def _path(self, user_id: str) -> str:
        user_dir = os.path.join(self._memory_dir, _safe(user_id))
        os.makedirs(user_dir, exist_ok=True)
        return os.path.join(user_dir, "locations.json")

    def _lock(self, user_id: str) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    async def _load(self, user_id: str) -> list[dict]:
        path = self._path(user_id)
        if not os.path.exists(path):
            return []
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                raw = await f.read()
            return json.loads(raw).get("visits", [])
        except (json.JSONDecodeError, OSError):
            return []

    async def _save(self, user_id: str, visits: list[dict]) -> None:
        path = self._path(user_id)
        payload = {
            "schema_version": 1,
            "user_id": user_id,
            "updated_at": _now(),
            "visits": visits,
        }
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(payload, indent=2, ensure_ascii=False))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
