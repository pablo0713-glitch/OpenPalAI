# Changelog

All notable changes to Trixxie Companion Agent are documented here.

---

## 2026-06-02

### Fixed

- **Per-companion model selection** — the model is now saved **per companion** instead of being a single global value that the last-configured agent overwrote (which forced every companion onto the same model). Each companion stores its own `model_override` (`{model_provider, model_name}`); wizard **Step 2** is now a per-companion step (the companion bar appears on it), while API keys and base URLs remain shared across companions. At runtime `AgentCore._adapter_for(agent_id)` resolves and caches a `ModelAdapter` from each companion's `model_override`, falling back to the global `.env` adapter when a companion has none. The `.env` model fields now mirror the **default** companion (the fallback used by supporting agents). New `make_adapter(settings, provider, model_name)` factory in `core/model_adapter.py` (used by `create_adapter`, `make_supporting_adapter`, and per-companion resolution).

---

## 2026-06-01

### Added

- **Multi-Companion Registry** (`core/persona.py`) — `agent_config.json` is now a companion registry (`agents: { id: {...} }`) with a `default_agent_id`. Every request carries an `agent_id` through `MessageContext`, and all memory paths, session-index queries, tool config, consolidation runs, and identity dirs are scoped per companion. Legacy single-agent installs are auto-migrated on load (`_legacy_to_registry()`) with read fallback so existing data is never lost. New public API: `get_default_agent_id()`, `get_companion_agent()`, `list_companion_agents()`, `resolve_platform_agent_id()`, `get_agent_identity_dir()`. See `MULTI_AGENT_MIGRATION.md`.

- **Command-center companion switching** — `/command/status`, `/command/chat`, and `/command/history` accept an `agent_id`; the command center UI has an **Active Companion** selector with separate per-companion memory.

- **Wizard multi-companion CRUD** (`setup/wizard.js`, `interfaces/setup_server.py`) — A companion selector bar on the per-companion wizard steps lets you create, edit, rename, and delete companions. `POST /setup/companion` and `DELETE /setup/companion/{id}` manage the registry and per-agent identity dirs (`data/agents/{id}/identity/`). The wizard saves the normalized `agents` registry. A notice clarifies that extra companions are Command-Center-only today (see Notes).

- **Companion aliases / nicknames** — each companion has an `aliases` list (wizard Step 1), mirroring the LSL `TRIGGER_NAMES` concept. In command-center group chat a companion responds when addressed by its name **or** any alias (case-insensitive, plus `@name` forms and bare first names). The participant roster injected into each prompt lists every companion's nicknames.

- **Editable group-chat rules** — the group-chat conduct rules now live in each companion's **Command Center platform awareness** (`platform_awareness.command`, editable in wizard Step 6), so each agent can have its own group-chat style. `_build_group_chat_block()` now injects only the dynamic participant roster (names, nicknames, tags). Addressing is **name-based** — a reply must include the name/nickname of whoever it answers; `@mention` is an optional fallback, no longer required. The hardcoded "Group chat ready…" placeholder header was removed from the command-center UI.

- **Command-center group chat** (`interfaces/command_center.py`, `command/`) — Multiple companions converse in one thread with name-based addressing (Discord-style `@mention` works as a fallback). Naming a companion signals it to respond, driving a cascade; each participant's system prompt carries the editable conduct rules plus the live roster. `_orchestrate_group_chat()` runs each responder through the normal `handle_message` pipeline (so group turns persist into each companion's own agent-scoped history and feed memory/consolidation), feeding each one only the labeled transcript delta it hasn't seen (per-agent cursors). An un-addressed message is answered by every selected companion; cascade and cost are bounded by `_GROUP_MAX_TURNS=8` / `_GROUP_MAX_PER_AGENT=2`. Endpoints: `POST /command/group-chat`, `GET /command/group-history`. The shared transcript lives in `data/memory/groups/`. UI adds a **Group chat** toggle, a participant picker, and per-companion avatar bubbles.

- **Command Center** (`interfaces/command_center.py`, `command/`) — New unified web control surface at `/command`. Combines browser chat, a native library browser, the existing setup wizard, and the existing debug page into one entry point. `/` now redirects to `/command`.

- **Browser chat uploads** — The command-center chat panel accepts images, text-like documents, PDF, and DOCX uploads and routes them through the normal `AgentCore` message path rather than a separate simplified handler.

- **PDF/DOCX extraction** — PDF uploads preserve page boundaries and use layout-aware extraction when available; DOCX uploads extract paragraph text, tables rendered as markdown, and embedded image metadata for chat and library-ingest flows.

- **Library ingest from uploads** — Command-center document uploads can be converted directly into `data/library/*.md` modules with generated front-matter, extracted text, and source metadata.

- **Library browser** — New `/command/library*` endpoints and matching UI for listing modules, previewing content, toggling `always_on`, refreshing, and deleting modules without leaving the command center.

### Changed

- **Primary web entry point** — `/command` is now the intended browser surface. `/setup` and `/debug` remain available directly, but are embedded inside the command center.

- **`AgentCore.handle_message(..., *, skip_rate_limit=False)`** — the group-chat orchestrator bypasses the per-user rate limiter during a cascade (turn caps bound cost instead). The single-agent path is unchanged.

- **Dependencies** — Added `pypdf` and `python-docx` to support PDF and DOCX parsing.

### Fixed

- **Generated library-module front-matter** — Command-center ingest now writes array fields in a format the existing `LibraryStore` parser can read reliably.

- **Command-center backend import path** — Added the missing `json` import used when writing generated library modules.

- **Setup-server form endpoints returning 422** — `_LibraryWriteBody`, `_AgentsCfgBody`, and the new `_CompanionCreateBody` were defined inside the router function. Under `from __future__ import annotations`, FastAPI cannot resolve Pydantic body models in local scope, so `POST /setup/library` and `POST /setup/agents` (library editor + Step-7 supporting-agents save) were silently failing. Hoisted to module scope.

### Notes

- **Extra companions are Command-Center-only for now** — additional companions (beyond the default) are fully functional in the command center, including group chat. Second Life and Discord still resolve to the **default companion** only; per-platform companion binding is Phase 4 (`platform_bindings` is already modeled in `agent_config.json`). The setup wizard surfaces this limitation inline.

## 2026-05-25

### Added

- **Multi-Agent Architecture** — `SupportingAgent` base class (`core/supporting_agent.py`) for specialist background agents. Each agent has its own `ModelAdapter` (independently configurable provider + model via the wizard's new Agents step), a focused system prompt, and an `asyncio.Lock`. `make_supporting_adapter()` reads `agent_config.json["supporting_agents"]` and falls back to the main model when unconfigured.

- **Memory Curator Agent** (`core/memory_curator.py`) — Scores every conversation turn 0.0–1.0 for long-term value. Batches 20 turns per `create_simple()` call (Haiku by default). Sentinel: -1.0 = unscored. `should_consolidate()` acts as a lightweight gate before the full consolidation model call. `_extract_json()` uses `re.search(r"\{.*\}", text, DOTALL)` as a fallback when the model wraps JSON in prose or markdown fences.

- **Importance scoring column in `sessions.db`** — `importance REAL DEFAULT -1.0`. Migrated via `_MIGRATE_IMPORTANCE_STMTS` (follows existing migration pattern). New `SessionIndex` methods: `set_importance_batch()` (single-transaction bulk update for all scores), `get_unscored_turns()`, `get_high_importance_turns()`. `index_turn()` now returns `int | None` (the inserted row id) — non-breaking.

- **Semantic Memory (ChromaDB)** (`memory/vector_store.py`) — `VectorMemoryStore` wraps a ChromaDB PersistentClient at `data/memory/chroma/`. Bundled ONNXMiniLM-L6-v2 embeddings — no PyTorch or sentence-transformers. All ChromaDB calls run in `run_in_executor(None, …)` to avoid blocking the event loop. One collection per `person_id` (`mem_{safe_id}`). Doc ID = SQLite rowid — links FTS5 and vector stores permanently.

- **Startup backfill** — `_backfill_vector_store()` in `main.py` indexes all existing `sessions.db` rows into ChromaDB on startup. Runs as a fire-and-forget background task in batches of 100 with 100 ms sleep. Idempotent via `has_document()`.

- **Semantic Recall Agent** (`core/recall_agent.py`) — Wraps `VectorMemoryStore.semantic_search()` with a reasoning pass that filters noise and annotates which results are actually relevant. Available as the `semantic_recall` tool when wired. Result format: `[PLATFORM | DATE | NAME · role | sim:0.87] content...`.

- **Library System** (`memory/library_store.py`, `data/library/`) — Drop-in Markdown reference modules with YAML-like front-matter (no PyYAML dep). Fields: `id`, `title`, `description`, `always_on`, `platforms`, `tags`. Always-on modules injected into Block 2 (uncached) on every matching-platform message, capped at `library_always_on_cap` chars. On-demand modules retrieved via the `library_lookup` tool.

- **Librarian Agent** (`core/librarian_agent.py`) — Retrieves relevant library modules using a keyword search followed by a reasoning pass. Avoids returning irrelevant keyword matches by reasoning about the current context before returning results.

- **System Prompt Block 2** — New uncached block inserted between Block 0 (static, cached) and Block 1 (dynamic) for always-on library modules. Block 0's `cache_control: ephemeral` remains stable.

- **Wizard Step 7 "Agents"** — New 8th step between Context and Save. Per-agent provider dropdown + model name input for `memory_curator`, `librarian`, and `semantic_recall`. Reads from and writes to `agent_config.json["supporting_agents"]`. Leave model blank to inherit the main agent's model.

- **Library CRUD API** — `GET/POST /setup/library` and `GET/DELETE /setup/library/{id}` endpoints in `interfaces/setup_server.py`. Supports creating, reading, listing, and deleting library modules from the wizard or directly via API.

- **`GET /setup/agents`** and **`POST /setup/agents`** — Read and update the `supporting_agents` config block. `POST` calls `reload_agent_config()` so changes take effect without a full restart.

- **`run.bat`** — Windows launcher equivalent of `run.sh`. Creates the venv if it doesn't exist, activates it, and starts `main.py`.

- **`check_install.py`** — Installation smoke test. Verifies 21 required files and 37 module imports (including all Phase 2 additions) without starting any server or writing to `data/`. Platform-aware: checks `run.bat` on Windows, `run.sh` on Linux/Mac. Exit 0 = clean install, exit 1 = something missing or unimportable.

- **CI: `.github/workflows/install-check.yml`** — Runs `pip install -r requirements.txt` + `python check_install.py` on every push and PR to `main`. Matrix: `ubuntu-latest` × `windows-latest` × Python 3.11 + 3.12 (4 jobs).

- **Documentation** — `ARCHITECTURE.md` fully updated to reflect Phase 2 (multi-agent diagram, memory layers, system prompt Block 2, threading diagram). New `MEMORY_SYSTEM.md` is a comprehensive standalone reference for all 6 memory layers, the consolidation pipeline, supporting agent models, environment variables, and a full test checklist.

### Changed

- **Memory consolidation pipeline** now scores unscored turns via `MemoryCuratorAgent` before building the transcript, filters the transcript to high-importance turns (≥ `importance_threshold`, default 0.6), and uses `should_consolidate()` as a gate before invoking the main model. Behavior is unchanged when no curator is wired.
- **`FileMemoryStore.append_turn()`** fires `_index_and_vectorize()` as a background task after each write — chains `SessionIndex.index_turn()` (returns row id) → `VectorMemoryStore.add_turn()`.
- **SQLite WAL mode** enabled on `sessions.db` via `PRAGMA journal_mode=WAL`. Prevents "database is locked" errors when the startup backfill and importance score writes run concurrently.
- **Wizard step count** increased from 7 to 8. Old Step 7 (Save) is now Step 8.
- **`chromadb>=1.5.9`** added to `requirements.txt` as a required dependency.
- **README** updated: capabilities table, wizard step-by-step, memory section (7-layer table + consolidation pipeline + library module guide), project layout, environment variables, troubleshooting.

### Fixed

- **`MemoryCuratorAgent` JSON truncation** — `max_tokens` raised from 256 to 600 for scoring batches. At 256, responses for 20-turn batches were truncated mid-JSON, causing silent fallback to empty score maps.
- **`data/agent_config.json` control characters** — Pre-existing issue where literal newline bytes inside JSON string values caused `json.loads()` to fail at startup. Detected and re-serialized cleanly.
- **Wizard "Step 7" script section references** — Wizard UI and README updated to reflect correct step numbers after inserting the new Agents step.

---

## 2026-05-12

### Added
- **Hybrid Architecture (Cool VL Viewer Native Lua)** — Migrated heavy sensory load (Avatars, Environment, Avatar State, and Ambient Chat) directly into the viewer's `automation.lua` scripting engine natively. This comprehensively resolves the out-of-memory crashes experienced with LSL HUDs in highly congested sims! 

### Fixed
- **Radar Distance Math** — Corrected astronomical distance values reported by the agent's radar by extracting pure `global_x` and `global_y` properties direct from `GetRadarData` via `pairs()` looping rather than using unsupported legacy vector arrays.


### Known Issues

- **LSL HUD stops responding to touch after extended uptime** — After running for some time, the HUD no longer responds to clicks (control panel doesn't open, sensor toggles stop working). Sensory data stops reaching the agent. Root cause is low or out of memory issue with LSL Mono. ~~**Workaround:** right-click the HUD object → Edit → Scripts → Reset Scripts, then close the editor. This resets script state without needing to detach and re-wear.~~

**Note:** The script will now auto reset when memory gets too low (this is the main culprit of the HUD not responding). 

---

## 2026-04-27

### Fixed

- **SL agent silent failure (history corruption loop)** — When the Anthropic API returned `stop_reason=end_turn` with an empty content block, the assistant turn was saved to history before the error was detected. On the next message, the model saw the empty turn and returned empty again, compounding indefinitely. Three changes in `core/agent.py` break the cycle:
  - `_sanitize_history()` now strips dangling `assistant[tool_use] + user[tool_result]` pairs (no final assistant response) and all trailing plain user turns before each API call.
  - The user turn is now persisted only **after** a successful non-empty reply, not before the tool loop runs.
  - `_run_tool_loop()` retries once when `stop_reason=end_turn` but text is empty, then returns a fallback string if still empty after the retry.

- **Wizard "Update Scripts" JSON parse error** — `res.json()` threw when the server returned an HTML error page (e.g. a 500). The fetch now wraps JSON parsing in a try/catch and falls back to `res.text()` to display the raw HTTP status and body.

- **LSL/Lua scripts not refreshing after `git pull`** — `_patch_scripts()` previously only copied the template when the output file was absent. Now `patch_scripts_from_env()` (called on every startup) uses `force_template=True`, which always copies the template before patching. `_template_has_changed()` compares credential-normalized content so purely cosmetic credential differences don't count as structural changes.

- **Wizard Step 7 script section not appearing** — The script section was gated on `state.sl_enabled`, which is only set when `SL_BRIDGE_SECRET` or `SL_BRIDGE_URL` appears in `.env`. Users who set up scripts manually (without using the wizard) never had these in `.env`, so the section was always hidden. Gate removed — the section always renders on Step 7.

- **Wizard Step 7 buttons absent on fresh remote deploy** — Generated scripts (`companion_bridge.lsl`, `agent_companion.lua`) are gitignored and only exist after the agent runs `patch_scripts_from_env()` on startup. On a fresh `git pull` before the first run, both were null and no buttons rendered. `bindStep7()` now auto-calls `POST /setup/update-scripts` silently when scripts are missing but a bridge URL is in state, then re-fetches before rendering.

- **Misleading Lua log on HTTP reply** — `OnHTTPReply` printed `"actions field is nil/absent in response"` whenever a reply had no action payloads — which is the normal case for most messages. Log line removed.

- **LSL HUD event queue flooding in busy regions** — The channel 0 listener (local chat) was always registered, consuming one of the 64 LSL event queue slots continuously in crowded sims and silently dropping `touch_start` events (HUD unresponsive). Channel 0 is now only registered when `s_chat = TRUE`.

### Added

- **LSL user-configurable time intervals** — Stream mode sensor intervals (`AV_TICKS`, `OBJ_TICKS`, `ENV_TICKS`, `CHAT_TICKS`, `RLV_TICKS`) were moved to the top of the LSL script config section. This is a QoL customization option to help manage data overhead until v2.0 solves the blind resend logic that contributes to "HUD memory low" resets.

- **`GET /setup/scripts` endpoint** (`interfaces/setup_server.py`) — Returns the patched LSL and Lua script content plus an `updated_on_startup` boolean flag. Used by `bindStep7()` to fetch scripts without exposing them in the initial page HTML.

- **Wizard Step 7 — Copy and Save buttons for LSL and Lua scripts** — Step 7 fetches both scripts from `/setup/scripts` and holds their content in memory only (never written to the DOM). Two buttons per script: **Copy** sends the full content to the clipboard; **Save** triggers a browser download with the correct filename. Useful for recovering a lost HUD or installing the Lua script from the settings page without a terminal. Script content is never visible in the page source or browser inspector.

- **Startup script update banner** — When `patch_scripts_from_env()` detects that a git pull brought in a structurally different template (new variables, new sections), it sets `_startup_script_updated = True`. Step 7 displays a yellow warning banner prompting the user to recopy the LSL script to their HUD and replace the Lua file.

---

## 2026-04-05 (v1.0 public release prep)

- Initial public release. See `whats-in-v10.md` for the full v1.0 feature set.

---

## Format

This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.
Categories used: **Added**, **Changed**, **Fixed**, **Removed**.
