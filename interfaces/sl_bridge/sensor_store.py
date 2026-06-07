from __future__ import annotations

import time
from typing import Any


class SensorStore:
    """
    In-memory cache of the latest sensor snapshots from OpenPalAI's HUD.
    Keyed by region name — sensor data describes the environment, not the user.

    Sensor types and their storage behaviour:
      avatars      → latest snapshot (list of {name, distance})
      environment  → latest snapshot ({region, parcel, time_of_day, ...})
      objects      → latest snapshot (list of {name, distance, scripted})
      clothing     → latest scan result ({target, items: [...]})
      chat         → rolling list of notable events (last max_chat_events entries)

    Each type also records an updated_at Unix timestamp so the agent can reason
    about data freshness without being told how the pipeline works.
    """

    def __init__(self, max_chat_events: int = 30) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._updated_at: dict[str, dict[str, float]] = {}
        self._last_sent: dict[str, dict[str, float]] = {}  # "{region}:{user_id}" → {stype: timestamp}
        self._max_chat = max_chat_events

    def update(self, region: str, sensor_type: str, data: Any) -> None:
        if region not in self._store:
            self._store[region] = {}
            self._updated_at[region] = {}
        if sensor_type == "chat":
            # data is either a single event dict or a list of strings (bulk flush from HUD)
            events: list = self._store[region].get("chat", [])
            if isinstance(data, list):
                events.extend(data)
            else:
                events.append(data)
            if len(events) > self._max_chat:
                events = events[-self._max_chat:]
            self._store[region]["chat"] = events
        else:
            self._store[region][sensor_type] = data
        self._updated_at[region][sensor_type] = time.monotonic()

    def get_snapshot(self, region: str) -> dict[str, Any]:
        """Return a copy of all sensor data plus per-type age in seconds."""
        snap = dict(self._store.get(region, {}))
        ages = self._updated_at.get(region, {})
        now = time.monotonic()
        snap["_ages"] = {k: int(now - t) for k, t in ages.items()}
        return snap

    # Sensor types that are always injected into the prompt regardless of
    # whether they changed since the last message.  These represent stable
    # context (location, avatar state) the agent needs on every turn.
    _ALWAYS_INCLUDE = frozenset({"environment", "rlv"})

    def get_changes(self, region: str, user_id: str) -> dict[str, Any]:
        """Return sensor types updated since this user's last message, plus
        any types in _ALWAYS_INCLUDE that exist in the store.

        On first call for a user, returns everything. On subsequent calls,
        fast-changing types (avatars, objects, chat, clothing) are suppressed
        if unchanged, but environment and rlv are always included so the agent
        always knows where it is and what state it's in.
        """
        store = self._store.get(region, {})
        region_ages = self._updated_at.get(region, {})
        user_key = f"{region}:{user_id}"
        last_seen = self._last_sent.get(user_key, {})
        now = time.monotonic()

        snap: dict[str, Any] = {}
        ages: dict[str, int] = {}

        for stype, data in store.items():
            updated = region_ages.get(stype, 0.0)
            prev = last_seen.get(stype, -1.0)
            if updated > prev or stype in self._ALWAYS_INCLUDE:
                snap[stype] = data
                ages[stype] = int(now - updated)

        if snap:
            snap["_ages"] = ages
            # Record what we just sent
            self._last_sent[user_key] = {k: region_ages.get(k, 0.0) for k in snap if not k.startswith("_")}

        return snap
