# Memory System — Complete Reference

This document covers every memory layer in the companion agent: what it stores, how it works, how to configure it, and how to test it.

---

## Overview

The memory system is multi-layered. Each layer serves a different time horizon and access pattern:

```
┌────────────────────────────────────────────────────────────────────┐
│ INJECTED INTO EVERY SYSTEM PROMPT (Block 0 — cached)               │
│  MEMORY.md  ≤2,000 chars  §-delimited facts, curated by agent      │
│  USER.md    ≤1,200 chars  Owner preferences and profile            │
├────────────────────────────────────────────────────────────────────┤
│ INJECTED WHEN always_on (Block 2 — uncached)                       │
│  Library modules  ≤library_always_on_cap chars  situational lore   │
├────────────────────────────────────────────────────────────────────┤
│ IDENTITY GRAPH                                                     │
│  PersonMap  Command Center root → command/Discord/SL platform IDs  │
├────────────────────────────────────────────────────────────────────┤
│ INJECTED FOR CROSS-PLATFORM CONTEXT (Block 3 — dynamic)            │
│  STM bridge  rolling 10 exchange summaries from linked platform UIDs│
├────────────────────────────────────────────────────────────────────┤
│ CONVERSATION CONTEXT (in-session, messages array)                   │
│  FileMemoryStore  JSON files  recent N turns per (user, channel)   │
├────────────────────────────────────────────────────────────────────┤
│ SEARCHABLE ON DEMAND (agent tools)                                  │
│  SessionIndex   SQLite FTS5  all turns, full-text search            │
│  VectorMemoryStore  ChromaDB  all turns, semantic similarity search │
│  LibraryStore   markdown files  situational reference modules       │
├────────────────────────────────────────────────────────────────────┤
│ BACKGROUND SCORING + CONSOLIDATION                                  │
│  MemoryCuratorAgent  importance 0.0–1.0  filters transcript         │
│  MemoryConsolidator  6h cycle  writes MEMORY.md from high-imp turns │
└────────────────────────────────────────────────────────────────────┘
```

---

## Layer 1 — Conversation Files (FileMemoryStore)

### What it stores

Recent conversation turns per `(user_id, channel_id)` pair as JSON files on disk.

```
data/memory/{safe_user_id}/{channel_id}.json
```

Each file is a `ConversationFile` with a `turns` array of `{"role": "user"|"assistant", "content": …}` objects. Content can be a string or an Anthropic-format list (for tool_use / tool_result blocks).

### How it works

- `FileMemoryStore.get_history(user_id, channel_id)` — returns recent turns for the conversation. Called at the start of every `AgentCore.handle_message()`.
- `FileMemoryStore.append_turn(…, person_id="")` — appends a turn, trims to `MEMORY_MAX_HISTORY` (default 20), fires `_index_and_vectorize()` as a background task.
- Per `(user_id, channel_id)` asyncio locks prevent write races on concurrent messages.
- `_sanitize_tool_pairs()` is applied on load and trim — drops orphaned `tool_use`/`tool_result` blocks that appear after history slicing, which would cause Anthropic API 400 errors.

### Configuration

| Env var | Default | Description |
|---|---|---|
| `MEMORY_MAX_HISTORY` | `20` | Max turns kept per conversation file |

### Testing

```bash
# Inspect a conversation file
cat data/memory/discord_<id>/<channel_id>.json | python3 -m json.tool | head -30

# Count turns per file
python3 -c "
import json, glob
for f in glob.glob('data/memory/**/*.json', recursive=True):
    if not f.endswith('_facts.json') and 'chroma' not in f:
        d = json.load(open(f))
        if 'turns' in d:
            print(f'{len(d[\"turns\"]):3d}  {f}')
"
```

---

## Layer 2 — Curated Memory Files (MEMORY.md / USER.md)

### What it stores

Two bounded markdown files per canonical `person_id`:

```
data/memory/agents/{agent_id}/{safe_person_id}/MEMORY.md   ≤2,000 chars
data/memory/agents/{agent_id}/{safe_person_id}/USER.md     ≤1,200 chars
```

- **MEMORY.md** — agent's notes about context, facts, and the world. Updated in real time via the `memory` tool.
- **USER.md** — owner preferences, communication style, background. Updated in real time via the `memory` tool.

Both use `§` as an entry delimiter. The agent writes entries like free-form bullet points or sentences.

### How it works

**Reading:** loaded once at the start of each `handle_message()` and injected **frozen** into Block 0. The content does not change mid-session, which maximises cache hit rate on the static identity block.

**Writing:** the `memory` tool (`action: add | replace | remove`) lets the agent curate these files mid-conversation. `_scan_entry()` blocks prompt-injection phrases, credential shapes, shell injection, and invisible Unicode before writing. Cap enforcement via `_trim_to_cap()` (entry-aware — drops oldest `§` entries, not a raw character slice).

**Injection format** (as it appears in the system prompt):
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

### Configuration

No env vars control these files directly. The caps (2,000 / 1,200 chars) are hardcoded in `core/tool_handlers/memory.py`. The wizard Step 4 (Identity) writes `data/identity/agent.md`, `soul.md`, and `user.md` — those are the persona files injected before MEMORY.md in Block 0, not to be confused with USER.md which is the agent-maintained owner profile.

### Testing

```bash
# View current curated memory for the owner
cat data/memory/agents/{agent_id}/{CommandCenterName}/MEMORY.md
cat data/memory/agents/{agent_id}/{CommandCenterName}/USER.md

# Check entry count
python3 -c "
text = open('data/memory/agents/{agent_id}/{CommandCenterName}/MEMORY.md').read()
print(f'Entries: {text.count(chr(0xa7))}')
print(f'Chars: {len(text)} / 2000')
"
```

To trigger an in-session write, send a message like: "Remember that I prefer casual language" — the agent should call the `memory` tool with `action: add`.

---

## Layer 3 — Session Index (FTS5 full-text search)

### What it stores

Every conversation turn ever written, indexed in a SQLite FTS5 table at:
```
data/memory/sessions.db
```

Schema:
```sql
CREATE TABLE sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id     TEXT NOT NULL DEFAULT '',
    user_id      TEXT NOT NULL,
    channel_id   TEXT NOT NULL,
    platform     TEXT NOT NULL,
    role         TEXT NOT NULL,
    content      TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    importance   REAL NOT NULL DEFAULT -1.0,  -- -1.0 = unscored
    consolidated_at TEXT NOT NULL DEFAULT '',
    consolidation_run_id TEXT NOT NULL DEFAULT ''
);
```

The `sessions_fts` virtual table (FTS5) covers `content` and `display_name`. An `AFTER INSERT` trigger keeps FTS in sync.

### How it works

**Write path:** `FileMemoryStore._index_and_vectorize()` fires as a background task after every `append_turn()`. Calls `SessionIndex.index_turn()` → inserts the row and returns the auto-incremented `id`.

**Search:** `SessionIndex.search(query, limit)` runs an FTS5 `MATCH` query with `snippet()` highlighting. Returns a list of dicts with platform, timestamp, display_name, role, and a highlighted snippet. Not user-scoped — all conversations are searchable (by design: cross-user recall is a feature).

**WAL mode:** enabled on first `_ensure_ready()` call. Allows concurrent reads (backfill task) alongside writes (importance scoring).

### The importance column

Added by migration `_MIGRATE_IMPORTANCE_STMTS`. Sentinel value `-1.0` means "not yet scored by the curator". Values range 0.0–1.0 after scoring.

| Value | Meaning |
|---|---|
| `-1.0` | Unscored (default) |
| `0.0` | Pure filler |
| `0.3` | Mild context |
| `0.6` | Notable |
| `1.0` | Pivotal |

The `importance` column drives what gets included in consolidation transcripts (above threshold) and what the vector index can filter on (`importance_threshold` in `semantic_search`). `consolidated_at` and `consolidation_run_id` make consolidation idempotent: a high-importance turn is only considered for `MEMORY.md` once unless explicitly reset.

### Configuration

| Env var | Default | Description |
|---|---|---|
| `IMPORTANCE_THRESHOLD` | `0.4` | Min score for a turn to appear in consolidation transcript |
| `IMPORTANCE_SCORE_BATCH_SIZE` | `20` | Turns per curator API call |

### Testing

```bash
# Check schema
sqlite3 data/memory/sessions.db "PRAGMA table_info(sessions);"

# Score distribution
sqlite3 data/memory/sessions.db "
SELECT 
  COUNT(*) as total,
  COUNT(CASE WHEN importance = -1.0 THEN 1 END) as unscored,
  COUNT(CASE WHEN importance >= 0.6 THEN 1 END) as high_importance,
  ROUND(AVG(CASE WHEN importance != -1.0 THEN importance END), 2) as avg_score
FROM sessions;
"

# Highest-importance turns
sqlite3 data/memory/sessions.db "
SELECT importance, display_name, substr(content, 1, 80)
FROM sessions
WHERE importance >= 0.9
ORDER BY importance DESC
LIMIT 10;
"

# Test FTS5 search
sqlite3 data/memory/sessions.db "
SELECT s.display_name, s.platform, s.timestamp,
       snippet(sessions_fts, 0, '[', ']', '...', 15) AS match
FROM sessions_fts
JOIN sessions s ON s.id = sessions_fts.rowid
WHERE sessions_fts MATCH 'mesh body'
LIMIT 5;
"

# Force a scoring cycle (restart the server — consolidation runs on startup if overdue)
# Or trigger manually:
python3 -c "
import asyncio
from config.settings import load_settings
from core.supporting_agent import make_supporting_adapter
from core.memory_curator import MemoryCuratorAgent
from core.persona import get_agent_config
from memory.session_index import SessionIndex
from pathlib import Path

async def main():
    settings = load_settings()
    agent_cfg = get_agent_config()
    adapter = make_supporting_adapter(settings, agent_cfg, 'memory_curator')
    curator = MemoryCuratorAgent(adapter)
    index = SessionIndex(Path(settings.memory_dir) / 'sessions.db')
    
    unscored = await index.get_unscored_turns('discord_1090657639781912677', limit=20)
    print(f'Unscored: {len(unscored)}')
    if unscored:
        scores = await curator.score_turns(unscored)
        print('Scores:', scores)
        await index.set_importance_batch(scores)
        print('Written.')

asyncio.run(main())
"
```

---

## Layer 4 — Vector Memory (ChromaDB)

### What it stores

Dense vector embeddings of all conversation turns, stored in ChromaDB at:
```
data/memory/chroma/
```

One collection per canonical `person_id`, named `mem_{safe_person_id}`. Document ID = `str(session_id)` from SQLite (stable, never reused). Metadata per document: `user_id`, `channel_id`, `platform`, `role`, `timestamp`, `display_name`, `importance`.

Embedding model: ONNXMiniLM-L6-v2 (bundled with ChromaDB — no PyTorch or sentence-transformers required). Model cached at `~/.cache/chroma/onnx_models/`. Downloaded once on first use (~80 MB).

### How it works

**Write path:** `FileMemoryStore._index_and_vectorize()` chains after `SessionIndex.index_turn()`. Calls `VectorMemoryStore.add_turn(person_id, session_id, content, metadata)`. All ChromaDB calls run in `asyncio.get_event_loop().run_in_executor(None, …)` — ChromaDB is synchronous; executor prevents event-loop blocking.

**Startup backfill:** `_backfill_vector_store()` in `main.py` fires as a fire-and-forget task. Reads all `sessions.db` rows in batches of 100, calls `VectorMemoryStore.add_turn()` for rows not yet in ChromaDB (checked via `has_document()`), sleeps 100ms between batches. Safe to re-run — idempotent by doc ID.

**Query path:** `VectorMemoryStore.semantic_search(person_id, query, n_results, importance_threshold)` calls `collection.query()` with optional `where={"importance": {"$gte": threshold}}` filter. Returns a list of dicts with `content`, `metadata`, and `distance`.

**Reasoning pass:** `SemanticRecallAgent.recall()` calls `semantic_search()` then passes raw results through a `create_simple()` call that filters noise and explains which results are actually relevant. Falls back to raw results if reasoning fails.

### Configuration

| Env var | Default | Description |
|---|---|---|
| `MEMORY_DIR` | `./data/memory` | Base dir for both `sessions.db` and `chroma/` |
| `IMPORTANCE_THRESHOLD` | `0.4` | Default threshold for `semantic_search` when called via tool |

Supporting agent model for semantic recall (in `data/agent_config.json`):
```json
{
  "supporting_agents": {
    "semantic_recall": { "model_provider": "anthropic", "model_name": "claude-sonnet-4-6" }
  }
}
```

### Testing

```bash
# Verify ChromaDB directory exists and has collections
ls -lh data/memory/chroma/
sqlite3 data/memory/chroma/chroma.sqlite3 "SELECT name FROM collections;"

# Count documents per collection
sqlite3 data/memory/chroma/chroma.sqlite3 "
SELECT c.name, COUNT(e.id) as docs
FROM collections c
LEFT JOIN embeddings e ON c.id = e.collection_id
GROUP BY c.id;
" 2>/dev/null || echo "embeddings table schema differs — check ChromaDB version"

# Trigger a semantic_recall from a running Discord session
# Send the message: "Do you recall what we discussed about sim ownership?"
# The agent should call semantic_recall tool and the response will reference past conversations.

# Manual semantic search test
python3 -c "
import asyncio
from config.settings import load_settings
from memory.vector_store import VectorMemoryStore

async def main():
    settings = load_settings()
    vs = VectorMemoryStore(settings.memory_dir)
    results = await vs.semantic_search('openpalai-carissa::Pablo', 'mesh body options', n_results=3)
    for r in results:
        print(f'sim={r[\"distance\"]:.3f}  {r[\"metadata\"][\"display_name\"]}')
        print(f'  {r[\"content\"][:100]}')
        print()

asyncio.run(main())
"
```

---

## Layer 5 — Situational Library

### What it stores

Markdown files in `data/library/` with front-matter metadata. Each file is a **library module** — a reference document with optional always-on injection and platform filtering.

```markdown
---
id: sl_gorean_rp
title: Gorean Roleplay Setting
description: Reference guide for Gor-based RP in SL
always_on: false
platforms: ["sl"]
tags: ["roleplay", "gor"]
---

# Gorean Roleplay
Full reference content here...
```

### Front-matter fields

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier — used in `library_lookup` calls |
| `title` | string | Human-readable name |
| `description` | string | One-line summary — used for keyword search and list display |
| `always_on` | bool | If `true`, injected into Block 2 on every message for this platform |
| `platforms` | list | `["sl"]`, `["discord"]`, or `["sl", "discord"]` — empty = all platforms |
| `tags` | list | Keywords for search |

### How it works

**Always-on injection:** on every `AgentCore.handle_message()`, `LibraryStore.get_always_on(platform)` returns modules where `always_on=true` and `platform in module.platforms` (or platforms is empty). The combined content is capped at `library_always_on_cap` chars (default 4,000) and injected as **Block 2** — uncached, so Block 0's cache stays stable.

**On-demand lookup:** the agent calls the `library_lookup` tool with a query or a specific `module_id`. The tool delegates to `LibrarianAgent.find_relevant()`, which:
1. Runs `LibraryStore.search(query)` for keyword candidates
2. Calls `create_simple()` with the candidate list + context summary
3. Returns the modules the librarian deems relevant, with reasoning

**Direct retrieval:** `library_lookup` with a `module_id` calls `LibrarianAgent.get_module()` → `LibraryStore.get_by_id()` for direct, no-reasoning retrieval.

**`library_list`:** the agent can also list all available modules (metadata only) to discover what's available before a lookup.

### Configuration

| Env var | Default | Description |
|---|---|---|
| `LIBRARY_DIR` | `./data/library` | Directory containing `*.md` module files |
| `LIBRARY_ALWAYS_ON_CAP` | `4000` | Max chars of always-on content injected per message |

Supporting agent model for librarian (in `data/agent_config.json`):
```json
{
  "supporting_agents": {
    "librarian": { "model_provider": "anthropic", "model_name": "claude-haiku-4-5-20251001" }
  }
}
```

### Creating modules

**Via wizard:** navigate to `http://localhost:8080/setup` → the wizard does not yet have a dedicated Library tab. Use the API directly for now.

**Via API:**
```bash
# Create a new module
curl -s -X POST http://localhost:8080/setup/library \
  -H 'Content-Type: application/json' \
  -d '{
    "filename": "my_rp_rules.md",
    "content": "---\nid: my_rp_rules\ntitle: RP Rules\ndescription: House rules for roleplay\nalways_on: true\nplatforms: [\"sl\"]\ntags: [\"roleplay\", \"rules\"]\n---\n\n# Roleplay Rules\nContent here..."
  }'

# List all modules
curl -s http://localhost:8080/setup/library | python3 -m json.tool

# Get a specific module
curl -s http://localhost:8080/setup/library/my_rp_rules | python3 -m json.tool

# Delete a module
curl -s -X DELETE http://localhost:8080/setup/library/my_rp_rules
```

**Direct file creation:**
```bash
cat > data/library/my_rp_rules.md << 'EOF'
---
id: my_rp_rules
title: Roleplay Rules
description: House rules for roleplay sessions
always_on: false
platforms: ["sl"]
tags: ["roleplay", "rules"]
---

# House Rules
...content...
EOF
```

### Testing

```bash
# List loaded modules
python3 -c "
from memory.library_store import LibraryStore
store = LibraryStore('data/library')
for m in store.list_modules():
    print(f'{m[\"id\"]:30s} always_on={m[\"always_on\"]}  {m[\"description\"][:50]}')
"

# Test always-on injection for SL
python3 -c "
from memory.library_store import LibraryStore
store = LibraryStore('data/library')
mods = store.get_always_on('sl')
print(f'Always-on for SL: {len(mods)} module(s)')
for m in mods:
    print(f'  {m.id}: {m.char_count} chars')
"

# Test keyword search
python3 -c "
from memory.library_store import LibraryStore
store = LibraryStore('data/library')
results = store.search('roleplay', limit=3)
for r in results:
    print(r.id, r.title)
"

# Verify Block 2 injection during SL message (check debug panel)
# Navigate to http://localhost:8080/debug → Prompts tab → select a user
# Look for 'library_context_chars' in the metadata section
```

---

## Layer 6 — Identity Map (PersonMap)

### What it stores

`data/person_map.json` links platform-specific storage IDs to one canonical person. The canonical owner identity is the setup wizard's **Command Center Name**.

```json
{
  "Pablo": [
    "command_user_<browser-id>",
    "discord_<snowflake>",
    "sl_<uuid>"
  ]
}
```

Command Center browser IDs (`command_user_*`) resolve to the canonical owner automatically. SL and Discord IDs are auto-linked when the incoming platform display name matches `OWNER_SL_NAME` or `OWNER_DISCORD_NAME`. Manual repair is still possible by editing `person_map.json`.

This identity map is used for curated memory paths, STM cross-platform bridging, vector namespaces, and consolidation targets.

---

## Layer 7 — Short-Term Memory Bridge (STM)

### What it stores

Rolling window of 10 exchange summaries per `user_id`, stored at:
```
data/memory/{safe_user_id}/stm.json
```

Each entry is a 1–2 sentence third-person summary of one exchange, capped at 120 chars. Entries are generated by the main model via `create_simple()` as a fire-and-forget background task after each reply.

### How it works

STM is **only** injected into Block 3 for **linked** platform UIDs (cross-platform bridge). If the owner has both a Discord and SL account linked in `person_map.json`, a message from Discord will include the recent SL conversation summaries in the dynamic block — and vice versa.

The current conversation's own turns are already in the messages array. STM is not duplicated there.

```
## Recent Activity — DISCORD
User asked about mesh body options; agent recommended checking The Shops at Kukua.
---
User shared a screenshot of their avatar outfit; agent praised the color choices.
```

### Testing

```bash
# View current STM entries
cat data/memory/discord_<your_id>/stm.json | python3 -m json.tool

# Verify cross-platform injection
# 1. Send a message from Discord
# 2. Send a message from SL
# 3. Check the debug panel (Prompts tab) for the SL conversation
# 4. Block 3 should include "Recent Activity — DISCORD" with summaries of Discord exchanges
```

---

## Memory Consolidation Pipeline

### Overview

`MemoryConsolidator` runs every 6 hours as a background loop. The timer is restart-resilient — `.last_consolidation` is read from disk to compute the remaining wait. Startup bypasses the wait when `sessions.db` contains unscored turns or high-importance rows pending consolidation.

Consolidation is driven by durable `sessions.db` rows, not by trimmed JSON conversation files. The JSON files are short working history; `sessions.db` is the source of truth for long-term memory graduation.

Consolidation triggers when pending high-importance rows for a canonical person exceed **30** (or **15** for the first `MEMORY.md`). The full pipeline with `MemoryCuratorAgent`:

```
1. get_unscored_turns(uid) for each linked user_id
        ↓
2. curator.score_turns(unscored)
   → batched Haiku calls, 20 turns per call
   → {"scores": [{"id": N, "score": 0.0–1.0}, ...]}
        ↓
3. session_index.set_importance_batch(scores)
   → single WAL transaction
   vector_store.set_importance_batch(scores)
   → keeps Chroma metadata aligned with SQLite scores
        ↓
4. get_unconsolidated_high_importance_turns(user_ids, threshold)
   → durable transcript from sessions.db rows where consolidated_at = ''
        ↓
5. curator.should_consolidate(transcript, existing_memory)
   → lightweight gate: {"consolidate": true|false}
   → if skipped, marks source rows consolidated so they do not loop forever
        ↓
6. main model: write first-person bullet-point notes
        ↓
7. append to MEMORY.md (oldest trimmed to maintain ≤2,000 char cap)
8. save timestamped audit trail and consolidation_runs.jsonl with source session IDs
9. mark source rows with consolidated_at + consolidation_run_id
10. trim conversation files to 10 turns each
```

### Configuration

| Env var | Default | Description |
|---|---|---|
| `IMPORTANCE_THRESHOLD` | `0.4` | Min score for transcript inclusion |
| `IMPORTANCE_SCORE_BATCH_SIZE` | `20` | Turns per curator batch call |

Consolidation interval (6 hours) is hardcoded in `main.py` as `CONSOLIDATION_INTERVAL_SECS = 6 * 3600`. The threshold (30 turns) is hardcoded in `memory/consolidator.py` as `CONSOLIDATION_THRESHOLD = 30`.

Supporting agents for consolidation (in `data/agent_config.json`):
```json
{
  "supporting_agents": {
    "memory_curator": { "model_provider": "anthropic", "model_name": "claude-haiku-4-5-20251001" }
  }
}
```

### Testing

```bash
# Check last consolidation time
python3 -c "
import time
from pathlib import Path
p = Path('data/memory/.last_consolidation')
if p.exists():
    t = float(p.read_text())
    elapsed = time.time() - t
    print(f'Last: {time.ctime(t)}')
    print(f'Elapsed: {elapsed/3600:.1f}h')
else:
    print('Never consolidated')
"

# Manually reset the timer to trigger consolidation on next startup
rm data/memory/.last_consolidation

# Watch consolidation logs (filter out noise)
./run.sh 2>&1 | grep -E "(consolidat|scored|curator|importance)"

# Verify results
cat data/memory/agents/{agent_id}/{CommandCenterName}/MEMORY.md
ls data/notes/{agent_id}/{CommandCenterName}/

# Test the curator gate: force all scores to 0.1 and re-run
# (consolidation should be skipped as nothing meets threshold)
sqlite3 data/memory/sessions.db "UPDATE sessions SET importance = 0.1;"
rm data/memory/.last_consolidation
# → restart; curator.should_consolidate() should return False and log "Curator gate: skipping"
```

---

## Supporting Agent Models

Each background agent uses its own `ModelAdapter`. Configure via the wizard Step 7 ("Agents") or directly in `data/agent_config.json`:

```json
{
  "supporting_agents": {
    "memory_curator": {
      "model_provider": "anthropic",
      "model_name": "claude-haiku-4-5-20251001"
    },
    "librarian": {
      "model_provider": "anthropic",
      "model_name": "claude-haiku-4-5-20251001"
    },
    "semantic_recall": {
      "model_provider": "anthropic",
      "model_name": "claude-sonnet-4-6"
    }
  }
}
```

Leave `model_name` empty to inherit the main agent's model. Set `model_provider` to `ollama` with a local model name to use a self-hosted model for background work (eliminates API costs for scoring and retrieval).

**Cost guidance:**
- `memory_curator` — runs every 6h, 20 turns/call. Haiku is cheap and sufficient.
- `librarian` — runs only when the agent calls `library_lookup`. Haiku works for keyword-based reasoning.
- `semantic_recall` — runs only when the agent calls `semantic_recall`. Sonnet recommended for quality filtering.

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `MEMORY_MAX_HISTORY` | `20` | Max turns per conversation file |
| `MEMORY_DIR` | `./data/memory` | Root dir for all memory files |
| `NOTES_DIR` | `./data/notes` | Root dir for consolidation audit trail |
| `LIBRARY_DIR` | `./data/library` | Library module directory |
| `LIBRARY_ALWAYS_ON_CAP` | `4000` | Max chars of always-on library content per message |
| `IMPORTANCE_THRESHOLD` | `0.4` | Min score for consolidation transcript inclusion |
| `IMPORTANCE_SCORE_BATCH_SIZE` | `20` | Turns per curator scoring batch |

---

## Full Test Checklist

### Startup verification

```bash
./run.sh 2>&1 | grep -E "(INFO|WARNING|ERROR)" | grep -v "PyNaCl\|davey"
```

Expected on first run:
- `SessionIndex: migrating sessions.db to add importance column` (once, then gone)
- `Script patch on startup: {'lsl': 'ok', 'lua': 'ok'}`
- `Person map loaded: N person(s) linked`
- `Running scheduled memory consolidation...` (if overdue)
- `Curator scored N/N turns for ...` (if unscored turns exist)
- No `ERROR` lines

### FTS5 search (session_search tool)

Send from Discord: "Do you remember what we talked about last week regarding sim ownership?"

Expected: the agent calls `session_search` with relevant keywords and returns timestamped snippets.

### Semantic recall (semantic_recall tool)

Send: "Recall our past conversations about building projects by meaning, not just keywords."

Expected: the agent calls `semantic_recall`, results reference turns with `sim:N.NN` score, the reasoning pass filters noise.

Verify ChromaDB was populated:
```bash
ls -lh data/memory/chroma/
```

### Importance scoring

```bash
sqlite3 data/memory/sessions.db "
SELECT 
  COUNT(*) as total,
  COUNT(CASE WHEN importance = -1.0 THEN 1 END) as unscored,
  COUNT(CASE WHEN importance >= 0.6 THEN 1 END) as high_importance
FROM sessions;"
```

All turns should have `importance != -1.0` after the first consolidation cycle.

### Library module

1. Create a test module:
```bash
curl -s -X POST http://localhost:8080/setup/library \
  -H 'Content-Type: application/json' \
  -d '{"filename":"test_module.md","content":"---\nid: test_module\ntitle: Test Module\ndescription: A test reference module\nalways_on: false\nplatforms: []\ntags: [\"test\"]\n---\n\n# Test Content\nThis is a test library module."}'
```

2. Ask the agent: "Can you look up the test module in the library?"

Expected: agent calls `library_list` to discover the module, then `library_lookup` with `module_id: test_module` to retrieve it.

3. Enable always-on and verify Block 2 injection:

Edit the file to set `always_on: true`, then check the debug panel (Prompts tab) — a Block 2 section with the library content should appear.

### Consolidation end-to-end

1. Delete `.last_consolidation` to force an immediate run on next startup
2. Ensure >30 turns exist (`sqlite3 data/memory/sessions.db "SELECT COUNT(*) FROM sessions;"`)
3. Restart the server
4. Watch logs: scoring → gate check → note writing → trim
5. Verify `data/memory/agents/{agent_id}/{CommandCenterName}/MEMORY.md` was updated
6. Verify `data/notes/{agent_id}/{CommandCenterName}/memories_*.md` and `consolidation_runs.jsonl` exist
7. Verify conversation files were trimmed to 10 turns

### Curated memory write (memory tool)

Send from Discord: "Please remember that I prefer verbose technical explanations."

Expected: agent calls `memory` tool with `action: add, store: user, text: Prefers verbose technical explanations`.

Verify: `cat data/memory/agents/{agent_id}/{CommandCenterName}/USER.md`

### Debug panel verification

Navigate to `http://localhost:8080/debug` → Prompts tab:
- Blocks 0, 2, 3 (if library active) should be visible
- `library_context_chars` shows always-on injection size
- `block2_chars` / `has_block2` confirm library injection

---

## Data Flow Diagram

```
                    incoming message
                          │
              ┌───────────▼──────────────┐
              │      AgentCore           │
              │   handle_message()       │
              └───────────┬──────────────┘
                          │
          ┌───────────────┼──────────────────────┐
          │               │                      │
    FileMemoryStore  LibraryStore.         SensorStore
    get_history()    get_always_on()       get_changes()
          │               │                      │
          │         library_context        sensor context
          │               │                      │
          └───────────────▼──────────────────────┘
                          │
              ┌───────────▼──────────────────────────────┐
              │        build_system_prompt_blocks()       │
              │  Block 0: identity + MEMORY + USER        │ ← cached
              │  Block 2: always-on library (if any)      │ ← uncached
              │  Block 3: STM bridge + sensors            │ ← uncached
              └───────────┬──────────────────────────────┘
                          │
                    Claude API call
                     tool loop
                          │
                ┌─────────┴──────────┐
                │                    │
          tool_result           end_turn
                │                    │
           ToolRegistry          reply text
          dispatch()                 │
         ┌──┴──┬────┐               │
         │     │    │               │
     memory sl_action  library_lookup  semantic_recall
      tool   tool     → LibrarianAgent  → SemanticRecallAgent
                                            │
                                     VectorMemoryStore
                                     .semantic_search()
                                          │
                                   reasoning pass
                                   (SemanticRecallAgent)
                                          │
                                     formatted results

                          after reply
                          │
              ┌───────────▼──────────────────────────┐
              │  fire-and-forget background tasks     │
              │  _append_stm_entry()    → stm.json    │
              │  _index_and_vectorize()               │
              │    → SessionIndex.index_turn()        │
              │    → VectorMemoryStore.add_turn()     │
              └──────────────────────────────────────┘

                   every 6 hours
                          │
              ┌───────────▼──────────────────────────┐
              │      MemoryConsolidator               │
              │                                      │
              │  MemoryCuratorAgent.score_turns()     │
              │  → set_importance_batch()             │
              │  → filter to high-importance turns   │
              │  curator.should_consolidate() gate    │
              │  → main model: write notes            │
              │  → MEMORY.md (trimmed to cap)         │
              │  → memories_YYYYMMDDTHHMMSSZ.md       │
              │  → consolidation_runs.jsonl           │
              │  → trim conversation files to 10      │
              └──────────────────────────────────────┘
```

## Non technical explanation:

How OpenPalAI Remembers Things
Think of OpenPalAI's memory like a person who keeps a diary, a filing cabinet, a sticky-note board, and a research library — all working together.

1. 📝 Short-Term Memory — "What we were just talking about"
Every conversation is saved turn-by-turn, like a chat log. OpenPalAI holds the last ~20 messages in her head while talking to you.

Example: You mention you're working on a sci-fi build in SL. Ten messages later you ask "how should I decorate it?" — she still knows it's sci-fi themed because it's in the recent scroll.

2. 🗂️ Long-Term Notes — "The important stuff she wrote down later"
After you've had 30+ exchanges, a background process reads the recent chats and writes a short personal journal entry: things that actually matter about you. These bullet points are what she loads every conversation so she always knows who you are.

Example after consolidation:

"Pablo loves dark cyberpunk aesthetics and hates anything 'too clean.'"
"He's building a Gorean RP sim in SL and is stressed about the timeline."
"He prefers blunt answers over gentle framing."
The next time you talk — even a week later — she already knows all of this.

3. 🔍 Full Archive + Keyword Search — "Let me look that up"
Everything ever said is stored in a searchable database. OpenPalAI has a tool called session_search she can invoke when you reference something specific from the past.

Example: You say "remember that thing I told you about my sister?" — she can search and pull up the exact exchange from three weeks ago.

4. 🧲 Meaning-Based Search — "What did we talk about that feels like this?"
The new ChromaDB layer goes beyond keyword matching. It understands meaning, so it can find relevant memories even when you use completely different words.

Example: You ask "have I ever mentioned feeling overwhelmed by the project?" — it finds turns where you said things like "I'm drowning in tasks" or "this is getting out of hand", even though "overwhelmed" never appeared.

5. ⭐ Importance Scoring — "What actually matters vs. filler"
A background mini-agent reads every message and scores it 0–1 for how important it is to remember long-term.

Score	Meaning	Example
0.0	Filler	"lol", "ok", "brb"
0.3	Mild preference	"I kinda like dark themes"
0.6	Notable	"I'm building a Gorean sim, it's my main project right now"
1.0	Pivotal	"My real name is Pablo, remember that" or "I had a rough day, my dad is sick"
Only high-scoring turns get promoted to the long-term notes. Small talk stays in the archive but doesn't clutter the notes.

6. 📚 Library Modules — "Reference sheets she can pull out"
You can create lore/reference documents (like a Gorean RP guide, or a fashion glossary) that OpenPalAI can look up on demand or keep always loaded for certain contexts.

Example: You set up a gorean_rp.md library module. When you start talking about RP dynamics, OpenPalAI automatically has the lore loaded and doesn't need you to explain it every session.

🔄 How It All Fits Together
When you send a message, OpenPalAI assembles her context like this:


[ Who she is + what she knows about you ]  ← long-term notes, always loaded
[ Sensor data: nearby avatars, location ]  ← SL only, real-time
[ Library modules if relevant ]            ← injected when useful
[ Recent conversation ]                    ← last 20 turns
→ Model generates reply
→ Background: score this turn, add to archive, maybe search for past context
The whole system is designed so she gradually gets better at knowing you without you having to repeat yourself — and without the conversation becoming one giant expensive blob of text.

## Technical Overview: OpenPalAI Memory System
Storage Backends
Layer	Backend	Location
Conversation history	JSON files	data/memory/{safe_uid}/{channel_id}.json
Curated notes	Markdown files	data/memory/{person_id}/MEMORY.md
Full-text search index	SQLite FTS5	data/memory/sessions.db
Semantic vectors	ChromaDB + ONNX	data/memory/chroma/
Explicit facts	JSON	data/memory/{safe_uid}/_facts.json
Library modules	Markdown + front-matter	data/library/*.md
Write Path (per turn)

AgentCore.handle_message()
  → FileMemoryStore.append_turn()
      → JSON file (conversation history)
      → asyncio.create_task(_index_and_vectorize())
          → SessionIndex.index_turn()       → sessions.db (FTS5, importance=-1.0)
          → VectorMemoryStore.add_turn()    → ChromaDB (run_in_executor)
index_turn() returns the SQLite rowid which becomes the ChromaDB doc ID — the two stores are permanently linked by that integer.

Importance Scoring Pipeline
Runs during consolidation (6h cycle) via MemoryCuratorAgent:


SessionIndex.get_unscored_turns(uid, limit=200)   → rows where importance = -1.0
MemoryCuratorAgent.score_turns(turns)
  → batches of 20, one create_simple() call per batch (Haiku)
  → prompt: "rate each turn 0.0–1.0, return JSON {scores: [{id, score}]}"
  → _extract_json() → re.search(r"\{.*\}", ..., DOTALL) for robustness
SessionIndex.set_importance_batch(scores)          → single WAL transaction
Scale: 0.0 filler → 0.3 mild → 0.6 notable → 1.0 pivotal.

Consolidation Gate + Pipeline

MemoryConsolidator._check_and_consolidate(person_id)
  1. Collect all JSON conv files for all linked user_ids (cross-platform)
  2. Total turns < 30 → skip
  3. Score unscored turns (above)
  4. MemoryCuratorAgent.should_consolidate(transcript, existing_MEMORY.md)
       → "is there new value here?" reasoning gate → bool
  5. _build_transcript(convs, high_importance_content=...)
       → filters to rows where importance >= threshold and consolidated_at = ''
  6. ModelAdapter.create_simple() → journal-style notes text
  7. Parse bullet points → _add_entry() → cap at 2000 chars (trim oldest)
  8. Write MEMORY.md + audit trail markdown
  9. Trim all JSON conv files to 10 turns
System Prompt Assembly

build_system_prompt_blocks() → list[dict]  (passed to _run_tool_loop)

Block 0  cache_control: ephemeral   identity + platform_awareness + MEMORY.md + facts
Block 1  (no cache)                 sensor snapshot + locations (SL only)
Block 2  (no cache)                 always-on library modules (when present)
Block 0 is the prompt cache anchor. Blocks 1 and 2 vary per message and are never cached.

Multi-Agent Architecture
All three specialist agents extend SupportingAgent:

Own ModelAdapter (provider + model configurable per-agent in agent_config.json["supporting_agents"])
Own focused system prompt, no persona/memory/tools
Scoped asyncio.Lock prevents concurrent runs of the same agent instance
Agent	Model default	Invocation
MemoryCuratorAgent	Haiku	Background (6h consolidation cycle)
LibrarianAgent	Haiku	On-demand tool call from main agent
SemanticRecallAgent	Sonnet	On-demand tool call from main agent
Key Design Decisions
WAL mode on sessions.db — allows concurrent readers during the startup backfill while the consolidation loop writes importance scores
run_in_executor(None, ...) for all ChromaDB calls — it's a sync library; blocking calls on the event loop would stall all platforms
_extract_json() regex fallback — model sometimes wraps JSON in prose or fences despite the system prompt; re.search(r"\{.*\}", text, DOTALL) is the last-resort extractor
Batch importance writes — one SQLite connection for all score updates per cycle instead of N connections, eliminates "database is locked" contention with the backfill task
max_tokens=600 for curator scoring — 20 turns × ~23 chars of JSON output each exceeds the original 256 limit; truncated JSON causes silent score-drop fallbacks to {}
Doc ID = SQLite rowid — stable, autoincrement, never reused; keeps FTS5 and ChromaDB in sync without a secondary mapping table

---

## What's Next

### Library Wizard Tab
The library system is fully implemented but has no wizard UI. Modules are currently managed via the `POST /setup/library` API only. A dedicated tab in the wizard (after Step 7) would allow creating, editing, toggling `always_on`, and setting platform filters without curl commands.

### Importance Threshold in Wizard
`IMPORTANCE_THRESHOLD` (default `0.4`) is env-var-only. It should be exposed in wizard Step 7 alongside the supporting agent model config, so users can tune what makes it into consolidation transcripts without editing `.env`.

### Lua-Side Persistence for Echo Table
The `sent_replies` echo-suppression table in `lua/agent_companion.lua` is reset every viewer restart, which allows reflected IMs to slip through on reconnect. `SetPerAccountData()` / `GetPerAccountData()` (Cool VL Viewer Lua API) should be used to persist this table across sessions. Same applies to the streaming toggle state.

### Manual Identity-Link Editor
Runtime auto-linking handles Command Center browser IDs and configured owner SL/Discord names, but a small setup/debug editor for `person_map.json` would make identity repair explicit when platform display names change.
