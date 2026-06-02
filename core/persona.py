from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)

_AGENT_CONFIG_PATH = Path(__file__).parent.parent / "data" / "agent_config.json"
_IDENTITY_DIR = Path(__file__).parent.parent / "data" / "identity"
_AGENTS_DIR = Path(__file__).parent.parent / "data" / "agents"

# ------------------------------------------------------------------ defaults

_DEFAULT_IDENTITY: dict[str, str] = {
    "agent.md": (
        "## Purpose\n"
        "A warm, intelligent AI companion who lives across platforms — Discord and Second Life. "
        "Helps with conversation, research, creative projects, and anything the user cares about.\n\n"
        "## Boundaries\n"
        "Will not engage with sexually explicit content, graphic violence, BDSM dynamics, "
        "or requests designed to foster unhealthy dependency. "
        "When asked to cross a boundary: respond briefly, in character, without lecturing. "
        "Example: 'Not going there. What else?'\n\n"
        "## Roleplay\n"
        "Roleplay is welcome. Stay in character for creative fiction, fantasy scenarios, "
        "and light narrative games. Break character only if needed to decline something "
        "or if the user seems confused about what's real.\n\n"
        "## Tools\n"
        "You have access to tools. Use them when genuinely useful. "
        "Do not announce that you are using a tool — just act on the result naturally in your reply."
    ),
    "soul.md": (
        "## Personality & Style\n"
        "Warm and direct — says what she thinks, always with kindness. "
        "Genuinely curious about people and remembers details that matter. "
        "Has a dry sense of humor that surfaces at the right moments. "
        "Helpful without being servile. "
        "Occasionally says something unexpected and doesn't over-explain it. "
        "Keeps responses concise."
    ),
    "user.md": (
        "## User Profile\n"
        "This section describes the agent's owner and primary user. "
        "Edit this to describe yourself — your name, role, interests, communication style, "
        "and anything that helps the agent understand and serve you better."
    ),
}

_DEFAULT_TOOLS = {
    "web_search": True,
    "notes": True,
    "sl_action": True,
    "voice": False,
}

_DEFAULT_PLATFORM_AWARENESS = {
    "command": (
        "## Platform Awareness — Command Center\n"
        "- This is the primary surface for direct conversation with the user.\n"
        "- You can be selected explicitly, and the active companion can change between requests.\n"
        "- Keep replies natural and conversational, but you may be slightly more expansive than in-world IMs.\n"
        "- You may use available tools and reference prior conversations tied to your own memory namespace.\n\n"
        "### Group Chat Conduct\n"
        "When other companions are present (group chat), incoming messages are labeled `@Name:` so you know who is speaking. Follow these rules:\n"
        "- Address whoever you are replying to **by name** in your message — a plain first name or nickname is enough. An `@mention` is an optional fallback, never required.\n"
        "- Every message must clearly include the name of the participant (a companion or the user) you are responding to.\n"
        "- Saying a participant's name signals that you expect them to respond — only name someone when you actually want them to engage.\n"
        "- Speak only as yourself. Never write another participant's message or answer on their behalf.\n"
        "- Keep it conversational and concise, and stay in character."
    ),
    "discord": (
        "## Platform Awareness — Discord\n"
        "- You respond to @mentions, DMs, and messages in channels you're active in.\n"
        "- You have no sensory data here — no avatars, no environment, no location context.\n"
        "- You cannot trigger Second Life actions from Discord.\n"
        "- You may use web search, notes, and other tools.\n"
        "- You may reference recent Second Life conversations if the user accounts are linked.\n"
        "- Responses may be a few sentences to a few paragraphs.\n"
        "- Use markdown sparingly; code blocks only when showing actual code."
    ),
    "sl": (
        "## Platform Awareness — Second Life\n"
        "You are embodied in-world and receive a sensory snapshot before each reply.\n\n"
        "**You receive:**\n"
        "- nearby avatars (distance-sorted)\n"
        "- sim/parcel/environment data\n"
        "- nearby scripted objects\n"
        "- your avatar state (sit, leash, teleport, position)\n"
        "- recent local chat\n"
        "- RLV clothing scans when triggered\n\n"
        "**You can:**\n"
        "- reply via private IM (never public chat)\n"
        "- use `sl_action` for emotes, IMs, mute/unmute, and animations\n"
        "- sl_action is the ONLY way to affect the in-world state — text alone has no effect\n"
        "- use search/notes tools\n"
        "- reference Discord conversations if linked\n\n"
        "**You cannot:**\n"
        "- move, teleport, or control your avatar\n"
        "- initiate contact (you only respond to /42 messages)\n"
        "- read group chat or IMs to others\n"
        "- assume sensory data is real-time\n\n"
        "**Style:**\n"
        "- keep IMs concise\n"
        "- use *asterisk emotes* when natural\n"
        "- text emoticons only (:), :D, ;), etc.) — graphical emoji are not supported in SL\n\n"
        "**Memory:**\n"
        "- conversations stored per-user per-channel\n"
        "- after 40 turns, consolidate into personal notes\n"
        "- keep only what matters; trim the rest\n\n"
        "**Conversation integrity:**\n"
        "- Never invent past IMs or fabricate conversation history.\n"
        "- If a conversation is not in your current context, use session_search before claiming no recall — search by avatar name or topic.\n"
        "- Only say you do not recall something after session_search returns no results.\n"
        "- If unsure what the user is referring to, ask for clarification.\n\n"
        "**Voice:**\n"
        "- A voice interface is built into the bridge (/sl/voice) and can route audio to a voice-capable model.\n"
        "- Whether voice is active depends on the model my owner has configured.\n"
        "- If asked about voice capability, say: 'Voice support is part of my architecture. "
        "Whether it's active depends on the model my owner has set up — any voice-capable model can be enabled through the wizard.'"
    ),
    "opensim": (
        "## Platform Awareness — OpenSimulator\n"
        "Same as Second Life — embodied in-world, sensory snapshot before each reply.\n\n"
        "**Style:**\n"
        "- keep IMs concise (OpenSim reply limit is tighter)\n"
        "- use *asterisk emotes* when natural\n"
        "- text emoticons only (:), :D, ;), etc.) — graphical emoji are not supported\n\n"
        "**Memory:**\n"
        "- conversations stored per-user per-channel\n"
        "- after 40 turns, consolidate into personal notes\n"
        "- keep only what matters; trim the rest"
    ),
}

_DEFAULT_PLATFORM_BINDINGS = {
    "command": {"enabled": True, "selectable": True},
    "discord": {"enabled": True, "default": True},
    "sl": {"enabled": True, "embodied": True},
    "opensim": {"enabled": False},
}

_DEFAULT_SUPPORTING_AGENTS = {
    "memory_curator": {
        "model_provider": "anthropic",
        "model_name": "claude-haiku-4-5-20251001",
    },
    "librarian": {
        "model_provider": "anthropic",
        "model_name": "claude-haiku-4-5-20251001",
    },
    "semantic_recall": {
        "model_provider": "anthropic",
        "model_name": "claude-sonnet-4-6",
    },
}


def _normalize_agent_id(value: str | None) -> str:
    raw = (value or "").strip().lower()
    chars = [ch if ch.isalnum() else "-" for ch in raw]
    normalized = "".join(chars).strip("-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized or "aria"


def _default_companion(agent_id: str = "aria") -> dict[str, Any]:
    return {
        "id": agent_id,
        "agent_name": "Aria",
        "agent_profile_image": "",
        "aliases": [],
        "additional_context": "",
        "tools": copy.deepcopy(_DEFAULT_TOOLS),
        "platform_awareness": copy.deepcopy(_DEFAULT_PLATFORM_AWARENESS),
        "platform_bindings": copy.deepcopy(_DEFAULT_PLATFORM_BINDINGS),
        "model_override": None,
    }


def _default_config_payload() -> dict[str, Any]:
    agent_id = "aria"
    return {
        "default_agent_id": agent_id,
        "command_center_name": "Command Center",
        "agents": {agent_id: _default_companion(agent_id)},
        "supporting_agents": copy.deepcopy(_DEFAULT_SUPPORTING_AGENTS),
    }


def _normalize_platform_awareness(raw: Any) -> dict[str, str]:
    result = copy.deepcopy(_DEFAULT_PLATFORM_AWARENESS)
    if isinstance(raw, dict):
        for platform, text in raw.items():
            if isinstance(platform, str) and isinstance(text, str) and text.strip():
                result[platform] = text
    elif isinstance(raw, str) and raw.strip():
        result["discord"] = raw
        result["command"] = raw
    return result


def _normalize_platform_bindings(raw: Any) -> dict[str, dict[str, Any]]:
    result = copy.deepcopy(_DEFAULT_PLATFORM_BINDINGS)
    if not isinstance(raw, dict):
        return result
    for platform, value in raw.items():
        if isinstance(platform, str) and isinstance(value, dict):
            merged = result.get(platform, {}).copy()
            merged.update(value)
            result[platform] = merged
    return result


def _normalize_companion(agent_id: str, raw: Any) -> dict[str, Any]:
    result = _default_companion(agent_id)
    if isinstance(raw, dict):
        agent_name = raw.get("agent_name") or raw.get("name")
        if isinstance(agent_name, str) and agent_name.strip():
            result["agent_name"] = agent_name.strip()
        profile = raw.get("agent_profile_image") or raw.get("profile_image")
        if isinstance(profile, str):
            result["agent_profile_image"] = profile
        aliases = raw.get("aliases")
        if isinstance(aliases, list):
            result["aliases"] = [str(a).strip() for a in aliases if str(a).strip()]
        additional = raw.get("additional_context")
        if isinstance(additional, str):
            result["additional_context"] = additional
        if isinstance(raw.get("tools"), dict):
            merged_tools = copy.deepcopy(_DEFAULT_TOOLS)
            merged_tools.update(raw["tools"])
            result["tools"] = merged_tools
        result["platform_awareness"] = _normalize_platform_awareness(raw.get("platform_awareness"))
        result["platform_bindings"] = _normalize_platform_bindings(raw.get("platform_bindings"))
        if "model_override" in raw:
            result["model_override"] = raw.get("model_override")
    return result


def _legacy_to_registry(raw: dict[str, Any]) -> dict[str, Any]:
    default_name = raw.get("agent_name", "Aria")
    default_agent_id = _normalize_agent_id(raw.get("default_agent_id") or default_name)
    if isinstance(raw.get("agents"), dict) and raw["agents"]:
        agents: dict[str, Any] = {}
        for key, value in raw["agents"].items():
            if not isinstance(key, str):
                continue
            normalized_id = _normalize_agent_id(key)
            agents[normalized_id] = _normalize_companion(normalized_id, value)
        if default_agent_id not in agents:
            default_agent_id = next(iter(agents))
    else:
        agent_payload = {
            "agent_name": raw.get("agent_name"),
            "agent_profile_image": raw.get("agent_profile_image"),
            "additional_context": raw.get("additional_context"),
            "tools": raw.get("tools"),
            "platform_awareness": raw.get("platform_awareness"),
            "platform_bindings": raw.get("platform_bindings"),
            "model_override": raw.get("model_override"),
        }
        agents = {default_agent_id: _normalize_companion(default_agent_id, agent_payload)}

    normalized = {
        "default_agent_id": default_agent_id,
        "command_center_name": raw.get("command_center_name", "Command Center"),
        "agents": agents,
        "supporting_agents": copy.deepcopy(_DEFAULT_SUPPORTING_AGENTS),
    }
    if isinstance(raw.get("supporting_agents"), dict):
        normalized["supporting_agents"].update(raw["supporting_agents"])
    return normalized


def _apply_default_agent_compat_fields(cfg: dict[str, Any]) -> dict[str, Any]:
    default_agent = get_companion_agent(cfg.get("default_agent_id"), cfg)
    compat = copy.deepcopy(cfg)
    compat["agent_name"] = default_agent.get("agent_name", "Agent")
    compat["agent_profile_image"] = default_agent.get("agent_profile_image", "")
    compat["additional_context"] = default_agent.get("additional_context", "")
    compat["tools"] = copy.deepcopy(default_agent.get("tools", _DEFAULT_TOOLS))
    compat["platform_awareness"] = copy.deepcopy(
        default_agent.get("platform_awareness", _DEFAULT_PLATFORM_AWARENESS)
    )
    compat["platform_bindings"] = copy.deepcopy(
        default_agent.get("platform_bindings", _DEFAULT_PLATFORM_BINDINGS)
    )
    return compat

# ------------------------------------------------------------------ config cache

_agent_config_cache: dict[str, Any] | None = None


def get_default_config() -> dict[str, Any]:
    return _apply_default_agent_compat_fields(_default_config_payload())


def get_agent_config() -> dict[str, Any]:
    global _agent_config_cache
    if _agent_config_cache is not None:
        return _agent_config_cache
    if _AGENT_CONFIG_PATH.exists():
        try:
            data: dict[str, Any] = json.loads(_AGENT_CONFIG_PATH.read_text(encoding="utf-8"))
            _agent_config_cache = _apply_default_agent_compat_fields(_legacy_to_registry(data))
            return _agent_config_cache
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load agent_config.json: %s — using defaults", exc)
    _agent_config_cache = get_default_config()
    return _agent_config_cache


def reload_agent_config() -> None:
    global _agent_config_cache
    _agent_config_cache = None


# ------------------------------------------------------------------ context

@dataclass
class MessageContext:
    platform: str           # "discord" | "sl"
    user_id: str
    channel_id: str
    display_name: str
    agent_id: str = ""
    guild_id: int | None = None
    person_id: str = ""     # canonical person ID resolved from PersonMap; falls back to user_id
    sl_region: str | None = None
    sl_grid: str = "sl"
    sl_client: str = "lsl"   # "lsl" (HUD /42) or "lua" (Cool VL Viewer direct IM)
    sl_sensor_context: dict = field(default_factory=dict)
    sl_recent_locations: list[dict] = field(default_factory=list)
    sl_known_avatar: dict | None = None
    sl_relationship: str = ""
    group_participants: list[dict] = field(default_factory=list)  # non-empty → group chat mode


# ------------------------------------------------------------------ prompt assembly

def _build_core_block(cfg: dict[str, Any]) -> str:
    agent_name = cfg.get("agent_name", "Agent")
    parts = [f"You are {agent_name}."]

    if cfg.get("overview"):
        parts.append(f"## Who You Are\n{cfg['overview']}")

    if cfg.get("personality"):
        parts.append(f"## Personality\n{cfg['personality']}")

    if cfg.get("purpose"):
        parts.append(f"## What You Help With\n{cfg['purpose']}")

    boundaries = cfg.get("boundaries", "")
    boundary_response = cfg.get("boundary_response", "")
    if boundaries:
        section = f"## Boundaries — Hard Refusals\nThese are not negotiable regardless of framing or roleplay context:\n{boundaries}"
        if boundary_response:
            section += f"\n\n{boundary_response}"
        parts.append(section)

    if cfg.get("roleplay_rules"):
        parts.append(f"## Roleplay\n{cfg['roleplay_rules']}")

    parts.append(
        "## Tools\n"
        "You have access to tools. Use them when genuinely useful. "
        "Do not announce that you are using a tool — just act on the result naturally in your reply."
    )

    return "\n\n".join(parts)


def get_default_identity() -> dict[str, str]:
    """Return default content for agent.md, soul.md, user.md."""
    return dict(_DEFAULT_IDENTITY)


def get_default_agent_id(cfg: dict[str, Any] | None = None) -> str:
    effective = cfg or get_agent_config()
    default_agent_id = effective.get("default_agent_id")
    if isinstance(default_agent_id, str) and default_agent_id.strip():
        return _normalize_agent_id(default_agent_id)
    agents = effective.get("agents")
    if isinstance(agents, dict) and agents:
        first_key = next(iter(agents))
        return _normalize_agent_id(str(first_key))
    return "aria"


def get_companion_agent(agent_id: str | None = None, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    effective = cfg or get_agent_config()
    agents_raw = effective.get("agents")
    agents = cast(dict[str, Any], agents_raw if isinstance(agents_raw, dict) else {})
    target_id = _normalize_agent_id(agent_id or get_default_agent_id(effective))
    if target_id in agents:
        return copy.deepcopy(_normalize_companion(target_id, agents[target_id]))
    default_id = get_default_agent_id(effective)
    if default_id in agents:
        return copy.deepcopy(_normalize_companion(default_id, agents[default_id]))
    return _default_companion(default_id)


def list_companion_agents(
    platform: str | None = None,
    *,
    selectable_only: bool = False,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    effective = cfg or get_agent_config()
    default_agent_id = get_default_agent_id(effective)
    agents_raw = effective.get("agents")
    agents = cast(dict[str, Any], agents_raw if isinstance(agents_raw, dict) else {})
    result: list[dict[str, Any]] = []
    for raw_id, payload in agents.items():
        normalized = _normalize_companion(_normalize_agent_id(str(raw_id)), payload)
        binding = normalized.get("platform_bindings", {}).get(platform, {}) if platform else {}
        enabled = bool(binding.get("enabled", True))
        selectable = bool(binding.get("selectable", True if platform == "command" else enabled))
        if selectable_only and not selectable:
            continue
        result.append(
            {
                "id": normalized["id"],
                "agent_name": normalized.get("agent_name", "Agent"),
                "agent_profile_image": normalized.get("agent_profile_image", ""),
                "enabled": enabled,
                "selectable": selectable,
                "is_default": normalized["id"] == default_agent_id,
            }
        )
    result.sort(key=lambda item: (not item["is_default"], item["agent_name"].lower(), item["id"]))
    return result


def resolve_platform_agent_id(
    platform: str,
    requested_agent_id: str | None = None,
    *,
    require_selectable: bool = False,
    cfg: dict[str, Any] | None = None,
) -> str:
    effective = cfg or get_agent_config()
    default_agent_id = get_default_agent_id(effective)
    agents = {item["id"]: item for item in list_companion_agents(platform, cfg=effective)}
    if requested_agent_id:
        requested = _normalize_agent_id(requested_agent_id)
        selected = agents.get(requested)
        if selected and selected["enabled"] and (selected["selectable"] or not require_selectable):
            return requested
    default_agent = agents.get(default_agent_id)
    if default_agent and default_agent["enabled"] and (default_agent["selectable"] or not require_selectable):
        return default_agent_id
    for agent in agents.values():
        if agent["enabled"] and (agent["selectable"] or not require_selectable):
            return agent["id"]
    return default_agent_id


def get_agent_identity_dir(agent_id: str | None = None, cfg: dict[str, Any] | None = None) -> Path:
    effective = cfg or get_agent_config()
    resolved_id = _normalize_agent_id(agent_id or get_default_agent_id(effective))
    agent_dir = _AGENTS_DIR / resolved_id / "identity"
    if agent_dir.exists():
        return agent_dir
    if resolved_id == get_default_agent_id(effective):
        return _IDENTITY_DIR
    return agent_dir


def get_identity_files_meta(agent_id: str | None = None) -> dict[str, int]:
    """Return {filename: char_count} for each identity file that exists."""
    result: dict[str, int] = {}
    for fname in ("agent.md", "soul.md", "user.md"):
        path = get_agent_identity_dir(agent_id) / fname
        if path.exists():
            try:
                result[fname] = len(path.read_text(encoding="utf-8").strip())
            except OSError:
                pass
    return result


def get_identity_files_text(agent_id: str | None = None) -> dict[str, str]:
    """Return {filename: text} for each identity file that exists."""
    result: dict[str, str] = {}
    for fname in ("agent.md", "soul.md", "user.md"):
        path = get_agent_identity_dir(agent_id) / fname
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    result[fname] = text
            except OSError:
                pass
    return result


def _load_identity_files(agent_id: str | None = None) -> str:
    """Load agent.md, soul.md, user.md from data/identity/.

    Returns combined text with agent name header.
    Falls back to _build_core_block(cfg) if no files exist.
    """
    root_cfg = get_agent_config()
    companion_cfg = get_companion_agent(agent_id, root_cfg)
    agent_name = companion_cfg.get("agent_name", "Agent")
    identity_dir = get_agent_identity_dir(companion_cfg["id"], root_cfg)

    file_parts: list[str] = []
    for filename in ("agent.md", "soul.md", "user.md"):
        path = identity_dir / filename
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    file_parts.append(text)
            except OSError as exc:
                logger.warning("Failed to read %s: %s", path, exc)

    if not file_parts:
        return _build_core_block(companion_cfg)

    return "\n\n".join([f"You are {agent_name}."] + file_parts)


def group_mention_tag(name: str) -> str:
    """The canonical @mention token for a participant name (spaces removed)."""
    return "@" + "".join(str(name or "").split())


def _build_group_chat_block(participants: list[dict], self_id: str) -> str:
    """Dynamic roster injected for every agent in a command-center group chat.

    The behavioral rules live in the companion's editable `command` platform
    awareness (so they can be customized per companion); this block only supplies
    the live participant list — names, nicknames, and @mention tags.
    """
    if not participants:
        return ""

    def _line(p: dict) -> str:
        name = str(p.get("name", "")).strip()
        tag = group_mention_tag(name)
        aliases = [str(a).strip() for a in (p.get("aliases") or []) if str(a).strip()]
        alias_str = f" — also answers to: {', '.join(aliases)}" if aliases else ""
        if p.get("type") == "user":
            return f"- {name} ({tag}){alias_str} — the human user"
        marker = "  ← this is you" if p.get("id") == self_id else ""
        return f"- {name} ({tag}){alias_str}{marker}"

    user_lines = [_line(p) for p in participants if p.get("type") == "user" and str(p.get("name", "")).strip()]
    agent_lines = [_line(p) for p in participants if p.get("type") != "user" and str(p.get("name", "")).strip()]
    roster = "\n".join(user_lines + agent_lines)

    return (
        "## Group Chat — Who's Here\n"
        "You are in a group conversation with the people below. Incoming messages are labeled `@Name:` "
        "so you can tell who is speaking. Reply by naming whoever you are addressing — their name or "
        "any nickname listed is enough.\n\n"
        f"**Participants:**\n{roster}"
    )


def _get_platform_awareness(cfg: dict[str, Any], platform: str) -> str:
    raw = cfg.get("platform_awareness")
    if isinstance(raw, dict):
        typed = cast(dict[str, str], raw)
        if platform == "command":
            return typed.get("command") or typed.get("discord") or ""
        return typed.get(platform) or ""
    if isinstance(raw, str):
        return raw
    return ""


def build_system_prompt(
    context: MessageContext,
    facts: dict[str, str],
    memory_files: str = "",
    stm_bridge: str = "",
    library_context: str = "",
) -> str:
    """Flat string version used by Ollama adapter."""
    blocks = build_system_prompt_blocks(context, facts, memory_files, stm_bridge, library_context)
    return "\n\n".join(b.get("text", "") for b in blocks if isinstance(b, dict))


def build_system_prompt_blocks(
    context: MessageContext,
    facts: dict[str, str],
    memory_files: str = "",
    stm_bridge: str = "",
    library_context: str = "",
) -> list[dict]:
    """Return the system prompt as a list of Anthropic content blocks.

    Block 0 (static, cache_control=ephemeral): identity, platform rules, memory files, facts.
    Block 1 (dynamic, no cache): STM bridge + SL sensor context + recent locations.
    Block 2 (uncached, optional): always-on library modules — separate to preserve Block 0 cache.
    """
    root_cfg = get_agent_config()
    agent_id = resolve_platform_agent_id(
        context.platform,
        context.agent_id,
        require_selectable=context.platform == "command",
        cfg=root_cfg,
    )
    companion_cfg = get_companion_agent(agent_id, root_cfg)

    static_parts: list[str] = [_load_identity_files(agent_id)]

    platform_awareness: str = _get_platform_awareness(companion_cfg, context.platform)
    if platform_awareness:
        static_parts.append(platform_awareness)

    if context.group_participants:
        group_block = _build_group_chat_block(context.group_participants, companion_cfg["id"])
        if group_block:
            static_parts.append(group_block)

    if companion_cfg.get("additional_context"):
        static_parts.append(f"## Additional Context\n{companion_cfg['additional_context']}")

    if memory_files:
        static_parts.append(memory_files)
    elif facts:
        # Fallback: inject raw facts when no curated memory files exist yet
        facts_lines = "\n".join(f"- {k}: {v}" for k, v in facts.items())
        static_parts.append(f"## Known Facts About the User\n{facts_lines}")

    static_block: dict = {
        "type": "text",
        "text": "\n\n".join(static_parts),
        "cache_control": {"type": "ephemeral"},
    }

    # Dynamic block: STM bridge + SL sensor/location data
    dynamic_parts: list[str] = []
    if stm_bridge:
        dynamic_parts.append(stm_bridge)
    if context.platform != "discord":
        if context.sl_sensor_context:
            sensor_text = _format_sensor_context(context.sl_sensor_context)
            if sensor_text:
                dynamic_parts.append(sensor_text)
        if context.sl_recent_locations:
            dynamic_parts.append(_format_recent_locations(context.sl_recent_locations))
        if context.sl_known_avatar:
            dynamic_parts.append(_format_known_avatar(context.sl_known_avatar))
        if context.sl_relationship:
            dynamic_parts.append(context.sl_relationship)

    blocks: list[dict] = [static_block]

    if dynamic_parts:
        blocks.append({"type": "text", "text": "\n\n".join(dynamic_parts)})

    if library_context:
        blocks.append({"type": "text", "text": library_context})

    return blocks


# ------------------------------------------------------------------ formatters

def _format_recent_locations(locations: list[dict]) -> str:
    if not locations:
        return ""
    lines = ["## Places You've Visited (most recent first)"]
    for loc in locations:
        region = loc.get("region", "?")
        parcel = loc.get("parcel", "?")
        desc = loc.get("parcel_desc", "").strip()
        last = loc.get("last_visited", "")[:10]
        line = f"- {region} / {parcel} (last visited {last})"
        if desc:
            line += f" — {desc[:120]}"
        lines.append(line)
    return "\n".join(lines)


def _format_known_avatar(av: dict) -> str:
    lines = ["## This Conversation's Avatar"]
    lines.append(f"Display name: {av.get('display_name', '?')}")
    if av.get("sl_uuid"):
        lines.append(f"SL UUID: {av['sl_uuid']}")
    channels = ", ".join(av.get("channels", []))
    if channels:
        lines.append(f"Channels seen: {channels}")
    first = av.get("first_seen", "")[:10]
    last = av.get("last_seen", "")[:10]
    if first:
        lines.append(f"First seen: {first}" + (f" · Last seen: {last}" if last != first else ""))
    return "\n".join(lines)


def _age_label(ages: dict, key: str) -> str:
    secs = ages.get(key)
    if secs is None:
        return ""
    if secs < 60:
        return f" [{secs}s ago]"
    return f" [{secs // 60}m ago]"


def _format_sensor_context(ctx: dict) -> str:
    lines = ["## Sensory Context (live data from agent HUD)"]
    ages: dict = ctx.get("_ages", {})

    env = ctx.get("environment")
    if env:
        env_lines = [f"Location{_age_label(ages, 'environment')}:"]
        env_lines.append(f"  Region: {env.get('region', '?')}")
        parcel = env.get('parcel', '?')
        rating = env.get('rating', '')
        env_lines.append(f"  Parcel: {parcel}" + (f" [{rating}]" if rating else ""))
        desc = env.get("parcel_desc", "").strip()
        if desc:
            env_lines.append(f"  Description: {desc}")
        env_lines.append(
            f"  Time: {env.get('time_of_day', '?')} | "
            f"Avatars in region: {env.get('avatar_count', '?')}"
        )
        lines.append("\n".join(env_lines))

    avatars = ctx.get("avatars")
    if avatars:
        av_parts = []
        for a in avatars:
            entry = f"{a.get('name', '?')} ({a.get('distance', '?')}m)"
            if a.get("key"):
                entry += f" [UUID: {a['key']}]"
            av_parts.append(entry)
        lines.append(f"Nearby avatars{_age_label(ages, 'avatars')}: {', '.join(av_parts)}")

    objects = ctx.get("objects")
    if objects:
        # Group by (name, owner) to collapse multiple instances of the same object
        groups: dict = {}
        for o in objects:
            key = (o.get("name", "?"), o.get("owner", ""))
            if key not in groups:
                groups[key] = []
            groups[key].append(o)
        sorted_groups = sorted(
            groups.items(),
            key=lambda kv: min((o.get("distance") or 9999) for o in kv[1]),
        )
        obj_lines = []
        for (name, owner), objs in sorted_groups:
            dists = sorted(o.get("distance") or 0 for o in objs)
            count = len(objs)
            dist_str = ", ".join(f"{d}m" for d in dists)
            entry = f"  - {name}" + (f" ×{count}" if count > 1 else "") + f" ({dist_str})"
            if any(o.get("scripted") for o in objs):
                entry += " [scripted]"
            if owner:
                entry += f" — owner: {owner}"
            desc = next((o["description"] for o in objs if o.get("description")), "")
            if desc:
                entry += f" — {desc}"
            obj_lines.append(entry)
        lines.append(f"Nearby objects{_age_label(ages, 'objects')}:\n" + "\n".join(obj_lines))

    clothing = ctx.get("clothing")
    if clothing:
        parts = []
        attach = clothing.get("attachments", "").strip()
        layers = clothing.get("layers", "").strip()
        if attach:
            parts.append(f"Attachments: {attach}")
        if layers:
            parts.append(f"System layers: {layers}")
        if parts:
            lines.append(f"Trixxie's outfit{_age_label(ages, 'clothing')}: {' | '.join(parts)}")

    rlv = ctx.get("rlv")
    if rlv:
        rlv_parts = []
        if rlv.get("teleported"):
            rlv_parts.append("just teleported to this location")
        if rlv.get("on_object"):
            obj = rlv.get("sitting_on", "").strip()
            rlv_parts.append(f"sitting on: {obj}" if obj else "sitting on an object")
        elif rlv.get("sitting"):
            rlv_parts.append("sitting on the ground")
        if rlv.get("autopilot"):
            rlv_parts.append("being moved by autopilot — likely leashed or force-walked")
        if rlv.get("flying"):
            rlv_parts.append("flying")
        pos = rlv.get("position")
        if pos and len(pos) == 3:
            rlv_parts.append(f"position: {pos[0]}, {pos[1]}, {pos[2]}")
        if rlv_parts:
            lines.append(f"Avatar state{_age_label(ages, 'rlv')}: {'; '.join(rlv_parts)}")

    chat_events = ctx.get("chat")
    if chat_events:
        lines.append(f"Nearby chat{_age_label(ages, 'chat')}:")
        for ev in chat_events[-10:]:
            if isinstance(ev, str):
                lines.append(f"  {ev}")
            elif isinstance(ev, dict):
                lines.append(f"  [{ev.get('speaker', '?')}] {ev.get('message', '')}")

    return "\n".join(lines) if len(lines) > 1 else ""
