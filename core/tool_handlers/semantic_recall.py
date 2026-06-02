from __future__ import annotations

from core.persona import MessageContext
from core.recall_agent import SemanticRecallAgent


async def handle_semantic_recall(
    tool_input: dict,
    context: MessageContext,
    recall_agent: SemanticRecallAgent,
) -> str:
    """Search conversation history by meaning rather than keywords."""
    query = (tool_input.get("query") or "").strip()
    if not query:
        return "query is required."

    limit = min(int(tool_input.get("limit", 5)), 10)
    importance_threshold = tool_input.get("importance_threshold")
    if importance_threshold is not None:
        try:
            importance_threshold = float(importance_threshold)
        except (TypeError, ValueError):
            importance_threshold = None

    person_id = context.person_id or context.user_id
    memory_namespace = f"{context.agent_id}::{person_id}" if context.agent_id else person_id
    return await recall_agent.recall(
        person_id=memory_namespace,
        query=query,
        n_results=limit,
        importance_threshold=importance_threshold,
    )
