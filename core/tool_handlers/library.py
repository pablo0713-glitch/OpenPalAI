from __future__ import annotations

from core.librarian_agent import LibrarianAgent
from core.persona import MessageContext
from memory.library_store import LibraryStore


async def handle_library_lookup(
    tool_input: dict,
    context: MessageContext,
    librarian_agent: LibrarianAgent,
) -> str:
    """Search or retrieve a library module. The librarian agent reasons about relevance."""
    module_id = (tool_input.get("module_id") or "").strip()
    query = (tool_input.get("query") or "").strip()

    if not module_id and not query:
        return "Provide either a module_id to retrieve or a query to search."

    if module_id:
        return await librarian_agent.get_module(module_id)

    modules = await librarian_agent.find_relevant(query)
    if not modules:
        return f"No library modules found matching '{query}'."

    parts = [f"Library results for: {query!r}\n"]
    for m in modules:
        parts.append(f"### {m.title} (id: {m.id})")
        if m.description:
            parts.append(m.description)
        parts.append(m.content[:800] + ("…" if len(m.content) > 800 else ""))
        parts.append("")
    return "\n".join(parts)


async def handle_library_list(
    tool_input: dict,
    context: MessageContext,
    library_store: LibraryStore,
) -> str:
    """List available library modules with metadata."""
    modules = library_store.list_modules()
    if not modules:
        return "No library modules available. Add .md files to data/library/."

    lines = ["Available library modules:\n"]
    for m in modules:
        platform_note = f" [{', '.join(m['platforms'])}]" if m["platforms"] else ""
        on_note = " [always-on]" if m["always_on"] else ""
        lines.append(f"- {m['id']}: {m['title']}{platform_note}{on_note}")
        if m["description"]:
            lines.append(f"  {m['description']}")
    return "\n".join(lines)
