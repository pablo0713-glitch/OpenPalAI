# Trixxie — Friendly Companion Agent

AI companion powered by Claude (claude-sonnet-4-6), running simultaneously on Discord and Second Life via a shared AgentCore. This is a personal project turned into a general-purpose framework.

## Run

```bash
./run.sh          # activates .venv and starts main.py
python main.py    # manual equivalent
```

SL bridge always starts. Discord bot only starts if `DISCORD_TOKEN` is set.

## Key Files

```
main.py                          Entry point — asyncio.gather() over three tasks
config/settings.py               All config loaded from .env via load_settings()
core/agent.py                    AgentCore — shared brain, async tool loop (MAX_TOOL_ROUNDS=5)
core/persona.py                  System prompt assembly + MessageContext dataclass + companion registry
core/model_adapter.py            ModelAdapter — wraps AsyncAnthropic + Ollama; prompt caching
core/tools.py                    ToolRegistry — platform-filtered, per-companion tool dispatch
memory/file_store.py             FileMemoryStore — JSON files, agent-scoped paths, legacy fallback
memory/consolidator.py           MemoryConsolidator — background Claude-written notes, per-agent (6h)
memory/person_map.py             PersonMap — links Discord + SL IDs to canonical person
memory/location_store.py         LocationStore — SL region/parcel visit history
memory/session_index.py          SessionIndex — SQLite FTS5 index, agent_id column, per-agent search
interfaces/discord_bot/bot.py    TrixxieBot — discord.py client
interfaces/sl_bridge/server.py   FastAPI bridge — /sl/message and /sl/sensor endpoints
interfaces/sl_bridge/sensor_store.py  SensorStore — in-memory sensor snapshot per region
interfaces/command_center.py     Command center API — chat, history, status with agent selection
interfaces/setup_server.py       Setup wizard API — GET/POST /setup/config
interfaces/debug_server.py       Debug page — logs (SSE), sensors, prompts + messages array
setup/wizard.js                  9-step config wizard (agent, model, platforms, persona, save)
command/app.js                   Command center browser logic — agent selector + per-agent chat
command/index.html               Command center UI — includes companion selector widget
lsl/companion_bridge.lsl         LSL HUD script worn by Trixxie's avatar (Mono compiler)
data/person_map.json             Canonical identity → platform user ID list
data/agent_config.json           Multi-agent companion registry (see MULTI_AGENT_MIGRATION.md)
MULTI_AGENT_MIGRATION.md         Full migration plan, what changed, pending phases
```

## Architecture in One Paragraph

Every message (Discord @mention/DM or SL /42 channel) goes through `AgentCore.handle_message()`. It resolves the active `agent_id` from `MessageContext`, loads agent-scoped history, facts, memory notes, and cross-platform context, then calls `build_system_prompt_blocks()` which returns two Anthropic content blocks — Block 0 (static: identity + platform awareness + memory summary + facts, marked `cache_control: ephemeral`) and Block 1 (dynamic: sensor context + locations, SL only, never cached). The model adapter runs the async tool loop. All turns including tool_use/tool_result blocks are persisted under the agent's memory namespace. The SL bridge also receives fire-and-forget sensor POSTs from the HUD (avatars, environment, chat, objects, clothing) stored in `SensorStore` and injected into Block 1 on the next message.

## Multi-Agent Architecture (Phase 1 Complete)

**See `MULTI_AGENT_MIGRATION.md` for the full plan, implementation details, and pending phases.**

The framework now supports a companion registry. `agent_config.json` stores multiple companion definitions under an `agents` dict keyed by `agent_id`. Every request carries an `agent_id` through `MessageContext`, and all memory paths, session index queries, tool configs, and consolidation runs are scoped to that agent.

Key public API in `core/persona.py`:
- `get_default_agent_id(cfg=None)` — resolves the configured default
- `get_companion_agent(agent_id=None, cfg=None)` — returns a normalized companion dict
- `list_companion_agents(platform=None, selectable_only=False)` — sorted list for UI
- `resolve_platform_agent_id(platform, requested=None)` — correct way to determine which companion handles a request
- `get_agent_identity_dir(agent_id=None)` — per-agent identity dir with legacy fallback

**Do not** read `get_agent_config().get("tools")` inside request handlers — use `get_companion_agent(context.agent_id)` instead.

## Platform Rules

- User IDs are namespaced: `discord_{snowflake}` and `sl_{uuid}`
- `MessageContext.platform` drives all platform differences; `MessageContext.agent_id` drives all companion differences
- `sl_action` tool is only available when `platform == "sl"`
- SL bridge always returns HTTP 200 — errors go in the JSON body (LSL throttle protection)
- Discord and SL resolve their companion via `resolve_platform_agent_id("discord")` / `resolve_platform_agent_id("sl")` — no live switching on those platforms today

## Memory Layout

```
data/memory/{safe_user_id}/            Legacy flat paths — still read for default agent compat
    {channel_id}.json
    _facts.json
    locations.json                     SL visit history (LocationStore)
    _cross_summary.txt                 cached cross-platform context summary
data/memory/agents/{agent_id}/{safe_user_id}/   Per-agent paths (new writes go here)
    {channel_id}.json
    _facts.json
    stm.json                           Short-term memory for this agent × user
    MEMORY.md                          Curated long-term notes (Hermes-style §-delimited)
data/identity/                         Legacy identity dir (agent.md, soul.md, user.md)
data/agents/{agent_id}/identity/       Per-agent identity files (override legacy)
data/notes/{agent_id}/{person_id}/
    memories_YYYY-MM-DD.md             Per-agent audit trail of consolidated notes
```

Consolidation triggers when **total turns across all files for a person × agent** exceeds **30**. Trims all files for that person to 10 turns after writing notes.

**Memory namespace for vector store:** `{agent_id}::{person_id}` — use `_memory_namespace()` from `file_store.py`.

## LSL Script Constraints (lsl/companion_bridge.lsl)

- Compiled with **Mono** (512 KB) — not LSO (64 KB). Do not reintroduce LSO-era memory caps.
- `json_s()` escapes `\\ " \n \t` only — `\r` is NOT a valid escape in LSL (it is the literal letter r).
- Avatar scan: 25 closest in region, sorted by distance via `llGetAgentList` + `llGetObjectDetails`.
- Reply chunking: `send_chunked()` splits at sentence boundaries (≤1000 chars per IM).
- Chat buffer: 10-line rolling window on channel 0, pre-escaped on store.
- `SECRET` and `SERVER_URL` are set at the top of the script; `SECRET` must match `SL_BRIDGE_SECRET`.

## Python Conventions

- Always `AsyncAnthropic` — never the sync client. The sync client blocks the event loop.
- Concurrent writes to memory files are serialized by per-(agent_id, user_id, channel_id) `asyncio.Lock`.
- `_serialize_content()` in `file_store.py` uses direct attribute access (`getattr`) — not `model_dump()` — to avoid Pydantic MockValSer on Python 3.14.
- `build_system_prompt_blocks()` returns `list[dict]` (two Anthropic content blocks). Never pass a flat string to `_run_tool_loop` — it expects the block list.
- `_get_platform_awareness(cfg, platform)` reads `cfg["platform_awareness"][platform]` — wizard-editable, not hardcoded.
- New tools: add schema to `core/tools.py`, handler to `core/tool_handlers/`, register in `ToolRegistry`.
- `resolve_platform_agent_id(platform, requested)` is the correct entry point for picking a companion — use it in every platform handler.

## Environment Variables (.env)

| Key | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Required |
| `DISCORD_TOKEN` | Optional — Discord bot skips if unset |
| `DISCORD_ALLOWED_GUILD_IDS` | Comma-separated guild IDs (empty = all guilds) |
| `DISCORD_ACTIVE_CHANNEL_IDS` | Channels where Trixxie responds without @mention |
| `SL_BRIDGE_SECRET` | Optional shared secret — must match `SECRET` in LSL script |
| `SL_BRIDGE_PORT` | Default 8080 |
| `SEARCH_PROVIDER` | `brave` or `serper` |
| `SEARCH_API_KEY` | Brave or Serper key |
| `MEMORY_MAX_HISTORY` | Turns kept per conversation file (default 20) |
| `OWNER_NAME` | Your name — used in memory notes and context; set via wizard Step 1 |

## Do Not

- Do not use `model_dump()` on Anthropic SDK response objects
- Do not add synchronous HTTP calls inside async handlers
- Do not commit `.env`, `.venv/`, or `data/memory/` (all gitignored)
- Do not reintroduce LSO memory workarounds (AV_MAX<25, message caps, loop candidate caps)
- Do not read tool config from `get_agent_config()` — use `get_companion_agent(context.agent_id)`
- Do not hardcode memory paths — always route through `_agent_root()` / `_memory_namespace()` in `file_store.py`
