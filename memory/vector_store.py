from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)

_LOOP = asyncio.get_event_loop


def _safe_id(person_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", person_id)[:60] or "default"


class VectorMemoryStore:
    """
    ChromaDB PersistentClient storing semantic embeddings of conversation turns.

    One collection per person_id, named mem_{safe_person_id}.
    ChromaDB is synchronous — all public methods use run_in_executor to avoid
    blocking the asyncio event loop.

    Doc ID = str(session_id) from sessions.db. Since SQLite AUTOINCREMENT ids
    are never reused, this gives stable, deduplicated keys across re-runs.

    Default embedding: ChromaDB's bundled ONNXMiniLM_L6_V2 (no extra deps).
    anonymized_telemetry is always disabled.
    """

    def __init__(self, memory_dir: str) -> None:
        self._chroma_dir = os.path.join(memory_dir, "chroma")
        os.makedirs(self._chroma_dir, exist_ok=True)
        self._client: chromadb.ClientAPI | None = None
        self._collections: dict[str, Any] = {}
        self._client_lock = asyncio.Lock()

    def _get_client(self) -> chromadb.ClientAPI:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=self._chroma_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        return self._client

    def _get_collection(self, person_id: str) -> Any:
        safe = _safe_id(person_id)
        if safe not in self._collections:
            self._collections[safe] = self._get_client().get_or_create_collection(
                name=f"mem_{safe}",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[safe]

    async def _run(self, fn, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def add_turn(
        self,
        person_id: str,
        session_id: int,
        content: str,
        metadata: dict,
    ) -> None:
        """Add or update a turn in the vector index. Idempotent by session_id."""
        if not content or not content.strip():
            return
        doc_id = str(session_id)

        def _upsert():
            col = self._get_collection(person_id)
            safe_meta = {
                k: (v if isinstance(v, (str, int, float, bool)) else str(v))
                for k, v in metadata.items()
            }
            col.upsert(
                ids=[doc_id],
                documents=[content[:2000]],
                metadatas=[safe_meta],
            )

        try:
            await self._run(_upsert)
        except Exception as exc:
            logger.warning("VectorMemoryStore.add_turn failed (id=%s): %s", session_id, exc)

    async def set_importance_batch(self, person_id: str, scores: dict[int, float]) -> None:
        """Update existing vector metadata with scored importance values."""
        if not scores:
            return
        ids = [str(session_id) for session_id in scores]

        def _update():
            col = self._get_collection(person_id)
            existing = col.get(ids=ids, include=["metadatas"])
            found_ids = existing.get("ids", [])
            metadatas = existing.get("metadatas", [])
            if not found_ids:
                return
            updated = []
            for doc_id, meta in zip(found_ids, metadatas):
                next_meta = dict(meta or {})
                next_meta["importance"] = max(0.0, min(1.0, float(scores[int(doc_id)])))
                updated.append(next_meta)
            col.update(ids=found_ids, metadatas=updated)

        try:
            await self._run(_update)
        except Exception as exc:
            logger.warning("VectorMemoryStore.set_importance_batch failed: %s", exc)

    async def semantic_search(
        self,
        person_id: str,
        query: str,
        n_results: int = 5,
        importance_threshold: float | None = None,
    ) -> list[dict]:
        """
        Return up to n_results turns semantically similar to query.
        Optionally filter to turns with importance >= importance_threshold.
        Each result: {content, metadata, distance}.
        """
        if not query.strip():
            return []

        where: dict | None = None
        if importance_threshold is not None:
            where = {"importance": {"$gte": float(importance_threshold)}}

        def _query():
            col = self._get_collection(person_id)
            kwargs: dict = dict(
                query_texts=[query],
                n_results=min(n_results, max(col.count(), 1)),
            )
            if where:
                kwargs["where"] = where
            return col.query(**kwargs)

        try:
            result = await self._run(_query)
            docs = result.get("documents", [[]])[0]
            metas = result.get("metadatas", [[]])[0]
            dists = result.get("distances", [[]])[0]
            return [
                {"content": d, "metadata": m, "distance": dist}
                for d, m, dist in zip(docs, metas, dists)
            ]
        except Exception as exc:
            logger.warning("VectorMemoryStore.semantic_search failed: %s", exc)
            return []

    async def delete_turns_for_user(self, person_id: str, user_id: str) -> None:
        """Remove all turns for a specific user_id within a person collection."""
        def _delete():
            col = self._get_collection(person_id)
            col.delete(where={"user_id": user_id})

        try:
            await self._run(_delete)
        except Exception as exc:
            logger.warning("VectorMemoryStore.delete_turns_for_user failed: %s", exc)

    async def has_document(self, person_id: str, session_id: int) -> bool:
        """Check if a session_id is already indexed (used by backfill)."""
        def _get():
            col = self._get_collection(person_id)
            return col.get(ids=[str(session_id)])

        try:
            result = await self._run(_get)
            return bool(result.get("ids"))
        except Exception:
            return False
