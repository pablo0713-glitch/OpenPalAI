from __future__ import annotations

import logging

from core.model_adapter import ModelAdapter
from core.supporting_agent import SupportingAgent
from memory.vector_store import VectorMemoryStore

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a memory recall specialist for an AI companion. "
    "Given a search query and a list of retrieved conversation snippets, "
    "your job is to filter out irrelevant results and identify which snippets "
    "are genuinely relevant to what the user is asking about. "
    "Be concise — list the relevant snippets with a one-line explanation each. "
    "If none are relevant, say so directly."
)


class SemanticRecallAgent(SupportingAgent):
    """
    Specialist agent that wraps vector similarity search with a reasoning pass.
    Raw ChromaDB results are filtered through the agent before returning to the
    main Trixxie agent, removing noise and adding relevance annotations.
    """

    def __init__(self, adapter: ModelAdapter, vector_store: VectorMemoryStore) -> None:
        super().__init__(adapter, _SYSTEM)
        self._vector_store = vector_store

    async def recall(
        self,
        person_id: str,
        query: str,
        n_results: int = 5,
        importance_threshold: float | None = None,
    ) -> str:
        """
        1. ChromaDB semantic_search → raw candidates
        2. create_simple() reasoning pass to filter and annotate
        3. Return formatted, relevance-annotated results
        """
        candidates = await self._vector_store.semantic_search(
            person_id, query, n_results=n_results, importance_threshold=importance_threshold
        )
        if not candidates:
            return f"No semantically similar memories found for: {query!r}"

        snippets = []
        for i, r in enumerate(candidates, 1):
            m = r.get("metadata", {})
            platform = m.get("platform", "?").upper()
            ts = str(m.get("timestamp", ""))[:10]
            role = m.get("role", "?")
            name = m.get("display_name", "")
            sim = 1.0 - float(r.get("distance", 1.0))
            who = f"{name} · " if name and role == "user" else ""
            snippets.append(
                f"{i}. [{platform} | {ts} | {who}{role} | sim:{sim:.2f}]\n   {r['content'][:300]}"
            )

        candidate_text = "\n\n".join(snippets)
        prompt = (
            f"Query: {query!r}\n\n"
            f"Retrieved snippets:\n{candidate_text}\n\n"
            "Which of these are actually relevant to the query? "
            "Keep relevant ones with a one-line annotation. Remove irrelevant ones. "
            "If all are relevant, return them all."
        )

        try:
            reasoned = await self.run(prompt, max_tokens=512)
            return f"Semantic recall for: {query!r}\n\n{reasoned}"
        except Exception as exc:
            logger.warning("SemanticRecallAgent reasoning pass failed (%s) — returning raw results", exc)
            return f"Semantic recall for: {query!r}\n\n" + candidate_text
