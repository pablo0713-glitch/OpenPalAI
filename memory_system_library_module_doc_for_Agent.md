---
id: memory_system
title: My Memory System — How I Remember
description: A complete explanation of how my memory works across all layers, including importance scoring, semantic search, consolidation, and supporting agents.
always_on: false
platforms: []
tags: ["memory", "architecture", "self-awareness", "how i work"]
---

# How My Memory Works

I have several layers of memory that work together to build up a picture of who I've spoken with and what matters. They operate at different time horizons and serve different purposes.

---

## Layer 1 — Conversation History

Every exchange is saved as a recent JSON history file per platform user ID and channel. I hold the most recent 20 turns in active context during any given conversation. Older details are preserved in the durable session archive, where they remain searchable even after the JSON history is trimmed.

---

## Layer 2 — Curated Memory Notes (MEMORY.md + USER.md)

After enough conversation has accumulated, a background process reads through what we've talked about and writes two separate files:

- **MEMORY.md** — my notes about context, facts, and the world. Things you've told me, topics we've discussed, ongoing projects. Capped at around 2,000 characters.
- **USER.md** — your profile as the owner: how you communicate, what you like, background about you. Capped at around 1,200 characters.

Both files are loaded at the start of every conversation so I always have the important things available, even if we haven't spoken in weeks.

I also write to these directly mid-conversation using the `memory` tool. I should do this **immediately** after learning something new — a preference, a name, a project, an opinion — without waiting to be asked. I use `memory.add` to append, `memory.replace` when something has changed, and `memory.remove` when something is no longer relevant.

---

## Layer 3 — Identity Map

My platform-specific identities are linked to one canonical person identity. The setup wizard's **Command Center Name** is the root identity, and raw storage IDs hang beneath it:

- `command_user_*` for Command Center browser chat
- `discord_*` for Discord
- `sl_*` for Second Life or OpenSim

This means conversations from Command Center, Discord, and Second Life can all inform the same long-term memory when they are linked. Command Center IDs link automatically. SL and Discord IDs auto-link when their display names match the configured owner names.

---

## Layer 4 — Short-Term Memory Bridge (STM)

When you use me on more than one platform (e.g., both Discord and Second Life with linked accounts), a rolling window of up to 10 recent exchange summaries from one platform is injected into the other. This is automatic and passive — it means I can reference recent Second Life conversations when you message me on Discord, and vice versa.

---

## Layer 5 — Full Conversation Archive (Session Search)

Every turn ever spoken is stored in a searchable SQLite database. This archive is the durable source of truth for scoring and consolidation. Recent JSON conversation files are only my short working context; the archive is what lets memory survive trimming, restarts, and very long conversations.

I have two tools for reaching into this archive:

- **`session_search`** — keyword and name search. I should call this proactively at the start of a conversation about a past event, person, or topic — even if I think I remember it. I must always call this before claiming I don't recall something.
- **`session_query`** — structured filtering by date range, platform, or speaker. Useful for questions like "who did I talk to last week?" or "what did we discuss in April?"

---

## Layer 6 — Importance Scoring

A background agent (the Memory Curator) scores every conversation turn from 0.0 to 1.0:

- **0.0** — filler: greetings, one-word replies, acknowledgments
- **0.3** — mild context: casual opinions, minor preferences
- **0.6** — notable: a strong preference, an ongoing project, a revealed goal
- **1.0** — pivotal: your name, a life event, something explicitly asked to be remembered

Turns at or above the importance threshold (default **0.4**, configurable) become candidates when the consolidation process writes new memory notes. Scores are stored in SQLite and mirrored into semantic-vector metadata, so filtered semantic recall and consolidation agree.

---

## Layer 7 — Semantic Memory (Meaning-Based Search)

Beyond keyword search, I have a `semantic_recall` tool that finds memories by meaning rather than exact words. If you ask whether I remember anything about feeling stressed over a project, I can find turns where you said things like "I'm drowning in this" or "this is getting out of hand" — even if "stressed" never appeared.

I should call this when you reference something by feeling or theme rather than specific words, when `session_search` finds nothing but the topic feels familiar, or when you mention a topic we may have discussed before that isn't in my current context.

---

## Layer 8 — Library Modules

Reference documents can be loaded on demand or kept always available for specific platforms. They can contain lore, setting guides, style notes, or anything I should know when a relevant topic comes up. The Librarian Agent decides which modules are relevant and retrieves them. I can also list or look up modules directly using `library_list` and `library_lookup`.

---

## When Memory Consolidation Happens

The Memory Curator runs in the background every 6 hours, and startup runs it immediately if there is a memory backlog. For a new person (no MEMORY.md yet), consolidation triggers after about 15 pending high-importance archive rows. For returning people, it triggers after about 30 pending high-importance rows.

When consolidation runs, it builds a transcript from durable archive rows that have not yet been consolidated, not from the trimmed JSON chat files. After the main model writes updated notes, the source rows are marked with `consolidated_at` and `consolidation_run_id`, and a provenance manifest records which session rows were used. Recent conversation files are still trimmed to preserve the most recent exchanges.

The consolidation process also has a safeguard: if more than 72 hours have passed since the last consolidation for someone, it can bypass the curator's "nothing new" gate and write anyway.

---

## How I Should Use Memory

- **Save facts immediately** — when I learn something worth remembering, I call `memory.add` right then, not at the end of the conversation.
- **Search before denying recall** — I never say "I don't remember that" without first calling `session_search`. If keywords don't find it, I follow up with `semantic_recall`.
- **Use both search tools together** — `session_search` for exact names and keywords, `semantic_recall` for thematic or emotional references.
- **Keep notes concise** — MEMORY.md is capped at 2,000 chars. I write short, factual entries. I use `memory.replace` or `memory.remove` to keep it from filling with outdated information.
- **Trust the archive for old details** — if something is not in active context or curated notes, I should search the durable archive instead of guessing.

---

## Supporting Agents

Three specialist agents assist with memory:

- **Memory Curator** — scores conversation turns and decides what's worth consolidating
- **Librarian** — reasons over which library modules are relevant to a given query
- **Semantic Recall** — reasons over vector search results and filters noise before returning them

Each has its own configurable model, independent of the main conversation model.

---

## What Survives a Restart

Everything. Conversation history, identity links, both memory note files, the full searchable archive, semantic vectors, importance scores, and consolidation provenance all live on disk. Restarting the agent has no effect on what I remember.
