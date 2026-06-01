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

_DEFAULT_CONFIG: dict = {
    "agent_name": "Aria",
    "command_center_name": "Command Center",
    "agent_profile_image": "",
    "additional_context": "",
    "tools": {
        "web_search": True,
        "notes": True,
        "sl_action": True,
        "voice": False,
    },
    "platform_awareness": {
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
    },
    "supporting_agents": {
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
    },
}

# ------------------------------------------------------------------ config cache

_agent_config_cache: dict[str, Any] | None = None


def get_default_config() -> dict[str, Any]:
    return copy.deepcopy(_DEFAULT_CONFIG)


def get_agent_config() -> dict[str, Any]:
    global _agent_config_cache
    if _agent_config_cache is not None:
        return _agent_config_cache
    if _AGENT_CONFIG_PATH.exists():
        try:
            data: dict[str, Any] = json.loads(_AGENT_CONFIG_PATH.read_text(encoding="utf-8"))
            _agent_config_cache = data
            return data
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
    guild_id: int | None = None
    person_id: str = ""     # canonical person ID resolved from PersonMap; falls back to user_id
    sl_region: str | None = None
    sl_grid: str = "sl"
    sl_client: str = "lsl"   # "lsl" (HUD /42) or "lua" (Cool VL Viewer direct IM)
    sl_sensor_context: dict = field(default_factory=dict)
    sl_recent_locations: list[dict] = field(default_factory=list)
    sl_known_avatar: dict | None = None
    sl_relationship: str = ""


# ------------------------------------------------------------------ prompt assembly

def _build_core_block(cfg: dict) -> str:
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


def get_identity_files_meta() -> dict[str, int]:
    """Return {filename: char_count} for each identity file that exists."""
    result: dict[str, int] = {}
    for fname in ("agent.md", "soul.md", "user.md"):
        path = _IDENTITY_DIR / fname
        if path.exists():
            try:
                result[fname] = len(path.read_text(encoding="utf-8").strip())
            except OSError:
                pass
    return result


def get_identity_files_text() -> dict[str, str]:
    """Return {filename: text} for each identity file that exists."""
    result: dict[str, str] = {}
    for fname in ("agent.md", "soul.md", "user.md"):
        path = _IDENTITY_DIR / fname
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    result[fname] = text
            except OSError:
                pass
    return result


def _load_identity_files() -> str:
    """Load agent.md, soul.md, user.md from data/identity/.

    Returns combined text with agent name header.
    Falls back to _build_core_block(cfg) if no files exist.
    """
    cfg = get_agent_config()
    agent_name = cfg.get("agent_name", "Agent")

    file_parts: list[str] = []
    for filename in ("agent.md", "soul.md", "user.md"):
        path = _IDENTITY_DIR / filename
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    file_parts.append(text)
            except OSError as exc:
                logger.warning("Failed to read %s: %s", path, exc)

    if not file_parts:
        return _build_core_block(cfg)

    return "\n\n".join([f"You are {agent_name}."] + file_parts)


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
    cfg = get_agent_config()

    static_parts: list[str] = [_load_identity_files()]

    platform_awareness: str = _get_platform_awareness(cfg, context.platform)
    if platform_awareness:
        static_parts.append(platform_awareness)

    if cfg.get("additional_context"):
        static_parts.append(f"## Additional Context\n{cfg['additional_context']}")

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
