# Trixxie Companion Agent — Agent Guide

This file is the canonical project guide for coding agents working in this repo. `CLAUDE.md` and `GEMINI.md` intentionally point here so implementation guidance stays in one place.

## Project Identity

Trixxie is a self-hosted companion-agent framework for Command Center browser chat, Discord, Second Life, and OpenSimulator. It is a personal companion system turned into a reusable framework: multi-companion, multi-platform, memory-heavy, and designed for long-running relationships rather than one-off chat.

The main promise is ownership and continuity: the user controls the code, model provider, data, identity files, memory archive, and platform bridges.

## Core Architecture

Every platform request flows through `AgentCore.handle_message()` in `core/agent.py`.

The high-level flow is:

1. Platform handler creates `MessageContext`.
2. `AgentCore` resolves canonical person identity through `PersonMap`.
3. Agent-scoped recent history, curated memory, STM bridge, sensor context, and library modules are loaded.
4. `build_system_prompt_blocks()` assembles Anthropic-style prompt blocks.
5. The async tool loop runs through `ModelAdapter`.
6. Successful user and assistant turns are persisted and indexed.
7. Background jobs update STM, score importance, consolidate memory, and backfill vectors.

Important files:

```text
main.py                          App entry point and background task startup
config/settings.py               Env-backed runtime settings
config/paths.py                  Sandbox-aware data/.env path helpers
core/agent.py                    Shared brain and tool loop
core/persona.py                  Companion registry, identity files, prompt assembly
core/model_adapter.py            Anthropic/OpenAI-compatible/local provider adapter
core/tools.py                    Tool schemas and dispatch
memory/file_store.py             Recent JSON conversation history + indexing hook
memory/session_index.py          SQLite FTS5 archive, importance, consolidation state
memory/vector_store.py           ChromaDB semantic memory
memory/consolidator.py           Background scoring and durable memory consolidation
memory/person_map.py             Canonical identity map
interfaces/command_center.py     Browser chat, uploads, group chat, library browser
interfaces/debug_server.py       Debug UI including Memory Pipeline
interfaces/setup_server.py       Setup wizard API and config writes
interfaces/sl_bridge/server.py   SL/OpenSim HTTP bridge
interfaces/discord_bot/bot.py    Discord client
setup/wizard.js                  Browser setup wizard
command/app.js                   Command Center frontend
lua/agent_companion.lua.template Cool VL Viewer automation template
lsl/companion_bridge.lsl.template LSL HUD fallback/object scanner
```

## Run And Verify

Local direct run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python check_install.py
./run.sh
```

Windows direct run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python check_install.py
.\run.bat
```

Compile check after Python edits:

```bash
python -m compileall main.py core interfaces memory config check_install.py
```

## Persistent Sandboxes

Use sandboxes for stable testing without touching live/local `data/` or `.env`.

Linux/Fedora/Podman sandbox:

```bash
./scripts/sandbox-linux.sh up
./scripts/sandbox-linux.sh logs
./scripts/sandbox-linux.sh down
```

Windows PowerShell sandbox:

```powershell
.\scripts\sandbox-windows.ps1 check
.\scripts\sandbox-windows.ps1 up
```

Sandbox state:

```text
.sandbox/linux/.env
.sandbox/linux/data/
.sandbox/linux/cache/

.sandbox/windows/.env
.sandbox/windows/data/
.sandbox/windows/.venv/
```

Path isolation is implemented with:

- `TRIXXIE_DATA_DIR`
- `TRIXXIE_ENV_FILE`
- `MEMORY_DIR`
- `NOTES_DIR`
- `LIBRARY_DIR`

Pull live VPS data into a sandbox only when needed:

```bash
REMOTE=user@host REMOTE_PATH=/path/to/companion-agent ./scripts/pull-live-data.sh
```

```powershell
.\scripts\pull-live-data-windows.ps1 -Remote user@host -RemotePath /path/to/companion-agent
```

By default, live `.env`, ChromaDB vectors, and cache are not copied. Let Chroma rebuild locally from `sessions.db` unless a test specifically needs the live vector store.

See `SANDBOXES.md` for details.

## Memory System

The memory architecture is intentionally layered:

- Recent JSON conversation files for short working context.
- `sessions.db` as the durable source of truth for all turns.
- SQLite FTS5 for keyword/name search.
- ChromaDB for semantic recall.
- `MEMORY.md` and `USER.md` as bounded curated notes.
- `person_map.json` linking Command Center, Discord, and SL IDs to one canonical person.
- STM bridge for recent cross-platform summaries.
- Library modules for reference material and lore.

The canonical owner identity is the setup wizard's Command Center Name. Raw IDs such as `command_user_*`, `discord_*`, and `sl_*` link beneath it.

Durable consolidation is session-index driven:

1. Unscored rows in `sessions.db` are scored by `MemoryCuratorAgent`.
2. Scores are written to SQLite and mirrored into Chroma metadata.
3. Rows with `importance >= IMPORTANCE_THRESHOLD` and `consolidated_at = ''` become consolidation candidates.
4. The curator gate may skip low-value transcript batches.
5. Consolidated or skipped source rows are marked with `consolidated_at` and `consolidation_run_id`.
6. Audit notes and provenance are written under `data/notes/{agent_id}/{person_id}/`.

Do not return consolidation to a JSON-file threshold model. JSON files are recent context only; `sessions.db` is the durable archive.

Key docs:

- `MEMORY_SYSTEM.md` — technical reference
- `data/library/memory_system.md` — agent-facing memory self-knowledge module
- `ARCHITECTURE.md` — full architecture notes

## Multi-Companion Rules

`data/agent_config.json` stores companion registry data:

- `default_agent_id`
- `command_center_name`
- `agents`
- `supporting_agents`

Every request should carry an `agent_id`. Use these APIs from `core/persona.py`:

- `get_default_agent_id(cfg=None)`
- `get_companion_agent(agent_id=None, cfg=None)`
- `list_companion_agents(platform=None, selectable_only=False, cfg=None)`
- `resolve_platform_agent_id(platform, requested=None, require_selectable=False, cfg=None)`
- `get_agent_identity_dir(agent_id=None)`

Do not read tool config from `get_agent_config().get("tools")` inside request handlers. Use `get_companion_agent(context.agent_id)`.

## Platform Rules

- User IDs are namespaced: `command_user_*`, `discord_*`, `sl_*`.
- `MessageContext.platform` drives platform behavior.
- `MessageContext.agent_id` drives companion behavior.
- `sl_action` is only available when `platform == "sl"`.
- SL bridge returns HTTP 200 with errors in JSON body to avoid LSL throttle/retry problems.
- Discord and SL currently use default platform bindings, while Command Center supports active companion selection and group chat.

## Prompt And Tool Rules

- Use `AsyncAnthropic`; do not use sync clients in async handlers.
- `build_system_prompt_blocks()` returns a list of Anthropic content blocks. Do not flatten it before calling the tool loop.
- Prompt Block 0 is the cache anchor: identity, platform awareness, and curated memory.
- Dynamic sensor context, STM bridge, and library modules should stay out of the cached static block.
- New tools need schema in `core/tools.py`, handler in `core/tool_handlers/`, and registration in `ToolRegistry`.

## File And Data Path Rules

- Runtime data must respect `TRIXXIE_DATA_DIR`.
- Runtime `.env` must respect `TRIXXIE_ENV_FILE`.
- Do not hardcode `data/...` for config, identity, memory, notes, library, or person map paths.
- Prefer existing helpers and store APIs:
  - `FileMemoryStore`
  - `SessionIndex`
  - `VectorMemoryStore`
  - `PersonMap`
  - setup server path globals derived from `config.paths`

## LSL And Lua Constraints

- Cool VL Viewer Lua is the preferred SL automation path.
- LSL HUD remains available as fallback/object scanner.
- LSL should compile with Mono, not LSO.
- Do not reintroduce LSO-era memory reductions without a clear reason.
- Keep OpenSimulator HTTP body limits in mind.
- `SECRET` and `SERVER_URL` in generated scripts must match `.env` / setup wizard config.

## Engineering Standards

- Make small, surgical changes.
- Preserve unrelated user changes.
- Avoid speculative abstractions.
- Prefer repo patterns over new frameworks.
- Use `rg` for search.
- Use `apply_patch` for manual edits.
- For frontend changes, keep Command Center practical and workflow-focused.
- For memory changes, preserve observability in `/debug` Memory Pipeline.

## Do Not

- Do not commit `.env`, `.venv/`, `.sandbox/`, or runtime `data/`.
- Do not use `model_dump()` on Anthropic SDK response objects.
- Do not add blocking HTTP or filesystem-heavy operations inside async request handlers without executor/thread handling.
- Do not make memory consolidation depend on trimmed JSON history.
- Do not bypass `PersonMap` for canonical identity.
- Do not treat silence from `asyncio.create_task()` background jobs as success; add logs or debug state when changing them.

## Useful Commands

```bash
python check_install.py
python -m compileall main.py core interfaces memory config check_install.py
./scripts/sandbox-linux.sh up
./scripts/sandbox-linux.sh logs
REMOTE=user@host REMOTE_PATH=/path/to/companion-agent ./scripts/pull-live-data.sh
```

```powershell
.\scripts\sandbox-windows.ps1 check
.\scripts\sandbox-windows.ps1 up
.\scripts\pull-live-data-windows.ps1 -Remote user@host -RemotePath /path/to/companion-agent
```
