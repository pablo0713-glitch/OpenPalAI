from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class LibraryModule:
    id: str
    title: str
    description: str
    always_on: bool
    platforms: list[str]
    tags: list[str]
    content: str
    char_count: int
    filename: str


class LibraryStore:
    """
    Manages markdown library modules stored in data/library/.
    Each .md file may have a YAML-like front-matter block bounded by '---'.
    Supported front-matter fields:
        id, title, description, always_on (bool), platforms ([]), tags ([])
    Files without front-matter are treated as on-demand modules with id derived
    from the filename.
    """

    def __init__(self, library_dir: str) -> None:
        self._dir = library_dir

    def load_all(self) -> list[LibraryModule]:
        modules: list[LibraryModule] = []
        try:
            if not os.path.isdir(self._dir):
                return []
            for fname in sorted(os.listdir(self._dir)):
                if not fname.endswith(".md"):
                    continue
                path = os.path.join(self._dir, fname)
                try:
                    mod = self._parse_file(path, fname)
                    if mod is not None:
                        modules.append(mod)
                except Exception as exc:
                    logger.warning("LibraryStore: skipping %s — %s", fname, exc)
        except OSError as exc:
            logger.warning("LibraryStore.load_all failed: %s", exc)
        return modules

    def get_always_on(self, platform: str | None = None) -> list[LibraryModule]:
        return [
            m for m in self.load_all()
            if m.always_on and (not m.platforms or not platform or platform in m.platforms)
        ]

    def get_by_id(self, module_id: str) -> LibraryModule | None:
        for m in self.load_all():
            if m.id == module_id:
                return m
        return None

    def search(self, query: str, limit: int = 3) -> list[LibraryModule]:
        """Keyword search across title, description, tags, and first 500 chars of content."""
        if not query.strip():
            return []
        terms = query.lower().split()
        scored: list[tuple[int, LibraryModule]] = []
        for m in self.load_all():
            searchable = " ".join([
                m.title, m.description, " ".join(m.tags), m.content[:500]
            ]).lower()
            hits = sum(1 for t in terms if t in searchable)
            if hits:
                scored.append((hits, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def list_modules(self) -> list[dict]:
        return [
            {
                "id": m.id,
                "title": m.title,
                "description": m.description,
                "always_on": m.always_on,
                "platforms": m.platforms,
                "tags": m.tags,
                "char_count": m.char_count,
                "filename": m.filename,
            }
            for m in self.load_all()
        ]

    def _parse_file(self, path: str, fname: str) -> LibraryModule | None:
        raw = Path(path).read_text(encoding="utf-8")
        meta: dict = {}
        content = raw

        if raw.startswith("---"):
            end = raw.find("\n---", 3)
            if end != -1:
                front = raw[3:end].strip()
                content = raw[end + 4:].strip()
                meta = _parse_frontmatter(front)

        stem = fname[:-3]  # strip .md
        module_id = meta.get("id") or re.sub(r"[^a-z0-9_-]", "_", stem.lower())
        title = meta.get("title") or stem.replace("_", " ").replace("-", " ").title()
        description = meta.get("description") or ""
        always_on = _parse_bool(meta.get("always_on", False))
        platforms = _parse_list(meta.get("platforms", []))
        tags = _parse_list(meta.get("tags", []))

        return LibraryModule(
            id=module_id,
            title=title,
            description=description,
            always_on=always_on,
            platforms=platforms,
            tags=tags,
            content=content,
            char_count=len(content),
            filename=fname,
        )


# ------------------------------------------------------------------ helpers

def _parse_frontmatter(text: str) -> dict:
    """Minimal front-matter parser for key: value pairs and JSON arrays."""
    result: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        result[key] = value
    return result


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "yes", "1")
    return bool(value)


def _parse_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        v = value.strip()
        if v.startswith("["):
            try:
                return [str(x) for x in json.loads(v)]
            except json.JSONDecodeError:
                pass
        if v:
            return [v]
    return []
