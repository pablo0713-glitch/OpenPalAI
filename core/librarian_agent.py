from __future__ import annotations

import logging

from core.model_adapter import ModelAdapter
from core.supporting_agent import SupportingAgent
from memory.library_store import LibraryModule, LibraryStore

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a librarian for an AI companion's situational knowledge base. "
    "When given a query and a list of available modules, you identify which modules "
    "are most relevant to the query and briefly explain why each one matters. "
    "You are precise and concise — no padding, no repetition."
)


class LibrarianAgent(SupportingAgent):
    """
    Specialist agent that reasons about library module relevance.
    Wraps LibraryStore.search() with a model reasoning pass so the main agent
    gets relevance-ranked, context-annotated results rather than raw keyword hits.
    """

    def __init__(self, adapter: ModelAdapter, library_store: LibraryStore) -> None:
        super().__init__(adapter, _SYSTEM)
        self._store = library_store

    async def find_relevant(self, query: str, context_summary: str = "") -> list[LibraryModule]:
        """
        1. Keyword-search library for candidate modules (up to 5)
        2. Ask the model which ones are actually relevant given context
        3. Return the filtered, relevance-ranked list
        """
        candidates = self._store.search(query, limit=5)
        if not candidates:
            return []

        # Build the reasoning prompt
        module_list = "\n".join(
            f"- id={m.id}: {m.title} — {m.description or 'no description'}"
            for m in candidates
        )
        prompt = (
            f"Query: {query}\n"
            + (f"Context: {context_summary[:400]}\n" if context_summary else "")
            + f"\nAvailable modules:\n{module_list}\n\n"
            "Which of these modules are genuinely relevant to the query and context? "
            "List only the relevant module IDs, one per line, most relevant first. "
            "If none are relevant, reply with 'none'."
        )

        try:
            raw = await self.run(prompt, max_tokens=128)
            selected_ids = {
                line.strip().lstrip("- ").split()[0]
                for line in raw.splitlines()
                if line.strip() and line.strip().lower() != "none"
            }
            ordered = [m for m in candidates if m.id in selected_ids]
            # Append any not returned by the model (preserve all keyword hits if model is sparse)
            for m in candidates:
                if m not in ordered:
                    ordered.append(m)
            return ordered[:3]
        except Exception as exc:
            logger.warning("LibrarianAgent.find_relevant failed (%s) — returning keyword results", exc)
            return candidates[:3]

    async def get_module(self, module_id: str) -> str:
        """Direct retrieval — no reasoning pass needed."""
        mod = self._store.get_by_id(module_id)
        if mod is None:
            return f"No library module found with id '{module_id}'."
        return f"## {mod.title}\n\n{mod.content}"
