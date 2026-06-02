from __future__ import annotations

import logging

from core.persona import MessageContext
from memory.session_index import SessionIndex

logger = logging.getLogger(__name__)


async def handle_session_search(
    tool_input: dict,
    context: MessageContext,
    session_index: SessionIndex,
) -> str:
    query = tool_input.get("query", "").strip()
    limit = int(tool_input.get("limit", 5))
    limit = max(1, min(limit, 10))

    if not query:
        return "query is required."

    rows = await session_index.search(query, limit, agent_id=context.agent_id)

    if not rows:
        return "No matching sessions found."

    lines = [f"Session search results for: {query!r}\n"]
    for r in rows:
        platform = r.get("platform", "?").upper()
        ts = r.get("timestamp", "")[:10]
        role = r.get("role", "?")
        name = r.get("display_name", "")
        snippet = r.get("snippet", "")
        who = f"{name} · " if name and role == "user" else ""
        lines.append(f"[{platform} | {ts} | {who}{role}] {snippet}")

    return "\n".join(lines)
