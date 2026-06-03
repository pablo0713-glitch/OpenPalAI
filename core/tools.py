from __future__ import annotations

from typing import Any, Optional

from config.settings import Settings
from core.persona import MessageContext
from memory.session_index import SessionIndex


# ------------------------------------------------------------------ schemas

WEB_SEARCH_SCHEMA = {
    "name": "web_search",
    "description": (
        "Search the web for current information, news, facts, shopping links, "
        "sim details, music lookups, or anything where freshness matters. "
        "Returns titles, snippets, and URLs. Do not announce you're searching — "
        "incorporate results naturally."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Targeted search query phrased as a web search, not a question.",
            },
            "num_results": {
                "type": "integer",
                "description": "Number of results to return. Default 5, max 10.",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}

_SL_ACTION_BASE_DESCRIPTION = (
    "Send a Second Life action from your avatar. "
    "Only available in Second Life — do not call this on Discord. "
    "Actions are queued and executed after your reply is sent. "
    "Note: your text reply is already delivered automatically — "
    "as public local chat for channel 0 messages, or private IM for /42 messages. "
    "Use sl_action for additional actions beyond the main reply."
)

_SL_ACTION_TYPE_DESCRIPTIONS = {
    "lsl": (
        "'say' = speak in public local chat (channel 0), visible to everyone nearby. "
        "'im' = send a private instant message to the target avatar. "
        "'emote' = send *action text* as a private IM to the target avatar. "
        "'anim_trigger' = play a named animation on your avatar. "
        "'scan_outfit' = trigger an RLV outfit scan; results appear in the clothing sensor context on the next message (HUD path only)."
    ),
    "lua": (
        "'say' = speak in public local chat (channel 0), visible to everyone nearby. "
        "'im' = send a private instant message to the target avatar. "
        "'emote' = send *action text* as a private IM to the target avatar. "
        "'anim_trigger' = play a named animation on your avatar. "
        "'scan_outfit' = trigger an RLV outfit scan; results appear in the clothing sensor context on the next message (HUD path only). "
        "'mute_avatar' = mute/block an avatar (text, voice, particles, sounds); set target_key to SL UUID, text to display name. "
        "'unmute_avatar' = remove a mute/block; set target_key to SL UUID, text to display name. "
        "'is_muted' = check whether an avatar is muted; set target_key to SL UUID — result is sent back as an IM."
    ),
}

_SL_ACTION_ENUMS = {
    "lsl": ["say", "im", "emote", "anim_trigger", "scan_outfit"],
    "lua": ["say", "im", "emote", "anim_trigger", "scan_outfit", "mute_avatar", "unmute_avatar", "is_muted"],
}


def _build_sl_action_schema(sl_client: str) -> dict:
    client = sl_client if sl_client in _SL_ACTION_ENUMS else "lsl"
    return {
        "name": "sl_action",
        "description": _SL_ACTION_BASE_DESCRIPTION,
        "input_schema": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": _SL_ACTION_ENUMS[client],
                    "description": _SL_ACTION_TYPE_DESCRIPTIONS[client],
                },
                "text": {
                    "type": "string",
                    "description": (
                        "The text to send, or animation name for anim_trigger. Max 1023 chars. "
                        "For mute_avatar / unmute_avatar / is_muted: the avatar's display name."
                    ),
                },
                "target_key": {
                    "type": "string",
                    "description": "Avatar UUID. Required for mute_avatar / unmute_avatar / is_muted — use the SL UUID shown in the avatar context block.",
                },
            },
            "required": ["action_type"],
        },
    }

NOTE_WRITE_SCHEMA = {
    "name": "note_write",
    "description": (
        "Save a persistent note for the current user. Survives across conversations. "
        "Use for places they like, goals, shopping lists, reminders — anything worth keeping. "
        "Overwrites if a note with this title already exists."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short unique identifier. Examples: 'favorite_sims', 'creative_goals', 'shopping_list'.",
            },
            "content": {"type": "string", "description": "Note content. Plain text, can be multi-line."},
        },
        "required": ["title", "content"],
    },
}

NOTE_READ_SCHEMA = {
    "name": "note_read",
    "description": "Read a previously saved note by title.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Exact title of the note to retrieve."}
        },
        "required": ["title"],
    },
}

NOTE_LIST_SCHEMA = {
    "name": "note_list",
    "description": "List all saved note titles for the current user. Use before note_read if unsure of the exact title.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

SESSION_QUERY_SCHEMA = {
    "name": "session_query",
    "description": (
        "Query your conversation history with structured filters. "
        "Use 'speakers' mode to answer questions like 'who did you talk to on April 18th?' or "
        "'list everyone you've spoken with this week'. "
        "Use 'turns' mode to retrieve recent messages from a specific person or date. "
        "All filters are optional and combinable."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["speakers", "turns"],
                "description": (
                    "'speakers' returns one row per unique person with turn count and date range. "
                    "'turns' returns individual messages with content snippets."
                ),
            },
            "date_from": {
                "type": "string",
                "description": "Start date filter, YYYY-MM-DD (inclusive).",
            },
            "date_to": {
                "type": "string",
                "description": "End date filter, YYYY-MM-DD (inclusive, covers full day).",
            },
            "platform": {
                "type": "string",
                "enum": ["sl", "discord"],
                "description": "Filter to a single platform.",
            },
            "include_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Only return these display names.",
            },
            "exclude_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exclude these display names from results.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return. Default 20, max 50.",
                "default": 20,
            },
        },
        "required": ["mode"],
    },
}

SESSION_SEARCH_SCHEMA = {
    "name": "session_search",
    "description": (
        "Search your full conversation history across all users and platforms. "
        "ALWAYS call this before saying you don't recall a person, conversation, or event — "
        "search by avatar display name, topic, or keywords. "
        "Also call this proactively at the start of a conversation about a past event, person, "
        "or topic — even if you think you remember it. "
        "Returns timestamped snippets with the speaker's name, platform, and date."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords or phrase to search for in past conversations.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return. Default 5, max 10.",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}

MEMORY_SCHEMA = {
    "name": "memory",
    "description": (
        "Curate your persistent memory. Two stores are available:\n"
        "  'memory' — your notes about context, facts, and the world (~2,000 chars).\n"
        "  'user'   — the owner's profile: their preferences, style, background (~1,200 chars).\n"
        "Both are injected into every system prompt. Use this to remember what matters and "
        "forget what doesn't. Do not announce that you are updating memory.\n"
        "Call memory.add immediately after learning any new fact about the owner — preferences, "
        "names, projects, plans, opinions — without waiting to be asked. Do not batch facts; "
        "save each one as you learn it. Use 'replace' when a fact has changed, 'remove' when "
        "it's no longer relevant."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "replace", "remove"],
                "description": "'add' appends a new entry. 'replace' rewrites part of an entry. 'remove' deletes an entry.",
            },
            "store": {
                "type": "string",
                "enum": ["memory", "user"],
                "description": "Which memory file to update.",
            },
            "text": {
                "type": "string",
                "description": "Entry text for 'add', or replacement text for 'replace'.",
            },
            "old_text": {
                "type": "string",
                "description": "Substring to match for 'replace' or 'remove'.",
            },
        },
        "required": ["action", "store"],
    },
}


LIBRARY_LOOKUP_SCHEMA = {
    "name": "library_lookup",
    "description": (
        "Look up a reference module from the Situational Library. "
        "Use when you need detailed lore, world-building, rules, or reference information "
        "not already in your current context. Search by keyword or retrieve by exact module id."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keyword search across module titles and descriptions.",
            },
            "module_id": {
                "type": "string",
                "description": "Exact module id to retrieve in full.",
            },
        },
    },
}

LIBRARY_LIST_SCHEMA = {
    "name": "library_list",
    "description": "List available Situational Library modules with their descriptions and ids.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

SEMANTIC_RECALL_SCHEMA = {
    "name": "semantic_recall",
    "description": (
        "Search conversation history by meaning rather than exact keywords. "
        "Use when looking for something thematically related — e.g. 'conversations about "
        "building projects' or 'times someone seemed upset'. "
        "Complements session_search (which matches exact keywords). "
        "Call this when the user references something by feeling or theme rather than specific "
        "words, or when session_search returns nothing but the topic feels familiar. "
        "Also call proactively when the user mentions a topic you may have discussed before "
        "but don't have in your current context."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Describe what you are looking for in natural language.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return. Default 5, max 10.",
                "default": 5,
            },
            "importance_threshold": {
                "type": "number",
                "description": "Only return turns scored at or above this importance (0.0–1.0). Optional.",
            },
        },
        "required": ["query"],
    },
}


# ------------------------------------------------------------------ registry

class ToolRegistry:
    def __init__(
        self,
        settings: Settings,
        session_index: SessionIndex | None = None,
        librarian_agent: Optional[Any] = None,
        recall_agent: Optional[Any] = None,
    ) -> None:
        self._settings = settings
        self._session_index = session_index
        self._librarian_agent = librarian_agent
        self._recall_agent = recall_agent

    def get_definitions(self, context: MessageContext) -> list[dict]:
        from core.persona import get_companion_agent
        cfg_tools = get_companion_agent(context.agent_id).get("tools", {})

        tools = []
        if cfg_tools.get("web_search", True):
            tools.append(WEB_SEARCH_SCHEMA)
        if cfg_tools.get("notes", True):
            tools.extend([NOTE_WRITE_SCHEMA, NOTE_READ_SCHEMA, NOTE_LIST_SCHEMA])
        if context.platform == "sl" and cfg_tools.get("sl_action", True):
            tools.append(_build_sl_action_schema("lua"))
        tools.append(MEMORY_SCHEMA)
        if self._session_index is not None:
            tools.append(SESSION_QUERY_SCHEMA)
            tools.append(SESSION_SEARCH_SCHEMA)
        if self._librarian_agent is not None:
            tools.extend([LIBRARY_LOOKUP_SCHEMA, LIBRARY_LIST_SCHEMA])
        if self._recall_agent is not None:
            tools.append(SEMANTIC_RECALL_SCHEMA)
        return tools

    async def dispatch(
        self,
        name: str,
        tool_input: dict[str, Any],
        context: MessageContext,
        action_queue: list[dict],
    ) -> str:
        from core.tool_handlers import notes, sl_action, web_search
        from core.tool_handlers.memory import handle_memory
        from core.tool_handlers.session_query import handle_session_query
        from core.tool_handlers.session_search import handle_session_search
        if name == "web_search":
            return await web_search.handle_web_search(
                tool_input,
                context,
                self._settings.search_provider,
                self._settings.search_api_key,
            )
        elif name == "sl_action":
            return await sl_action.handle_sl_action(tool_input, context, action_queue)
        elif name == "note_write":
            return await notes.handle_note_write(tool_input, context, self._settings.notes_dir)
        elif name == "note_read":
            return await notes.handle_note_read(tool_input, context, self._settings.notes_dir)
        elif name == "note_list":
            return await notes.handle_note_list(tool_input, context, self._settings.notes_dir)
        elif name == "memory":
            return await handle_memory(tool_input, context, self._settings.memory_dir)
        elif name == "session_query":
            if self._session_index is None:
                return "Session query is not available."
            return await handle_session_query(tool_input, context, self._session_index)
        elif name == "session_search":
            if self._session_index is None:
                return "Session search is not available."
            return await handle_session_search(tool_input, context, self._session_index)
        elif name == "library_lookup":
            if self._librarian_agent is None:
                return "Library is not available."
            from core.tool_handlers.library import handle_library_lookup
            return await handle_library_lookup(tool_input, context, self._librarian_agent)
        elif name == "library_list":
            if self._librarian_agent is None:
                return "Library is not available."
            from core.tool_handlers.library import handle_library_list
            from memory.library_store import LibraryStore
            store = LibraryStore(self._settings.library_dir)
            return await handle_library_list(tool_input, context, store)
        elif name == "semantic_recall":
            if self._recall_agent is None:
                return "Semantic recall is not available."
            from core.tool_handlers.semantic_recall import handle_semantic_recall
            return await handle_semantic_recall(tool_input, context, self._recall_agent)
        else:
            return f"Unknown tool: {name}"
