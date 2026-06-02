# Trixxie — Friendly Companion Agent — Architecture

## Overview

Trixxie is a stateful AI agent built around a single shared core (`AgentCore`) that serves two platform interfaces simultaneously plus a unified web control surface. The core handles identity, memory, tool use, and the Claude API loop. The interfaces handle platform-specific protocol, formatting, and delivery.

```
┌─────────────────────────────────────────────────────┐
│                      AgentCore                      │
│  system prompt · tool loop · memory · rate limiting │
└──────────────────┬──────────────────┬───────────────┘
                   │                  │
     ┌─────────────▼──────┐  ┌────────▼──────────────┐
     │   Discord Bot      │  │   SL HTTP Bridge      │
     │   (discord.py)     │  │   (FastAPI + uvicorn) │
     │                    │  │                       │
     │   @mention / DM    │  │   POST /sl/message    │
     │   → AgentCore      │  │   ← JSON reply        │
     │   ← chunked reply  │  │                       │
     └────────────────────┘  └──────┬─────────┬──────┘
                                     │         │
                          Browser UI │         │ llHTTPRequest
                   ┌─────────────────▼──┐  ┌──▼─────────────────┐
                   │  Command Center     │  │  LSL HUD            │
                   │  /command           │  │  (worn by Trixxie)  │
                   │                     │  │                     │
                   │  chat / library /   │  │  /42 msg → POST     │
                   │  setup / debug      │  │  sensor data → POST │
                   └──────────┬──────────┘  │  reply → llIM       │
                              │             └─────────────────────┘
                     PostHTTP │
                   ┌──────────▼──────────┐
                   │  Cool VL Viewer     │
                   │  automation.lua     │
                   │                     │
                   │  private IM → POST  │
                   │  typing indicator   │
                   │  reply → SendIM     │
                   └─────────────────────┘
```

Both interfaces and the web control surface share the same `AgentCore`, `FileMemoryStore`, `LocationStore`, and `AvatarStore`. A `PersonMap` links platform-specific user IDs to a canonical person identity so that conversations on either platform inform the same memory context. The web command center reuses the same `AgentCore` path for browser chat, document uploads, and library-module management rather than maintaining a separate toy inference path.

---

## Component Map

```
main.py                          Entry point. Starts Discord bot, SL HTTP bridge,
                                 and memory consolidation loop concurrently via
                                 asyncio.gather().
run.sh                           Linux/Mac launcher. Activates .venv and starts main.py.
run.bat                          Windows launcher. Creates .venv if absent, activates,
                                 starts main.py.
check_install.py                 Installation smoke test. Verifies required files and
                                 module imports without starting any server or writing
                                 to data/. Platform-aware (run.sh vs run.bat check).
                                 Exit 0 = clean, exit 1 = broken.
.github/workflows/
  install-check.yml              CI workflow. Runs pip install + check_install.py on
                                 every push/PR. Matrix: ubuntu + windows × Py 3.11 + 3.12.

config/
  settings.py                    Loads all configuration from environment variables.
                                 Single Settings dataclass passed everywhere.

core/
  agent.py          AgentCore    Central message handler. Loads history + facts,
                                 resolves person_id via PersonMap, loads curated
                                 memory files (MEMORY.md + USER.md) and cross-platform
                                 STM bridge, builds system prompt, runs the Claude tool
                                 loop, persists all turns, returns AgentResponse.
                                 Uses AsyncAnthropic — fully non-blocking.
                                 After each exchange: fire-and-forget _append_stm_entry()
                                 generates a 1–2 sentence summary and appends it to
                                 stm.json (rolling 10 entries) for cross-platform bridging.
                                 History sanitization: _sanitize_history() strips two
                                 classes of tail corruption before each call — dangling
                                 tool-use cycles (assistant[tool_use] + user[tool_result]
                                 with no final assistant turn) and accumulated unresponded
                                 user messages (consecutive plain user turns saved during
                                 prior empty responses). User turn is persisted only after
                                 a successful non-empty reply, preventing accumulation.
                                 Empty-response retry: _run_tool_loop() retries once when
                                 stop_reason=end_turn but response text is empty, then
                                 returns a fallback string if still empty.

  persona.py        Persona      Identity-file-based persona. _load_identity_files()
                                 reads data/identity/agent.md + soul.md + user.md
                                 (created by the wizard); falls back to
                                 _build_core_block(cfg) if no files exist.
                                 Platform awareness is wizard-editable per platform
                                 (discord / sl / opensim) via _get_platform_awareness().
                                 MessageContext carries platform, user, channel, person_id
                                 (canonical, set by AgentCore), sensor data, and locations.
                                 build_system_prompt_blocks() returns two Anthropic content
                                 blocks: Block 0 (static: identity files + platform +
                                 context + MEMORY.md + USER.md, cache_control=ephemeral) +
                                 Block 1 (dynamic: STM bridge + sensor context + locations).
                                 Objects in the sensor block are grouped by (name, owner)
                                 with ×N count and distance list.

  model_adapter.py  ModelAdapter Abstract adapter over the model client.
                                 AnthropicAdapter wraps AsyncAnthropic; accepts system
                                 as str or list[dict]. When a list is passed, adds the
                                 anthropic-beta: prompt-caching-2024-07-31 header so
                                 the static identity block is eligible for caching.
                                 OllamaAdapter wraps openai.AsyncOpenAI pointed at
                                 the Ollama /v1 endpoint, with full Anthropic↔OpenAI
                                 message format conversion. _flatten_system_blocks()
                                 merges content-block lists to a plain string for Ollama.
                                 ModelResponse.history_content is always Anthropic-
                                 format dicts regardless of provider — FileMemoryStore
                                 always receives plain dicts.

  supporting_agent.py SupportingAgent  Base class for all specialist background agents.
                                 Each instance holds its own ModelAdapter (allowing a
                                 different provider/model than the main agent) and an
                                 asyncio.Lock that prevents concurrent runs.
                                 run(user_message, max_tokens) → str calls
                                 adapter.create_simple() with the agent's focused system
                                 prompt. No memory, tools, or persona — scoped calls only.
                                 make_supporting_adapter(settings, agent_cfg, agent_name)
                                 reads agent_cfg["supporting_agents"][name] and overrides
                                 provider + model on a copy of Settings; falls back to the
                                 main model if unconfigured.

  memory_curator.py MemoryCuratorAgent(SupportingAgent)
                                 Scores conversation turns 0.0–1.0 for long-term value.
                                 score_turns(turns) → dict[int, float]: batches 20 turns
                                 per create_simple() call; asks for JSON
                                 {"scores":[{"id":int,"score":float}...]}; _extract_json()
                                 strips prose/fences before parsing; falls back to {} on
                                 error (turns stay -1.0, retried next cycle). max_tokens=600.
                                 should_consolidate(transcript, existing_memory) → bool:
                                 lightweight gate before the full consolidation model call;
                                 defaults True on any error.

  librarian_agent.py LibrarianAgent(SupportingAgent)
                                 Retrieves relevant library modules using a reasoning pass.
                                 find_relevant(query, context_summary) → list[LibraryModule]:
                                 1. LibraryStore.search() for keyword candidates
                                 2. create_simple() to rank/filter by relevance
                                 3. Returns final list with relevance reasoning.
                                 get_module(module_id) → str: direct retrieval, no reasoning.

  recall_agent.py   SemanticRecallAgent(SupportingAgent)
                                 Wraps VectorMemoryStore with a reasoning pass.
                                 recall(person_id, query, n_results, importance_threshold)
                                 → str: 1. vector_store.semantic_search() for candidates
                                 2. create_simple() to filter noise + annotate relevance
                                 3. Returns formatted, annotated results. Falls back to raw
                                 results when the reasoning call fails.

  tools.py          ToolRegistry Holds tool schemas and dispatch logic.
                                 get_definitions(context) filters by platform —
                                 sl_action is only included when platform == "sl".
                                 session_search/query included when SessionIndex is wired.
                                 library_lookup/list included when LibrarianAgent is wired.
                                 semantic_recall included when SemanticRecallAgent is wired.

  rate_limiter.py   RateLimiter  Per-user token bucket. In-memory. Prevents runaway
                                 usage — a polite slowdown, not a hard block.

  tool_handlers/
    web_search.py                Brave or Serper Search API. Returns formatted
                                 title/snippet/URL list to Claude.
    sl_action.py                 Appends to an action_queue list. Actions flush
                                 back to the interface after the loop ends.
    notes.py                     Per-user flat-file note storage. One .txt per note.
    memory.py                    Curates MEMORY.md and USER.md for the current person.
                                 §-delimited entries; actions: add, replace, remove.
                                 Enforces char caps (MEMORY: 2,000 / USER: 1,200).
                                 _scan_entry() blocks prompt-injection phrases,
                                 credential-format strings (API keys, SSH headers),
                                 shell injection, and invisible Unicode before writing.
                                 Consolidator path is also scanned.
    session_search.py            Wraps SessionIndex.search() for in-conversation recall.
                                 Returns platform + date + display_name + FTS snippet list.
                                 Not user-scoped — all conversations are searchable.
    session_query.py             Structured SQL query tool (speakers / turns modes).
                                 Supports date_from/date_to, platform, include_names,
                                 exclude_names, and limit filters.
    library.py                   Delegates to LibrarianAgent.find_relevant() or
                                 direct LibraryStore.get_by_id(). handle_library_list()
                                 returns metadata-only list (no reasoning pass needed).
    semantic_recall.py           Delegates to SemanticRecallAgent.recall(). Returns
                                 formatted results with similarity score:
                                 [PLATFORM | DATE | NAME · role | sim:0.87] content...

memory/
  base.py           AbstractMemoryStore   Interface contract. Async methods:
                                          get_history, append_turn, get_facts,
                                          upsert_fact, get_all_conversations.
                                          append_turn() accepts person_id as keyword arg
                                          (default "") for vector indexing.
  file_store.py     FileMemoryStore       JSON files on disk. Per-(user,channel)
                                          asyncio.Lock prevents write races.
                                          _serialize_content() converts Anthropic SDK
                                          objects to plain dicts via direct attribute
                                          access (avoids Pydantic MockValSer on Py 3.14).
                                          append_turn() fires _index_and_vectorize() as a
                                          background task — chains SessionIndex.index_turn()
                                          (returns row id) → VectorMemoryStore.add_turn()
                                          when vector_store and person_id are set.
                                          _sanitize_tool_pairs() filters empty-content
                                          turns before orphan-cleanup passes — prevents
                                          invalid turns from accumulating via history trim.
  schemas.py                              Pydantic models for JSON file structure.
  person_map.py     PersonMap             Loads data/person_map.json. Maps canonical
                                          person IDs ↔ platform user IDs.
  consolidator.py   MemoryConsolidator    Background task (every 6 hours). When
                                          MemoryCuratorAgent is wired:
                                          1. Calls curator.score_turns() on all unscored
                                          turns per user_id, writes scores via
                                          session_index.set_importance_batch() in one tx.
                                          2. Filters transcript to high-importance turns
                                          (threshold default 0.6).
                                          3. curator.should_consolidate() gate — skips if
                                          the curator says nothing new is worth adding.
                                          Keeps markdown audit trail at
                                          data/notes/SL_Notes/memories_YYYY-MM-DD.md.
  session_index.py  SessionIndex          SQLite FTS5 index of all conversation turns.
                                          WAL mode enabled for concurrent read + write.
                                          Lazy-init; schema created on first write.
                                          index_turn() inserts into sessions table +
                                          triggers FTS5 update. Returns int | None (row id).
                                          importance column (REAL, default -1.0 sentinel)
                                          added via _MIGRATE_IMPORTANCE_STMTS.
                                          set_importance_batch(scores) — single-transaction
                                          UPDATE for all scores in one open/close cycle.
                                          get_unscored_turns(user_id) / get_high_importance_turns()
                                          for curator scoring pipeline.
                                          Database: data/memory/sessions.db.
  vector_store.py   VectorMemoryStore     ChromaDB PersistentClient at
                                          {memory_dir}/chroma/. Required dep.
                                          One collection per person_id: mem_{safe_id}.
                                          ALL public methods run in run_in_executor(None,…)
                                          — ChromaDB is synchronous; executor prevents
                                          event-loop blocking.
                                          add_turn(person_id, session_id, content, metadata)
                                          upserts by str(session_id) doc ID.
                                          semantic_search(person_id, query, n_results,
                                          importance_threshold) — optional where filter by
                                          importance. Returns list of result dicts.
                                          has_document(person_id, session_id) — used by
                                          the startup backfill to avoid re-indexing.
  library_store.py  LibraryStore          Parses data/library/*.md files with inline
                                          YAML-like front-matter (no PyYAML dep).
                                          LibraryModule dataclass: id, title, description,
                                          always_on, platforms, tags, content, char_count.
                                          get_always_on(platform) — modules to inject into
                                          Block 2 on every message.
                                          search(query, limit) — keyword match across
                                          title + description + tags.
                                          list_modules() — metadata only (no full content).
  location_store.py LocationStore         Persists SL region/parcel visit history.
                                          Per-user asyncio.Lock. Deduplicates by
                                          region+parcel key.
  avatar_store.py   AvatarStore           Global registry of SL avatars Trixxie has
                                          spoken with. Single asyncio.Lock (file-level).
                                          record_encounter(user_id, display_name, channel)
                                          upserts on every /sl/message. get_avatar_async()
                                          returns the entry for Block 1 injection.
                                          File: data/memory/known_avatars.json.

data/
  identity/
    agent.md                              Role, purpose, behaviors, boundaries, RP rules.
    soul.md                               Tone, humor, quirks, conversational style.
    user.md                               Owner profile (name, role, preferences).
  person_map.json                         Canonical identity → platform ID list.
  library/
    *.md                                  Library modules with YAML front-matter block.
                                          Fields: id, title, description, always_on (bool),
                                          platforms (list), tags (list). Content follows.
                                          always_on modules injected into Block 2 on every
                                          message (capped at library_always_on_cap chars).
                                          On-demand modules retrieved via library_lookup tool.
  memory/{safe_user_id}/
    {channel_id}.json                     Conversation turns per channel.
    _facts.json                           Persistent key/value facts about the user.
    stm.json                              Short-term memory: rolling 10 exchange summaries
                                          (1–2 sentences each), used as cross-platform bridge.
    locations.json                        SL visit history (LocationStore).
  memory/known_avatars.json               Global AvatarStore registry. Maps sl_{uuid} →
                                          {display_name, first_seen, last_seen, channels[]}.
                                          Not per-user — one file covering all SL avatars.
  memory/{safe_person_id}/
    MEMORY.md                             Agent-curated notes about context and world
                                          (~2,000 chars max; §-delimited entries).
    USER.md                               Owner preferences, style, background
                                          (~1,200 chars max; §-delimited entries).
  memory/sessions.db                      SQLite FTS5 index + importance scores.
                                          WAL mode. Columns: id, user_id, channel_id,
                                          platform, role, content, timestamp, display_name,
                                          importance (REAL, default -1.0 = unscored).
  memory/chroma/                          ChromaDB persistent vector store.
                                          One collection per person_id: mem_{safe_id}.
                                          Populated by backfill task on startup + live
                                          append_turn() indexing.
  notes/SL_Notes/
    memories_YYYY-MM-DD.md                Consolidated memory notes audit trail.

interfaces/
  sl_bridge/
    server.py                             FastAPI HTTP bridge. Two endpoints:
                                          POST /sl/sensor — stores sensor data,
                                            records location visits on environment posts.
                                          POST /sl/message — records avatar encounter
                                            (AvatarStore), loads location history,
                                            calls SensorStore.get_changes() for this user,
                                            builds MessageContext (including sl_known_avatar),
                                            calls AgentCore.
                                          Always returns HTTP 200 — errors go in the
                                          JSON body to protect LSL's error throttle.
    sensor_store.py   SensorStore         In-memory snapshot of latest sensor data per
                                          region. Tracks per-type update timestamps and
                                          per-user last-delivered timestamps.
                                          get_changes(region, user_id) always returns
                                          environment and rlv (location + avatar state
                                          needed every turn); returns other types only
                                          when updated since the user's last message.
                                          Snapshot includes _ages dict (seconds since
                                          update) surfaced as labels in the system prompt.
    formatters.py                         Grid-aware reply cap: 4000 chars (SL) or 1800
                                          chars (OpenSim). Normalizes Unicode to ASCII.
                                          Strips non-BMP characters (U+10000+, i.e. emoji)
                                          — LSL cannot handle 4-byte UTF-8 sequences and
                                          produces garbled bytes (ð) without this filter.

  discord_bot/
    bot.py          TrixxieBot            discord.py Client. Responds to @mentions
                                          in servers and all DMs. Ignores own messages.
    formatters.py                         Splits long replies into ≤2,000-char chunks
                                          at sentence/paragraph boundaries.

lsl/
  companion_bridge.lsl                    LSL script worn as a HUD by Trixxie's avatar.
                                          Streams sensor data to /sl/sensor: avatars,
                                          environment (region, parcel, description, rating
                                          via llRequestSimulatorData/dataserver), objects
                                          (name, distance, scripted, description, owner),
                                          chat (90s flush + pre-message), rlv (avatar
                                          state: sitting, autopilot, teleport, position).
                                          Listens on channel 42 for /42 conversation —
                                          POSTs to /sl/message, delivers reply via
                                          llInstantMessage (send_chunked).
                                          Also listens on channel 0 for name-trigger:
                                          any name in TRIGGER_NAMES list (default:
                                          ["Trixxie", "Trix", "Trixx"]) triggers is_triggered().
                                          POSTs to /sl/message (channel 0), delivers
                                          reply via llSay(0, say_chunked) — visible to
                                          all nearby as public local chat. Applies to all
                                          avatars including the owner.

lua/
  agent_companion.lua                   Cool VL Viewer automation script.
                                          Copy to user_settings/automation.lua.
                                          OnInstantMsg → PostHTTP → OnHTTPReply → SendIM.
                                          SetAgentTyping wraps inference for typing indicator.
                                          Chat context delivered via HUD sensor pipeline —
                                          no OnReceivedChat buffer in the Lua script.
                                          Replaces the /42 conversation path; sensor HUD
                                          remains required for environmental context.
                                          Echo suppression: sent_replies table stamps each
                                          outbound chunk before SendIM. Cool VL Viewer
                                          reflects sent IMs back through OnInstantMsg with
                                          the recipient UUID (bypasses the self-check).
                                          Chunks are matched against sent_replies within a
                                          10-second window and discarded if found, preventing
                                          loopback from triggering a second inference call.
                                          IMPORTANT: this script must only run on the agent's
                                          viewer. Running it on the owner's viewer causes the
                                          owner's viewer to forward the agent's replies back
                                          to the bridge, producing a hallucination loop.

command/
  index.html                              Unified command-center shell. Panels: Chat,
                                          Library, Setup, Debug.
  style.css                               Command-center styling. Chat composer,
                                          library browser, and embedded iframe panels.
  app.js                                  Client logic for /command. Handles chat sends,
                                          chat uploads, document-to-library ingest,
                                          library list/detail browsing, always_on toggle,
                                          and delete actions.

setup/
  index.html                              Wizard shell — step bar, content area, footer.
  style.css                               Dark theme, toggle switches, platform/tool cards.
  wizard.js                               8-step configuration wizard. Fetches current
                                          config on load, collects state per step, POSTs
                                          to /setup/config on save. Masked secrets pass
                                          through unchanged.
                                          Steps: Agent, Model, Platforms, Identity,
                                          Tools, Context, Agents, Save.
                                          Step 7 (Agents): per-agent model_provider +
                                          model_name dropdowns for memory_curator,
                                          librarian, and semantic_recall. Reads from and
                                          writes to agent_config["supporting_agents"] via
                                          the main POST /setup/config payload. Leave model
                                          blank to inherit the main agent's model.
                                          Step 8 (Save): always renders a script section.
                                          bindStep8() fetches GET /setup/scripts; if both
                                          scripts are null but a bridge URL is in state,
                                          auto-calls POST /setup/update-scripts to generate
                                          them before rendering. Renders one row per script
                                          (LSL + Lua) with Copy (clipboard) and Save
                                          (browser download) buttons. Script content is
                                          held in memory only — never placed in the DOM —
                                          so credentials are not exposed in the page source
                                          or browser inspector. If updated_on_startup is
                                          true, a yellow warning banner is displayed.

interfaces/
  command_center.py                       FastAPI APIRouter for the unified web control
                                          surface.
                                          GET /              — redirect to /command.
                                          GET /command       — command-center page.
                                          GET /command/status — model/provider/upload caps.
                                          POST /command/chat — browser chat entry point.
                                            Reuses AgentCore.handle_message() with
                                            synthetic command_* user/channel ids.
                                            Accepts text, images, text-like docs, PDF,
                                            and DOCX uploads.
                                          POST /command/library-upload — converts uploaded
                                            documents into data/library/*.md modules with
                                            generated front-matter and extracted text.
                                          GET /command/library — list library modules.
                                          GET /command/library/{module_id} — preview one.
                                          PATCH /command/library/{module_id} — toggle
                                            always_on for a module.
                                          DELETE /command/library/{module_id} — delete one.

  setup_server.py                         FastAPI APIRouter for the setup wizard.
                                          GET /setup, /setup/status, /setup/config.
                                          POST /setup/config — writes .env and
                                          agent_config.json (including supporting_agents
                                          block), calls reload_agent_config(), then runs
                                          _migrate_owner_key() which renames any non-SL_Notes
                                          key in person_map.json to SL_Notes and moves the
                                          notes folder accordingly.
                                          POST /setup/update-scripts — patches LSL + Lua.
                                          GET /setup/scripts — returns script content +
                                          updated_on_startup flag.
                                          GET/POST /setup/library — list or create library
                                          modules (LibraryWriteBody: filename + content).
                                          GET/DELETE /setup/library/{module_id} — read or
                                          delete a specific module by id.
                                          GET /setup/agents — returns supporting_agents
                                          block from agent_config.json.
                                          POST /setup/agents — saves supporting_agents
                                          block; calls reload_agent_config() immediately
                                          so changes take effect without full restart.
                                          patch_scripts_from_env() — called on every
                                          startup; _template_has_changed() compares
                                          normalized content to detect structural changes.

  debug_server.py                         FastAPI APIRouter for live agent inspection.
                                          Accepts session_index: SessionIndex | None as a
                                          third argument to create_debug_router().
                                          GET /debug — inline HTML debug page (three tabs).
                                            Header includes a red "Reset Memory" button that
                                            opens a confirmation modal before deletion.
                                          GET /debug/logs — SSE stream of all Python log
                                            records; client-side filter by level + logger.
                                            250ms poll loop; initial comment flushes headers
                                            immediately so EventSource.onopen fires.
                                          GET /debug/sensors — JSON snapshot of all
                                            SensorStore regions with per-type ages.
                                            Sensors tab shows raw JSON (left) and formatted
                                            plain-text panel (right): Objects with name,
                                            description, owner, distance; Avatars with name,
                                            distance; Environment; Chat; Clothing.
                                          GET /debug/prompts — last system prompt, full
                                            messages array (JSON), and exchange per user_id.
                                            Shows char counts per section and total payload
                                            size estimate (~system + messages).
                                            User selected via data-uid attribute on list items.
                                          DELETE /debug/reset-memory — wipes all agent state:
                                            truncates sessions.db (DELETE FROM sessions),
                                            resets session_index._ready = False,
                                            removes all per-user memory subdirs,
                                            deletes known_avatars.json + .last_consolidation,
                                            recreates empty notes dir,
                                            clears agent_core._last_prompt and _last_exchange.
                                            Returns {status: "ok"} on success. Confirmation
                                            modal in JS guards against accidental clicks.
                                          SSELogHandler bridges logging → asyncio.Queue.
                                          Fan-out broadcaster task copies records to all
                                          connected subscriber queues.
```

---

## Identity and Platform Linking

`data/person_map.json` maps a canonical person ID to all of their platform-specific user IDs:

```json
{
  "SL_Notes": [
    "discord_<snowflake>",
    "sl_<uuid>"
  ]
}
```

On every message, `AgentCore` calls:
- `PersonMap.get_person_id(user_id)` → canonical ID, used to load memory notes
- `PersonMap.get_linked_ids(user_id)` → all other platform IDs, used to load cross-platform context

User IDs are namespaced by platform (`discord_` / `sl_`) to prevent collisions. The person map is the only place where these identities are joined.

---

## The Agentic Tool Loop

Every message from either platform goes through the same loop in `AgentCore._run_tool_loop()`:

```
1. Build messages list = stored history + new user message
2. Call Claude API async (tools enabled, tool_choice="auto")
3. If stop_reason == "end_turn":
      extract text → return
4. If stop_reason == "tool_use":
      for each tool_use block:
          dispatch to tool handler
          if sl_action: append to action_queue (not executed yet)
      append tool_result turn
      go to step 2
5. After MAX_TOOL_ROUNDS (5), force tool_choice="none"
      get final text reply → return
```

The `action_queue` accumulates during the loop. After it ends, the SL interface flushes it — sending each action as an IM or emote via `llInstantMessage`. Discord ignores it.

All turns — including intermediate tool_use and tool_result blocks — are persisted to memory so the full context is replayable on the next message.

---

## Multi-Agent Architecture

Phase 2 introduced **supporting agents** — specialist background agents that assist the main agent without expanding its scope. Each supporting agent:

- Has its **own `ModelAdapter`** (provider + model independently configurable via the wizard's "Agents" step)
- Has a **focused system prompt** with no persona, memory, or tools
- Runs through `SupportingAgent.run()` → `adapter.create_simple()` — a single non-streaming call
- Uses an `asyncio.Lock` to prevent concurrent runs of the same agent

Supporting agents are **not** full `AgentCore` instances. They cannot call tools, update memory, or perceive sensors.

```
                          ┌──────────────────────────────────────┐
                          │             AgentCore                │
                          │  (main model: claude-sonnet-4-6)     │
                          └──────┬──────────┬──────────┬─────────┘
                                 │          │          │
                    tool call    │          │          │  6h cycle
                        ┌────────▼──┐  ┌───▼───────┐  │
                        │ Librarian │  │  Recall   │  │
                        │  Agent    │  │  Agent    │  │
                        │ (Haiku)   │  │ (Sonnet)  │  │
                        └──────┬────┘  └─────┬─────┘  │
                               │             │        ▼
                        LibraryStore   VectorStore  MemoryCurator
                                                      (Haiku)
                                                         │
                                                    score_turns()
                                                    → SessionIndex
```

### Agent configuration

`data/agent_config.json["supporting_agents"]` holds per-agent model config:

```json
{
  "supporting_agents": {
    "memory_curator":  { "model_provider": "anthropic", "model_name": "claude-haiku-4-5-20251001" },
    "librarian":       { "model_provider": "anthropic", "model_name": "claude-haiku-4-5-20251001" },
    "semantic_recall": { "model_provider": "anthropic", "model_name": "claude-sonnet-4-6" }
  }
}
```

`make_supporting_adapter(settings, agent_cfg, agent_name)` in `core/supporting_agent.py` reads this and returns a configured `ModelAdapter`. Falls back to the main model if unconfigured or empty.

### Invocation patterns

| Agent | When invoked | By whom |
|---|---|---|
| `MemoryCuratorAgent` | Every 6 h consolidation cycle | `MemoryConsolidator._check_and_consolidate()` |
| `LibrarianAgent` | `library_lookup` tool call | `AgentCore` tool loop → `ToolRegistry.dispatch()` |
| `SemanticRecallAgent` | `semantic_recall` tool call | `AgentCore` tool loop → `ToolRegistry.dispatch()` |

---

## Companion Registry & Group Chat

> Distinct from the **supporting agents** above. "Supporting agents" are background specialists with no persona. **Companions** are full `AgentCore` personas — multiple selectable characters. Full migration detail lives in `MULTI_AGENT_MIGRATION.md`.

### Companion registry

`data/agent_config.json` is a registry keyed by `agent_id`:

```json
{
  "default_agent_id": "aria",
  "command_center_name": "Command Center",
  "agents": {
    "aria": {
      "id": "aria",
      "agent_name": "Aria",
      "agent_profile_image": "",
      "aliases": ["Ari", "Riri"],
      "additional_context": "",
      "tools": { "web_search": true, "notes": true, "sl_action": true, "voice": false },
      "platform_awareness": { "command": "...incl. group chat rules...", "discord": "...", "sl": "...", "opensim": "..." },
      "platform_bindings": { "command": {"enabled": true, "selectable": true}, "discord": {"default": true}, "sl": {"embodied": true} },
      "model_override": { "model_provider": "anthropic", "model_name": "claude-opus-4-6" }
    }
  },
  "supporting_agents": { ... }
}
```

Every request carries an `agent_id` on `MessageContext`. All memory paths, the session index, the vector store, STM, consolidation, tool config, and identity dirs are scoped by it. Legacy single-agent configs are auto-migrated on load (`_legacy_to_registry()`), with read fallback so existing installs keep their data.

Key API in `core/persona.py`: `get_default_agent_id()`, `get_companion_agent(agent_id)`, `list_companion_agents(platform, selectable_only=)`, `resolve_platform_agent_id(platform, requested)`, `get_agent_identity_dir(agent_id)`. **Never** read persona/tool config from the global config inside a request handler — resolve the companion via `MessageContext.agent_id`.

Per-companion identity files live in `data/agents/{id}/identity/` (legacy `data/identity/` is the default agent's fallback). Per-companion memory lives under `data/memory/agents/{id}/{user}/`.

**Per-companion model:** each companion's `model_override` (`{model_provider, model_name}`) selects its model. At runtime `AgentCore._adapter_for(agent_id)` builds and caches a `ModelAdapter` from it (via `make_adapter()`), falling back to the global `.env` adapter when a companion has no override. API keys/base URLs are shared (global `.env`); only the provider + model name are per companion. The `.env` model fields mirror the default companion and back the supporting agents.

### Platform resolution

`resolve_platform_agent_id(platform, requested)` decides which companion handles a request: it honors an explicitly requested (and selectable) companion, else the configured default, else the first enabled one.

- **Command center** — passes the UI-selected `agent_id`; companions are switchable per request.
- **Discord / Second Life** — pass no request, so they always resolve to the **default** companion. Per-platform companion binding (`platform_bindings`) is modeled but **not yet wired** — extra companions are command-center-only today.

### Group chat (command center)

Multiple companions converse in one thread with Discord-style `@mention` routing. Orchestrated server-side in `interfaces/command_center.py`.

- **Rules (editable) + roster (dynamic)** — the behavioral rules live in each companion's **`command` platform awareness** (`platform_awareness.command`, editable in wizard Step 6), so they can be customized per companion. `_build_group_chat_block()` in `core/persona.py` adds only the live participant roster (triggered by `MessageContext.group_participants`) — each participant's name, configured **aliases/nicknames**, and `@mention` tag, with the active companion marked "← this is you". Incoming messages are labeled `@Name: ...`. Addressing is **name-based**: a reply must include the name (or any alias) of whoever it answers; `@mention` is an optional fallback. Naming a participant signals it to respond.
- **Aliases** — each companion has `aliases: []` (like the LSL `TRIGGER_NAMES`). `_agent_mention_ids()` matches a companion by its name **or** any alias (case-insensitive; `@name` forms and bare first names ≥3 chars), so being addressed by a nickname still pulls it in.

- **Orchestration** — `_orchestrate_group_chat()`:
  1. Appends the user message to a shared transcript (`data/memory/groups/{user}__{channel}.json`).
  2. Picks initial responders: agents named in the message, or **all** selected companions if none are named.
  3. Runs each responder through the normal `AgentCore.handle_message(..., skip_rate_limit=True)` — feeding it only the **labeled transcript delta it hasn't seen** (tracked via per-agent `cursors`). Because it's the normal pipeline, group turns persist into each companion's own agent-scoped history and feed STM/consolidation.
  4. Scans each reply for `@mentions`/names and enqueues those companions (the cascade).
  5. Bounds runaway with `_GROUP_MAX_TURNS=8` total and `_GROUP_MAX_PER_AGENT=2` per user message.

- **Endpoints** — `POST /command/group-chat` (returns ordered `replies`), `GET /command/group-history` (union transcript view). The group channel is namespaced `command_group_{conversation}`, separate from the 1:1 `command_chat_{conversation}` channel.

```
user message
     │  append to shared transcript
     ▼
initial responders (named, else all)
     │
     ▼  for each: handle_message(labeled delta, skip_rate_limit=True)
companion reply ──► persist to that companion's agent-scoped history
     │  scan reply for @mentions
     ▼
enqueue mentioned companions  ──►  (cascade, capped)
```

The shared transcript file is **only** the UI union view + delta cursors; per-agent history remains the source of truth for generation.

---

## Memory

### Conversation Files

History is persisted per `(user_id, channel_id)` pair as JSON files under `data/memory/{safe_user_id}/`. Each file is a `ConversationFile` with a `turns` array of `{role, content}` objects.

`FileMemoryStore` exposes:
- `get_history(user_id, channel_id)` — recent turns for the current conversation
- `get_facts(user_id)` — persisted key/value facts about the user (legacy fallback)
- `get_all_conversations(user_id)` — all files across all channels (used by the consolidator)
- `append_turn(...)` — appends a turn, trims to `memory_max_history`, and fires `SessionIndex.index_turn()` as a background task

### Curated Memory Files (Hermes-style)

Each canonical `person_id` has two bounded files in `data/memory/{safe_person_id}/`:

| File | Cap | Content |
|---|---|---|
| `MEMORY.md` | ~2,000 chars | Agent's notes about context, facts, and the world |
| `USER.md` | ~1,200 chars | Owner preferences, communication style, background |

Both use `§`-delimited entries. The agent curates these in real time via the `memory` tool (add / replace / remove). They are loaded once at the start of each `handle_message()` call and injected **frozen** into Block 0 — content doesn't change mid-session, which maximises cache stability.

Cap enforcement in `_load_memory_files()` calls `_trim_to_cap()` (entry-aware: drops oldest `§` entries until the file fits) — not a raw character slice. This ensures no entry is ever split mid-text at load time.

Injection format:
```
MEMORY (agent's notes) [42% — 840/2,000 chars]
§
User prefers short replies in-world.
§
YourAvatar owns the Nakano sim.

USER (owner profile) [61% — 732/1,200 chars]
§
Alex, goes by YourAvatar in SL. Builder and sim owner.
§
Prefers direct tone; dislikes over-explaining.
```

If `MEMORY.md` is absent, `get_facts()` is injected as a fallback (legacy transition path).

### Identity Files

Three markdown files in `data/identity/` define the agent's core persona, editable via the setup wizard:

| File | Content |
|---|---|
| `agent.md` | Role, purpose, behaviors, hard boundaries, RP rules |
| `soul.md` | Tone, humor, quirks, conversational style |
| `user.md` | Owner profile (single user) |

`_load_identity_files()` in `core/persona.py` reads these and joins them with `\n\n`. Falls back to `_build_core_block(cfg)` if the files don't exist (backwards compatibility).

### Importance Scoring

Every turn in `sessions.db` carries an `importance` score (REAL, sentinel -1.0 = unscored). `MemoryCuratorAgent.score_turns()` scores unscored turns in batches of 20 using `claude-haiku` (configurable). Scores written via `set_importance_batch()` in a single WAL transaction.

| Score | Meaning |
|---|---|
| 0.0 | Pure filler — greetings, one-word replies, social noise |
| 0.3 | Mild context — casual opinions, minor preferences |
| 0.6 | Notable — strong preference, ongoing project, revealed need |
| 1.0 | Pivotal — name, life event, explicit request to remember |

The `importance_threshold` setting (default 0.6) controls what graduates to long-term memory. Turns that score below threshold are kept in FTS5/vector indexes but excluded from consolidation transcripts.

### Memory Consolidation

`MemoryConsolidator` runs as a background task every 6 hours. The timer is restart-resilient — startup reads `.last_consolidation` timestamp from `data/memory/` and sleeps only the remaining interval.

Consolidation triggers when the **total turns across all files** for a person exceeds **30**. When triggered, it:

1. Calls `MemoryCuratorAgent.score_turns()` on all unscored turns for each linked user_id
2. Writes scores in one transaction via `SessionIndex.set_importance_batch()`
3. Builds a transcript filtered to high-importance turns (≥ threshold)
4. `curator.should_consolidate()` gate — if the curator says nothing new is worth adding, stops here
5. Calls the main model to write first-person bullet-point memory notes
6. Extracts each bullet and appends it to `MEMORY.md` via `_add_entry()` (oldest trimmed to maintain cap)
7. Keeps a full audit trail at `data/notes/SL_Notes/memories_YYYY-MM-DD.md`
8. Trims all source conversation files to their most recent **10 turns**

### Short-Term Memory Bridge (STM)

After every exchange, `_append_stm_entry()` fires as a background `asyncio.create_task`. It calls `create_simple()` to generate a 1–2 sentence third-person summary (max 120 chars) and appends it to `data/memory/{safe_uid}/stm.json` — a rolling window of 10 entries.

STM is **only** injected into Block 1 for **linked** platform UIDs (cross-platform bridge). The current conversation's own turns are already in the messages array and never duplicated.

```
## Recent Activity — DISCORD
User asked about mesh body options; agent recommended checking The Shops at Kukua.
---
User shared a screenshot of their avatar outfit; agent praised the color choices.
```

### Session Search (FTS5)

`SessionIndex` maintains a SQLite FTS5 full-text search index at `data/memory/sessions.db`. Every turn written via `FileMemoryStore.append_turn()` is automatically indexed (fire-and-forget background task).

The `session_search` tool lets the agent query past conversations mid-reply:
```
session_search(query="Botanical sim recommendations", limit=5)
→ [DISCORD | 2026-04-10 | assistant] "The [Botanical] sim has great atmosphere for..."
```

Results are not user-scoped — all of Trixxie's conversation history is searchable, enabling cross-user recall (e.g. "did someone named Flendo ever mention the Botanical sim?"). The `session_query` tool provides structured SQL-style access (speakers mode / turns mode) with date, platform, and name filters.

### Semantic (Vector) Memory

`VectorMemoryStore` wraps a ChromaDB PersistentClient at `data/memory/chroma/`. One collection per `person_id` (named `mem_{safe_id}`). Documents are indexed with the bundled ONNXMiniLM-L6-v2 embedding model — no PyTorch or sentence-transformers required. All ChromaDB calls run in `run_in_executor(None, …)` to avoid blocking the event loop.

**Write path:** `FileMemoryStore._index_and_vectorize()` chains `SessionIndex.index_turn()` (→ row id) → `VectorMemoryStore.add_turn()` using the returned row id as the stable doc ID. Metadata stored per doc: `user_id`, `channel_id`, `platform`, `role`, `timestamp`, `display_name`, `importance`.

**Startup backfill:** `_backfill_vector_store()` in `main.py` indexes all existing `sessions.db` rows not yet in ChromaDB. Runs as a fire-and-forget background task. Idempotent — `has_document()` prevents re-indexing.

**Query path:** `SemanticRecallAgent.recall()` calls `VectorMemoryStore.semantic_search()`, then passes the raw results to a `create_simple()` call that filters noise and annotates which results are actually relevant. Result format:
```
[SL | 2026-04-12 | StonedGrits · user | sim:0.87] We were talking about mesh bodies...
```

### Library System

`LibraryStore` reads `data/library/*.md` files with inline YAML-like front-matter (no external dep). Two modes:

**Always-on modules** (`always_on: true`) are injected into Block 2 on every message, up to `library_always_on_cap` chars (default 4,000). Block 2 is uncached to preserve Block 0's `cache_control: ephemeral`. Platform filtering via the `platforms` list — a module with `platforms: ["discord"]` does not appear in SL messages.

**On-demand modules** are retrieved by the agent via the `library_lookup` tool, which delegates to `LibrarianAgent.find_relevant()`. The librarian does a keyword search to get candidates, then a reasoning pass to filter by relevance to the current query context.

```markdown
---
id: sl_gorean_rp
title: Gorean Roleplay Setting
description: Reference guide for Gor-based RP in SL
always_on: false
platforms: ["sl"]
tags: ["roleplay", "gor"]
---
# full content here...
```

Manage modules via the command center at `/command` → Library, via the Chat panel's Library Ingest upload flow, or directly via the API (`GET/POST /setup/library`, `DELETE /setup/library/{id}`, `GET/PATCH/DELETE /command/library/{id}`). The command-center ingest path accepts text-like documents, PDF, and DOCX, generates valid front-matter automatically, and stores extracted text in `data/library/*.md`.

---

## Location Tracking

`LocationStore` persists a log of every distinct region/parcel Trixxie has visited, stored at `data/memory/{safe_user_id}/locations.json`.

**Write path:** the `/sl/sensor` endpoint calls `location_store.record_visit()` whenever `payload.type == "environment"`. A visit is "new" when the region or parcel differs from the most recent entry. Returning to the same parcel only refreshes `last_visited`. The HUD detects parcel changes via a `last_parcel` global and fires a new env scan within one timer tick (30 s).

**Read path:** the `/sl/message` endpoint calls `location_store.get_recent_visits(limit=10)` and passes the result to `MessageContext.sl_recent_locations`. This surfaces in the system prompt under `## Places You've Visited`.

Deduplication key: `"{region}\x00{parcel}"` — the null byte ensures region and parcel names can never be ambiguously joined.

---

## System Prompt Assembly

**The system prompt is built fresh on every message and split into two Anthropic content blocks.** Block 0 (static: identity files, platform awareness, curated memory) is marked `cache_control: ephemeral` — Anthropic re-caches it when the text changes. Block 1 (dynamic: STM bridge + sensor context + recent locations) is never cached. The debug page flattens both blocks for display.

The data *inside* the prompt comes from sources with different update frequencies. Some is static, some is live, some may be hours old. The agent receives everything in one block and cannot distinguish freshness except via the age labels injected by `_age_label()`.

### What is sent on every message

| Section | How often the underlying data changes |
|---|---|
| Identity files (agent.md + soul.md + user.md) | Only when wizard saves files to `data/identity/` |
| Platform awareness | Only when wizard is saved — wizard-editable per platform |
| Additional context | Only when wizard is saved |
| MEMORY.md | Updated by the `memory` tool during conversation; loaded **frozen** at session start |
| USER.md | Updated by the `memory` tool; loaded **frozen** at session start |
| STM bridge | Rolling 10 summaries per linked uid — injected when linked IDs exist |
| **Environment** (region, parcel, description, rating) | Refreshed on startup, region change, parcel crossing, and every 600s — **always included** |
| **RLV / avatar state** (sitting, autopilot, teleport, position) | Refreshed every 30s — **always included** |
| Avatars | Refreshed every 60s — included only when updated since the user's last message |
| Objects | Refreshed every 300s — included only when updated since the user's last message |
| Chat | Flushed every 90s and immediately before each message — included only when new lines arrived |
| Clothing | Triggered manually via HUD menu — included only when a new scan result is available |
| Places visited | Written on every environment POST; read at message time from `LocationStore` |
| Known facts | Legacy fallback when MEMORY.md is empty; updated via `upsert_fact` |

### Timing summary

```
Message received
       │
       ├── load history + facts from disk              (current state)
       ├── resolve person_id via PersonMap
       ├── load MEMORY.md + USER.md from disk          (frozen snapshot for this session)
       ├── load STM bridge entries from stm.json       (linked uids only)
       ├── SensorStore.get_changes()                   (environment: up to 600s old
       │                                                rlv: up to 30s old
       │                                                others: only if updated)
       ├── LocationStore.get_recent_visits()           (current state)
       ├── AvatarStore.record_encounter() + get_avatar_async() (upsert then read)
       │
       ├── LibraryStore.get_always_on(platform)          (modules marked always_on)
       │
       └── build_system_prompt_blocks() → [static (cached), library (uncached), dynamic]
                                                        → Claude API call
       │
       └── fire-and-forget: _append_stm_entry()        (1–2 sentence exchange summary → stm.json)
                            FileMemoryStore._index_and_vectorize() (FTS5 + ChromaDB)
```

The age labels in the sensor context (`[47s ago]`, `[4m ago]`) are the only signal to the agent about data freshness. Environment and RLV are always present so the agent always knows where it is and what state it's in.

The platform awareness block tells the agent what it can perceive, what it cannot do, and how to behave on the current platform. It is wizard-editable per platform (discord / sl / opensim) and injected from `cfg["platform_awareness"][platform]`.

### Section order (as assembled by `build_system_prompt_blocks()`)

**Block 0 — static, `cache_control: ephemeral`**

| # | Section | Source | Condition |
|---|---|---|---|
| 1 | Identity files | `_load_identity_files()` — agent.md + soul.md + user.md | Always (falls back to `_build_core_block`) |
| 2 | Platform awareness | `_get_platform_awareness(cfg, platform)` — wizard-editable | If non-empty |
| 3 | Additional context | `cfg["additional_context"]` | If non-empty |
| 4 | MEMORY.md + USER.md | `_load_memory_files(person_id)` — frozen at session start | If files exist; else falls back to facts |

**Block 2 — library context, no cache**

| # | Section | Source | Condition |
|---|---|---|---|
| 5 | Always-on library modules | `LibraryStore.get_always_on(platform)` — capped at `library_always_on_cap` chars | If any `always_on: true` modules exist for this platform |

Block 2 is intentionally **uncached** so that Block 0's `cache_control: ephemeral` remains stable. Library content changes infrequently but shouldn't invalidate the main identity cache when it does.

**Block 3 — dynamic, no cache** (called Block 1 in code — index shifts with library presence)

| # | Section | Source | Condition |
|---|---|---|---|
| 6 | STM bridge | `_load_stm_bridge(linked_ids)` — rolling exchange summaries | If linked platform IDs exist |
| 7 | Sensor context | `SensorStore.get_changes()` — objects grouped by (name,owner) | SL only, if non-empty |
| 8 | Places visited | `LocationStore.get_recent_visits()` | SL only, if non-empty |
| 9 | Known avatar | `AvatarStore.get_avatar_async()` — display name, SL UUID, channels, first/last seen | SL only, if avatar has prior record |

---

## Second Life Communication Flow

### Via LSL HUD (channel 42)

```
YourAvatar types: /42 hey what do you think of this sim?
        │
        ▼
Trixxie's HUD (LSL, channel 42 listener)
        │  llHTTPRequest POST /sl/message  [X-SL-Secret header]
        ▼
cloudflared tunnel  →  FastAPI bridge (localhost:8080)
        │
        ├── SensorStore.get_changes(region, uid)   ← only types updated since last msg
        ├── LocationStore.get_recent_visits(uid)   ← SL visit history
        │
        ▼
AgentCore.handle_message()
        │  builds system prompt with persona + self-awareness + sensor + memory + locations
        ▼
Model API  →  reply text (+ optional sl_actions)
        │
        ▼
FastAPI returns JSON: { "reply": "...", "actions": [...] }
        │
        ▼
LSL HUD receives http_response
        │  llInstantMessage(YourAvatar_key, reply)
        ▼
Private IM arrives in YourAvatar' chat window
```

### Via Cool VL Viewer Lua (direct IM)

```
YourAvatar sends a private IM to Trixxie's avatar
        │
        ▼
automation.lua — OnInstantMsg(session_id, origin_id, type=0, ...)
        │  SetAgentTyping(true)   ← typing indicator appears
        │  PostHTTP POST /sl/message  [secret in body]
        ▼
cloudflared tunnel  →  FastAPI bridge (localhost:8080)
        │
        ├── SensorStore.get_changes(region, uid)   ← only types updated since last msg
        ├── LocationStore.get_recent_visits(uid)   ← SL visit history
        │
        ▼
AgentCore.handle_message()
        ▼
Claude API  →  reply text
        │
        ▼
FastAPI returns JSON: { "reply": "...", "actions": [...] }
        │
        ▼
automation.lua — OnHTTPReply(handle, success, reply)
        │  SetAgentTyping(false)  ← typing indicator clears
        │  SendIM(session_id, chunk) × N
        ▼
Reply arrives in YourAvatar' IM window — no /42 required
```


### Hybrid Architecture (Cool VL Viewer Native Sensors)

To overcome LSL's strict 512KB HTTP-POST dictionary string concatenation memory limits (which often crashed scripts in highly populated SIMs), a **Hybrid Architecture** runs entirely inside `automation.lua`.

```
YourAvatar is near Trixxie in Second Life
        │
        ▼
automation.lua — SensorLoop() runs on CallbackAfter timers
        │  Uses pcall(GetRadarList) to fetch surrounding avatars instantaneously
        │  Uses pcall(GetParcelInfo) & GetTimeStamp
        │  Uses pcall(GetAgentState)
        │  PostHTTP POST /sl/sensor  [secret in body]
        ▼
cloudflared tunnel  →  FastAPI bridge (localhost:8080)
        │
        ▼
SensorStore  ← updates in-memory arrays with lightning fast JSON snapshots.
```

In this mode, the LSL HUD is only relied upon to provide Scene Object data since that cannot be parsed fully by the viewer UI as effectively.

Sensor data travels a separate path in both cases — the HUD POSTs to `/sl/sensor` on independent timers and on location changes. The `/sl/message` endpoint calls `SensorStore.get_changes()` which returns only sensor types updated since that user's last message. Chat is no longer piggybacked on `/42` or IM payloads — it is flushed via `do_chat_flush()` to `/sl/sensor` every 90 seconds and immediately before each `/42` POST.

---

## LSL HUD — Detailed Reference

The HUD (`lsl/companion_bridge.lsl`) sits between Second Life's runtime and the companion bridge server. It collects data from five sources (environment, avatars, local chat, nearby objects, avatar attachments) and streams each as a JSON POST to `/sl/sensor`. It handles two conversation flows: channel 42 (`/42 message`) and local chat name-trigger (channel 0).

```
┌─────────────────────────────────────────────┐
│              Second Life Region              │
│                                             │
│  Local chat ──┬─ name trigger ────────────┐ │
│  Avatars ─────┤                           │ │
│  Environment ─┼──► sensor pipeline ───────┤──► /sl/sensor
│  Objects ─────┤                           │ │
│  Attachments ─┘                           ├──► /sl/message
│                    /42 chat ──────────────┘ │
└─────────────────────────────────────────────┘
```

### API Endpoints

#### `POST /sl/sensor`

Fire-and-forget sensor data. All sensor types share this endpoint, distinguished by the `type` field.

```json
{
  "type": "avatars | environment | chat | objects | clothing",
  "region": "Region Name",
  "user_id": "<owner UUID>",
  "data": { ... }
}
```

`user_id` is `llGetOwner()`. The server uses it to index location records when `type` is `"environment"`. The HUD discards the response (HTTP key cleared in `http_response`).

#### `POST /sl/message`

Sent from two paths: channel 42 (`/42 message`) and channel 0 name-trigger.

```json
{
  "user_id": "<UUID>",
  "display_name": "Resident Name",
  "message": "the message text",
  "region": "Region Name",
  "channel": 0,
  "grid": "sl"
}
```

`channel` reflects the source: `0` for name-trigger, `42` for channel 42. The server uses this to namespace conversation memory (`sl_0` vs `sl_42`).

**Response format:**
```json
{
  "reply": "optional direct reply string",
  "actions": [
    { "action_type": "say | im | emote | anim_trigger | mute_avatar | unmute_avatar", "text": "..." },
    ...
  ]
}
```

Up to 5 actions are processed per reply path:

| `action_type` | Channel 42 path | Channel 0 (name-trigger) path |
|---|---|---|
| `say` | `say_chunked(text)` — public `llSay(0)` | `say_chunked(text)` — public `llSay(0)` |
| `im` | `llInstantMessage(sender, text)` | *(not processed)* |
| `emote` | `llInstantMessage(sender, "*text*")` | `say_chunked("*text*")` |
| `mute_avatar` | `AddMute(target_key, 1)` *(Lua only)* | `AddMute(target_key, 1)` *(Lua only)* |
| `unmute_avatar` | `RemoveMute(target_key, 1)` *(Lua only)* | `RemoveMute(target_key, 1)` *(Lua only)* |
| `is_muted` | `IsMuted(target_key, 1)` → `SendIM` result *(Lua only)* | *(not processed)* |

`target_key` for mute actions must be the avatar UUID. `text` is the display name (used only for the feedback IM). Mute/unmute/is_muted actions are only executable from the Lua path (`OnHTTPReply`); the LSL HUD path does not implement them. `is_muted` is read-only — it reports current mute state without changing it.

The primary `reply` text follows the same rule: channel 42 → `llInstantMessage`; channel 0 → `llSay(0)`.

### Sensor Data Formats

#### `avatars`
```json
[
  { "name": "Display Name", "distance": 12.3, "key": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" },
  ...
]
```
Sourced from `llGetAgentList(AGENT_LIST_REGION, [])`. Sorted nearest-first, capped at **25 entries** (Stack-Heap Collision protection for crowded sims). HUD owner excluded. Distances rounded to 1 decimal. `key` is the avatar UUID — injected into the sensor context so the agent can use it as `target_key` for `sl_action` mute/unmute/is_muted calls.

#### `environment`
```json
{
  "region": "Region Name",
  "parcel": "Parcel Name",
  "parcel_desc": "Parcel description text",
  "rating": "General",
  "time_of_day": "0.75",
  "sun_altitude": "0.42",
  "avatar_count": 14
}
```
`rating` is fetched asynchronously via `llRequestSimulatorData(region, DATA_SIM_RATING)` on startup and region change — normalised from `"PG"/"MATURE"/"ADULT"` to `"General"/"Moderate"/"Adult"`. Empty on the first POST if the dataserver hasn't responded yet.

`parcel_desc` carriage returns (char 13) are stripped before JSON encoding — SL text fields use `\r\n` and a raw CR causes a server 422.

#### `chat`
```json
["Speaker: line of chat", "Speaker: line of chat"]
```
Pre-escaped strings. Sent by `do_chat_flush()` every 90 s and immediately before each `/42` POST. Server accumulates up to 30 lines rolling.

#### `objects`
```json
[
  {
    "name": "Object Name",
    "distance": 5.1,
    "scripted": true,
    "description": "Object description text",
    "owner": "Resident Name"
  }
]
```
Capped at 20 objects. Avatars excluded. `scripted` is `true` for physical/scripted objects. `description` truncated at 200 chars. `owner` resolved via `llKey2Name`.

#### `rlv`
```json
{
  "sitting": true,
  "on_object": true,
  "sitting_on": "Pose Stand",
  "autopilot": false,
  "flying": false,
  "teleported": false,
  "position": [128.5, 64.2, 23.1]
}
```
Sent every 30 s and on parcel crossings. Uses `llGetAgentInfo(llGetOwner())` flags: `AGENT_SITTING`, `AGENT_ON_OBJECT`, `AGENT_AUTOPILOT`, `AGENT_FLYING`. `teleported` is `true` for one tick when position jumped >10m. When `on_object` is true, a 2m `llSensor` sweep (scan_mode 4) resolves `sitting_on` before posting.

#### `clothing`
```json
{
  "target": "Avatar Name",
  "items": [
    { "item": "Attachment Name", "creator": "Creator Name" }
  ]
}
```
Only worn attachments (non-zero attachment point) owned by the scanned avatar are included.

### Timer Architecture

Single 30-second tick (`TICK_SECS = 30.0`). All scanning is driven by tick count or change-detection.

| Trigger | Interval | Sensors fired |
|---|---|---|
| Startup (`state_entry`) | once | env + sim rating + avatars + rlv + objects |
| Region change | immediate | env + objects + sim rating request |
| Parcel crossing | immediate | env + objects + rlv |
| Every 1 tick | 30 s | RLV / avatar state |
| Every 3 ticks | 90 s | chat flush |
| Every 2 ticks | 60 s | avatars |
| Every 10 ticks | 300 s | objects |
| Every 20 ticks | 600 s | environment (time-of-day drift) |
| On /42 received | immediate | chat flush + rlv (per-message mode only: + avatars + env) |

**Change detection** runs on every tick before interval checks:
1. **Region change** — `llGetRegionName()` vs `last_region`. Fires env + objects, resets `tick = 0`.
2. **Parcel crossing** — if region unchanged, reads parcel name and compares to `last_parcel`. Fires env + objects + rlv. `do_env_scan()` always updates `last_parcel`.

**Server-side deduplication:** `SensorStore.get_changes()` tracks the last delivery timestamp per user per sensor type. Unchanged snapshots are suppressed on consecutive fast messages.

### Scan Mode State Machine

The clothing and object scanners use `scan_mode` to coordinate async `llSensor` results:

```
scan_mode = 0  Idle

scan_mode = 1  AGENT sweep in progress (clothing — find nearest avatar)
               → stores clo_target / clo_name, triggers scan_mode = 2

scan_mode = 2  Attachment sweep in progress (clothing — find worn items)
               → process_clothing_hits(), posts clothing payload, scan_mode = 0

scan_mode = 3  Object proximity sweep in progress
               → process_object_hits(), posts objects payload, scan_mode = 0

scan_mode = 4  RLV sitting-object resolution (2m sweep to find sit target name)
               → post_rlv_data(obj_name), scan_mode = 0
```

`no_sensor()` resets `scan_mode` and clears `clo_target`/`clo_name`.

### HTTP Key Management

| Key | Purpose |
|---|---|
| `sk_av` | Avatar scan post (fire-and-forget) |
| `sk_env` | Environment scan post |
| `sk_obj` | Object proximity post |
| `sk_clo` | Clothing scan post |
| `sk_chat` | Chat flush post |
| `sk_rlv` | RLV / avatar state post |
| `reply_http` | Active channel-42 conversation request |
| `reply_sender` | UUID of channel-42 sender — held until `http_response` fires |
| `reply_lc_http` | Active channel-0 name-trigger conversation request |
| `reply_lc_id` | UUID of local chat speaker — held until `http_response` fires |
| `sk_sim_query` | `llRequestSimulatorData` key (dataserver, not HTTP) |

`reply_http` and `reply_lc_http` are independent in-flight guards — a channel-42 reply in flight does not block a local chat trigger. While `reply_http` is non-null, new `/42` messages are rejected with `*still thinking...*`.

### Chat Buffer

Channel 0 messages are appended to `nearby_chat` (rolling `CHAT_BUF_SIZE = 10` lines). Every `CHAT_TICKS` ticks (90 s), `do_chat_flush()` POSTs the buffer to `/sl/sensor` as `type: "chat"` and clears the list. It also fires immediately when a `/42` message is received, capturing any chat since the last flush.

The `s_chat` toggle controls buffering entirely — when `FALSE`, `nearby_chat` stays empty.

### Function Reference

| Function | Description |
|---|---|
| `json_s(string)` | Escapes `\`, `"`, `\n`, `\t` for JSON string embedding |
| `sensor_post(type, data_json)` | Wraps data in the `/sl/sensor` envelope and POSTs it |
| `do_avatar_scan()` | Collects nearest 25 agents via `llGetAgentList`, sorts by distance, posts `avatars` |
| `do_env_scan()` | Reads parcel/region/time data, posts `environment`; updates `last_parcel` |
| `do_object_scan()` | Triggers `llSensor` sweep for scan_mode 3 |
| `do_rlv_scan()` | Reads `llGetAgentInfo` flags + position delta; triggers 2m sensor sweep (scan_mode 4) when sitting |
| `post_rlv_data(sitting_on)` | Builds and posts `rlv` payload |
| `do_clothing_scan()` | Triggers `llSensor` AGENT sweep for scan_mode 1 |
| `process_clothing_hits(num)` | scan_mode 2 handler — filters attachments, posts `clothing` |
| `process_object_hits(num)` | scan_mode 3 handler — collects objects, posts `objects` |
| `send_chunked(target, text)` | Splits reply at sentence boundaries, delivers via `llInstantMessage` (≤1000 chars each) |
| `say_chunked(text)` | Same split logic, delivers via `llSay(0)` — public local chat |
| `is_triggered(msg)` | Returns TRUE if any name in `TRIGGER_NAMES` appears in `msg` (case-insensitive) |
| `show_menu()` | Displays the HUD control dialog |
| `show_status()` | Prints sensor state to owner chat |

### OpenSimulator Compatibility

The HUD works on OpenSimulator (0.9.3.0+, YEngine) with one configuration change:

```lsl
string  GRID = "opensim";   // caps replies at 1800 chars (default OpenSim HTTP body limit)
```

All LSL functions used (`llHTTPRequest`, `llGetAgentList`, `llGetObjectDetails`, `llGetParcelDetails`, `llReplaceSubString`, `llJsonGetValue`, `llInstantMessage`, `llDialog`, `llSensor`, `llGetEnv`, `HTTP_CUSTOM_HEADER`) are supported in current OpenSim. To raise the body limit and allow longer replies, set `HttpBodyMaxLenMAX = 16384` in `OpenSim.ini [Network]`.

---

## Platform Differences

| Concern | Discord | SL — LSL HUD | SL — Lua script |
|---|---|---|---|
| Input trigger | @mention, DM, or active channel | `/42 message` in local chat | Private IM to avatar |
| Output delivery | `channel.send()`, chunked ≤2,000 chars | `llInstantMessage`, chunked ≤1,000 chars | `SendIM`, chunked ≤1,000 chars |
| Typing indicator | No | No | Yes — `SetAgentTyping` |
| Auth mechanism | N/A | `X-SL-Secret` HTTP header | `secret` field in JSON body |
| Unicode | Markdown supported | Normalized to ASCII | Normalized to ASCII |
| `sl_action` tool | Not available | Available — queued, sent after reply | Available — queued, sent after reply |
| Sensor context | Not available | environment (region, parcel, description, rating) + rlv always; avatars, objects (description+owner), chat, clothing when changed | From HUD snapshots via get_changes() |
| Location history | Not available | Recent 10 parcels injected into prompt | Recent 10 parcels injected into prompt |
| User ID prefix | `discord_` | `sl_` | `sl_` |
| Active channel config | `DISCORD_ACTIVE_CHANNEL_IDS` in `.env` | N/A | N/A |

`MessageContext.platform` is the single field that drives all of these differences. The core agent has no platform-specific logic.

---

## Threading / Async Model

The application is fully async (asyncio). The Anthropic client is `AsyncAnthropic` — API calls are non-blocking awaitable coroutines, keeping the Discord WebSocket heartbeat and SL bridge responsive during inference.

```
asyncio event loop
  ├── consolidation_loop()              (restart-resilient, every 6 hours)
  │     └── MemoryCuratorAgent          (Haiku scoring pass per uid)
  │         MemoryConsolidator          (main model for note writing)
  ├── _backfill_vector_store()          (fire-and-forget startup task)
  │     └── VectorMemoryStore.add_turn()  (executor, 100ms sleep per 100-row batch)
  ├── debug_server._broadcaster()       (SSE log fan-out, always running)
  ├── discord.py tasks                  (fully async)
  └── uvicorn                           (FastAPI HTTP bridge, async)
        ├── POST /sl/sensor → SensorStore.update()
        ├── POST /sl/message → AgentCore.handle_message()
        │     └── _index_and_vectorize()  (fire-and-forget: FTS5 + ChromaDB)
        ├── GET  /debug/logs → SSE StreamingResponse
        ├── DELETE /debug/reset-memory → wipe all agent state
        └── GET/POST /setup/* → wizard API (agents, library, config)
```

**ChromaDB and the event loop:** all `VectorMemoryStore` methods wrap synchronous ChromaDB calls in `asyncio.get_event_loop().run_in_executor(None, lambda: …)`. This dispatches the blocking call to the default thread pool, keeping the asyncio loop fully unblocked.

**SQLite WAL mode:** `sessions.db` runs in WAL (Write-Ahead Logging) mode, set on the first `_ensure_ready()` call. WAL allows concurrent readers alongside one writer — essential because the startup backfill (long-running reader) runs in parallel with the consolidation loop (writer for importance scores).

If `ANTHROPIC_API_KEY` (or the equivalent provider key) is missing when `main()` starts, `load_settings()` raises `EnvironmentError`. `main()` catches this and calls `_run_setup_wizard_only()`, which starts a minimal single-router FastAPI app (wizard only, no bridge, no debug page) so the user can complete setup at `/setup` without being blocked by a startup crash.

All three services share the same `AgentCore`, `FileMemoryStore`, `LocationStore`, and `AvatarStore` instances. Concurrent writes to the same memory file are serialised by per-(user, channel) `asyncio.Lock` in `FileMemoryStore`. `LocationStore` uses a per-user `asyncio.Lock`; `AvatarStore` uses a single file-level lock (one global file for all avatars).

---

## Security Notes

- **`.env` is gitignored.** API keys never touch version control.
- **SL HTTP bridge** uses an optional shared secret in the `X-SL-Secret` header. Always returns HTTP 200 — errors go in the JSON body to avoid burning LSL's 5-errors-in-60s throttle.
- **Rate limiting** is per-user in-memory token bucket. Not persistent across restarts — by design (soft throttle, not a hard block).
- **Memory scanner** — `_scan_entry()` in `core/tool_handlers/memory.py` guards every write to `MEMORY.md` and `USER.md`. Blocks prompt-injection phrases, API key / SSH credential shapes, shell injection (`` `cmd` ``, `$(cmd)`), and invisible Unicode (zero-width, directional overrides). All patterns are structural or require action + destination context — bare keywords are intentionally excluded to avoid false positives when the agent discusses security topics.

---

## Known Constraints

| Constraint | Detail |
|---|---|
| SL direct IMs (LSL path) | LSL cannot intercept IMs sent directly to an avatar. Channel 42 is the interaction mechanism for the LSL HUD. The Cool VL Viewer Lua script solves this — it uses `OnInstantMsg` to receive private IMs natively. |
| Tunnel URL changes | Free cloudflared tunnels get a new URL on each restart. A named tunnel (paid or self-hosted) gives a permanent URL and avoids updating the LSL script. |
| Avatar scan cap | Avatar list is capped at 25 nearest to prevent Stack-Heap Collision in crowded sims (up to 100 avatars). |
| Consolidation is person-wide | Trimming conversation files to 10 turns affects all platforms for that person simultaneously. |

---

## Future Considerations

| Area | Notes |
|---|---|
| Radegast C# plugin | Native IM loop for Radegast viewer — same `/sl/message` endpoint; requires C# build pipeline |
| Named tunnel | Permanent subdomain so the LSL `SERVER_URL` never needs updating |
| More tools | Register a new handler in `ToolRegistry` and add a schema in `tools.py` |
| Library UI in wizard | Currently CRUD is via `/setup/library` API; a dedicated wizard tab would help non-technical users |
| Vector re-ranking | ChromaDB returns raw similarity scores; a reranker pass could improve precision for long-tail queries |
| Per-user token accounting | Framework should track API usage per canonical person_id for multi-tenant SaaS billing |
| Proactive agent loop | See below |

---

## Proactive Agent Loop (Future)

Currently the agent is purely reactive — it only processes a message when a user sends one. Sensor data accumulates in `SensorStore` continuously but the agent never sees it unless a message arrives. The proactive loop removes that dependency.

### Concept

A background asyncio task runs alongside the existing services. On a configurable interval (e.g. every 60 seconds), it inspects `SensorStore` for significant changes — new avatars entering range, a teleport detected in the RLV state, a leash autopilot starting, a notable chat line — and if a threshold is met, calls `AgentCore.handle_message()` with a synthetic context message. The agent produces a response, which is queued for delivery to the HUD.

```
asyncio event loop
  ├── consolidation_loop()        (every 6 hours)
  ├── proactive_loop()            (every N seconds — future)
  │     ├── inspect SensorStore for significant deltas
  │     ├── if threshold met → AgentCore.handle_message(synthetic_msg, context)
  │     └── queue response → pending_ims[owner_uuid]
  ├── debug_server._broadcaster()
  ├── discord.py tasks
  └── uvicorn
        ├── POST /sl/sensor → SensorStore.update()
        ├── POST /sl/message → AgentCore.handle_message()
        └── GET  /sl/poll   → drain pending_ims[user_id]  (future)
```

### Delivery problem

The server cannot push an IM to Second Life on its own — LSL `llHTTPRequest` is outbound-only and `llInstantMessage` must be called from within the script. Two approaches:

**Option A — HUD polling:** Add a `GET /sl/poll` endpoint. The HUD calls it on a timer (e.g. every 10s) and delivers any queued proactive messages via `llInstantMessage`. No new channel required. Latency is bounded by the poll interval.

**Option B — Dedicated push channel:** The HUD listens on a second private channel (e.g. channel 43). The server POSTs to a new `/sl/push` endpoint; the HUD's `http_response` handler calls `llInstantMessage` with the body. Lower latency but requires an additional outbound POST per proactive message.

### What the agent can react to proactively

- A new avatar entering range (avatars sensor delta)
- An avatar leaving — someone walked away mid-conversation
- Teleport detected in RLV state — likely a leash drag or force-TP
- Autopilot started — being walked on a leash
- Sitting on a new object — force-sit by a collar or piece of furniture
- Chat on channel 0 from a non-user — someone spoke nearby without using `/42`

### Key design constraints

- Proactive calls use the same `AgentCore.handle_message()` path — full tool loop, memory, system prompt
- A synthetic `user_id` (e.g. `sl_proactive`) or the owner's UUID can be used; using the owner's UUID means proactive turns appear in the same conversation history
- The rate limiter and `reply_http` lock must be respected — proactive calls should not fire while a user message is in flight
- The agent needs clear framing in the synthetic message: `"[Sensor update — no user message] A new avatar entered range: ..."` so it understands it is initiating, not responding
