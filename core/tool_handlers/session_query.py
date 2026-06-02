from __future__ import annotations

import logging

from core.persona import MessageContext
from memory.session_index import SessionIndex

logger = logging.getLogger(__name__)


async def handle_session_query(
    tool_input: dict,
    context: MessageContext,
    session_index: SessionIndex,
) -> str:
    mode = tool_input.get("mode", "speakers")
    if mode not in ("speakers", "turns"):
        return "mode must be 'speakers' or 'turns'."

    date_from = tool_input.get("date_from", "")
    date_to = tool_input.get("date_to", "")
    platform = tool_input.get("platform", "")
    include_names = tool_input.get("include_names") or []
    exclude_names = tool_input.get("exclude_names") or []
    limit = min(int(tool_input.get("limit", 20)), 50)

    rows = await session_index.query(
        mode=mode,
        date_from=date_from,
        date_to=date_to,
        platform=platform,
        include_names=include_names or None,
        exclude_names=exclude_names or None,
        limit=limit,
        agent_id=context.agent_id,
    )

    if not rows:
        return "No matching records found."

    if mode == "speakers":
        lines = ["Speakers found:\n"]
        for r in rows:
            first = r.get("first_seen", "")[:10]
            last = r.get("last_seen", "")[:10]
            turns = r.get("turns", 0)
            plat = r.get("platform", "?").upper()
            name = r.get("display_name", "?")
            date_range = first if first == last else f"{first} – {last}"
            lines.append(f"- {name} [{plat}] {date_range} ({turns} turn(s))")
    else:
        lines = ["Turns found:\n"]
        for r in rows:
            ts = r.get("timestamp", "")[:16].replace("T", " ")
            plat = r.get("platform", "?").upper()
            role = r.get("role", "user")
            raw_name = r.get("display_name", "")
            name = raw_name if raw_name else ("me" if role == "assistant" else "?")
            snippet = r.get("snippet", "")
            lines.append(f"[{plat} | {ts} | {name}] {snippet}")

    return "\n".join(lines)
