from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Optional

LEGACY_CANONICAL_OWNER_ID = "SL_Notes"
COMMAND_USER_PREFIX = "command_user_"


def canonical_owner_id(name: str | None) -> str:
    cleaned = (name or "").strip()
    return cleaned or LEGACY_CANONICAL_OWNER_ID


def migrate_owner_identity(
    person_map_path: str | Path,
    canonical_id: str,
    *,
    memory_dir: str | Path | None = None,
    notes_dir: str | Path | None = None,
) -> None:
    """Move legacy owner identity data to the canonical Command Center name."""
    canonical_id = canonical_owner_id(canonical_id)
    path = Path(person_map_path)
    if not path.exists():
        return

    try:
        data: dict[str, list[str]] = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return

    owner_aliases = [LEGACY_CANONICAL_OWNER_ID, "Command Center"]
    old_keys = [key for key in owner_aliases if key != canonical_id and key in data]
    if not old_keys:
        return

    merged = list(data.get(canonical_id, []))
    for old_key in old_keys:
        for uid in data.get(old_key, []):
            if uid not in merged:
                merged.append(uid)
        data.pop(old_key, None)
    data[canonical_id] = merged
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    for base in [Path(notes_dir) if notes_dir else None]:
        if base is not None:
            _merge_dirs(base, old_keys, canonical_id)

    if memory_dir:
        memory_base = Path(memory_dir)
        _merge_dirs(memory_base, old_keys, canonical_id)
        agents_dir = memory_base / "agents"
        if agents_dir.exists():
            for agent_dir in agents_dir.iterdir():
                if agent_dir.is_dir():
                    _merge_dirs(agent_dir, old_keys, canonical_id)


def _merge_dirs(base: Path, old_keys: list[str], canonical_id: str) -> None:
    dest = base / _safe_path_part(canonical_id)
    for old_key in old_keys:
        src = base / _safe_path_part(old_key)
        if not src.exists() or src == dest:
            continue
        if not dest.exists():
            shutil.move(str(src), str(dest))
            continue
        for child in src.iterdir():
            target = dest / child.name
            if not target.exists():
                shutil.move(str(child), str(target))
        shutil.rmtree(str(src), ignore_errors=True)


def _safe_path_part(value: str) -> str:
    return value.replace("/", "_").replace(":", "_")


class PersonMap:
    """
    Maps canonical person IDs to all their platform-specific user_ids.

    The source of truth is data/person_map.json:
        {
          "pablorios": [
            "discord_1090657639781912677",
            "sl_0f2a4fb8-efc6-4bf7-9dc5-87f99d5ce8b0"
          ]
        }

    A PersonMap with no entries is valid — it just means no cross-platform
    linking is configured yet.
    """

    def __init__(
        self,
        data: dict[str, list[str]],
        canonical_owner: str = "",
        path: str | Path | None = None,
    ) -> None:
        self._canonical_owner = canonical_owner_id(canonical_owner)
        self._by_person: dict[str, list[str]] = data
        self._path = Path(path) if path else None
        # Reverse index: user_id → person_id
        self._by_user: dict[str, str] = {}
        for person_id, user_ids in data.items():
            for uid in user_ids:
                self._by_user[uid] = person_id

    @classmethod
    def load(cls, path: str, canonical_owner: str = "") -> "PersonMap":
        if not os.path.exists(path):
            return cls({}, canonical_owner, path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data, canonical_owner, path)

    def get_person_id(self, user_id: str) -> Optional[str]:
        """Return the canonical person name for a platform user_id, or None."""
        if user_id.startswith(COMMAND_USER_PREFIX):
            return self._canonical_owner
        return self._by_user.get(user_id)

    def get_linked_ids(self, user_id: str) -> list[str]:
        """All user_ids for the same person, excluding the given one."""
        person_id = self.get_person_id(user_id)
        if person_id is None:
            return []
        return [uid for uid in self._by_person.get(person_id, []) if uid != user_id]

    def get_person_user_ids(self, person_id: str) -> list[str]:
        """All user_ids linked to a person."""
        return list(self._by_person.get(person_id, []))

    def all_persons(self) -> list[str]:
        return list(self._by_person.keys())

    def canonical_owner(self) -> str:
        return self._canonical_owner

    def link_user_id(self, person_id: str, user_id: str) -> bool:
        """Persistently link a platform user_id to a canonical person."""
        person_id = canonical_owner_id(person_id)
        if not user_id:
            return False
        existing = self._by_user.get(user_id)
        if existing == person_id:
            return False

        if existing and existing in self._by_person:
            self._by_person[existing] = [
                uid for uid in self._by_person[existing] if uid != user_id
            ]

        self._by_person.setdefault(person_id, [])
        if user_id not in self._by_person[person_id]:
            self._by_person[person_id].append(user_id)
        self._by_user[user_id] = person_id

        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._by_person, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        return True
